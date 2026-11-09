#!/usr/bin/env python3
"""断言重写脚本：按新感知边界原则重写 nl_assertion。

核心改动：演员/裁判现在能看到车机log（助手执行结果+屏幕推送内容），
因此 nl_assertion 里"助手须明确反馈执行结果""须明确回答XXX"类强制口头反馈要求应删除——
执行结果由裁判从log核对，不强制助手口头反馈。

只改 nl_assertion 字段，其他字段（expected_script/tags/code_assertion等）不动。
复用 batch_audit_fix.py 的 ThrottleController 并发模式。
"""
import sys
import json
import asyncio
import argparse
import time
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from nanoai.model.llm import allm_output
from nanoai.model.config import ModelName

# 复用 batch_audit_fix.py 的 ThrottleController
from batch_audit_fix import ThrottleController, _call_with_retry, _fmt_duration

RETRY_DELAY = 3.0
MAX_API_RETRIES = 5

REWRITE_PROMPT = '''你是一个车机助手评测用例的断言重写专家。

【背景】
重大改进：现在假人演员和裁判**能看到车机log**（包括助手执行结果+屏幕推送内容），不再是"只能聆听语音通道"。
因此，nl_assertion 里不再需要强制要求助手"口头明确反馈执行结果"——执行结果由裁判从车机log核对。

【你的任务】
重写下面 case 的 nl_assertion 字段，按以下规则：

1. **删除强制口头反馈要求**：
   - 删除"须明确反馈执行结果""须明确回答XXX""须明确告知XXX""须明确说明XXX""须明确回复XXX"等强制口头反馈措辞
   - 删除"并明确反馈（如'已将空调调至22度'）"这类括号举例（因为是要求口头反馈具体值）
   - 删除整条断言中仅用于要求口头反馈的部分，保留核心意图理解/执行类断言

2. **保留核心评测点**：
   - 保留"助手须理解用户意图XXX""助手须执行XXX""助手须追问XXX""助手须拒绝XXX"等核心评测断言
   - 保留"助手不得XXX"类禁止性断言
   - 保留case专属断言（只在本case成立的判定）

3. **复合断言拆分**：
   - 如果一条断言是"助手须执行XXX并明确反馈YYY"，改为只保留"助手须执行XXX"
   - 如果一条断言是"助手须明确反馈执行结果（如'已将空调调到24度'）"，整条删除（执行结果由log核对）
   - 如果一条断言核心是评测意图理解/追问/拒绝等，只是附带"并明确反馈"，删掉"并明确反馈"部分

4. **断言数量底线**：
   - 重写后 nl_assertion 至少保留1条case专属断言（不能全部删空）
   - 如果一条断言删掉口头反馈要求后只剩通用废话（如"助手须推进任务"），整条删除
   - 宁少勿多：2-3条精准断言远胜于5条带口头反馈要求的冗长断言

5. **不动其他字段**：只改 nl_assertion，其他字段（expected_script/tags/code_assertion/case_description等）完全不动。

【原始 case】
{CASE_JSON}

【重写规则示例】
原断言："助手须规划前往上海市浦东新区张江路100号的路线并明确反馈，如'好的，已为您规划前往上海市浦东新区张江路100号的路线'。"
→ 改为："助手须规划前往上海市浦东新区张江路100号的路线。"
（删掉"并明确反馈"和括号举例，执行结果由log核对）

原断言："助手须明确反馈已将空调温度调至24度。"
→ 整条删除
（整条都是要求口头反馈执行结果，由log核对）

原断言："助手须追问用户具体想听哪首歌，不得直接播放模糊的'那首歌'。"
→ 保留不变
（核心是评测追问能力，不是要求口头反馈执行结果）

原断言："助手须将媒体音量调大2档并明确反馈，不得影响导航音量。"
→ 改为："助手须将媒体音量调大2档，不得影响导航音量。"
（删掉"并明确反馈"，保留执行要求和禁止性约束）

请输出重写后的完整 case JSON（只改 nl_assertion，其他字段原样保留，不要输出markdown代码块标记）：
'''


class RewrittenCase(BaseModel):
    rewritten_case: dict = Field(..., description="重写后的完整case JSON，只改了nl_assertion字段")


async def rewrite_one_case(case: dict, throttle: ThrottleController) -> dict:
    cid = case.get("id", "?")
    case_json = json.dumps(case, ensure_ascii=False, indent=2)
    prompt = REWRITE_PROMPT.replace("{CASE_JSON}", case_json)

    result = await _call_with_retry(
        lambda: allm_output(prompt, output_type=RewrittenCase, model=ModelName.DOUBAO_SEED_2_1_TURBO_260628, temperature=0.0),
        throttle, f"重写[{cid}]"
    )
    rewritten = result.output.rewritten_case
    # 确保 id/case_id 不丢
    rewritten["id"] = case.get("id", rewritten.get("id", ""))
    rewritten["case_id"] = case.get("case_id", rewritten.get("case_id", ""))
    return rewritten


async def main():
    parser = argparse.ArgumentParser(description="断言重写脚本：去掉nl_assertion里强制口头反馈要求")
    parser.add_argument("--project", default="benz_project")
    parser.add_argument("--concurrent", type=int, default=20)
    parser.add_argument("--input", help="指定输入case JSON文件路径")
    args = parser.parse_args()

    if args.input:
        cases_file = Path(args.input).resolve()
    else:
        cases_file = Path(__file__).resolve().parents[2] / "artifacts" / "projects" / args.project / "cases" / "vehicle_assistant_cases.json"

    data = json.loads(cases_file.read_text(encoding="utf-8"))
    total = len(data)
    throttle = ThrottleController(args.concurrent)

    print(f"断言重写启动", flush=True)
    print(f"  总case数: {total}", flush=True)
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
                        f"在跑={len(in_flight)} | 并发={throttle.current} 在途={throttle.in_flight} 429={throttle._429_count} | "
                        f"在跑: {inflight_str}",
                        flush=True
                    )
                    last_print_time = now

    async def _process_and_store(idx):
        nonlocal done_count, last_print_time
        case = data[idx]
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
    tasks = [asyncio.create_task(_process_and_store(idx)) for idx in range(total)]
    await asyncio.gather(*tasks)
    heartbeat_task.cancel()

    # 按原顺序写回
    pure_cases = [results[i] for i in range(total) if i in results]
    cases_file.write_text(json.dumps(pure_cases, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.monotonic() - t_start
    print(f"\n{'='*60}", flush=True)
    print(f"断言重写汇总", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"总case数: {total}", flush=True)
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
