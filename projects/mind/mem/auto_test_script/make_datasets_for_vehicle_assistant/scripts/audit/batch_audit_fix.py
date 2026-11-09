#!/usr/bin/env python3
import sys
import json
import asyncio
import argparse
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from full_case_audit import _filter_cases, _fmt_duration
from fix_case_by_audit import audit_case, fix_case_once, _apply_preamble_safeguard

RETRY_DELAY = 3.0
MAX_API_RETRIES = 5


def _is_429_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return '429' in msg or 'rate' in msg or 'tpm' in msg or 'ratelimit' in msg


class ThrottleController:
    """信号量控流。信号量大小固定为 concurrent，429 用指数退避重试（不动态降并发，避免 permit 泄漏）。

    用法：
        async with throttle:
            await llm_call()
    """
    def __init__(self, concurrent: int):
        self._concurrent = concurrent
        self._sem = asyncio.Semaphore(concurrent)
        self._429_count = 0
        self._error_count = 0
        self._in_flight = 0

    async def __aenter__(self):
        await self._sem.acquire()
        self._in_flight += 1
        return self

    async def __aexit__(self, *args):
        self._in_flight -= 1
        self._sem.release()

    def on_429(self):
        self._429_count += 1

    def on_error(self):
        self._error_count += 1

    @property
    def current(self):
        return self._concurrent

    @property
    def in_flight(self):
        return self._in_flight

    @property
    def stats(self):
        return {
            "429_count": self._429_count,
            "error_count": self._error_count,
            "current_concurrent": self._concurrent,
            "in_flight": self._in_flight,
        }


async def _call_with_retry(coro_factory, throttle: ThrottleController, label: str = ""):
    """每次 LLM 调用通过 throttle 信号量控流，保证真实并发 <= concurrent。"""
    for attempt in range(MAX_API_RETRIES):
        try:
            async with throttle:
                return await coro_factory()
        except Exception as e:
            if _is_429_error(e):
                throttle.on_429()
                delay = RETRY_DELAY * (2 ** min(attempt, 4))
                if label:
                    print(f"  [429限流] {label} 第{attempt+1}次重试，等{delay:.0f}s（累计429: {throttle._429_count}）", flush=True)
                await asyncio.sleep(delay)
            else:
                throttle.on_error()
                if attempt < MAX_API_RETRIES - 1:
                    delay = RETRY_DELAY * (attempt + 1)
                    if label:
                        print(f"  [API错误] {label} {type(e).__name__}: {str(e)[:80]}，第{attempt+1}次重试", flush=True)
                    await asyncio.sleep(delay)
                else:
                    raise


async def process_one_case(case: dict, throttle: ThrottleController, max_rounds: int) -> dict:
    cid = case.get("id", "?")
    cname = case.get("case_id", "?")
    current_case = case
    audit_result = None

    for round_num in range(max_rounds + 1):
        try:
            if round_num > 0:
                print(f"  [{cid}] 第{round_num}轮修复中...", flush=True)
                fixed = await _call_with_retry(
                    lambda cc=current_case, ar=audit_result, rn=round_num: fix_case_once(cc, ar, rn),
                    throttle, f"修复[{cid}R{round_num}]"
                )
                fixed["id"] = cid
                fixed["case_id"] = cname
                # 兜底：确保修复后 expected_script 仍以重试先导段开头（fix_case_once 内部已有兜底，这里双保险）
                fixed = _apply_preamble_safeguard(fixed)
                current_case = fixed

            print(f"  [{cid}] 第{round_num}轮审核中..." + ("(初始审核)" if round_num == 0 else "(修复后审核)"), flush=True)
            audit_result = await _call_with_retry(
                lambda cc=current_case: audit_case(cc),
                throttle, f"审核[{cid}R{round_num}]"
            )

            if audit_result.get("audit_pass", True):
                return {
                    "original_id": cid,
                    "original_case_id": cname,
                    "fixed_case": current_case,
                    "audit_rounds": round_num + 1,
                    "final_pass": True,
                    "issues_if_failed": []
                }
            else:
                issues = audit_result.get("issues", [])
                issue_dims = [i.get("dimension", "?") for i in issues[:3]]
                print(f"  [{cid}] 第{round_num}轮未通过，问题: {issue_dims}", flush=True)
        except Exception as e:
            print(f"  [{cid}] 第{round_num}轮异常: {type(e).__name__}: {str(e)[:100]}", flush=True)
            continue

    return {
        "original_id": cid,
        "original_case_id": cname,
        "fixed_case": current_case,
        "audit_rounds": max_rounds + 1,
        "final_pass": False,
        "issues_if_failed": audit_result.get("issues", []) if audit_result else []
    }


async def main():
    parser = argparse.ArgumentParser(description="全量并发审核修复脚本")
    parser.add_argument("--project", default="general_vehicle_assistant", help="项目名（默认 general_vehicle_assistant）")
    parser.add_argument("--all", action="store_true", help="处理全部case")
    parser.add_argument("--ids", nargs="+", help="指定case id")
    parser.add_argument("--id-range", nargs=2, type=int, metavar=("LO", "HI"), help="id数字范围")
    parser.add_argument("--tags", nargs="+", help="按标签过滤")
    parser.add_argument("--concurrent", type=int, default=200, help="并发数（默认200，由信号量统一控流）")
    parser.add_argument("--max-rounds", type=int, default=5, help="最大审核修复轮数（默认5）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理N条case（0=不限）")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent), help="输出目录")
    parser.add_argument("--input", help="指定输入 case JSON 文件路径（默认读取 vehicle_assistant_cases.json）")
    args = parser.parse_args()

    # 优先用 --input 指定的文件，否则按项目目录找
    if args.input:
        cases_file = Path(args.input).resolve()
    else:
        cases_file = Path(__file__).resolve().parents[2] / "artifacts" / "projects" / args.project / "cases" / "vehicle_assistant_cases.json"
        if not cases_file.exists():
            cases_file = Path(__file__).resolve().parents[2] / "artifacts" / "projects" / args.project / "cases" / "vehicle_assistant_leaf_cases.json"
    data = json.loads(cases_file.read_text(encoding="utf-8"))
    cases = _filter_cases(data, args)

    if not cases:
        print("没有匹配的case")
        return

    if args.limit > 0:
        cases = cases[:args.limit]

    total = len(cases)
    max_rounds = args.max_rounds
    throttle = ThrottleController(args.concurrent)  # 信号量统一控流，所有 LLM 调用通过 async with throttle

    print(f"全量审核修复启动 | 项目: {args.project}", flush=True)
    print(f"  总case数: {total}", flush=True)
    print(f"  初始并发: {args.concurrent}", flush=True)
    print(f"  最大修复轮数: {max_rounds}", flush=True)
    print(f"  case文件: {cases_file}", flush=True)
    print(flush=True)

    results = {}
    done_count = 0
    pass_count = 0
    fail_count = 0
    t_start = time.monotonic()
    print_lock = asyncio.Lock()
    last_print_time = t_start
    in_flight = set()  # 正在处理的 cid

    async def _heartbeat():
        """每5秒输出一次心跳：进度 + 在跑的 case"""
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
                        f"PASS={pass_count} FAIL={fail_count} 在跑={len(in_flight)} | "
                        f"并发={throttle.current} 在途={throttle.in_flight} 429={throttle._429_count} | "
                        f"在跑: {inflight_str}",
                        flush=True
                    )
                    last_print_time = now

    async def _process_and_store(idx):
        nonlocal done_count, pass_count, fail_count, last_print_time
        case = cases[idx]
        cid = case.get("id", "?")
        in_flight.add(cid)
        try:
            result = await process_one_case(case, throttle, max_rounds)
        except Exception as e:
            result = {
                "original_id": cid,
                "original_case_id": case.get("case_id", "?"),
                "fixed_case": case,
                "audit_rounds": 0,
                "final_pass": False,
                "error": str(e)
            }
        finally:
            in_flight.discard(cid)

        results[idx] = result
        done_count += 1
        if result.get("final_pass"):
            pass_count += 1
        else:
            fail_count += 1

        now = time.monotonic()
        async with print_lock:
            elapsed = now - t_start
            avg = elapsed / done_count if done_count else 0
            eta = avg * (total - done_count)
            status = "PASS" if result.get("final_pass") else "FAIL"
            rounds = result.get("audit_rounds", 0)
            print(
                f"[{_fmt_duration(elapsed)}] {done_count}/{total} "
                f"({done_count/total*100:.1f}%) | ETA {_fmt_duration(eta)} | "
                f"PASS={pass_count} FAIL={fail_count} | "
                f"并发={throttle.current} 在途={throttle.in_flight} | [{cid}] {status} ({rounds}轮)",
                flush=True
            )
            last_print_time = now

    # 启动心跳
    heartbeat_task = asyncio.create_task(_heartbeat())

    # 每个 case 一个 task，由 throttle 信号量统一控流（避免任务倾斜：长 case 卡住 worker，短 case 早退浪费并发）
    tasks = [asyncio.create_task(_process_and_store(idx)) for idx in range(total)]
    await asyncio.gather(*tasks)
    heartbeat_task.cancel()

    errored = [idx for idx, r in results.items() if r.get("error")]
    retry_round = 0
    while errored:
        retry_round += 1
        print(f"\n[重试第{retry_round}轮] {len(errored)}条因执行错误需重试...", flush=True)
        # 先收集要重试的 idx，再删除 results 中的旧记录
        to_retry = list(errored)
        for idx in to_retry:
            del results[idx]
        done_count = len(results)
        errored = []

        # 同样：每 case 一个 task，信号量统一控流
        retry_tasks = [asyncio.create_task(_process_and_store(idx)) for idx in to_retry]
        await asyncio.gather(*retry_tasks)

        errored = [idx for idx, r in results.items() if r.get("error")]
        if errored and retry_round >= 10:
            print(f"[警告] 重试{retry_round}轮后仍有{len(errored)}条错误，停止重试")
            break

    all_results = [results[i] for i in range(total) if i in results]
    passed = [r for r in all_results if r.get("final_pass")]
    failed = [r for r in all_results if not r.get("final_pass")]

    elapsed = time.monotonic() - t_start
    out_dir = Path(args.output_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 过程产物（带审计元信息，不能直接导入平台）
    all_path = out_dir / f"batch_all_{ts}.json"
    pass_path = out_dir / f"batch_pass_{ts}.json"
    fail_path = out_dir / f"batch_fail_{ts}.json"
    all_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    pass_path.write_text(json.dumps(passed, ensure_ascii=False, indent=2), encoding="utf-8")
    fail_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")

    # ★ 最终产物：纯净 case 数组，直接覆盖原 cases 文件，可导入平台
    # 顺序与原文件一致（按 idx 升序），保留未通过 case 的最新修复结果（尽力而为）
    pure_cases = []
    for r in all_results:
        fc = r.get("fixed_case")
        if isinstance(fc, dict):
            # 确保id/case_id不丢
            fc["id"] = r.get("original_id", fc.get("id", ""))
            fc["case_id"] = r.get("original_case_id", fc.get("case_id", ""))
            pure_cases.append(fc)
    cases_file.write_text(json.dumps(pure_cases, ensure_ascii=False, indent=2), encoding="utf-8")

    tstats = throttle.stats
    print(f"\n{'='*60}", flush=True)
    print(f"全量审核修复汇总", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"总case数: {total}", flush=True)
    print(f"修复后通过: {len(passed)} ({len(passed)/total*100:.1f}%)", flush=True)
    print(f"修复后未通过: {len(failed)} ({len(failed)/total*100:.1f}%)", flush=True)
    print(f"总耗时: {_fmt_duration(elapsed)}", flush=True)
    print(f"429限流次数: {tstats['429_count']}", flush=True)
    print(f"API错误次数: {tstats['error_count']}", flush=True)
    print(f"最终并发数: {tstats['current_concurrent']}", flush=True)
    print(f"\n过程产物（含审计元信息，勿导入平台）:", flush=True)
    print(f"  全量(通过+未通过): {all_path} ({len(all_results)} 条)", flush=True)
    print(f"  通过: {pass_path} ({len(passed)} 条)", flush=True)
    print(f"  未通过: {fail_path} ({len(failed)} 条)", flush=True)
    print(f"\n★ 最终产物（纯净 case 数组，已覆盖原文件，可直接导入平台）:", flush=True)
    print(f"  {cases_file} ({len(pure_cases)} 条)", flush=True)

    # 跑 format 校验，确保回写后格式合法
    check_script = Path(__file__).resolve().parent.parent / "leaf_cases" / "check_json_format.py"
    if check_script.exists():
        import subprocess
        print(f"\n[运行 format 校验] {check_script}", flush=True)
        try:
            r = subprocess.run(
                [sys.executable, str(check_script), str(cases_file)],
                capture_output=True, text=True, encoding="utf-8"
            )
            print(r.stdout, flush=True)
            if r.returncode != 0:
                print(f"[警告] format 校验失败（exit={r.returncode}）", flush=True)
                if r.stderr:
                    print(r.stderr, flush=True)
        except Exception as e:
            print(f"[警告] 跑 format 校验异常: {e}", flush=True)
    else:
        print(f"[警告] 找不到 format 校验脚本: {check_script}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
