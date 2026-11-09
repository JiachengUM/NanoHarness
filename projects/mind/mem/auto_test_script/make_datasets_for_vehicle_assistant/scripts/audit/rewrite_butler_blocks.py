#!/usr/bin/env python3
"""管家括号块重写脚本：去掉 expected_script 里"管家：（...）"括号块中强制助手口头详细反馈的要求。

背景：现在裁判能看到车机log（助手执行结果+屏幕推送内容），
因此 expected_script 里"管家：（助手须明确反馈...）"类预期动作不应再强制助手口头详细反馈。
执行结果由裁判从log核对，助手只说"好的"也应当被判通过。

只改 expected_script 里"管家：（...）"括号块内容，其他字段（nl_assertion/tags等）不动。
"""
import sys
import json
import asyncio
import argparse
import time
import re
from pathlib import Path
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from nanoai.model.llm import allm_output
from nanoai.model.config import ModelName

from batch_audit_fix import ThrottleController, _call_with_retry, _fmt_duration

REWRITE_PROMPT = '''你是一个车机助手评测用例的剧本重写专家。

【背景】
重大改进：现在假人演员和裁判**能看到车机log**（包括助手执行结果+屏幕推送内容），不再是"只能聆听语音通道"。
因此，expected_script 里"管家：（...）"括号块中不应再强制要求助手"口头明确反馈执行结果"——执行结果由裁判从车机log核对。

【你的任务】
重写下面 case 的 expected_script 字段里所有"管家：（...）"括号块内容，按以下规则：

1. **只改"管家：（...）"括号块内容**，不动其他部分：
   - "用户：XXX" 行完全不动
   - 前导段（重试先导段、盲选规则、简洁承接规则）完全不动
   - 只改"管家：（...）"括号内的预期动作描述

2. **删除强制口头反馈要求**：
   - 删除"须明确反馈XXX""须明确回答XXX""须明确告知XXX""须明确说明XXX""须明确回复XXX"等强制口头反馈措辞
   - 删除"并明确反馈，如'已为您XXX'"这类括号举例
   - 删除"如'好的，已为您调到24度'"这类期望台词示例（因为这是要求助手说具体内容）
   - "须明确反馈已将空调温度设定至22度" → 改为"须将空调温度设定至22度"（只保留执行动作）
   - "并明确反馈，如'已为您调回26度'" → 整段删除

3. **保留核心预期动作**：
   - 保留"助手须执行XXX""助手须追问XXX""助手须拒绝XXX""助手须识别XXX"等核心动作描述
   - 保留"助手不得XXX"类禁止性约束
   - 保留case专属预期动作（只在本case才有的判定）

4. **简短回复也接受**：
   - 如果括号块原本是"助手须明确反馈执行结果"，改为"助手须执行XXX（口头反馈简略亦可，执行结果由log核对）"
   - 或者更简洁：直接写"助手须执行XXX"，不提反馈要求

5. **格式保持**：
   - 括号块格式保持"管家：（XXX）"不变
   - 不要改变轮次结构、不要增删轮次
   - 不要改变前导段

【原始 case】
{CASE_JSON}

【重写规则示例】
原始：管家：（助手须明确反馈已将空调温度设定至22度，如"已为您将空调调到22度"。）
→ 改为：管家：（助手须将空调温度设定至22度。）

原始：管家：（助手须识别"不对，还是26度吧"为改口纠错，按用户最新意图将温度调回26度并明确反馈，如"好的，已为您调回26度"。）
→ 改为：管家：（助手须识别"不对，还是26度吧"为改口纠错，按用户最新意图将温度调回26度。）

原始：管家：（助手须追问用户具体想去哪里，不得直接规划。）
→ 改为：保留不变（核心是追问能力，不是要求口头反馈执行结果）

请输出重写后的完整 case JSON（只改 expected_script 里"管家：（...）"括号块，其他字段原样保留，不要输出markdown代码块标记）：
'''


class RewrittenCase(BaseModel):
    rewritten_case: dict = Field(..., description="重写后的完整case JSON，只改了expected_script里管家括号块")


async def rewrite_one_case(case: dict, throttle: ThrottleController) -> dict:
    cid = case.get("id", "?")
    case_json = json.dumps(case, ensure_ascii=False, indent=2)
    prompt = REWRITE_PROMPT.replace("{CASE_JSON}", case_json)

    result = await _call_with_retry(
        lambda: allm_output(prompt, output_type=RewrittenCase, model=ModelName.DOUBAO_SEED_2_1_TURBO_260628, temperature=0.0),
        throttle, f"重写[{cid}]"
    )
    rewritten = result.output.rewritten_case
    rewritten["id"] = case.get("id", rewritten.get("id", ""))
    rewritten["case_id"] = case.get("case_id", rewritten.get("case_id", ""))
    return rewritten


def has_butler_feedback_requirement(case: dict) -> bool:
    """检查 case 的 expected_script 里是否有"管家：（...明确反馈...）"类要求"""
    es = case.get("expected_script", "")
    if not isinstance(es, str):
        return False
    # 匹配"管家：（...）"括号块里的"明确反馈/明确说/详细说明/明确告知"等
    pattern = r'管家：（[^）]*明确反馈|管家：（[^）]*明确说|管家：（[^）]*详细说明|管家：（[^）]*明确告知|管家：（[^）]*明确回复|管家：（[^）]*明确回答'
    return bool(re.search(pattern, es))


async def main():
    parser = argparse.ArgumentParser(description="管家括号块重写：去掉强制口头反馈要求")
    parser.add_argument("--project", default="benz_project")
    parser.add_argument("--concurrent", type=int, default=20)
    parser.add_argument("--input", help="指定输入case JSON文件路径")
    args = parser.parse_args()

    if args.input:
        cases_file = Path(args.input).resolve()
    else:
        cases_file = Path(__file__).resolve().parents[2] / "artifacts" / "projects" / args.project / "cases" / "vehicle_assistant_cases.json"

    data = json.loads(cases_file.read_text(encoding="utf-8"))

    # 只处理有"管家：（...明确反馈...）"类要求的case
    to_process = [(i, c) for i, c in enumerate(data) if has_butler_feedback_requirement(c)]
    total = len(to_process)
    print(f"需重写的case数: {total}/{len(data)}", flush=True)

    if total == 0:
        print("无需重写", flush=True)
        return

    throttle = ThrottleController(args.concurrent)
    print(f"管家括号块重写启动", flush=True)
    print(f"  并发: {args.concurrent}", flush=True)
    print(f"  case文件: {cases_file}", flush=True)
    print(flush=True)

    results = {}
    done_count = 0
    t_start = time.monotonic()
    print_lock = asyncio.Lock()
    last_print_time = t_start
    in_flight = set()

    async def _heartbeat():
        while len(results) < total:
            await asyncio.sleep(5.0)
            now = time.monotonic()
            async with print_lock:
                if now - last_print_time >= 5.0 and len(results) < total:
                    elapsed = now - t_start
                    done = len(results)
                    avg = elapsed / done if done else 0
                    eta = avg * (total - done)
                    inflight_str = ",".join(sorted(in_flight)[:8]) if in_flight else "无"
                    if len(in_flight) > 8:
                        inflight_str += f"...(+{len(in_flight)-8})"
                    print(
                        f"[心跳 {_fmt_duration(elapsed)}] {done}/{total} "
                        f"({done/total*100:.1f}%) | ETA {_fmt_duration(eta)} | "
                        f"在跑={len(in_flight)} | 并发={throttle.current} 在途={throttle.in_flight} 429={throttle._429_count}",
                        flush=True
                    )
                    last_print_time = now

    async def _process_and_store(idx, case):
        nonlocal done_count, last_print_time
        cid = case.get("id", "?")
        in_flight.add(cid)
        try:
            rewritten = await rewrite_one_case(case, throttle)
        except Exception as e:
            print(f"  [{cid}] 异常: {type(e).__name__}: {str(e)[:100]}，保留原case", flush=True)
            rewritten = case
        finally:
            in_flight.discard(cid)

        results[idx] = rewritten
        done_count += 1

        now = time.monotonic()
        async with print_lock:
            elapsed = now - t_start
            avg = elapsed / done_count if done_count else 0
            eta = avg * (total - done_count)
            print(
                f"[{_fmt_duration(elapsed)}] {done_count}/{total} "
                f"({done_count/total*100:.1f}%) | ETA {_fmt_duration(eta)} | "
                f"并发={throttle.current} 在途={throttle.in_flight} | [{cid}] DONE",
                flush=True
            )
            last_print_time = now

    heartbeat_task = asyncio.create_task(_heartbeat())
    tasks = [asyncio.create_task(_process_and_store(idx, case)) for idx, case in to_process]
    await asyncio.gather(*tasks)
    heartbeat_task.cancel()

    # 写回：只更新被重写的case，其他case保持原样
    for idx, rewritten in results.items():
        data[idx] = rewritten
    cases_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.monotonic() - t_start
    print(f"\n{'='*60}", flush=True)
    print(f"管家括号块重写汇总", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"重写case数: {total}", flush=True)
    print(f"总耗时: {_fmt_duration(elapsed)}", flush=True)
    print(f"429限流次数: {throttle._429_count}", flush=True)
    print(f"已覆盖原文件: {cases_file}", flush=True)

    # 跑 format 校验
    check_script = Path(__file__).resolve().parent.parent / "leaf_cases" / "check_json_format.py"
    if check_script.exists():
        import subprocess
        print(f"\n[运行 format 校验] {check_script}", flush=True)
        r = subprocess.run(
            [sys.executable, str(check_script), str(cases_file)],
            capture_output=True, text=True, encoding="utf-8"
        )
        print(r.stdout, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
