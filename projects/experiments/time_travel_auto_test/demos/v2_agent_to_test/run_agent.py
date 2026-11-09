"""极简 v2 Agent 体验脚本 —— 改 QUERY/QUERIES 然后 python run_agent.py。"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

_sys_path = Path(__file__).resolve()
for _ in range(6):
    _sys_path = _sys_path.parent
sys.path.insert(0, str(_sys_path))

from tested_assistant import TestedAssistant
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar

# ============================================================
# 改这里 ↓
# ============================================================
QUERY = "提醒我30分钟后喝水"

# 多轮对话：填了 QUERIES 就用它，否则用 QUERY
QUERIES: list[str] = [
    # "现在几点了？",
    # "帮我搜一下上海今天天气",
    # "播放一首张学友的歌",
    # "导航到人民广场",
    # "记住，我家住在浦江镇",
    # "退下",
    # "回家",
]
# 定时任务演示：设 True 走「设置提醒 → 时间快进 → 提醒触发」流程
ENABLE_SCHEDULED_DEMO: bool = True
# 快进到多久之后（秒）触发提醒
SCHEDULED_DEMO_FAST_FORWARD_SECONDS: int = 1800  # 30 分钟
# ============================================================


def _diff_car(before: dict, after: dict) -> dict:
    """返回变更的字段（值不同 + 新增）。"""
    diff = {}
    all_keys = set(before) | set(after)
    for k in sorted(all_keys):
        bv = before.get(k, "<不存在>")
        av = after.get(k, "<不存在>")
        if bv != av:
            diff[k] = (bv, av)
    return diff


async def main() -> None:
    car = VirtualCar()
    assistant = TestedAssistant(virtual_car=car)
    assistant.create(session_id="manual-test")

    if ENABLE_SCHEDULED_DEMO:
        await _run_scheduled_demo(assistant, car)
        return

    queries = QUERIES if QUERIES else [QUERY]

    for i, q in enumerate(queries):
        car_before = dict(car.car_info)
        print(f"\n{'═'*60}")
        print(f"  [{i+1}] 用户: {q}")

        reply = await assistant.achat(q)
        print(f"  助手: {reply}")

        diff = _diff_car(car_before, dict(car.car_info))
        if diff:
            print(f"  ── 车态变更 ──")
            for k, (old, new) in diff.items():
                print(f"    {k}: {old} → {new}")
        else:
            print(f"  (车态无变化)")

    print()


async def _run_scheduled_demo(assistant: TestedAssistant, car: VirtualCar) -> None:

    print("═" * 60)
    print("  定时任务演示")
    print("─" * 60)

    # 确保 _current_time 有初始值（模拟 TimeTravel Runner 的行为）
    t0 = datetime.now()
    assistant._current_time = t0
    print(f"  T0 时间: {t0.strftime('%H:%M:%S')}")

    # 1. 用户设置提醒
    print(f"\n  [1] 用户: {QUERY}")
    reply = await assistant.achat(QUERY)
    print(f"  助手: {reply}")

    # 检查 pending 任务
    pending = assistant._scheduled_tasks.get_pending()
    print(f"\n  Pending 定时任务: {len(pending)} 个")
    for t in pending:
        print(f"    - {t.task_id}: {t.description} @ {t.trigger_time.strftime('%H:%M:%S')}")

    # 2. 时间快进
    fast_forward = timedelta(seconds=SCHEDULED_DEMO_FAST_FORWARD_SECONDS)
    new_time = assistant._current_time + fast_forward
    print(f"\n  [快进] {assistant._current_time.strftime('%H:%M:%S')} → {new_time.strftime('%H:%M:%S')}")

    ctx_result = await assistant.aupdate_context(car.car_info, current_time=new_time)
    if ctx_result.proactive_text:
        print(f"  [主动话语] {ctx_result.proactive_text}")
    else:
        print(f"  (无主动话语)")

    print("\n" + "═" * 60)


if __name__ == "__main__":
    asyncio.run(main())