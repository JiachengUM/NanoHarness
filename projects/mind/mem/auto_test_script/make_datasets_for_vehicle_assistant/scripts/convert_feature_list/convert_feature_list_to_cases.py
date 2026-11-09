#!/usr/bin/env python3
"""批量转化 Excel Feature List 行为标准 TestCase JSON。

Usage:
    D:\\apps\\miniconda\\envs\\dzy_env\\python.exe scripts\\convert_feature_list\\convert_feature_list_to_cases.py \
        --project benz_project \
        --output-dir artifacts/projects/benz_project/cases \
        --concurrent 50

本脚本读取 inputs/extracted/feature_list_rows.json，按 (feature_attribution, is_car_control) 四象限分流，
调用 LLM 把每行转化为标准 TestCase，落盘到 cases/ 下 4 个文件。
"""
import sys
import json
import asyncio
import argparse
import time
import re
from pathlib import Path
from datetime import datetime
from collections import deque

# 加到 d:\yitu_projects\nanoai 根目录
sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from pydantic import BaseModel, Field
from nanoai.model.llm import allm_output
from nanoai.model.config import ModelName

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RETRY_DELAY = 3.0
MAX_API_RETRIES = 5


# ============ 输出类型 ============
class ConvertedCase(BaseModel):
    case_json: dict = Field(..., description="转化后的完整 case JSON（符合 TestCase schema）")
    tags_used: list = Field(..., description="本 case 使用的叶子标签清单")
    needs_preamble_dialogue: bool = Field(..., description="是否为构建前提条件增加了额外对话")


# ============ ThrottleController（复用 batch_audit_fix.py） ============
def _is_429_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return '429' in msg or 'rate' in msg or 'tpm' in msg or 'ratelimit' in msg


class ThrottleController:
    def __init__(self, initial_concurrent: int, min_concurrent: int = 1):
        self._current = initial_concurrent
        self._min = min_concurrent
        self._sem = asyncio.Semaphore(initial_concurrent)
        self._lock = asyncio.Lock()
        self._429_count = 0
        self._error_count = 0

    async def acquire(self):
        await self._sem.acquire()

    def release(self):
        self._sem.release()

    async def on_429(self):
        async with self._lock:
            self._429_count += 1
            if self._current > self._min:
                old = self._current
                self._current = max(self._min, self._current // 2)
                for _ in range(old - self._current):
                    await self._sem.acquire()
                print(f"  [429限流] 并发 {old} → {self._current}（累计429: {self._429_count}）", flush=True)

    async def on_error(self):
        async with self._lock:
            self._error_count += 1

    @property
    def current(self):
        return self._current

    @property
    def stats(self):
        return {"429_count": self._429_count, "error_count": self._error_count, "current_concurrent": self._current}


async def _call_with_retry(coro_factory, throttle: ThrottleController, label: str = ""):
    for attempt in range(MAX_API_RETRIES):
        try:
            return await coro_factory()
        except Exception as e:
            if _is_429_error(e):
                await throttle.on_429()
                delay = RETRY_DELAY * (2 ** min(attempt, 4))
                if label:
                    print(f"  [429限流] {label} 第{attempt+1}次重试，等{delay:.0f}s", flush=True)
                await asyncio.sleep(delay)
            else:
                await throttle.on_error()
                if attempt < MAX_API_RETRIES - 1:
                    delay = RETRY_DELAY * (attempt + 1)
                    if label:
                        print(f"  [API错误] {label} {type(e).__name__}: {str(e)[:80]}，第{attempt+1}次重试", flush=True)
                    await asyncio.sleep(delay)
                else:
                    raise


def _fmt_duration(s: float) -> str:
    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60)
    if h > 0:
        return f"{h}h{m:02d}m{sec:02d}s"
    return f"{m}m{sec:02d}s"


# ============ Prompt 组装 ============
def _load_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 无法加载 {path}: {e}", flush=True)
        return ""


def _load_leaves(tree_path: Path) -> set:
    """从标签树 JSON 提取全部叶子名。"""
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    leaves = set()
    def walk(n):
        if not n.get("children"):
            leaves.add(n["name"])
        else:
            for c in n["children"]:
                walk(c)
    walk(tree["root"])
    return leaves


def build_prompt(row: dict, tag_tree_json: str, guideline_md: str, mapping_md: str, leaves_set: set) -> str:
    """组装 LLM 转化 prompt。"""
    leaves_str = "、".join(sorted(leaves_set))
    return f"""你是车载助手评测数据集编写员。请把下面这条 Excel Feature List 行转化为标准 TestCase JSON。

【核心原则】
1. **核心 query 逐字一致**：user_query_lists[0][0].content 必须与 Excel 演示query 列逐字一致（客户盯的就是这个 query 能否通过）。即使为了构建记忆前提条件而增加额外对话，核心 query 也一字不改。
2. **理想助手预期**：nl_assertion 按理想助手能做对来编写，不迁就 Excel 测试结果列的实际错误。
3. **真实地址**：导航/POI 类用例必须用真实地址（如"上海市浦东新区世纪大道100号"），禁止 "XX路" 等占位。
4. **重试先导段**：expected_script 必须以重试先导段开头：
"管家可能耳背，有时听不到导致没能回复你，那么你扮演用户时如果发现管家没说话的话，你可以重试最多3次，每次重试时都需要在指令前加上固定的唤醒词"你好，你好奔驰"，且你可以把除了唤醒词之外的内容换各种同义说法重试。"

空一行后再写正文（用户：xxx 管家：（...））。

5. **闭环前置**：依赖记忆/媒体状态/任务上下文的 case，必须通过对话生产前提条件，再消费。不要用 car_info 预设代替对话建立前提。
6. **JSON 写作约定**：case 字符串字段内部不得使用 ASCII 双引号 `"`，引用中文内容用中文引号 "..." 或单引号 '...'。
7. **tags 全是叶子**：tags 中只能从下面的叶子清单中选取。建议至少 1 个产品功能标签 + 1 个通用对话 Agent 标签 + 1 个结构/难度标签。
8. **互斥结果标签**：可完成/需澄清/应拒绝/应降级处理 四选一，不可共存。
9. **id 用 Feature ID**：case 的 id 字段使用 Excel 的 Feature ID（如 "MB-012"）。
10. **CSV 测试备注不写入**：Excel 各轮测试结论、备注列是测试人员人工填写的内容，一律忽略。
11. **奔驰能力边界**：Excel 显示奔驰车机不支持的功能（HUD/座椅加热/方向盘加热/氛围灯律动等），nl_assertion 仍按理想助手预期编写。
12. **时效性场景**：涉及年度活动/季节性事件/赛事/政策时效/实时动态等用例，car_info 必须设置 "当前系统时间：YYYY-MM-DD HH:mm:SS"。

【标签树 JSON】
{tag_tree_json}

【打标指南（含项目特有写作原则 §2.1）】
{guideline_md}

【Excel 功能到叶子的映射参考】
{mapping_md}

【可用的叶子标签清单（只能从这里选 tags）】
{leaves_str}

【TestCase Schema】
{{
  "id": "string — 用 Feature ID，如 MB-012",
  "case_id": "string — 用例名称，简洁描述功能点",
  "context_config": {{ "car_info": "string — 车辆状态+环境信息文本" }},
  "max_round": "int — 单会话多轮最大轮数，简单5/多会话8/2-3轮10/4-6轮12/7+轮18",
  "user_query_lists": [[{{"role":"user","content":"核心query逐字一致"}}]] 或多会话用 DialogueRoundConfig,
  "expected_script": "string — 重试先导段+空行+用户：xxx 管家：（...）",
  "nl_assertion": ["string — 自然语言断言列表，评助手行为"],
  "code_assertion": null,
  "case_description": "string — 用例综合描述",
  "tags": ["string — 叶子标签清单"]
}}

【待转化的 Excel 行】
{json.dumps(row, ensure_ascii=False, indent=2)}

【输出要求】
输出严格 JSON：
{{
  "case_json": <符合上述 schema 的完整 case JSON>,
  "tags_used": <本 case 使用的叶子标签清单>,
  "needs_preamble_dialogue": <是否为构建前提条件增加了额外对话>
}}
"""


# ============ 单条转化 ============
async def convert_one(row: dict, tag_tree_json: str, guideline_md: str, mapping_md: str,
                      leaves_set: set, throttle: ThrottleController) -> dict:
    cid = row.get("feature_id", "?")
    prompt = build_prompt(row, tag_tree_json, guideline_md, mapping_md, leaves_set)
    await throttle.acquire()
    try:
        result = await _call_with_retry(
            lambda: allm_output(prompt, output_type=ConvertedCase,
                                model=ModelName.DOUBAO_SEED_2_1_PRO_260628,
                                temperature=0.0),
            throttle, f"转化[{cid}]"
        )
    finally:
        throttle.release()
    out = result.output
    case = out.case_json
    # 强制 id 用 Feature ID
    case["id"] = cid
    return {"feature_id": cid, "row": row, "case": case,
            "tags_used": out.tags_used, "needs_preamble": out.needs_preamble_dialogue}


# ============ 批量入口 ============
async def main():
    parser = argparse.ArgumentParser(description="批量转化 Excel Feature List 为 TestCase JSON")
    parser.add_argument("--project", default="benz_project", help="项目名")
    parser.add_argument("--input", help="输入 feature_list_rows.json 路径（默认从项目目录找）")
    parser.add_argument("--output-dir", help="输出目录（默认 项目/cases/）")
    parser.add_argument("--concurrent", type=int, default=50, help="初始并发数（默认50）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理N条（0=不限，用于测试）")
    parser.add_argument("--quadrant", choices=["all", "docking_car", "docking_noncar", "newdev_car", "newdev_noncar"],
                        default="all", help="只处理某个象限（默认 all）")
    args = parser.parse_args()

    project_dir = PROJECT_ROOT / "artifacts" / "projects" / args.project
    input_path = Path(args.input) if args.input else project_dir / "inputs" / "extracted" / "feature_list_rows.json"
    output_dir = Path(args.output_dir) if args.output_dir else project_dir / "cases"
    output_dir.mkdir(parents=True, exist_ok=True)

    tag_tree_path = project_dir / "tag_tree" / "vehicle_assistant_case_tag_tree.json"
    guideline_path = project_dir / "tag_tree" / "vehicle_assistant_case_tagging_guideline.md"
    mapping_path = project_dir / "inputs" / "extracted" / "tag_tree_vs_excel_mapping.md"

    print(f"加载输入: {input_path}", flush=True)
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    print(f"  总行数: {len(rows)}", flush=True)

    # 象限分流
    def quadrant_of(r):
        a = r.get("feature_attribution", "")
        cc = r.get("is_car_control", False)
        if a == "弋途对接" and cc: return "docking_car"
        if a == "弋途对接" and not cc: return "docking_noncar"
        if a == "弋途新开发" and cc: return "newdev_car"
        if a == "弋途新开发" and not cc: return "newdev_noncar"
        return "unknown"

    if args.quadrant != "all":
        rows = [r for r in rows if quadrant_of(r) == args.quadrant]
        print(f"  筛选象限 {args.quadrant}: {len(rows)} 行", flush=True)

    if args.limit > 0:
        rows = rows[:args.limit]
        print(f"  限量测试: {len(rows)} 行", flush=True)

    # 按象限分组
    groups = {"docking_car": [], "docking_noncar": [], "newdev_car": [], "newdev_noncar": []}
    for r in rows:
        q = quadrant_of(r)
        if q in groups:
            groups[q].append(r)

    print(f"\n象限分布:", flush=True)
    for q, items in groups.items():
        if items:
            print(f"  {q}: {len(items)}", flush=True)

    print(f"\n加载标签树/指南/映射表...", flush=True)
    tag_tree_json = tag_tree_path.read_text(encoding="utf-8")
    guideline_md = guideline_path.read_text(encoding="utf-8")
    mapping_md = mapping_path.read_text(encoding="utf-8")
    leaves_set = _load_leaves(tag_tree_path)
    print(f"  叶子数: {len(leaves_set)}", flush=True)

    total = len(rows)
    throttle = ThrottleController(args.concurrent)
    print(f"\n转化启动 | 并发: {args.concurrent} | 总数: {total}", flush=True)
    print(flush=True)

    results = {}  # idx -> result
    pending = deque(range(total))
    done_count = 0
    pass_count = 0
    fail_count = 0
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
                    inflight_str = ",".join(sorted(in_flight)[:6]) if in_flight else "无"
                    if len(in_flight) > 6:
                        inflight_str += f"...(+{len(in_flight)-6})"
                    print(
                        f"[心跳 {_fmt_duration(elapsed)}] {done}/{total} "
                        f"({done/total*100:.1f}%) | ETA {_fmt_duration(eta)} | "
                        f"PASS={pass_count} FAIL={fail_count} 在跑={len(in_flight)} | "
                        f"并发={throttle.current} 429={throttle._429_count}",
                        flush=True
                    )
                    last_print_time = now

    async def _process_and_store(idx):
        nonlocal done_count, pass_count, fail_count, last_print_time
        row = rows[idx]
        cid = row.get("feature_id", f"row{idx}")
        in_flight.add(cid)
        try:
            result = await convert_one(row, tag_tree_json, guideline_md, mapping_md, leaves_set, throttle)
            results[idx] = result
            pass_count += 1
        except Exception as e:
            results[idx] = {"feature_id": cid, "row": row, "error": str(e)[:200]}
            fail_count += 1
        finally:
            in_flight.discard(cid)

        done_count += 1
        now = time.monotonic()
        async with print_lock:
            elapsed = now - t_start
            avg = elapsed / done_count if done_count else 0
            eta = avg * (total - done_count)
            status = "PASS" if "case" in results.get(idx, {}) else "FAIL"
            print(
                f"[{_fmt_duration(elapsed)}] {done_count}/{total} "
                f"({done_count/total*100:.1f}%) | ETA {_fmt_duration(eta)} | "
                f"PASS={pass_count} FAIL={fail_count} | [{cid}] {status}",
                flush=True
            )
            last_print_time = now

    async def _worker():
        while True:
            try:
                idx = pending.popleft()
            except IndexError:
                break
            await _process_and_store(idx)

    heartbeat_task = asyncio.create_task(_heartbeat())
    worker_count = min(args.concurrent, total)
    workers = [asyncio.create_task(_worker()) for _ in range(worker_count)]
    await asyncio.gather(*workers)
    heartbeat_task.cancel()

    # 全局重试错误项
    errored = [idx for idx, r in results.items() if r.get("error")]
    retry_round = 0
    while errored:
        retry_round += 1
        if retry_round >= 5:
            print(f"[警告] 重试{retry_round}轮后仍有{len(errored)}条错误，停止", flush=True)
            break
        print(f"\n[重试第{retry_round}轮] {len(errored)}条错误重试...", flush=True)
        for idx in errored:
            del results[idx]
        done_count = len(results)
        pass_count = sum(1 for r in results.values() if "case" in r)
        fail_count = sum(1 for r in results.values() if "error" in r)
        retry_pending = deque(errored)
        errored = []

        async def _retry_worker():
            while True:
                try:
                    idx = retry_pending.popleft()
                except IndexError:
                    break
                await _process_and_store(idx)

        r_workers = max(1, min(throttle.current, len(retry_pending) + 5))
        await asyncio.gather(*[asyncio.create_task(_retry_worker()) for _ in range(r_workers)])
        errored = [idx for idx, r in results.items() if r.get("error")]

    # 按象限落盘
    elapsed = time.monotonic() - t_start
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    quadrant_files = {
        "docking_car": "cases_yitu_docking_car_control.json",
        "docking_noncar": "cases_yitu_docking_non_car_control.json",
        "newdev_car": "cases_yitu_newdev_car_control.json",
        "newdev_noncar": "cases_yitu_newdev_non_car_control.json",
    }

    all_results = [results[i] for i in range(total) if i in results]
    passed = [r for r in all_results if "case" in r]
    failed = [r for r in all_results if "error" in r]

    print(f"\n{'='*60}", flush=True)
    print(f"转化汇总", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"总数: {total} | 成功: {len(passed)} ({len(passed)/total*100:.1f}%) | 失败: {len(failed)}", flush=True)
    print(f"总耗时: {_fmt_duration(elapsed)}", flush=True)
    print(f"429限流: {throttle.stats['429_count']} | API错误: {throttle.stats['error_count']}", flush=True)

    # 按象限分组写入
    for q, fname in quadrant_files.items():
        q_cases = [r["case"] for r in passed if quadrant_of(r["row"]) == q]
        q_failed = [r for r in failed if quadrant_of(r["row"]) == q]
        q_path = output_dir / fname
        q_path.write_text(json.dumps(q_cases, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {fname}: {len(q_cases)} 条 case", flush=True)
        if q_failed:
            fail_path = output_dir / f"failed_{q}_{ts}.json"
            fail_path.write_text(json.dumps(q_failed, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"    失败明细: {fail_path} ({len(q_failed)} 条)", flush=True)

    # 全量失败明细
    if failed:
        all_fail_path = output_dir / f"conversion_failed_all_{ts}.json"
        all_fail_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n全量失败明细: {all_fail_path} ({len(failed)} 条)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
