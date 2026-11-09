"""WebSocket 会话管理 + 出站推送 pump。

从 voice_test_api.py 拆分。包含：
- VoiceWsSession（封装 adapter/text_adapter/run_task/batch_step + cancel_run）
- pump_outbound（事件优先 + PCM 其次的出站推送）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable

from fastapi import WebSocket, WebSocketDisconnect

from projects.voice_test.schemas.browser_schemas import (
    DoneEvent,
    ErrorEvent,
    OutMessage,
)
from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.adapter.browser_text_adapter import BrowserTextAdapter
from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.adapter.browser_agent_catalog import TestMode
from projects.voice_test.config.adapter_config import VoiceAdapterConfig

from projects.mind.test_backend.api.voice_test.batch_runner import (
    BatchStepController,
    CancelReason,
)

_log = get_vt_logger("ws_session")
_pump_log = get_vt_logger("pump")

# pump 出站轮询时间片：事件队列短轮询，音频队列长轮询
# 50ms 检查一次是否有新事件插队，保证 phase/asr 等状态切换延迟 < 50ms
_PUMP_EVENT_POLL_SEC = 0.05
# 事件队列空时最多等 450ms 音频帧，超时后回到外层循环重新检查事件队列
_PUMP_AUDIO_POLL_SEC = 0.45


async def push_ws_error(out_queue: asyncio.Queue[OutMessage], message: str) -> None:
    """协议/业务错误统一经事件队列 → pump_outbound 下发。"""
    await out_queue.put(ErrorEvent(message=message))


async def pump_outbound(
    event_queue: asyncio.Queue[OutMessage],
    audio_queue: asyncio.Queue[bytes],
    ws: WebSocket,
    stopped: asyncio.Event,
    pump_exited: asyncio.Event | None = None,
) -> None:
    """事件优先于 PCM：避免音频堵在队列里拖慢 phase / asr 等状态切换。

    退出依赖：stopped 事件（正常关闭）或 send 抛异常（连接断开）。
    不检查 ws.client_state：TCP 静默断开时该状态不会更新，不可靠。
    异常退出时通过 pump_exited 通知上层 receive 循环，避免依赖二次异常捕获。
    """
    try:
        while not stopped.is_set():
            frame: object | None = None
            is_audio = False
            try:
                frame = event_queue.get_nowait()
            except asyncio.QueueEmpty:
                try:
                    frame = audio_queue.get_nowait()
                    is_audio = True
                except asyncio.QueueEmpty:
                    try:
                        frame = await asyncio.wait_for(event_queue.get(), timeout=_PUMP_EVENT_POLL_SEC)
                    except asyncio.TimeoutError:
                        try:
                            frame = await asyncio.wait_for(audio_queue.get(), timeout=_PUMP_AUDIO_POLL_SEC)
                            is_audio = True
                        except asyncio.TimeoutError:
                            continue

            try:
                if is_audio:
                    assert isinstance(frame, (bytes, bytearray, memoryview))
                    await ws.send_bytes(bytes(frame))
                else:
                    assert not isinstance(frame, (bytes, bytearray, memoryview))
                    await ws.send_json(frame.model_dump(mode="json"))
            except (WebSocketDisconnect, RuntimeError) as exc:
                # pump send 失败：TCP 半开连接感知点，记录便于区分"pump 触发"还是"接收超时触发"
                _pump_log.warning("pump send failed, treat as disconnected: %r", exc)
                break
    finally:
        if pump_exited is not None:
            pump_exited.set()


@dataclass
class VoiceWsSession:
    ws: WebSocket
    out_queue: asyncio.Queue[OutMessage]
    voice_adapter: BrowserVoiceAdapter
    text_adapter: BrowserTextAdapter
    test_mode: TestMode = "voice"
    run_task: asyncio.Task[None] | None = None
    batch_step: BatchStepController | None = None
    # cancel 原因：user_stop=用户主动结束（标 FAILED），pause/ws_disconnect=WS 断连（标 PAUSED）
    cancel_reason: CancelReason | None = None

    def adapter_for(
        self, test_mode: TestMode
    ) -> BrowserVoiceAdapter | BrowserTextAdapter:
        return self.text_adapter if test_mode == "text" else self.voice_adapter

    async def send_error(self, message: str) -> None:
        await push_ws_error(self.out_queue, message)

    def busy(self) -> bool:
        return self.run_task is not None and not self.run_task.done()

    async def reject_if_busy(self) -> bool:
        if self.busy():
            await self.send_error("上一轮尚未结束")
            return True
        return False

    def start_run(
        self,
        operation: Awaitable[object],
        *,
        session_config: VoiceAdapterConfig,
        test_mode: TestMode,
    ) -> None:
        self.test_mode = test_mode
        # session_config：语音在会话级 apply_config；文本无 adapter 配置，仅透传给 runner。
        if test_mode == "voice":
            self.voice_adapter.apply_config(session_config)
        self.run_task = asyncio.create_task(self._wrap_run(operation, test_mode))

    async def _wrap_run(
        self,
        operation: Awaitable[object],
        test_mode: TestMode,
    ) -> None:
        adapter = self.adapter_for(test_mode)
        try:
            await operation
            await adapter.push_event(DoneEvent())
        except asyncio.CancelledError:
            # user_stop：前端需要知道批跑已结束，推 DoneEvent
            # pause/ws_disconnect：由 run_voice_batch 的 except 分支推 BatchPausedEvent
            if self.cancel_reason == CancelReason.USER_STOP:
                try:
                    await adapter.push_event(DoneEvent())
                except Exception as exc:
                    _log.debug("push DoneEvent on user_stop failed (ws likely disconnected): %r", exc)
            raise
        except Exception as exc:
            _log.error("run failed: %s: %r", type(exc).__name__, exc)
            await adapter.push_event(ErrorEvent(message=str(exc)))
            await adapter.push_event(DoneEvent())
        finally:
            # 清理本次运行状态，避免残留影响下次批跑
            self.batch_step = None
            self.cancel_reason = None

    async def cancel_run(self, reason: CancelReason | None = None) -> None:
        # 只在首次设置时记录原因，避免 finally 覆盖 user_stop
        if self.cancel_reason is None and reason is not None:
            self.cancel_reason = reason
        if self.batch_step is not None:
            self.batch_step.unblock()
        if self.run_task is not None and not self.run_task.done():
            self.run_task.cancel()
            await asyncio.gather(self.run_task, return_exceptions=True)
        self.run_task = None
