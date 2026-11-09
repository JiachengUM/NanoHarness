"""极薄 mock 适配器：新协议的「参考接入样本」。

目的不是复刻真实助手的业务逻辑，而是用最小体积演示新协议要覆盖的共性机制：
- 普通回复 + 文字增量流
- 异步工具调用 → 结果晚到 → 接续回复（on_result 挂载续接源）
- 主动话语（定时提醒到期，快进后无用户输入自主开口）
- 车态变更（操作注入的 virtual_car）

注意：本类是「被测助手」的替身，属于被验证对象，不是框架的一部分；
框架不认识它，只通过 protocol.AssistantAdapter 的接口驱动它。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Optional

from projects.experiments.time_travel_auto_test.adapter_v2.protocol import (
    AdapterEnv,
    AssistantEvent,
    Capabilities,
    EventType,
    Turn,
    TurnKind,
    WorldUpdate,
)


# ---------------- 模拟原生事件（mock 助手的"土话"） ----------------

@dataclass
class RawText:
    wall: datetime
    delta: str


@dataclass
class RawToolCall:
    wall: datetime
    task_id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawToolResult:
    wall: datetime
    task_id: str
    name: str
    result: str


class MockAdapter:
    """极薄 mock 被测助手，实现 AssistantAdapter。"""

    def __init__(self) -> None:
        self.capabilities = Capabilities(
            supports_barge_in=True,
            has_async_tools=True,
            can_proactive_speak=True,
            needs_time_source=True,
        )
        self._car: Any = None
        self._get_time: Optional[Any] = None
        self._session_id = ""
        self._history: list[dict[str, str]] = []
        self._reminder_trigger: Optional[datetime] = None
        self._proactive_text: Optional[str] = None
        # 打断（助手自驱）：指向当前未耗尽回复源的取消信号；None = 无活跃回复源
        self._barge_signal: Optional[asyncio.Event] = None
        # 被打断次数（供验证脚本断言"插话打断确实发生"）
        self._barged_in_count = 0

    # ---------------- 协议实现 ----------------

    def setup(self, env: AdapterEnv) -> None:
        self._session_id = env.session_id
        self._car = env.virtual_car
        self._get_time = env.get_virtual_time
        self._history = []
        self._reminder_trigger = None
        self._proactive_text = None
        self._barge_signal = None
        self._barged_in_count = 0

    def _now(self) -> datetime:
        return self._get_time() if self._get_time is not None else datetime.now()

    def initial_sources(self, turn: Turn) -> list[AsyncIterator[Any]]:
        # 自驱打断（中立观察者）：新用户输入到来、上一个回复源尚未耗尽且支持打断时，
        # 助手自行置位信号中断旧流——完全对应旧协议 achat_stream 开头的
        # self._active_reply.interrupt()。框架从始至终没有 cancel 旧流，
        # 旧流在下一个说话间隔点自然提前结束，上层据此拼接"半截话"。
        if (
            turn.kind is TurnKind.USER
            and self.capabilities.supports_barge_in
            and self._barge_signal is not None
        ):
            self._barge_signal.set()
            self._barged_in_count += 1

        if turn.kind is TurnKind.PROACTIVE:
            return [self._proactive_source(turn)]
        if "提醒" in turn.text:
            # 异步工具：回复源（先说话 + 调工具）+ 结果源（稍后返回）
            return [self._reply_source(turn), self._async_tool_source()]
        return [self._reply_source(turn)]

    def translate(self, raw: Any) -> Optional[AssistantEvent]:
        if isinstance(raw, RawText):
            return AssistantEvent(
                type=EventType.TEXT_DELTA, wall_time=raw.wall, delta=raw.delta
            )
        if isinstance(raw, RawToolCall):
            return AssistantEvent(
                type=EventType.TOOL_CALL, wall_time=raw.wall,
                tool_name=raw.name, tool_args=raw.args, task_id=raw.task_id,
            )
        if isinstance(raw, RawToolResult):
            return AssistantEvent(
                type=EventType.TOOL_RESULT, wall_time=raw.wall,
                tool_name=raw.name, tool_result=raw.result, task_id=raw.task_id,
            )
        return None

    def on_result(self, raw: Any) -> Optional[AsyncIterator[Any]]:
        if isinstance(raw, RawToolResult):
            return self._continuation_source(raw.result)
        return None

    async def apply_world_update(self, update: WorldUpdate) -> list[datetime]:
        """时间推进 → 判断定时提醒是否到期；未到期则返回停靠点。"""
        anchors: list[datetime] = []
        ct = update.current_time
        if ct is not None and self._reminder_trigger is not None:
            if ct >= self._reminder_trigger and self._proactive_text is None:
                self._proactive_text = "时间到了，该喝水啦。"
            elif ct < self._reminder_trigger:
                anchors.append(self._reminder_trigger)
        return anchors

    def dump_history(self) -> list[dict[str, str]]:
        return list(self._history)

    # ---------------- 各条原生源（mock 的内部实现） ----------------

    async def _reply_source(self, turn: Turn) -> AsyncIterator[Any]:
        wall = datetime.now()          # 真实墙钟（事件时间戳，协议要求）
        virt_now = self._now()          # 业务虚拟时刻（定时触发等业务逻辑）
        text = turn.text
        self._history.append({"role": "user", "content": text})
        reply_parts: list[str] = []
        # 注册本源的打断信号（新输入到来时据此自驱中断；本源耗尽后释放）
        signal = asyncio.Event()
        self._barge_signal = signal
        try:
            if "提醒" in text:
                yield RawText(wall, "好的，我来帮你设置提醒。")
                reply_parts.append("好的，我来帮你设置提醒。")
                yield RawToolCall(wall, task_id="t1", name="set_reminder",
                                  args={"seconds": 1800})
                self._reminder_trigger = virt_now + timedelta(seconds=1800)
            elif "空调" in text:
                yield RawText(wall, "好的，已为您打开空调。")
                reply_parts.append("好的，已为您打开空调。")
                if self._car is not None:
                    self._car.set_field("空调开启状态及模式", "制冷中")
            elif "故事" in text or "讲" in text or "长" in text:
                # 长回复：多个 chunk + 说话间隔，供"用户插话打断"演示
                sentences = ["从前有座山，", "山里有座庙，", "庙里有个老和尚，",
                             "正在讲故事，", "故事讲的是一个车载助手。"]
                for sentence in sentences:
                    if signal.is_set():
                        break  # 被打断：提前结束（半截话）
                    yield RawText(datetime.now(), sentence)
                    reply_parts.append(sentence)
                    await asyncio.sleep(0.3)  # 模拟说话间隔（可被插话打断）
            else:
                chunk = f"收到您的请求：{text[:20]}"
                yield RawText(wall, chunk)
                reply_parts.append(chunk)
        finally:
            # 本源结束，释放打断信号（仅当信号仍是本源的）
            if self._barge_signal is signal:
                self._barge_signal = None
            # 整段回复文本写回历史（续接段由 _continuation_source 单独补记）
            self._history.append({"role": "assistant", "content": "".join(reply_parts)})

    async def _async_tool_source(self) -> AsyncIterator[Any]:
        """模拟异步工具：稍后返回真实结果。"""
        await asyncio.sleep(0.3)
        yield RawToolResult(datetime.now(), task_id="t1", name="set_reminder",
                            result="提醒已设置为30分钟后")

    async def _continuation_source(self, result: str) -> AsyncIterator[Any]:
        """异步结果到达后，助手接续说一段。"""
        await asyncio.sleep(0.1)
        chunk = f"好的，{result}，到点我会提醒你。"
        self._history.append({"role": "assistant", "content": chunk})
        yield RawText(datetime.now(), chunk)

    async def _proactive_source(self, turn: Turn) -> AsyncIterator[Any]:
        """主动话语（定时提醒到期）：无用户输入，自主开口。"""
        chunk = self._proactive_text or "时间到了。"
        self._history.append({"role": "assistant", "content": chunk})
        yield RawText(datetime.now(), chunk)