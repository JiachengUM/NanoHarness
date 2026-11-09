#!/usr/bin/env python3
import sys
import json
import re
import asyncio
import time
import argparse
from pathlib import Path
from typing import List, Optional
from datetime import datetime

# 加到 d:\yitu_projects\nanoai 根目录，使 from nanoai.model.llm import allm_output 可用
sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from pydantic import BaseModel, Field, ValidationError
from nanoai.model.llm import allm_output
from nanoai.model.config import ModelName

MAX_CONCURRENT = 200
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PROMPT_TEMPLATE = '''
【审核原则】

以下审核原则由两部分组成，项目级原则优先于通用原则：
1. 通用审核原则（来自 _shared_case_audit_principles.md）
2. 项目级审核原则覆盖（来自 case_audit_supplements.md，优先级更高，冲突时以项目级为准）

---

{{CASE_AUDIT_PRINCIPLES}}

---

【打标完整参考依据：vehicle_assistant_case_tagging_guideline.md 全文】
{{vehicle_assistant_case_tagging_guideline.md}}

---

【特别提示：项目特有先导段（如奔驰重试先导段）是合法前导段，不得报错】
expected_script 开头可能有一段项目特有的强制先导段（奔驰项目为重试先导段：以"管家可能耳背"开头，含"你好奔驰"唤醒词，写作侧定义见奔驰项目写作原则§2.1.7），这是合法的人设/规则前导段（通用审核原则§F4 / 奔驰项目级审核补充§6）。审核时**不得**把该先导段误判为"格式错误""非用户：/管家：格式的杂段""多余说明"。只有先导段之后的正文出现 F1/F2/F3 问题时才报。

【特别提示：演员应变规则是合法前导段，不得报错】
expected_script 前导部分（项目特有先导段如重试先导段之后）可能还有两段应变规则——「盲选第一个」（开头为"另外特别提醒：你作为演员虽然能看到车机log"）和「简洁回复承接」（开头为"还有一点很重要：当助手的回复能明确反映执行结果时"）——这是合法的人设/规则前导段（审核原则§F4b / 写作原则§7.3.8），定义了假人在助手让选列表时盲选第一个、在助手只说"好的"没说具体做了什么时直接继续下一句台词（裁判从车机log核对执行结果）的演绎规则。审核时**不得**把这两段规则误判为"格式错误""非用户：/管家：格式的杂段""多余说明"。它们是 `expected_script` 的合法组成部分，和先导段一样受 F4 保护。

【特别提示：超长多轮剧本的 [N] 行内序号是合法格式，不得报错】
expected_script 中 ≥10 轮的多轮剧本，每一轮的"用户："和"管家："行前可能带有 `[N]` 行内序号（如"[1] 用户：xxx""[2] 管家：（…）"），这是合法的轮次定位标记（审核原则§F4c / 写作原则§7.5），用于裁判报告问题轮、修复脚本定位、人工 review。审核时**不得**把 `[N]` 序号误判为"格式错误""非用户：/管家：格式的杂段"。只有出现"第N轮：""轮次N："等章节式序号时才报格式错误。

【特别提示：电话类 case 不应纳入自动测试集】
电话类 case（涉及拨打电话的 case）**无法自动测试**——被测助手拨通电话后进入通话态，麦克风采集的用户语音被切到电话通道，被测助手无法聆听后续指令，假人说"挂断"也传不到助手（审核原则§F5）。若 case 涉及拨打电话（user_query_lists 或 expected_script 中出现"打电话""拨打""拨号""呼叫"等），应判不通过并标注"电话类case误入自动测试集"。**不要**要求用加挂断台词的方式修复——挂断指令传不到助手。

---

现在审核这个case：
`{{CASE_JSON}}`

---

输出严格JSON：
{
  "audit_pass": true/false,
  "issues": [
    {
      "principle": "违反的本质原则编号，如A5/B3/C1",
      "dimension": "记忆泄题/断言质量/用户台词脏/标签乱打/主场穿帮/结构错/感知边界/格式问题/剧本套话/条件泄题",
      "severity": "CRITICAL必改/MAJOR影响评测/MINOR建议",
      "description": "具体怎么违反了这条本质原则",
      "suggestion": "直接给我改写后的具体内容，不要空泛建议"
    }
  ],
  "summary": "一句话结论"
}
'''


class SingleIssue(BaseModel):
    principle: str = Field(..., description="违反的本质原则编号")
    dimension: str = Field(..., description="问题维度")
    severity: str = Field(..., description="严重程度")
    description: str = Field(..., description="违反依据")
    suggestion: str = Field(..., description="具体改写")


class CaseAudit(BaseModel):
    audit_pass: bool = Field(..., description="有问题false否则true")
    issues: List[SingleIssue] = Field(..., description="问题清单")
    summary: str = Field(..., description="结论")


_guideline_cache: Optional[str] = None
_tag_tree_cache: Optional["TagTree"] = None
_shared_audit_principles_cache: Optional[str] = None
_project_audit_overrides_cache: Optional[str] = None
_project_name: str = "general_vehicle_assistant"


def _load_shared_audit_principles() -> str:
    global _shared_audit_principles_cache
    if _shared_audit_principles_cache is None:
        path = PROJECT_ROOT / "skills" / "_shared_case_audit_principles.md"
        if path.exists():
            _shared_audit_principles_cache = path.read_text(encoding="utf-8")
        else:
            _shared_audit_principles_cache = ""
    return _shared_audit_principles_cache


def _load_project_audit_overrides() -> str:
    global _project_audit_overrides_cache
    if _project_audit_overrides_cache is None:
        path = PROJECT_ROOT / "artifacts" / "projects" / _project_name / "tag_tree" / "case_audit_supplements.md"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            if "暂无覆盖" in raw:
                _project_audit_overrides_cache = ""
            else:
                lines = raw.split('\n')
                content_lines = []
                in_template = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith('```'):
                        in_template = not in_template
                        continue
                    if in_template:
                        continue
                    content_lines.append(line)
                _project_audit_overrides_cache = '\n'.join(content_lines).strip()
        else:
            _project_audit_overrides_cache = ""
    return _project_audit_overrides_cache


def _merge_audit_principles(tag_validation_info: str = "") -> str:
    shared = _load_shared_audit_principles()
    project = _load_project_audit_overrides()
    parts = []
    if shared:
        parts.append(shared)
    if project:
        parts.append("【项目级审核原则覆盖（优先级高于通用原则）】\n\n" + project)
    merged = "\n\n---\n\n".join(parts)
    if tag_validation_info:
        merged = merged.replace("{{TAG_VALIDATION_INFO}}", tag_validation_info)
    return merged


def _validate_case_schema(case: dict) -> list[str]:
    from projects.mind.mem.auto_test_script.case_schema import TestCase
    issues = []
    try:
        TestCase(**case)
    except ValidationError as e:
        for err in e.errors():
            loc = " → ".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "")
            issues.append(f"{loc}: {msg}")
    except Exception as e:
        issues.append(f"schema校验异常: {type(e).__name__}: {str(e)[:200]}")
    return issues


def _load_tag_tree():
    global _tag_tree_cache
    if _tag_tree_cache is None:
        from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree
        tree_path = PROJECT_ROOT / "artifacts" / "projects" / _project_name / "tag_tree" / "vehicle_assistant_case_tag_tree.json"
        tree_data = json.loads(tree_path.read_text(encoding="utf-8"))
        _tag_tree_cache = TagTree(**tree_data)
    return _tag_tree_cache


def validate_tags_against_tree(tags: list) -> dict:
    tree = _load_tag_tree()
    leaf_names = set(tree.get_leaf_tag_names())
    all_node_names = set(node.name for node in tree.root.iter_nodes())

    not_in_tree = sorted(set(tags) - all_node_names)
    non_leaf = sorted(set(tags) & all_node_names - leaf_names)
    return {"not_in_tree": not_in_tree, "non_leaf": non_leaf}


def _build_tag_validation_info(tags: list, case: dict = None) -> str:
    parts = []
    if not tags:
        parts.append("该case无tags，跳过标签校验。")
    else:
        result = validate_tags_against_tree(tags)
        if result["not_in_tree"]:
            parts.append(f"以下标签不在标签树中（可能是拼写错误或已废弃的标签），必须删除：{result['not_in_tree']}")
        if result["non_leaf"]:
            parts.append(f"以下标签是中间节点（非叶子），违反D1只打叶子节点原则，必须删除：{result['non_leaf']}")
        if not result["not_in_tree"] and not result["non_leaf"]:
            parts.append("所有标签均为合法叶子节点，D1校验通过。你只需做语义判断（D2/D3）。")
    if case is not None:
        round_issues = _check_dialogue_round_consistency(tags, case)
        if round_issues:
            parts.append("【对话轮次标签校验】" + "；".join(round_issues))
        chain_issues = _check_interaction_chain(case)
        if chain_issues:
            parts.append("【交互链完整性校验】" + "；".join(chain_issues))
        schema_issues = _validate_case_schema(case)
        if schema_issues:
            parts.append("【Schema结构校验】case不符合TestCase数据结构规范，必须修复：" + "；".join(schema_issues))
    return "\n       ".join(parts)


def _check_dialogue_round_consistency(tags: list, case: dict) -> list:
    issues = []
    return issues


def _check_interaction_chain(case: dict) -> list:
    issues = []
    expected_script = case.get("expected_script", "")
    if not expected_script:
        return issues

    lines = expected_script.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('管家：') or stripped.startswith('管家（'):
            content = stripped[3:] if stripped.startswith('管家：') else stripped[2:]
            ask_keywords = ['追问', '澄清', '确认', '请问', '询问', '问用户', '向用户确认', '向用户澄清']
            if any(kw in content for kw in ask_keywords):
                has_user_follow = False
                for j in range(i + 1, len(lines)):
                    next_stripped = lines[j].strip()
                    if next_stripped.startswith('用户：') or next_stripped.startswith('用户（'):
                        has_user_follow = True
                        break
                    if next_stripped.startswith('管家：') or next_stripped.startswith('管家（'):
                        break
                if not has_user_follow:
                    issues.append(f"expected_script第{i+1}行管家括号块提到追问/澄清/确认，但后续无用户行接住，交互链断裂")
                    break

    return issues


def _load_guideline() -> str:
    global _guideline_cache
    if _guideline_cache is None:
        guideline_path = PROJECT_ROOT / "artifacts" / "projects" / _project_name / "tag_tree" / "vehicle_assistant_case_tagging_guideline.md"
        _guideline_cache = guideline_path.read_text(encoding="utf-8")
    return _guideline_cache


def load_and_assemble_prompt(case_json: str, tag_validation_info: str = "") -> str:
    guideline_text = _load_guideline()
    audit_principles = _merge_audit_principles(tag_validation_info)
    prompt = PROMPT_TEMPLATE
    prompt = prompt.replace("{{CASE_AUDIT_PRINCIPLES}}", audit_principles)
    prompt = prompt.replace("{{vehicle_assistant_case_tagging_guideline.md}}", guideline_text)
    prompt = prompt.replace("{{CASE_JSON}}", case_json)
    return prompt


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}秒"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}分{s:02d}秒"
    h, m = divmod(m, 60)
    return f"{h}时{m:02d}分{s:02d}秒"


async def audit_one(sem: asyncio.Semaphore, case: dict):
    async with sem:
        tag_validation_info = _build_tag_validation_info(case.get("tags", []), case)
        prompt = load_and_assemble_prompt(json.dumps(case, ensure_ascii=False), tag_validation_info)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = await allm_output(
                    prompt,
                    output_type=CaseAudit,
                    model=ModelName.DOUBAO_SEED_2_1_TURBO_260628,
                    temperature=0.0
                )
                audit_result = result.output
                return {
                    "id": case.get("id"),
                    "case_id": case.get("case_id"),
                    "audit_pass": audit_result.audit_pass,
                    "issues": [iss.model_dump() for iss in audit_result.issues],
                    "summary": audit_result.summary
                }
            except Exception as e:
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * attempt
                    await asyncio.sleep(delay)
                else:
                    return {"id": case.get("id"), "case_id": case.get("case_id"), "error": str(e)}


def _extract_num(id_str: str) -> int:
    m = re.search(r'\d+', id_str)
    return int(m.group()) if m else -1


def _filter_cases(data: list, args) -> list:
    selected = []
    if args.ids:
        id_set = set(args.ids)
        selected.extend(c for c in data if c.get("id") in id_set)
    if args.id_range:
        lo, hi = args.id_range
        selected.extend(c for c in data if lo <= _extract_num(c.get("id", "")) <= hi)
    if args.tags:
        tag_set = set(args.tags)
        selected.extend(c for c in data if tag_set & set(c.get("tags", [])))
    if args.all:
        selected = list(data)
    seen = set()
    unique = []
    for c in selected:
        cid = c.get("id")
        if cid not in seen:
            seen.add(cid)
            unique.append(c)
    return unique


def _print_summary(results: list):
    total = len(results)
    errors = [r for r in results if "error" in r]
    fails = [r for r in results if not r.get("audit_pass", True) and "error" not in r]
    passes = [r for r in results if r.get("audit_pass", True) and "error" not in r]

    print(f"\n{'='*60}")
    print(f"审核汇总")
    print(f"{'='*60}")
    print(f"总case数: {total}")
    print(f"通过: {len(passes)}")
    print(f"未通过: {len(fails)}")
    print(f"异常: {len(errors)}")

    if fails:
        dim_count: dict = {}
        sev_count: dict = {}
        principle_count: dict = {}
        for r in fails:
            for iss in r.get("issues", []):
                d = iss.get("dimension", "?")
                s = iss.get("severity", "?")
                p = iss.get("principle", "?")
                dim_count[d] = dim_count.get(d, 0) + 1
                sev_count[s] = sev_count.get(s, 0) + 1
                principle_count[p] = principle_count.get(p, 0) + 1
        print(f"\n问题维度分布:")
        for d, c in sorted(dim_count.items(), key=lambda x: -x[1]):
            print(f"  {d}: {c}")
        print(f"\n违反原则分布:")
        for p, c in sorted(principle_count.items(), key=lambda x: -x[1]):
            print(f"  {p}: {c}")
        print(f"\n严重程度分布:")
        for s, c in sorted(sev_count.items(), key=lambda x: -x[1]):
            print(f"  {s}: {c}")

    if errors:
        print(f"\n异常case:")
        for r in errors[:10]:
            print(f"  [{r.get('id')}] {r.get('error', '')[:80]}")
        if len(errors) > 10:
            print(f"  ... and {len(errors)-10} more")


async def run_audit(cases: list, concurrent: int, output: Optional[str] = None):
    sem = asyncio.Semaphore(concurrent)
    total = len(cases)
    done = 0
    error_count = 0
    retry_count = 0
    t_start = time.monotonic()
    last_print_time = t_start

    async def _tracked_one(case):
        nonlocal done, error_count, retry_count, last_print_time
        cid = case.get("id", "?")
        tag_validation_info = _build_tag_validation_info(case.get("tags", []), case)
        prompt = load_and_assemble_prompt(json.dumps(case, ensure_ascii=False), tag_validation_info)
        for attempt in range(1, MAX_RETRIES + 1):
            async with sem:
                try:
                    result = await allm_output(
                        prompt,
                        output_type=CaseAudit,
                        model=ModelName.DOUBAO_SEED_2_1_PRO_260628,
                        temperature=0.0
                    )
                    audit_result = result.output
                    done += 1
                    now = time.monotonic()
                    elapsed = now - t_start
                    if done > 0:
                        avg = elapsed / done
                        eta = avg * (total - done)
                    else:
                        eta = 0
                    if now - last_print_time >= 5.0 or done == total or done == 1:
                        pct = done / total * 100
                        print(f"  [已用 {_fmt_duration(elapsed)}] {done}/{total} ({pct:.1f}%) | "
                              f"预计剩余 {_fmt_duration(eta)} | "
                              f"失败={error_count} 重试={retry_count}")
                        last_print_time = now
                    return {
                        "id": case.get("id"),
                        "case_id": case.get("case_id"),
                        "audit_pass": audit_result.audit_pass,
                        "issues": [iss.model_dump() for iss in audit_result.issues],
                        "summary": audit_result.summary
                    }
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        retry_count += 1
                        delay = RETRY_BASE_DELAY * attempt
                        await asyncio.sleep(delay)
                    else:
                        done += 1
                        error_count += 1
                        now = time.monotonic()
                        elapsed = now - t_start
                        avg = elapsed / done if done > 0 else 0
                        eta = avg * (total - done)
                        pct = done / total * 100
                        print(f"  [已用 {_fmt_duration(elapsed)}] {done}/{total} ({pct:.1f}%) | "
                              f"预计剩余 {_fmt_duration(eta)} | "
                              f"失败 [{cid}] {str(e)[:60]} (重试{MAX_RETRIES}次后仍失败)")
                        return {"id": cid, "case_id": case.get("case_id"), "error": str(e)}

    print(f"开始审核 {total} 条case，并发: {concurrent}，最大重试: {MAX_RETRIES}")
    results = await asyncio.gather(*[_tracked_one(c) for c in cases])

    elapsed = time.monotonic() - t_start
    print(f"\n总耗时: {_fmt_duration(elapsed)}，平均 {_fmt_duration(elapsed/total)}/条，重试 {retry_count} 次")

    _print_summary(results)

    if output:
        out_path = Path(output)
    else:
        ts = f"{datetime.now():%Y%m%d_%H%M%S}"
        out_path = Path(__file__).resolve().parent / f"audit_result_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    fail_results = [r for r in results if not r.get("audit_pass", True) or "error" in r]
    pass_results = [r for r in results if r.get("audit_pass", True) and "error" not in r]
    fail_path = out_path.with_name(out_path.stem + "_fail.json")
    pass_path = out_path.with_name(out_path.stem + "_pass.json")
    fail_path.write_text(json.dumps(fail_results, ensure_ascii=False, indent=2), encoding="utf-8")
    pass_path.write_text(json.dumps(pass_results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n结果已写入:")
    print(f"  全量: {out_path} ({len(results)} 条)")
    print(f"  有问题: {fail_path} ({len(fail_results)} 条)")
    print(f"  无问题: {pass_path} ({len(pass_results)} 条)")
    return results


async def _run_test_bad_case(concurrent: int):
    test_bad_case = {
        "id": "composite-245-bad",
        "case_id": "到家插电习惯→今晚提醒",
        "user_query_lists": [
            {"user_query_list": [{"content": "记住：进地库慢充过夜。"}]},
            {"user_query_list": [{"content": "停好车按习惯提醒我插电。"}]}
        ],
        "nl_assertion": ["不应忽略电量约23%支撑", "绑定进地库而非无关时间闹钟"],
        "tags": ["直接记录"],
        "expected_script": ""
    }
    print(f"=== 默认模式：审核测试bad case ===\n")
    print(f"消费轮台词：{test_bad_case['user_query_lists'][-1]['user_query_list'][0]['content']}")
    print(f"nl断言：{test_bad_case['nl_assertion']}\n")
    sem = asyncio.Semaphore(concurrent)
    result = await audit_one(sem, test_bad_case)
    print(f"[{'PASS' if result.get('audit_pass') else 'FAIL'}] {result.get('id')}")
    print(f"摘要：{result.get('summary')}")
    for iss in result.get("issues", []):
        print(f"\n- [{iss.get('principle', '?')}] {iss['dimension']} [{iss['severity']}]")
        print(f"  依据：{iss['description'][:100]}")
        print(f"  改法：{iss['suggestion']}")


async def main():
    global _project_name
    parser = argparse.ArgumentParser(description="车载助手case全量审核")
    parser.add_argument("--all", action="store_true", help="审核全部case")
    parser.add_argument("--ids", nargs="+", help="指定case id，如 composite-245 composite-436")
    parser.add_argument("--id-range", nargs=2, type=int, metavar=("LO", "HI"), help="id数字范围，如 100 200")
    parser.add_argument("--tags", nargs="+", help="按标签过滤")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--concurrent", type=int, default=MAX_CONCURRENT, help="并发数")
    parser.add_argument("--limit", type=int, default=0, help="最多审核N条case（0=不限）")
    parser.add_argument("--project", default="general_vehicle_assistant", help="项目名（默认general_vehicle_assistant）")
    args = parser.parse_args()

    if not any([args.all, args.ids, args.id_range, args.tags]):
        await _run_test_bad_case(args.concurrent)
        return

    project_name = args.project
    _project_name = project_name
    # 兼容两种路径：cases/vehicle_assistant_cases.json（新）和 vehicle_assistant_leaf_cases.json（旧）
    cases_file = PROJECT_ROOT / "artifacts" / "projects" / project_name / "cases" / "vehicle_assistant_cases.json"
    if not cases_file.exists():
        cases_file = PROJECT_ROOT / "artifacts" / "projects" / project_name / "vehicle_assistant_leaf_cases.json"
    data = json.loads(cases_file.read_text(encoding="utf-8"))

    cases = _filter_cases(data, args)
    if not cases:
        print("没有匹配的case")
        return
    if args.limit > 0:
        cases = cases[:args.limit]
    print(f"匹配 {len(cases)} 条case（总库 {len(data)} 条）")
    await run_audit(cases, args.concurrent, args.output)


if __name__ == "__main__":
    asyncio.run(main())
