"""EventScheduler：事件调度器（heapq 优先队列 + asyncio.Event 零轮询）。

设计：
- 主循环：pop 就绪事件 → 回调 on_execute → 等待下一事件
- 优先级：锚点到达时间 < 边界事件（None）< 未来锚点
- 零轮询：用 asyncio.Event 唤醒主循环，不用 sleep 轮询
- 动态插入：schedule_one 可在运行时插入事件并唤醒

边界事件处理：
- timedelta=None 的事件立即就绪，按 original_index 顺序执行
- 但如果当前有正在执行的边界事件，要等它完成
"""

from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Awaitable, Callable, Optional

from projects.experiments.time_travel_auto_test.script_events.script_event import (
    ScriptEvent,
    VirtualCarStateCheckScriptEvent,
    WorldTickScriptEvent,
)


class EventSource(str, Enum):
    """事件来源标记。"""
    ANCHOR = "anchor"       # 锚点事件（有显式时间戳）
    BOUNDARY = "boundary"   # 边界事件（无时间戳，立即就绪）
    STATE_CHECK = "state_check"  # 状态检查（也是锚点事件，但标记来源）


@dataclass(order=True)
class ScheduledEvent:
    """调度器中的事件条目。

    sort_key 用于 heapq 排序：
    - 锚点事件：(anchor_time, original_index)
    - 边界事件：(datetime.max, original_index) → 排在所有锚点之后
    """
    # heapq 用 sort_key 排序
    sort_key: tuple
    # 实际事件
    event: ScriptEvent = field(compare=False)
    source: EventSource = field(compare=False, default=EventSource.BOUNDARY)
    original_index: int = field(compare=False, default=0)
    # 锚点事件的绝对触发时间（边界事件为 None）
    anchor_time: Optional[datetime] = field(compare=False, default=None)

    @classmethod
    def from_event(
        cls,
        event: ScriptEvent,
        t0: datetime,
        original_index: int,
    ) -> "ScheduledEvent":
        """根据 event.event_t0_plus_timedelta 构造 ScheduledEvent。

        优先级语义：
        - 边界事件（delta=None）：立即就绪，sort_key 用 (t0, original_index)
          → 和 PT0S 锚点同等优先级，按 original_index 排序
        - 锚点事件（delta=PT0S 等）：sort_key 用 (anchor_time, original_index)
          → 按时间先后排序
        """
        delta = event.event_t0_plus_timedelta
        if delta is None:
            # 边界事件：立即就绪，和 PT0S 锚点同等优先级
            return cls(
                sort_key=(t0, original_index),
                event=event,
                source=EventSource.BOUNDARY,
                original_index=original_index,
                anchor_time=None,
            )
        else:
            # 锚点事件：t0 + delta
            anchor = t0 + delta
            # 判断是否是 state_check 或 world_tick
            if isinstance(event, VirtualCarStateCheckScriptEvent):
                source = EventSource.STATE_CHECK
            elif isinstance(event, WorldTickScriptEvent):
                source = EventSource.ANCHOR  # WorldTick 是锚点事件，无特殊来源
            else:
                source = EventSource.ANCHOR
            return cls(
                sort_key=(anchor, original_index),
                event=event,
                source=source,
                original_index=original_index,
                anchor_time=anchor,
            )


# 回调类型
ExecuteCallback = Callable[[ScheduledEvent], Awaitable[None]]
ShutdownCallback = Callable[[], None]


class EventScheduler:
    """事件调度器：管理时间线，事件就绪时回调 Runner。

    核心循环：
    1. 从 heapq pop 最早就绪的事件
    2. 如果是边界事件 → 立即回调 on_execute
    3. 如果是锚点事件 → 等待到 anchor_time（用 asyncio.wait_for + Event）
    4. 回调完成后继续下一轮
    5. 所有事件完成或 shutdown() 后退出

    中立观察者模型（2026-08-25）：
    - on_execute 回调只做"即时效果"（假人说话/车态检查等），
      不等待助手回复完成——助手回复在 Runner 的后台流任务里异步进行
    - 因此锚点事件总是按 anchor_time 准时触发（不被慢回复拖晚），
      助手回复期间到达的插话与回复在时间上自然重叠，如实记录
    """

    def __init__(
        self,
        fast_mode: bool = False,
        acceleration_threshold: Optional[timedelta] = None,
        get_now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._heap: list[ScheduledEvent] = []
        self._on_execute: Optional[ExecuteCallback] = None
        self._wakeup_event: asyncio.Event = asyncio.Event()
        self._shutdown_flag: bool = False
        self._running: bool = False
        # fast_mode：跳过锚点事件的真实时间等待（仅测试用）
        self._fast_mode: bool = fast_mode
        # 时间加速阈值：锚点距当前时间 > 此值时，不真实等待，直接执行
        # Runner 的 _maybe_accelerate 会处理快进逻辑（更新 mock_time + 通知助手）
        # None 表示不启用（按真实时间等待）
        self._acceleration_threshold: Optional[timedelta] = acceleration_threshold
        # 当前时间源：锚点等待/就绪判定基于哪个时钟。
        # Runner 注入 TimelineEngine.mock_time（虚拟时间）——虚拟时间与真实时间
        # 1:1 自然流逝，但快进后虚拟时间领先真实时间，等待必须按虚拟距离算。
        # 默认用真实时钟（独立使用 scheduler 的场景）。
        self._get_now: Callable[[], datetime] = get_now or datetime.now

    # ---------------- 配置 ----------------

    def set_on_execute(self, fn: ExecuteCallback) -> None:
        self._on_execute = fn

    # ---------------- 事件管理 ----------------

    def schedule_batch(
        self,
        events: list[ScheduledEvent],
    ) -> None:
        """批量加入事件。"""
        for ev in events:
            heapq.heappush(self._heap, ev)
        self._wakeup_event.set()

    def schedule_one(
        self,
        event: ScheduledEvent,
        immediate: bool = False,
    ) -> None:
        """运行时动态插入单个事件。immediate=True 时唤醒主循环立即检查。"""
        heapq.heappush(self._heap, event)
        if immediate:
            self._wakeup_event.set()

    def has_pending_events(self) -> bool:
        return len(self._heap) > 0

    def peek_next(self) -> Optional[ScheduledEvent]:
        """查看下一个事件（不弹出）。"""
        return self._heap[0] if self._heap else None

    # ---------------- 主循环 ----------------

    async def run(self) -> None:
        """启动调度器主循环，直到所有事件完成或 shutdown()。"""
        self._running = True
        try:
            await self._main_loop()
        finally:
            self._running = False

    async def _main_loop(self) -> None:
        while not self._shutdown_flag:
            if not self._heap:
                # 没有事件了，等 shutdown 或新事件插入
                self._wakeup_event.clear()
                if self._shutdown_flag:
                    break
                try:
                    await asyncio.wait_for(self._wakeup_event.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    if not self._heap:
                        # 真的没事件了，退出
                        break
                continue

            next_event = self._heap[0]

            if next_event.source == EventSource.BOUNDARY:
                # 边界事件：立即执行
                heapq.heappop(self._heap)
                await self._execute(next_event)
            else:
                # 锚点事件：等待到 anchor_time（基于注入的时间源 = 虚拟时间）
                now = self._get_now()
                if next_event.anchor_time is not None:
                    wait_seconds = (next_event.anchor_time - now).total_seconds()
                else:
                    wait_seconds = 0

                # 时间加速判定：若启用阈值且锚点距当前 > 阈值，不真实等待，直接执行
                # Runner 的 _maybe_accelerate 会处理快进逻辑（更新 mock_time + 通知助手）
                should_skip_wait = (
                    self._acceleration_threshold is not None
                    and wait_seconds > self._acceleration_threshold.total_seconds()
                )

                if wait_seconds <= 0 or self._fast_mode or should_skip_wait:
                    # 时间已到 / fast_mode / 时间加速：立即执行
                    heapq.heappop(self._heap)
                    await self._execute(next_event)
                else:
                    # 等待到 anchor_time，但可被新事件抢占
                    self._wakeup_event.clear()
                    try:
                        await asyncio.wait_for(
                            self._wakeup_event.wait(),
                            timeout=wait_seconds,
                        )
                        # 被唤醒（可能有新更高优先级事件插入）
                        continue
                    except asyncio.TimeoutError:
                        # 时间到，执行
                        heapq.heappop(self._heap)
                        await self._execute(next_event)

    async def _execute(self, event: ScheduledEvent) -> None:
        """执行单个事件的回调。"""
        if self._on_execute is None:
            return
        await self._on_execute(event)

    # ---------------- 控制 ----------------

    def shutdown(self) -> None:
        """通知调度器退出。"""
        self._shutdown_flag = True
        self._wakeup_event.set()

    @property
    def is_running(self) -> bool:
        return self._running
