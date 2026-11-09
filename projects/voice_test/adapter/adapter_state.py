"""S2S 适配器共享状态（浏览器 / 物理链路共用，不依赖 PyAudio）。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum

from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.config.adapter_config import VoiceAdapterConfig, adapter_config
from projects.voice_test.config.core_config import (
    AsrExtraModel,
    StartSessionReqModel,
    start_session_req,
)

_log = get_vt_logger("state")


class AdapterPhase(StrEnum):
    IDLE = "idle"
    SPEAKING = "speaking"
    LISTENING = "listening"
    CLOSED = "closed"


class InjectTtsGate(StrEnum):
    """注入 TTS 闸门（相对 S2S 对话模型闲聊 TTS）。

    服务端关不掉自动闲聊，客户端默认静音；自定义注入发出并对齐后短暂放行 PCM。

        静音 ──开始说──► 静音(记下模式)
             ──注入请求已发出──► 等对齐
             ──SentenceStart 对上──► 放行
             ──说完 / ASR 后 / 开麦──► 静音
    """

    SILENT = "silent"
    WAIT_ALIGN = "wait_align"
    PASS = "pass"


# ---------------------------------------------------------------------------
# 三袋：会话进度 / 注入 TTS 闸门 / 等外部回话
# ---------------------------------------------------------------------------


@dataclass
class SessionCursor:
    """同一条 S2S 连接上、跨多轮还要记住的进度。"""

    # AutoTest 冷启动对话 id；变了要换 S2S
    framework_session_id: str = ""
    # 本连接是否已「立住」：立住后改用 ChatTTSText
    s2s_ready: bool = False
    # 唤醒词是否已经拼过一次
    wake_up_used: bool = False

    @property
    def use_say_hello(self) -> bool:
        """还没立住 → SayHello；立住了 → ChatTTSText。"""
        return not self.s2s_ready

    def mark_ready(self) -> None:
        self.s2s_ready = True

    def reset_for_session(self, session_id: str) -> None:
        self.framework_session_id = session_id
        self.s2s_ready = False
        self.wake_up_used = False

    def clear(self) -> None:
        self.framework_session_id = ""
        self.s2s_ready = False
        self.wake_up_used = False


@dataclass
class InjectTtsController:
    """丢掉对话模型闲聊，只放行自定义注入的 PCM。"""

    gate: InjectTtsGate = InjectTtsGate.SILENT
    # 本轮注入方式：say_hello | chat_tts_text
    inject_mode: str = ""
    # 当前正在播放的 TTS 轨类型（default 即 S2S 内置闲聊，需过滤其 PCM 防串音）
    current_tts_type: str = ""
    # 本轮注入 TTS 结束（TTSEnded）时 set
    tts_done: asyncio.Event | None = None
    # 日志器（由 AdapterState 注入，带 sid/run 前缀）
    log: logging.Logger | logging.LoggerAdapter = field(
        default_factory=lambda: _log, repr=False
    )

    def silent(self) -> None:
        prev = self.gate
        self.gate = InjectTtsGate.SILENT
        self.inject_mode = ""
        self.current_tts_type = ""
        if prev != InjectTtsGate.SILENT:
            self.log.info("gate %s->SILENT", prev.name)

    def begin(self, *, inject_mode: str) -> asyncio.Event:
        self.tts_done = asyncio.Event()
        self.inject_mode = inject_mode
        self.current_tts_type = ""
        self.gate = InjectTtsGate.SILENT
        self.log.info("gate begin inject_mode=%s", inject_mode)
        return self.tts_done

    def on_inject_sent(self) -> None:
        """SayHello / ChatTTSText 已发出，开始等对齐事件。"""
        if self.inject_mode:
            prev = self.gate
            self.gate = InjectTtsGate.WAIT_ALIGN
            self.log.info("gate %s->WAIT_ALIGN inject_mode=%s", prev.name, self.inject_mode)

    def on_sentence_start(self, tts_type: str) -> None:
        # 跟踪当前 TTS 轨类型：default 即 S2S 内置闲聊，accepting 据此过滤其 PCM
        if tts_type:
            self.current_tts_type = tts_type
            if tts_type == "default":
                self.log.info("tts_type=default detected, drop its PCM")
        if self.gate != InjectTtsGate.WAIT_ALIGN:
            return
        if self.inject_mode == "chat_tts_text" and tts_type == "chat_tts_text":
            self.gate = InjectTtsGate.PASS
            self.log.info("gate WAIT_ALIGN->PASS tts_type=%s", tts_type)
            return
        # SayHello：发出后的首个 Start 即视为注入轨
        if self.inject_mode == "say_hello":
            self.gate = InjectTtsGate.PASS
            self.log.info("gate WAIT_ALIGN->PASS (say_hello)")

    def on_ended(self) -> None:
        if self.tts_done is not None and not self.tts_done.is_set():
            self.tts_done.set()
        self.silent()

    def end(self) -> None:
        self.tts_done = None
        self.silent()

    @property
    def accepting(self) -> bool:
        # default = S2S 内置闲聊轨，需过滤其 PCM 防串音
        return self.gate == InjectTtsGate.PASS and self.current_tts_type != "default"


class AsrEndedTimeout(TimeoutError):
    """有 ASR 后等不到 ASREnded；text 为最后一帧完整识别（通常来自 Delta）。"""

    def __init__(self, message: str, *, text: str = "") -> None:
        super().__init__(message)
        self.text = text


@dataclass
class ExternalReplyWait:
    """开麦后等外部 ASR。

    - 无 ASR：空等 N 秒 → 没听到
    - 有 ASR：N 作废；每帧 Delta 覆盖最新文本并刷新 M
    - 正常 ASREnded：用当前最新文本
    - M 超时：用当前最新文本（当 asr_final 发出去）
    """

    latest_asr_text: str = ""
    reply_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    got_any_asr: asyncio.Event = field(default_factory=asyncio.Event)
    last_asr_at: float | None = None
    # 首个含非空 content 的 ASRDelta 到达时刻；用于统计首字响应时间
    first_asr_at: float | None = None
    listening_asr_logged: bool = False
    # 日志器（由 AdapterState 注入，带 sid/run 前缀）
    log: logging.Logger | logging.LoggerAdapter = field(
        default_factory=lambda: _log, repr=False
    )

    def begin(self) -> None:
        self.latest_asr_text = ""
        self.got_any_asr = asyncio.Event()
        self.last_asr_at = None
        self.first_asr_at = None
        self.listening_asr_logged = False

    def clear_replies(self) -> None:
        while not self.reply_queue.empty():
            self.reply_queue.get_nowait()

    def note_got_asr(self, text: str = "") -> None:
        """Delta：完整文本覆盖，并刷新 M。"""
        self.got_any_asr.set()
        now = time.monotonic()
        self.last_asr_at = now
        if self.first_asr_at is None:
            self.first_asr_at = now
        content = text.strip()
        if content:
            self.latest_asr_text = content

    def on_asr_final(self, text: str = "") -> None:
        """Final 只刷新 M；文本只认 Delta，超时/Ended 都拿 latest。"""
        self.got_any_asr.set()
        self.last_asr_at = time.monotonic()

    def take_latest_asr_text(self) -> str:
        text = self.latest_asr_text
        self.latest_asr_text = ""
        return text

    async def on_asr_ended(self) -> str | None:
        text = self.take_latest_asr_text()
        if text:
            await self.reply_queue.put(text)
        return text or None

    def _raise_asr_ended_timeout(self, asr_ended_timeout_sec: float) -> None:
        text = self.take_latest_asr_text()
        self.log.warning("asr_ended timeout %ss text=%r", asr_ended_timeout_sec, text)
        raise AsrEndedTimeout(
            f"有 ASR 后等待结束超时（{asr_ended_timeout_sec:g}s 内无 ASREnded）",
            text=text,
        )

    async def wait(
        self,
        timeout_sec: float,
        *,
        asr_ended_timeout_sec: float,
    ) -> str:
        deadline_no_asr = time.monotonic() + timeout_sec
        poll_sec = 0.2
        while True:
            now = time.monotonic()
            if self.got_any_asr.is_set():
                last_at = self.last_asr_at if self.last_asr_at is not None else now
                remaining = (last_at + asr_ended_timeout_sec) - now
                if remaining <= 0:
                    self._raise_asr_ended_timeout(asr_ended_timeout_sec)
                wait_time = min(remaining, poll_sec)
            else:
                remaining = deadline_no_asr - now
                if remaining <= 0:
                    self.log.warning("external reply timeout %ss (no ASR)", timeout_sec)
                    raise TimeoutError(
                        f"等待外部设备回复超时（{timeout_sec}s 内无 ASR）"
                    )
                wait_time = remaining
            try:
                return await asyncio.wait_for(
                    self.reply_queue.get(),
                    timeout=wait_time,
                )
            except asyncio.TimeoutError as exc:
                if self.got_any_asr.is_set():
                    continue
                self.log.warning("external reply timeout %ss (no ASR)", timeout_sec)
                raise TimeoutError(
                    f"等待外部设备回复超时（{timeout_sec}s 内无 ASR）"
                ) from exc


class AdapterState:
    """说听编排门面：相位 + 会话进度 / 注入 TTS / 等外部回话。"""

    def __init__(self, log: logging.Logger | logging.LoggerAdapter | None = None) -> None:
        self.phase = AdapterPhase.IDLE
        self.session = SessionCursor()
        # 接受外部 logger（带 sid/run 前缀）；未传入时回退到模块默认 logger
        self._log = log if log is not None else _log
        self.inject = InjectTtsController(log=self._log)
        self.reply = ExternalReplyWait(log=self._log)

    # --- 会话进度 ---

    @property
    def framework_session_id(self) -> str:
        return self.session.framework_session_id

    @property
    def s2s_ready(self) -> bool:
        return self.session.s2s_ready

    @property
    def wake_up_used(self) -> bool:
        return self.session.wake_up_used

    @wake_up_used.setter
    def wake_up_used(self, value: bool) -> None:
        self.session.wake_up_used = value

    @property
    def use_say_hello(self) -> bool:
        return self.session.use_say_hello

    def mark_s2s_ready(self) -> None:
        self.session.mark_ready()

    @property
    def listening_asr_logged(self) -> bool:
        return self.reply.listening_asr_logged

    @listening_asr_logged.setter
    def listening_asr_logged(self, value: bool) -> None:
        self.reply.listening_asr_logged = value

    @property
    def is_listening(self) -> bool:
        return self.phase == AdapterPhase.LISTENING

    @property
    def accept_tts_audio(self) -> bool:
        return self.phase == AdapterPhase.SPEAKING and self.inject.accepting

    def _set_phase(self, new_phase: AdapterPhase) -> None:
        prev = self.phase
        self.phase = new_phase
        if prev != new_phase:
            self._log.info("phase %s->%s", prev.value, new_phase.value)

    def begin_speaking(self, *, injected_mode: str = "") -> asyncio.Event:
        self._set_phase(AdapterPhase.SPEAKING)
        return self.inject.begin(inject_mode=injected_mode)

    def on_inject_sent(self) -> None:
        if self.phase == AdapterPhase.SPEAKING:
            self.inject.on_inject_sent()

    def end_speaking(self) -> None:
        self._set_phase(AdapterPhase.IDLE)
        self.inject.end()

    def on_tts_sentence_start(self, tts_type: str) -> None:
        self.inject.on_sentence_start(tts_type)

    def on_tts_ended(self) -> None:
        self.inject.on_ended()

    def prepare_for_external_asr_end(self) -> None:
        """外部说完：静音，丢掉 S2S 自带闲聊。"""
        self.inject.silent()

    def begin_listening(self) -> None:
        self._set_phase(AdapterPhase.LISTENING)
        self.reply.begin()
        self.inject.silent()

    def end_listening(self) -> None:
        self._set_phase(AdapterPhase.IDLE)
        self.inject.silent()

    def note_got_asr(self, text: str = "") -> None:
        if self.phase == AdapterPhase.LISTENING:
            self.reply.note_got_asr(text)

    def on_asr_final(self, text: str) -> None:
        self.reply.on_asr_final(text)

    async def on_asr_ended(self) -> None:
        if self.phase != AdapterPhase.LISTENING:
            return
        await self.reply.on_asr_ended()
        self._set_phase(AdapterPhase.IDLE)

    async def wait_for_external_reply(
        self,
        timeout_sec: float,
        *,
        asr_ended_timeout_sec: float,
    ) -> str:
        return await self.reply.wait(
            timeout_sec,
            asr_ended_timeout_sec=asr_ended_timeout_sec,
        )

    def switch_framework_session(self, session_id: str) -> None:
        self.session.reset_for_session(session_id)

    def clear_replies(self) -> None:
        self.reply.clear_replies()

    def reset_on_close(self) -> None:
        self._set_phase(AdapterPhase.CLOSED)
        self.session.clear()
        self.inject.end()
        self.reply = ExternalReplyWait()


def build_start_session_req(
    config: VoiceAdapterConfig = adapter_config,
) -> StartSessionReqModel:
    custom_req = start_session_req.model_copy(deep=True)
    custom_req.asr.extra = AsrExtraModel(
        end_smooth_window_ms=config.vad_timeout_ms,
        enable_custom_vad=True,
    )
    custom_req.tts.speaker = config.s2s_speaker
    return custom_req
