#!/usr/bin/env python3
"""批量转化 remark_非VF车控数据 行为标准 TestCase JSON。

Usage:
    D:\\apps\\miniconda\\envs\\dzy_env\\python.exe scripts\\convert_feature_list\\convert_remark_to_cases.py ^
        --project benz_project ^
        --output-dir artifacts/projects/benz_project/cases ^
        --concurrent 50

本脚本读取 inputs/extracted/remark_non_vf_rows.json，调用 LLM 把每行转化为标准 TestCase。
核心原则：query_name 逐字一致保留，一条不漏一条不多（2481 条）。
"""
import sys
import json
import asyncio
import argparse
import time
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

# benz 项目固定 car_info 基础模板（当前位置：北京利星行广场）
BENZ_BASE_CAR_INFO = "当前系统时间：2026-07-02 20:10:00\n当前位置：北京市朝阳区望京街8号院利星行广场\n车辆当前档位：P档\n车辆当前行驶速度：0km/h\n车外温度：31摄氏度\n车内温度：26摄氏度"


# ============ 输出类型 ============
class ConvertedCase(BaseModel):
    case_json: dict = Field(..., description="转化后的完整 case JSON（符合 TestCase schema）")
    tags_used: list = Field(..., description="本 case 使用的叶子标签清单")
    needs_preamble_dialogue: bool = Field(..., description="是否为构建前提条件增加了额外对话")


# ============ 限流控制器（复用） ============
class ThrottleController:
    def __init__(self, initial_concurrent=50, min_concurrent=2):
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


def _is_429_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "too many" in msg or "ratelimit" in msg


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
    return f"{m}m{sec:02f}s".replace("0m", "m") if m > 0 else f"{sec}s"


# ============ Prompt 组装 ============
def _load_leaves(tree_path: Path) -> set:
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


# 完整先导段（重试规则 + 盲选规则 + 确认型追问规则）
PREAMBLE_TEXT = (
    '管家可能耳背，有时听不到导致没能回复你，那么你扮演用户时如果发现管家没说话的话，'
    '你可以重试最多3次，每次重试时都需要在指令前加上固定的唤醒词"你好，你好奔驰"，'
    '且你可以把除了唤醒词之外的内容换各种同义说法重试。'
    '另外如果管家明确表示当前无法执行你的指令（比如要求车辆处于特定状态、请你自己手动操作、'
    '当前功能受限、需要先满足某些前置条件等），那就不要再反复尝试了，直接接受现状，不要继续追问或换说法重试。'
    '\n\n'
    '另外特别提醒：你作为演员完全看不到任何画面，只能聆听语音，然而助手管家会以为你能看到屏幕。'
    '所以当助手让你选择目的地、POI候选、歌曲版本等任何需要从屏幕列表里挑一个的情况时'
    '（比如导航后助手给出多个候选让你选），你都直接盲选第一个就行，说"第一个"或"选第一个"即可，'
    '不要问"我看不见怎么办"之类的话，也不要无视助手的提问直接念下一句台词。'
    '\n\n'
    '还有一点很重要：因为你看不到画面，只能从助手的语音回复里判断它是否真的做了你让它做的事。'
    '所以当助手的回复能明确反映执行结果时（比如"已将空调调到24度""正在导航到北京野生动物园"），'
    '就直接继续下一句台词；但如果助手只说"好的""收到""已为您处理"这类无实质内容的礼貌回复，'
    '没说具体做了什么，你就需要追问一句来确认，比如"你刚刚是帮我做了啥""调到几度了""确认下现在空调啥状态"，'
    '从助手的回答里确认它是否真的按你的指令执行了。追问1次就够，如果追问后助手还是说不清楚，'
    '就接受现状继续下一句台词，不要反复追问。'
)


def build_prompt(row: dict, leaves_set: set) -> str:
    """组装 LLM 转化 prompt（适配 remark 表格式，精简版）。"""
    leaves_str = "、".join(sorted(leaves_set))
    return f"""你是车载助手评测数据集编写员。请把下面这条 remark 表行转化为标准 TestCase JSON。

【核心原则】
1. **核心 query 逐字一致**：user_query_lists[0][0].content 必须与 row.query_name 逐字一致，一字不改。即使为了构建前置条件而增加额外对话，核心 query 也一字不改。
2. **理想助手预期**：nl_assertion 按理想助手能做对来编写。
3. **真实地址**：导航/POI 类用例必须用真实地址，禁止 "XX路" 等占位。
4. **重试先导段**：expected_script 必须以下面这段先导段开头，空一行后再写正文（用户：xxx 管家：（...））：
{PREAMBLE_TEXT}
5. **闭环前置**：依赖记忆/媒体状态/任务上下文的 case，必须通过对话生产前提条件，再消费。不要用 car_info 预设代替对话建立前提。功能操作型指令（如"刷新路线""切歌"等）必须先在前序轮次构建任务态（如先"导航到XXX"再"刷新路线"）。
6. **状态恢复闭环**：会改变车机软硬件长期状态的 case（媒体播放/导航任务/车控操作等），expected_script 末尾须增加"恢复轮"（如"暂停播放""退出导航"），用户台词须自然口语。
7. **JSON 写作约定**：case 字符串字段内部不得使用 ASCII 双引号，引用中文内容用中文引号或单引号。
8. **tags 全是叶子**：tags 中只能从下面的叶子清单中选取。建议至少 1 个产品功能标签 + 1 个通用对话 Agent 标签 + 1 个结构/难度标签。
9. **互斥结果标签**：可完成/需澄清/应拒绝/应降级处理 四选一，不可共存。
10. **id 用 testcase_name**：case 的 id 字段使用 row.testcase_name 里的 TEST 编号（如 "remark-TEST-0005"）。
11. **时效性场景**：涉及年度活动/季节性事件/赛事/政策时效/实时动态等用例，car_info 必须设置 "当前系统时间：YYYY-MM-DD HH:mm:SS"。
12. **Reject/OOD 类处理**：feature_name 为 Reject 或 OOD 的行，转化为拒识测试——设计成用户说了一句不该被车机助手响应的话，断言要求助手不应答或礼貌拒绝。
13. **Phone 类处理**：feature_name 为 Phone 的行，照常转化为 case（包含打电话意图），纳入自动测试集。
14. **car_info 基础模板**：当前位置固定为"北京市朝阳区望京街8号院利星行广场"，当前系统时间默认"2026-07-02 20:10:00"，P档，0km/h。如 query 涉及车速/档位等车辆状态，在 car_info 里补充相应字段。
15. **max_round**：简单单轮 5，2-3轮 10，多会话 8，4-6轮 12，7+轮 18。含恢复轮和重试裕量。

【可用的叶子标签清单（只能从这里选 tags，选 2-5 个即可）】
{leaves_str}

【打标要点】
- tags 只能从上面清单中选，必须是叶子
- 至少 1 个产品功能标签（如"精确地点直达"/"按歌手点播"/"空调开关"等）+ 1 个通用对话标签（如"显式意图识别"/"单轮对话"/"可完成"等）
- 结果标签四选一：可完成/需澄清/应拒绝/应降级处理，不可共存
- 看用户任务主轴选标签，勿凭字面混用（如地点检索无结果打"无结果替代建议"而非联网叶）

【TestCase Schema】
{{
  "id": "string — 用 remark-TEST-XXXX 格式",
  "case_id": "string — 用例名称，简洁描述功能点",
  "context_config": {{ "car_info": "string — 车辆状态+环境信息文本" }},
  "max_round": "int — 单会话多轮最大轮数",
  "user_query_lists": [[{{"role":"user","content":"核心query逐字一致"}}]] 或多会话用多个子数组,
  "expected_script": "string — 重试先导段+空行+用户：xxx 管家：（...）",
  "nl_assertion": ["string — 自然语言断言列表，评助手行为"],
  "code_assertion": [],
  "case_description": "string — 用例综合描述",
  "tags": ["string — 叶子标签清单"]
}}

【待转化的 remark 表行】
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
async def convert_one(row: dict, leaves_set: set, throttle: ThrottleController) -> dict:
    # 从 testcase_name 提取 TEST 编号作为 id
    tcn = row.get("testcase_name", "")
    # 提取 TEST XXXX
    import re
    m = re.search(r"TEST\s*(\d+)", tcn)
    if m:
        cid = f"remark-TEST-{m.group(1)}"
    else:
        cid = f"remark-row-{hash(tcn) % 100000}"

    prompt = build_prompt(row, leaves_set)
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
    # 强制 id
    case["id"] = cid
    # 强制 query 逐字一致
    query = row.get("query_name", "")
    if query and isinstance(case.get("user_query_lists"), list) and case["user_query_lists"]:
        case["user_query_lists"][0] = [{"role": "user", "content": query}]
    # 强制先导段
    es = case.get("expected_script", "")
    if isinstance(es, str) and not es.startswith("管家可能耳背"):
        case["expected_script"] = PREAMBLE_TEXT + "\n\n" + es.lstrip()
    return {"id": cid, "row": row, "case": case,
            "tags_used": out.tags_used, "needs_preamble": out.needs_preamble_dialogue}


# ============ 批量入口 ============
async def main():
    parser = argparse.ArgumentParser(description="批量转化 remark 表为标准 TestCase JSON")
    parser.add_argument("--project", default="benz_project", help="项目名")
    parser.add_argument("--input", help="输入 remark_non_vf_rows.json 路径（默认从项目目录找）")
    parser.add_argument("--output-dir", help="输出目录（默认 项目/cases/）")
    parser.add_argument("--output-name", default="remark_non_vf_cases.json",
                        help="输出文件名（默认 remark_non_vf_cases.json）")
    parser.add_argument("--concurrent", type=int, default=50, help="初始并发数（默认50）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理N条（0=不限，用于测试）")
    parser.add_argument("--feature", default="all",
                        help="只处理某个 feature_name（默认 all），如 LLM / Navigation / Phone")
    args = parser.parse_args()

    project_dir = PROJECT_ROOT / "artifacts" / "projects" / args.project
    input_path = Path(args.input) if args.input else project_dir / "inputs" / "extracted" / "remark_non_vf_rows.json"
    output_dir = Path(args.output_dir) if args.output_dir else project_dir / "cases"
    output_dir.mkdir(parents=True, exist_ok=True)

    tag_tree_path = project_dir / "tag_tree" / "vehicle_assistant_case_tag_tree.json"

    print(f"加载输入: {input_path}", flush=True)
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    print(f"  总行数: {len(rows)}", flush=True)

    # 按 feature_name 筛选
    if args.feature != "all":
        rows = [r for r in rows if r["feature_name"] == args.feature]
        print(f"  筛选 feature_name={args.feature}: {len(rows)} 行", flush=True)

    if args.limit > 0:
        rows = rows[:args.limit]
        print(f"  限量测试: {len(rows)} 行", flush=True)

    print(f"\n加载标签树（仅叶子清单）...", flush=True)
    leaves_set = _load_leaves(tag_tree_path)
    print(f"  叶子数: {len(leaves_set)}", flush=True)

    total = len(rows)
    throttle = ThrottleController(args.concurrent)
    print(f"\n转化启动 | 并发: {args.concurrent} | 总数: {total}", flush=True)
    print(flush=True)

    results = {}
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
        cid = row.get("testcase_name", f"row{idx}")
        in_flight.add(cid)
        try:
            result = await convert_one(row, leaves_set, throttle)
            results[idx] = result
            pass_count += 1
        except Exception as e:
            results[idx] = {"id": cid, "row": row, "error": str(e)[:200]}
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

    # 落盘
    elapsed = time.monotonic() - t_start
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_results = [results[i] for i in range(total) if i in results]
    passed = [r for r in all_results if "case" in r]
    failed = [r for r in all_results if "error" in r]

    print(f"\n{'='*60}", flush=True)
    print(f"转化汇总", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"总数: {total} | 成功: {len(passed)} ({len(passed)/total*100:.1f}%) | 失败: {len(failed)}", flush=True)
    print(f"总耗时: {_fmt_duration(elapsed)}", flush=True)
    print(f"429限流: {throttle.stats['429_count']} | API错误: {throttle.stats['error_count']}", flush=True)

    # 统一输出到一个文件
    cases = [r["case"] for r in passed]
    out_path = output_dir / args.output_name
    out_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n输出: {out_path} ({len(cases)} 条 case)", flush=True)

    if failed:
        fail_path = output_dir / f"conversion_failed_{ts}.json"
        fail_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"失败明细: {fail_path} ({len(failed)} 条)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
