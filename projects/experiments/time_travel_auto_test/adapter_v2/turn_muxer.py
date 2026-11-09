"""TurnMuxer：回合多路复用器（框架核心基础设施）。

把一个回合（Turn）里的多条原生事件源汇合成一条有序的「已盖戳统一事件流」，
并在所有源自然耗尽时结束——这就是"Turn=生成器耗尽即空闲"的落地：

- 多源汇合：initial_sources 返回的 N 条线 + on_result 挂载的接续源，
  全部扇入同一个队列，按到达顺序消费。
- 引用计数判耗尽：每挂一个源计数 +1，源消耗完 -1；计数归零且队列空 = 回合结束。
- wall→mock 盖戳：translate 出的 AssistantEvent 只带 wall_time，这里用
  TimelineEngine.wall_to_mock 统一换算成虚拟时刻（框架独有，接入者零感知）。
- cancel：**测试基建超时兜底**——仅当被测助手底层流卡死（超时）时，
  框架才强制终止消费协程防止测试挂死。它**不是**"用户插话打断"；
  打断由助手自驱（见 protocol.Capabilities.supports_barge_in）。

彻底中立：本模块不认识任何被测助手，只认 protocol.AssistantAdapter 的接口。
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from projects.experiments.time_travel_auto_test.adapter_v2.protocol import (
    AssistantAdapter,
    SourcedEvent,
    Turn,
)
from projects.experiments.time_travel_auto_test.case_runner.timeline import TimelineEngine


class TurnMuxer:
    """把一个回合的多条原生事件源汇合成一条已盖戳的统一事件流。

    用法（上层/校验脚本）：
        async for sourced in TurnMuxer(adapter, turn, timeline).stream():
            # sourced.mock_time / sourced.event 直接落盘（复用 TraceRecorder）

    契约：上层必须在 stream() 自然耗尽后才允许快进（TimelineEngine.accelerate_to），
    否则 wall→mock 换算会因快进重锚定而失真。
    """

    def __init__(
        self,
        adapter: AssistantAdapter,
        turn: Turn,
        timeline: TimelineEngine,
    ) -> None:
        self._adapter = adapter
        self._turn = turn
        self._timeline = timeline
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._active = 0                 # 尚未耗尽的源数量（含接续源）
        self._cancelled = False
        self._consumer_tasks: list[asyncio.Task] = []
        self._started = False

    # ---------------- 内部 ----------------

    def _spawn(self, src: AsyncIterator[Any]) -> None:
        """挂载一条原生源：计数 +1，起消费协程。"""
        self._active += 1
        task = asyncio.create_task(self._consume(src))
        self._consumer_tasks.append(task)

    async def _consume(self, src: AsyncIterator[Any]) -> None:
        """把一条源的原始事件逐个扇入队列；耗尽/取消时放哨兵唤醒主循环。"""
        try:
            async for raw in src:
                if self._cancelled:
                    break
                await self._queue.put(raw)
        finally:
            self._active -= 1
            await self._queue.put(None)  # 哨兵：通知主循环"少了一条源"

    def _handle_raw(self, raw: Any) -> AsyncIterator[SourcedEvent]:
        """处理一条原始事件：翻译 → 盖戳 → 产出；再判断是否挂接续源。

        用同步生成器拆出（避免在 async 里 return 难处理），交给上层逐个 yield。
        """
        event = self._adapter.translate(raw)
        if event is not None:
            mock = self._timeline.wall_to_mock(event.wall_time)
            yield SourcedEvent(mock_time=mock, event=event, turn=self._turn)
        cont = self._adapter.on_result(raw)
        if cont is not None:
            self._spawn(cont)

    # ---------------- 对外 ----------------

    async def stream(self) -> AsyncIterator[SourcedEvent]:
        """多路复用产出已盖戳事件，直到所有源耗尽（回合自然结束）。"""
        self._started = True
        sources = self._adapter.initial_sources(self._turn)
        for src in sources:
            self._spawn(src)
        if self._active == 0:
            return  # 无任何源：空回合

        while not self._cancelled:
            item = await self._queue.get()
            if item is None:  # 某条源耗尽
                if self._active <= 0 and self._queue.empty():
                    return  # 全部耗尽且无积压：回合结束
                continue
            for sourced in self._handle_raw(item):
                yield sourced

    def cancel(self) -> None:
        """测试基建超时兜底：强制终止尚未耗尽的所有活跃消费协程。

        仅用于"被测助手底层流卡死"（如回复超时 180s）时防止测试挂死；
        不用于用户插话打断——打断由被测助手自驱实现（supports_barge_in）。
        取消后各源在 finally 里释放计数，回合随之结束，"半截话"由上层
        从已产出的 TEXT_DELTA 增量拼接得到。
        """
        if not self._started:
            return
        self._cancelled = True
        for task in self._consumer_tasks:
            if not task.done():
                task.cancel()


async def run_turn(
    adapter: AssistantAdapter,
    turn: Turn,
    timeline: TimelineEngine,
) -> list[SourcedEvent]:
    """便捷入口：跑完一个回合，收集全部已盖戳事件（供校验脚本直接断言）。"""
    out: list[SourcedEvent] = []
    muxer = TurnMuxer(adapter, turn, timeline)
    async for sourced in muxer.stream():
        out.append(sourced)
    return out