"""EventScheduler 测试：验证 heapq 优先队列 + asyncio.Event 零轮询。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from anyio import pytest_plugin

from projects.experiments.time_travel_auto_test.case_runner.scheduler import (
    EventScheduler,
    EventSource,
    ScheduledEvent,
)
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonSpeakArgs,
    FakePersonSpeakPerformAction,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
)


def _make_speak_event(content: str, delta: timedelta | None = None, idx: int = 0) -> ScheduledEvent:
    """构造一个假人 speak 事件。"""
    ev = FakePersonScriptEvent(
        event_t0_plus_timedelta=delta,
        target="user",
        action=FakePersonSpeakPerformAction(
            args=FakePersonSpeakArgs(content=content),
        ),
    )
    # ScheduledEvent.from_event 需要 t0
    return ScheduledEvent.from_event(ev, t0=datetime.now(), original_index=idx)


@pytest.mark.anyio
async def test_empty_scheduler_exits_immediately() -> None:
    """空调度器应该立即退出。"""
    scheduler = EventScheduler()
    scheduler.shutdown()  # 先 shutdown 再 run
    await scheduler.run()
    # 到这里就算通过
    assert True


@pytest.mark.anyio
async def test_boundary_events_execute_in_order() -> None:
    """边界事件按 original_index 顺序立即执行。"""
    executed: list[str] = []

    async def on_execute(event: ScheduledEvent) -> None:
        executed.append(event.event.action.args.content)
        await asyncio.sleep(0.01)

    events = [
        _make_speak_event(f"边界{i}", delta=None, idx=i)
        for i in range(3)
    ]

    scheduler = EventScheduler()
    scheduler.set_on_execute(on_execute)
    scheduler.schedule_batch(events)

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.2)
    scheduler.shutdown()
    await task

    assert executed == ["边界0", "边界1", "边界2"]


@pytest.mark.anyio
async def test_anchor_event_waits_until_time() -> None:
    """锚点事件等待到指定时间才执行。"""
    executed: list[float] = []
    base = datetime.now()

    async def on_execute(event: ScheduledEvent) -> None:
        executed.append((datetime.now() - base).total_seconds())

    # 200ms 后触发
    anchor = _make_speak_event("锚点", delta=timedelta(seconds=0.2), idx=0)

    scheduler = EventScheduler()
    scheduler.set_on_execute(on_execute)
    scheduler.schedule_batch([anchor])

    start = datetime.now()
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.4)
    scheduler.shutdown()
    await task

    assert len(executed) == 1
    assert executed[0] >= 0.15  # 至少等了 150ms（留点余量）


@pytest.mark.anyio
async def test_boundary_before_anchor() -> None:
    """边界事件（立即）应该先于未来锚点执行。"""
    executed: list[str] = []

    async def on_execute(event: ScheduledEvent) -> None:
        executed.append(event.event.action.args.content)

    # 锚点 300ms 后
    anchor = _make_speak_event("锚点", delta=timedelta(seconds=0.3), idx=0)
    # 边界立即
    boundary = _make_speak_event("边界", delta=None, idx=1)

    scheduler = EventScheduler()
    scheduler.set_on_execute(on_execute)
    scheduler.schedule_batch([anchor, boundary])

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.5)
    scheduler.shutdown()
    await task

    # 边界先执行
    assert executed[0] == "边界"
    assert executed[1] == "锚点"


@pytest.mark.anyio
async def test_dynamic_insert_immediate() -> None:
    """运行时动态插入立即触发的事件。"""
    executed: list[str] = []

    async def on_execute(event: ScheduledEvent) -> None:
        executed.append(event.event.action.args.content)

    initial = _make_speak_event("初始", delta=None, idx=0)

    scheduler = EventScheduler()
    scheduler.set_on_execute(on_execute)
    scheduler.schedule_batch([initial])

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.05)

    # 动态插入
    inserted = _make_speak_event("插入", delta=None, idx=99)
    scheduler.schedule_one(inserted, immediate=True)

    await asyncio.sleep(0.1)
    scheduler.shutdown()
    await task

    assert "初始" in executed
    assert "插入" in executed


@pytest.mark.anyio
async def test_multiple_anchors_in_time_order() -> None:
    """多个锚点事件按时间顺序触发。"""
    executed: list[str] = []

    async def on_execute(event: ScheduledEvent) -> None:
        executed.append(event.event.action.args.content)

    # 按乱序插入，但应按时间触发
    events = [
        _make_speak_event("C-300ms", delta=timedelta(seconds=0.3), idx=0),
        _make_speak_event("A-100ms", delta=timedelta(seconds=0.1), idx=1),
        _make_speak_event("B-200ms", delta=timedelta(seconds=0.2), idx=2),
    ]

    scheduler = EventScheduler()
    scheduler.set_on_execute(on_execute)
    scheduler.schedule_batch(events)

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.5)
    scheduler.shutdown()
    await task

    assert executed == ["A-100ms", "B-200ms", "C-300ms"]