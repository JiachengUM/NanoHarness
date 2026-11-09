"""新接入协议（事件源适配器模式）验证脚本。

独立于现有代码运行（不动 case_runner），仅复用与协议无关的基础设施：
- TimelineEngine（wall→mock 换算）
- TraceRecorder（轨迹落盘）
- VirtualCar（虚拟车）

验证五个机制点：
1. 异步工具回灌回合：说话 → 调工具 → 结果晚到 → 续接回复（on_result 挂载）
2. 快进 → 定时提醒到期 → 主动话语（无用户输入）
3. 车控穿过协议写虚拟车
4. 打断（助手自驱）：新输入到来，助手自行中断旧长回复（框架从不 cancel）
5. 新协议产出可无缝喂给现有 TraceRecorder

运行：
  D:\\apps\\miniconda\\envs\\dzy_env\\python.exe projects/experiments/time_travel_auto_test/adapter_v2/verify.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from projects.experiments.time_travel_auto_test.case_runner.timeline import TimelineEngine
from projects.experiments.time_travel_auto_test.case_runner.trace import TraceRecorder
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar

from projects.experiments.time_travel_auto_test.adapter_v2.protocol import (
    AdapterEnv,
    EventType,
    Turn,
    TurnKind,
    WorldUpdate,
)
from projects.experiments.time_travel_auto_test.adapter_v2.turn_muxer import (
    run_turn,
)
from projects.experiments.time_travel_auto_test.adapter_v2.mock_adapter import MockAdapter


def _dump(events) -> None:
    for ev in events:
        label = ev.event.delta or ev.event.tool_name or ""
        extra = f"task_id={ev.event.task_id}" if ev.event.task_id else ""
        print(f"  [{ev.mock_time.strftime('%H:%M:%S.%f')[:-3]}] "
              f"{ev.event.type.value:<12} {label!r} {extra}".rstrip())


async def main() -> None:
    t0 = datetime.now().replace(microsecond=0)
    timeline = TimelineEngine(t0)
    car = VirtualCar()
    adapter = MockAdapter()
    adapter.setup(AdapterEnv(
        session_id="verify",
        virtual_car=car,
        get_virtual_time=lambda: timeline.mock_time,
    ))
    trace = TraceRecorder()  # 复用（不接 event_bus，行为同旧版）

    # ---- 1. 异步工具回灌回合 ----
    print("═══ 1. 异步工具回灌回合（说话 → 调工具 → 结果晚到 → 续接回复）═══")
    turn1 = Turn(kind=TurnKind.USER, text="帮我设置一个30分钟后的提醒", at=timeline.mock_time)
    events1 = await run_turn(adapter, turn1, timeline)
    _dump(events1)

    types1 = [e.event.type for e in events1]
    assert types1 == [
        EventType.TEXT_DELTA, EventType.TOOL_CALL, EventType.TOOL_RESULT, EventType.TEXT_DELTA,
    ], f"事件序列不符: {types1}"
    call = next(e for e in events1 if e.event.type is EventType.TOOL_CALL)
    result = next(e for e in events1 if e.event.type is EventType.TOOL_RESULT)
    assert call.event.task_id == result.event.task_id == "t1", "task_id 配对失败"
    mocks1 = [e.mock_time for e in events1]
    assert all(mocks1[i] <= mocks1[i + 1] for i in range(len(mocks1) - 1)), "mock 时间戳非单调"
    print("  ✓ 事件序列 / task_id 配对 / 单调时间戳均通过；回合自然耗尽（无需超时）")

    # ---- 2. 快进 → 主动话语 ----
    print("\n═══ 2. 快进 → 定时提醒到期 → 主动话语（无用户输入）═══")
    timeline.accelerate_to(timeline.mock_time + timedelta(seconds=1800))
    await adapter.apply_world_update(WorldUpdate(current_time=timeline.mock_time))
    turn2 = Turn(kind=TurnKind.PROACTIVE, text="", at=timeline.mock_time)
    events2 = await run_turn(adapter, turn2, timeline)
    _dump(events2)
    assert len(events2) == 1 and events2[0].event.delta == "时间到了，该喝水啦。"
    print("  ✓ 主动话语按快进后的虚拟时刻产出")

    # ---- 3. 车控穿过协议写虚拟车 ----
    print("\n═══ 3. 车态变更（车控穿过协议写虚拟车）═══")
    turn3 = Turn(kind=TurnKind.USER, text="开空调", at=timeline.mock_time)
    events3 = await run_turn(adapter, turn3, timeline)
    _dump(events3)
    assert car.get_field("空调开启状态及模式") == "制冷中"
    print("  ✓ 虚拟车车态被正确修改")

    # ---- 4. 助手自驱打断（中立观察者：框架从不 cancel） ----
    print("\n═══ 4. 助手自驱打断（新输入到来，助手自行中断旧长回复）═══")
    # 旧回合（长回复）后台起跑：多个 chunk + 0.3s 说话间隔
    old_turn = Turn(kind=TurnKind.USER, text="给我讲个长故事", at=timeline.mock_time)
    old_task = asyncio.create_task(run_turn(adapter, old_turn, timeline))
    await asyncio.sleep(0.5)  # 让它先说 1~2 个 chunk

    # 新用户插话：框架并发发起新 Turn → mock 的 initial_sources 自行置位信号中断旧流
    new_turn = Turn(kind=TurnKind.USER, text="停一下，改去机场", at=timeline.mock_time)
    new_task = asyncio.create_task(run_turn(adapter, new_turn, timeline))

    old_events = await old_task
    new_events = await new_task

    old_text = "".join(
        e.event.delta for e in old_events if e.event.type is EventType.TEXT_DELTA
    )
    expected_full = "从前有座山，山里有座庙，庙里有个老和尚，正在讲故事，故事讲的是一个车载助手。"
    assert adapter._barged_in_count == 1, "助手应记录一次自驱打断"
    assert 0 < len(old_events) < 5, "旧长回复应被打断为半截话（chunk 少于一整段）"
    assert expected_full.startswith(old_text), "半截话应是完整句子的前缀"
    assert any(e.event.type is EventType.TEXT_DELTA for e in new_events), "新回合应正常产出"
    new_text = "".join(e.event.delta for e in new_events if e.event.type is EventType.TEXT_DELTA)
    print(f"  ✓ 旧回合半截话: {old_text!r}")
    print(f"  ✓ 打断由助手自驱（_barged_in_count={adapter._barged_in_count}），框架全程未 cancel")
    print(f"  ✓ 新回合正常完成: {new_text!r}")

    # ---- 5. 复用 TraceRecorder 落盘 ----
    print("\n═══ 5. 新协议产出喂给现有 TraceRecorder（复用验证）═══")
    for ev in events1 + events3:
        if ev.event.type is EventType.TOOL_CALL:
            trace.record_tool_call(
                ev.mock_time, ev.event.tool_name, ev.event.tool_args, ev.event.task_id
            )
        elif ev.event.type is EventType.TOOL_RESULT:
            trace.record_tool_result(
                ev.mock_time, ev.event.tool_name, ev.event.tool_result, 0.0, ev.event.task_id
            )
    print(f"  trace 记录数: {len(trace.records)}")
    print(f"  trace 摘要键: {sorted(trace.summary().keys())}")
    print("  ✓ 无缝复用现有 TraceRecorder")

    print("\n════════ 全部验证通过 ════════")


if __name__ == "__main__":
    asyncio.run(main())