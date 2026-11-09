"""AssistantProtocol：被测助手接入协议（事件流协议 v2 + 流式输入）。

命名说明（见 CONTEXT.md §0.9）：
- SUT/TestedAssistant → 直接叫 AssistantProtocol（助手协议）
- 类比 auto_test 的 AnyBotToTest，标准化接入接口
- 流式回复用 StreamingReply，产出 AssistantEvent 而非 str

v2 升级（2026-08-25）：
- achat_stream 产出 AssistantEvent 序列（TEXT_DELTA / TOOL_CALL / TOOL_RESULT），
  替代旧版 str 文本流
- 每个 AssistantEvent 携带 wall_time 时间戳，Runner 可做时序分析
  （首字延迟、停顿检测）并传给 Judge
- 各助手在对接时负责将自身原生事件翻译为 AssistantEvent

流式输入升级（2026-08-26）：
- achat_stream 的输入从完整文本改为异步文本流（模拟流式 ASR）：
  - 第一个 chunk 到达 = 用户开口（插话打断时机信号）
  - 迭代器耗尽 = 用户说完
- 插话打断能力测试契约：支持插话打断的助手应在收到输入流第一个 chunk
  时中断自己旧的输出流（旧 StreamingReply 提前结束）；不支持打断的助手
  会在旧流说完后才开始处理新输入（多流并行）——框架如实记录两种行为
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

from projects.experiments.time_travel_auto_test.script_events.script_event import (
    WorldTickScriptEvent,
)


# ---------------- 事件流类型 ----------------

class AssistantEventType(str, Enum):
    """助手流式回复中产生的事件类型。"""
    TEXT_DELTA = "text_delta"       # 流式文本增量
    TOOL_CALL = "tool_call"         # 工具调用开始
    TOOL_RESULT = "tool_result"     # 工具调用返回


@dataclass
class AssistantEvent:
    """助手在流式回复中产生的统一事件。

    各助手在对接时负责将自身原生事件翻译为此格式。
    每个事件携带 wall_time 时间戳，Runner 可据此做时序分析。

    Attributes:
        type: 事件类型
        wall_time: 真实时间戳（datetime.now()），用于计算首字延迟和停顿
        delta: TEXT_DELTA 事件的文本增量
        tool_name: TOOL_CALL / TOOL_RESULT 事件的工具名
        tool_args: TOOL_CALL 事件的工具参数
        tool_result: TOOL_RESULT 事件的工具返回结果
        tool_duration_ms: TOOL_RESULT 事件的工具执行耗时（毫秒）
    """
    type: AssistantEventType
    wall_time: datetime
    # TEXT_DELTA
    delta: str = ""
    # TOOL_CALL / TOOL_RESULT
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    tool_duration_ms: float = 0.0


# ---------------- ContextUpdateResult ----------------

@dataclass
class ContextUpdateResult:
    """aupdate_context 的结构化返回结果。

    替代旧版 str | None 返回值，支持：
    - proactive_text: 助手主动说话的内容（旧版返回值）
    - injected_events: 助手运行时注入的 WorldTick 事件（如定时任务触发时间）
      Runner 将这些事件注入事件队列，与剧本事件统一调度
    - proactive_segments: 主动话语的流式分段（chunk 级时间戳），
      每项为 (相对生成起点的偏移秒, 文本增量)。Runner 以定时任务触发时刻 at
      为锚点重建区间与流式内容，避免主动话语在时间线中渲染为瞬时点。
      未提供（空列表）时，Runner 回退到旧行为（ttft 点事件）。
    """

    proactive_text: Optional[str] = None
    injected_events: list[WorldTickScriptEvent] = field(default_factory=list)
    proactive_segments: list[tuple[float, str]] = field(default_factory=list)


# ---------------- StreamingReply ----------------

class StreamingReply:
    """流式回复：支持增量获取 AssistantEvent 和打断。

    用法：
        async def input_stream():  # 模拟流式 ASR（第一个 chunk = 用户开口）
            for ch in "开空调":
                yield ch
        reply = await assistant.achat_stream(input_stream())
        async for event in reply.stream():
            if event.type == AssistantEventType.TEXT_DELTA:
                print(event.delta, end="")
            elif event.type == AssistantEventType.TOOL_CALL:
                print(f"[调用工具: {event.tool_name}]")
        # 如果需要打断：
        reply.interrupt()  # 保存已说部分为半截话

    打断机制：
        生产者协程可把 anyio.CancelScope 挂到 _cancel_scope；
        interrupt() 会调用 cs.cancel() 真正取消正在进行的推理，
        同时放入哨兵让消费者 stream() 立即停止。
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AssistantEvent | None] = asyncio.Queue()
        self._done: bool = False
        self._interrupted: bool = False
        self._collected_text: str = ""
        self._events: list[AssistantEvent] = []  # 所有已接收的事件
        self._lock: asyncio.Lock = asyncio.Lock()
        self._cancel_scope: Any = None

    async def put_event(self, event: AssistantEvent) -> None:
        """生产者：放入一个事件。"""
        if self._done or self._interrupted:
            return
        async with self._lock:
            self._events.append(event)
            if event.type == AssistantEventType.TEXT_DELTA and event.delta:
                self._collected_text += event.delta
            await self._queue.put(event)

    async def put_chunk(self, chunk: str) -> None:
        """生产者：放入一个文本片段（兼容旧版，自动转为 TEXT_DELTA 事件）。"""
        await self.put_event(AssistantEvent(
            type=AssistantEventType.TEXT_DELTA,
            wall_time=datetime.now(),
            delta=chunk,
        ))

    async def finish(self) -> None:
        """生产者：标记回复完成。"""
        async with self._lock:
            self._done = True
            await self._queue.put(None)  # 哨兵

    def interrupt(self) -> None:
        """打断：保存已说部分，标记为半截话。

        注意：不在此处放入哨兵——哨兵统一由 finish() 放入。
        若在流式 chunk 尚未入队的间隙打断，提前放入哨兵会导致 _consume 在 chunk 到达前就终止，
        丢失已生成但尚未入队的 chunk。正确的做法是：
        1. 设置 _interrupted = True → _produce 在下一个循环迭代检查并 break
        2. _produce 在 finally 中调用 finish() → 放入哨兵
        3. _consume 在收到哨兵后返回已收集的完整文本
        """
        self._interrupted = True
        if self._cancel_scope is not None:
            try:
                self._cancel_scope.cancel()
            except Exception:
                pass

    async def stream(self) -> AsyncIterator[AssistantEvent]:
        """消费者：迭代获取 AssistantEvent。遇到 None 哨兵停止。"""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event

    # 兼容旧版：stream_text() 只产出字符串
    async def stream_text(self) -> AsyncIterator[str]:
        """消费者：迭代获取文本片段（兼容旧版接口）。"""
        async for event in self.stream():
            if event.type == AssistantEventType.TEXT_DELTA and event.delta:
                yield event.delta

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def is_interrupted(self) -> bool:
        return self._interrupted

    @property
    def collected_text(self) -> str:
        """已收集的完整文本（包括打断前的部分）。"""
        return self._collected_text

    @property
    def events(self) -> list[AssistantEvent]:
        """所有已接收的事件（包括 TEXT_DELTA / TOOL_CALL / TOOL_RESULT）。"""
        return list(self._events)


# ---------------- AssistantProtocol ----------------

@runtime_checkable
class AssistantProtocol(Protocol):
    """被测助手接入协议（事件流协议 v2）。

    实现这个协议的类（如 TestedAssistant / MockAssistant）即可接入 CaseRunner。

    achat_stream 产出 AssistantEvent 序列（TEXT_DELTA / TOOL_CALL / TOOL_RESULT），
    替代旧版 str 文本流。每个 AssistantEvent 携带 wall_time 时间戳，
    Runner 可据此做时序分析（首字延迟、停顿检测）并传给 Judge。

    aupdate_context 协议升级（2026-07-24，§2.5 主动智能测试）：
    - 加 current_time 参数：用于注入虚拟时间，让助手内部定时任务可触发
    - 返回 ContextUpdateResult：proactive_text + injected_events
    """

    def create(self, session_id: str, system_prompt: str = "") -> None:
        """创建/重置对话会话。"""
        ...

    async def achat(self, user_text: str) -> str:
        """发送用户消息，返回助手完整回复（非流式）。

        简单场景用这个即可。
        """
        ...

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        """发送用户消息（流式输入），返回流式回复对象。

        输入是异步文本流（模拟流式 ASR）：
        - 第一个 chunk 到达 = 用户开口（插话打断时机信号）
        - 迭代器耗尽 = 用户说完

        打断能力测试契约：
        - 支持插话打断的实现：应在收到第一个 chunk 时中断自己旧的
          输出流（旧 StreamingReply 提前结束），等输入流耗尽后生成新回复
        - 不支持打断的实现：可以等输入聚合完再处理（如实暴露底层限制），
          框架将记录多流并行的实际行为

        输出：StreamingReply.stream() 迭代 AssistantEvent
        （TEXT_DELTA / TOOL_CALL / TOOL_RESULT），每个事件携带 wall_time。
        """
        ...

    async def aupdate_context(
        self,
        car_info: dict[str, Any],
        current_time: Optional[datetime] = None,
    ) -> ContextUpdateResult:
        """通知助手外部上下文变化（车态 + 时间）。

        - 车态变更：剧本 set_state 模拟的外部世界变化（驾驶员挂 D 档等）
        - 时间推进：快进到目标时间时，通过 current_time 注入新时间，
          助手内部定时任务到期时可以自主触发行为（主动智能）

        返回值：
        - ContextUpdateResult.proactive_text：助手自主说话的内容（主动智能触发）
        - ContextUpdateResult.injected_events：助手注入的 WorldTick 事件，
          Runner 会将其合并到事件队列中统一调度
        """
        ...

    async def adump_history(self) -> list[dict[str, str]]:
        """导出对话历史，格式：[{"role": "user"/"assistant", "content": "..."}]"""
        ...


def is_assistant(obj: Any) -> bool:
    """检查对象是否实现 AssistantProtocol。"""
    return (
        hasattr(obj, "create")
        and hasattr(obj, "achat")
        and hasattr(obj, "achat_stream")
        and hasattr(obj, "aupdate_context")
        and hasattr(obj, "adump_history")
    )