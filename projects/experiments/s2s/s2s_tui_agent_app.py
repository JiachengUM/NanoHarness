"""Reusable S2S TUI agent application shell.

The app owns the realtime speech session, microphone gate, audio playback, and
agent TTS output. Agent and runner wiring stays outside via a factory callable
that receives (user_data, on_text_start, on_text_delta, on_text_done) and
returns (runner, agent).
"""
from __future__ import annotations

import asyncio
import os
import queue
import signal
import sys
import threading
import time
import wave
from typing import Any, Callable, Literal

import numpy as np
import pyaudio
from pydantic import BaseModel, Field
from rich import print

from projects.experiments.s2s.config import input_audio_config, output_audio_config, ws_connect_config
from projects.experiments.s2s.event import (
    ASRDelta,
    ASREnded,
    ASRFinal,
    ASRInfo,
    TTSEnded,
    S2sServerNotify,
    ServerErrorResponse,
    ServerEventPrinter,
    SessionFailed,
    SessionFinished,
    TTSSentenceStart,
    TTSResponse,
)
from projects.experiments.microphone_gate import (
    MicrophoneInputGate,
    is_microphone_trigger_key,
)
from projects.experiments.s2s.realtime_dialog_client import (
    ChatTtsTextRequest,
    RealtimeClientOptions,
    RealtimeDialogClient,
    SayHelloRequest,
)

from aicore.simulation.user_env.data_source import UserDataSourceBase

from projects.experiments.s2s.session_runner import SESSION_RESET_INPUT, SessionResetInterceptAgent

_IS_WINDOWS = os.name == "nt"

DEFAULT_IDLE_SESSION_FAREWELL_LINE = "如果没有事情的话我就先退下啦。"

# 一轮 chat_tts 含多句时，服务端可能对每句各发 TTSEnded；用短时静默防抖识别『整段结束』，避免
# 首句 TTSEnded 就放行 _chat_tts_gate / 写静音锚（否则 Agent 仍在播报长文时就会开始计用户静音超时）。
TTS_STREAM_END_DEBOUNCE_SEC = 0.45
# TTSEnded 早于本地扬声器「播完」：下行 PCM 仍在 ``audio_queue`` 中排队时不得写静音锚。
# 排空判定为连续若干次 poll 队列为空（见 ``_await_assistant_speaker_audio_queue_drained``）。
AUDIO_QUEUE_DRAIN_STABLE_POLLS = 4
AUDIO_QUEUE_DRAIN_POLL_SEC = 0.05

# ── 多轮对话（multiturn）语义与数据流 ─────────────────────────────────────────
# 「一轮」= 自首条 finalized ASR 注入 Runner（打「第N次多轮对话开始」）起到 ``inner.new_session()``
# 执行完毕（SessionResetInterceptAgent 回调打「第N次多轮对话结束」）止；中间用户继续说话仍属同轮，
# 不会重复打印开始日志。结束本轮的方式：
#   (A) 静音超时 — ``multiturn_session_idle_sec``：计时锚点为 **本地扬声器已不再积压** 本轮助手 PCM
#       （``audio_queue`` 排空）、且（若启用）ReAct 整轮已结束；并非服务端 TTSEnded 瞬间。
#       ReAct 多段文本/多工具时，中间段 TTS 结束**不写**锚，避免「Agent 仍在跑工具/说下一段」却计用户静音。
#       若此后连续 silent 超时，先走告别 `_play_idle_session_farewell_and_wait`，再
#       `put(SESSION_RESET_INPUT)`。（开场 `say_hello` 且无模型 TTS 时，用首场 TTSEnded 落锚。）
#   (B) 关键字 — ``multiturn_session_end_keyword``：本条用户话仍照常 `put(text)`；
#       随后立即 `put(SESSION_RESET_INPUT)`，由 Runner 在适当时机 `new_session`（通常为
#       当前轮模型处理完成之后由队列顺序决定；若需「等回复后再切」一般由队列顺序保证）。
#
# 「故意结束多轮」后（关键字或静音告别 + new_session）：不得再对**该段收尾 TTS**或会话空窗
# 落静音锚，否则用户说「退下」后不说话仍会误触超时告别。见 ``_suppress_idle_anchor_until_next_user_inject``。
#
# Runner 必须使用 SessionResetInterceptAgent 包裹内层 Agent，哨兵串才会变成 new_session；
# 否则哨兵可能进入模型。见 ``session_runner.py``。
# v1 ReAct 的 ``ReActFinishEvent`` / ``ReActErrorEvent`` 由 ``S2STUIAgentApp`` 在构造后包装
# ``AgentRunnerBase._client`` 监听（见 ``_install_v1_react_finish_client_wrapper_if_configured``），
# 无需改 ``s2s_tui_agent_app_main.build_v1_runner_bundle``。
# ───────────────────────────────────────────────────────────────────────────


def _convert_input_to_output_audio(pcm: bytes) -> bytes:
    """上行 int16/16k → 播放 float32/24k（numpy 插值重采样）。"""
    if not pcm:
        return b""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0
    in_n = int(x.size)
    if in_n == 0:
        return b""
    out_n = max(1, int(round(in_n * output_audio_config.sample_rate / float(input_audio_config.sample_rate))))
    src_i = np.linspace(0.0, in_n - 1, num=out_n, dtype=np.float64)
    y = np.interp(src_i, np.arange(in_n, dtype=np.float64), x).astype(np.float32)
    return y.tobytes()


def _scale_float32_pcm(pcm: bytes, gain: float) -> bytes:
    """Scale float32 PCM playback bytes, clipping to the valid audio range."""
    if gain < 0:
        raise ValueError("audio gain must be >= 0")
    if gain == 1.0 or not pcm:
        return pcm
    sample_width = np.dtype(np.float32).itemsize
    if len(pcm) % sample_width != 0:
        return pcm

    samples = np.frombuffer(pcm, dtype=np.float32)
    scaled = np.clip(samples * gain, -1.0, 1.0).astype(np.float32)
    return scaled.tobytes()


MicMode = Literal["space_gate", "continuous"]
KeyboardControl = Literal["stdin", "external", "none"]
InputSource = Literal["microphone", "audio_files"]
AudioFilePlaybackMode = Literal["auto", "manual"]


class S2SAgentAppConfig(BaseModel):
    session_id_prefix: str = Field(default="s2s-tui-agent")
    mic_mode: MicMode = Field(default="space_gate")
    keyboard_control: KeyboardControl = Field(default="stdin")
    say_hello: str | None = Field(default="你好，我是豆包，有什么可以帮助你的？")
    
    input_source: InputSource = Field(default="microphone")
    audio_file_list: list[tuple[str, float]] = Field(default_factory=list)
    audio_file_playback_mode: AudioFilePlaybackMode = Field(default="auto")
    s2s_audio_gain: float = Field(
        default=1.0,
        ge=0.0,
        description="服务端 S2S TTS 下行 float32 PCM 写入扬声器前的本地增益；不影响本地音频文件回放。",
    )
    # --- 以下为「一轮多轮」边界相关的三项配置 ---
    multiturn_session_idle_sec: float | None = Field(
        default=None,
        description=(
            "自 Agent 本轮回复在本机扬声器侧播完（audio_queue 排空）、且满足 ReAct/尾段 TTS 规则后起算，"
            "用户连续 silent 超过该秒数则播告别语并 new_session；None 关闭"
        ),
    )
    multiturn_session_end_keyword: str | None = Field(
        default=None,
        description=(
            "用户 finalized 文案包含该子串时：先把本条 ASR put 给 Runner；紧接着 put SESSION_RESET_INPUT，"
            "由 SessionResetInterceptAgent 执行 new_session；None 关闭"
        ),
    )
    multiturn_idle_session_farewell_text: str | None = Field(
        default=None,
        description="因静音超时结束多轮前播报的告别语；None 表示使用内置默认",
    )
    multiturn_idle_anchor_after_react_turn_only: bool = Field(
        default=False,
        description=(
            "为 True：仅当 ReAct 对该条用户话已结束且尾段 TTS 收口后才写静音锚（v1 下由 App 包装 "
            "``runner._client`` 监听 ReActFinish/ReActError，无需改 build_v1_runner_bundle）。"
            "v2 无该事件时请保持 False。"
        ),
    )


class S2SAgentAppState(BaseModel):
    is_running: bool = Field(default=True)
    is_user_querying: bool = Field(default=False)
    agent_voice_only: bool = Field(default=False)
    latest_final_asr_text: str = Field(default="")


class QueueUserDataSource(UserDataSourceBase):
    """Async queue data source for complete ASR text."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def put(self, text: str) -> None:
        await self._queue.put(text)

    async def close(self) -> None:
        await self._queue.put(None)

    async def __call__(self):
        while True:
            data = await self._queue.get()
            if data is None:
                return
            yield data


class S2STUIAgentApp:
    """S2S 实时链路与麦克风/播放/ASR→Runner 注入的编排壳。

    多轮会话的计时锚点、关键字与 ``SESSION_RESET_INPUT`` 的配合方式见本文件模块级说明与
    ``projects.experiments.s2s.session_runner``。
    """

    def __init__(
        self,
        *,
        runner_factory: Callable[..., tuple[Any, Any]],
        config: S2SAgentAppConfig | None = None,
        user_text_client: Callable[[str, bool], None] | None = None,
        microphone_state_client: Callable[[str], None] | None = None,
        # 可选：例如 TUI ``call_later(write_log)``，与控制台 print 同步收到「第N次多轮对话开始/结束」。
        multiturn_log_client: Callable[[str], None] | None = None,
        # 不经 Runner 的整段助手文案（如静音告别 TTS）同步到调试 UI 聊天区。
        synthetic_assistant_text_ui_client: Callable[[str], None] | None = None,
        realtime_client: RealtimeDialogClient | None = None,
        audio_device: Any | None = None,
    ) -> None:
        self.config = config or S2SAgentAppConfig()
        self.state = S2SAgentAppState()
        self.microphone_gate = MicrophoneInputGate(
            is_open=self.config.mic_mode == "continuous"
        )
        self.user_text_client = user_text_client
        self.microphone_state_client = microphone_state_client
        self.multiturn_log_client = multiturn_log_client
        self.synthetic_assistant_text_ui_client = synthetic_assistant_text_ui_client

        self.client = realtime_client or RealtimeDialogClient(
            options=RealtimeClientOptions(
                ws_config=ws_connect_config,
                session_id=f"{self.config.session_id_prefix}-{int(time.time())}",
            )
        )

        if audio_device is None:
            from projects.experiments.s2s.audio_manager import AudioDeviceManager

            audio_device = AudioDeviceManager(input_audio_config, output_audio_config)
        self.audio_device = audio_device

        self.server_event_printer = ServerEventPrinter(show_audio_binary=False)
        self.user_data_source = QueueUserDataSource()
        # ASRInfo 会清空 ``latest_final_asr_text``；若服务端在 ASREnded 之前已为下一段口述发了 ASRInfo，
        # 仅靠 latest 注入会拿不到「上一轮」ASRFinal 文本，用户栏与 Runner 双双漏字（常见于短句如「退下」）。
        self._asr_inject_text_fallback: str = ""
        # 静音超时：从「Agent 本轮 TTS 播完」起的 monotonic 锚点；None 表示当前不在计时窗内。
        self._multiturn_idle_anchor_monotonic: float | None = None
        # True 表示当前正在播「空闲告别」；避免告别播完后误把锚点再次推到当前时刻。
        self._playing_idle_farewell_tts: bool = False
        # say_hello 已发且等首场 TTSEnded 来落首次空闲锚（模型尚未产 TTS 时）。
        self._say_hello_idle_anchor_pending: bool = False
        # True：刚结束一轮多轮（关键字/静音告别等）且下一条「用户 finalized ASR」尚未注入——禁止为
        # 上一段 Agent TTS 闭合写静音锚，避免「退下」后仍计静音超时。下一条用户话进 inject 时清回 False。
        self._suppress_idle_anchor_until_next_user_inject: bool = False
        # multiturn idle：ReAct 对「本条用户输入」整轮结束（Finish/Error）后才允许写静音锚，见 ``mark_react_turn_complete_for_multiturn_idle``。
        self._react_turn_finished_for_idle_anchor: bool = False
        # 尾段 TTS 已在 ReActFinish 之前闭合时，Finish 到达后补写静音锚。
        self._idle_anchor_pending_until_react_finish: bool = False
        self.runner, self.agent = runner_factory(
            user_data=self.user_data_source,
            on_text_start=self.emit_agent_text_start,
            on_text_delta=self.emit_agent_text_delta,
            on_text_done=self.emit_agent_text_done,
        )
        self._install_v1_react_finish_client_wrapper_if_configured()

        self._multiturn_round_no = 0
        # True：下一条带正文的 finalized ASR 注入时记为「新一轮多轮」并打开始日志。
        self._multiturn_log_begin_pending = True
        ra = self.runner._agent
        # 仅当内层已是拦截包装器时挂载；否则结束回调不会触发，但「第N次多轮对话开始」仍会打。
        if isinstance(ra, SessionResetInterceptAgent):
            ra.on_after_session_reset = self._on_multiturn_session_after_reset_logged

        self.runner_task: asyncio.Task[Any] | None = None
        self.tts_task: asyncio.Task[Any] | None = None
        self.audio_player_thread: threading.Thread | None = None
        self.microphone_reader_thread: threading.Thread | None = None

        self.mic_audio_queue: queue.Queue[bytes] = queue.Queue()
        self.file_audio_queue: queue.Queue[bytes] = queue.Queue()
        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self.agent_text_queue: asyncio.Queue[str | None] = asyncio.Queue()

        self._chat_tts_gate: asyncio.Event | None = None
        # 参见 ``TTS_STREAM_END_DEBOUNCE_SEC``：末段 TTSEnded 的防抖任务，与 _chat_tts_gate / hello 锚共用。
        self._tts_stream_end_debounce_task: asyncio.Task[None] | None = None
        self._idle_farewell_tts_barrier: asyncio.Event | None = None
        self._expect_idle_farewell_tts: bool = False
        self._manual_audio_file_event: asyncio.Event | None = None
        self._manual_audio_file_trigger_count = 0
        self._audio_file_input_active = self.config.input_source == "audio_files"

        byte_count = (
            input_audio_config.chunk
            * input_audio_config.channels
            * pyaudio.get_sample_size(input_audio_config.bit_size)
        )
        self._silence_pcm = b"\x00" * byte_count

        signal.signal(signal.SIGINT, self._on_keyboard_interrupt)

    def _install_v1_react_finish_client_wrapper_if_configured(self) -> None:
        """不修改 main 里的 bundle：在 ``multiturn_idle_anchor_after_react_turn_only`` 时包装 ``runner._client``，转发 v1 ReAct 整轮结束。"""
        if not self.config.multiturn_idle_anchor_after_react_turn_only:
            return
        base = getattr(self.runner, "_client", None)
        if base is None or not callable(base):
            return
        app = self

        def wrapped(event: Any) -> None:
            from aicore.events.react import ReActErrorEvent, ReActFinishEvent

            if isinstance(event, (ReActFinishEvent, ReActErrorEvent)):
                app.mark_react_turn_complete_for_multiturn_idle()
            base(event)

        self.runner._client = wrapped  # type: ignore[method-assign, assignment]

    def _on_keyboard_interrupt(self, sig: int, frame: object) -> None:
        print("[yellow]收到 Ctrl+C，准备退出...[/yellow]")
        self.stop()

    def _cancel_tts_stream_end_debounce(self) -> None:
        t = self._tts_stream_end_debounce_task
        if t is None:
            return
        if not t.done():
            t.cancel()
        self._tts_stream_end_debounce_task = None

    def _flush_pending_tts_stream_end_signals(self) -> None:
        """整段 say_hello / 本轮 Agent chat_tts 在下游的最后一帧 TTSEnded 上应执行：放行 gate、落开场静音锚。"""
        if self._chat_tts_gate is not None and not self._chat_tts_gate.is_set():
            self._chat_tts_gate.set()
        idle_sec_cfg = self.config.multiturn_session_idle_sec
        if (
            idle_sec_cfg is not None
            and float(idle_sec_cfg) > 0
            and self._say_hello_idle_anchor_pending
            and not self._suppress_idle_anchor_until_next_user_inject
        ):
            self._say_hello_idle_anchor_pending = False
            self._multiturn_idle_anchor_monotonic = time.monotonic()

    def _schedule_tts_stream_end_debounce(self) -> None:
        """末段 TTSEnded 若不带 no_content，用静默窗口合并多句各自下发的 TTSEnded。"""
        self._cancel_tts_stream_end_debounce()

        async def _run() -> None:
            try:
                await asyncio.sleep(TTS_STREAM_END_DEBOUNCE_SEC)
                self._flush_pending_tts_stream_end_signals()
            except asyncio.CancelledError:
                raise

        t = asyncio.create_task(_run())

        def _clear_done(_fut: asyncio.Future[Any]) -> None:
            if self._tts_stream_end_debounce_task is t:
                self._tts_stream_end_debounce_task = None

        t.add_done_callback(_clear_done)
        self._tts_stream_end_debounce_task = t

    def stop(self) -> None:
        self._cancel_tts_stream_end_debounce()
        self.state.is_running = False
        if self._manual_audio_file_event is not None:
            self._manual_audio_file_event.set()

    def request_next_audio_file(self) -> bool:
        if self.config.input_source != "audio_files":
            return False
        if self.config.audio_file_playback_mode != "manual":
            return False
        self._manual_audio_file_trigger_count += 1
        if self._manual_audio_file_event is not None:
            self._manual_audio_file_event.set()
        return True

    def _on_multiturn_session_after_reset_logged(self) -> None:
        """SessionResetInterceptAgent 在 ``SESSION_RESET_INPUT`` → ``new_session()`` 完成后同步调用。

        与 ``_maybe_log_multiturn_session_begin`` 成对：标记上一「多轮」在 Agent/火山侧已切边。
        同时清静音锚并 ``_suppress_idle_anchor_until_next_user_inject``，防止 new_session 之后空窗
        仍沿用上一段 TTS 的闭合锚或竞态写锚。
        """
        if self._multiturn_round_no < 1:
            return
        msg = f"第{self._multiturn_round_no}次多轮对话结束，正在生成/更新本次对话的记忆，需耗时10-15秒。"
        print(msg)
        cb = self.multiturn_log_client
        if cb is not None:
            cb(msg)
        self._cancel_tts_stream_end_debounce()
        self._multiturn_idle_anchor_monotonic = None
        self._react_turn_finished_for_idle_anchor = False
        self._idle_anchor_pending_until_react_finish = False
        self._suppress_idle_anchor_until_next_user_inject = True
        self._multiturn_log_begin_pending = True

    def _maybe_log_multiturn_session_begin(self) -> None:
        """同轮内仅首条 finalized ASR 注入前打印「第N次多轮对话开始」并递增次数。

        ``_multiturn_log_begin_pending`` 在上一轮 ``new_session`` 完成（或进程启动）时为 True。
        """
        if not self._multiturn_log_begin_pending:
            return
        self._multiturn_round_no += 1
        n = self._multiturn_round_no
        msg = f"第{n}次多轮对话开始"
        print(msg)
        cb = self.multiturn_log_client
        if cb is not None:
            cb(msg)
        self._multiturn_log_begin_pending = False

    def emit_agent_text_start(self) -> None:
        self.agent_text_queue.put_nowait(None)

    def emit_agent_text_delta(self, text: str) -> None:
        if text.strip() == "":
            return
        self.agent_text_queue.put_nowait(text)

    def emit_agent_text_done(self) -> None:
        self.agent_text_queue.put_nowait(None)

    def mark_react_turn_complete_for_multiturn_idle(self) -> None:
        """由包装后的 ``runner._client`` 在 ``ReActFinishEvent`` / ``ReActErrorEvent`` 上调用。

        尾段 TTS 可能在 ReActFinish 之前已 TTSEnded；落锚前须再等本地 ``audio_queue`` 排空，故用 task。
        """
        self._react_turn_finished_for_idle_anchor = True
        if not self._idle_anchor_pending_until_react_finish:
            return
        self._idle_anchor_pending_until_react_finish = False
        idle_sec_cfg = self.config.multiturn_session_idle_sec
        if idle_sec_cfg is None or float(idle_sec_cfg) <= 0:
            return
        if (
            not self.state.is_running
            or self._suppress_idle_anchor_until_next_user_inject
            or self._playing_idle_farewell_tts
        ):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._multiturn_idle_anchor_monotonic = time.monotonic()
            return
        loop.create_task(self._apply_idle_anchor_after_assistant_playback_drained())

    async def _apply_idle_anchor_after_assistant_playback_drained(self) -> None:
        await self._await_assistant_speaker_audio_queue_drained()
        idle_sec_cfg = self.config.multiturn_session_idle_sec
        if idle_sec_cfg is None or float(idle_sec_cfg) <= 0:
            return
        if (
            not self.state.is_running
            or self._suppress_idle_anchor_until_next_user_inject
            or self._playing_idle_farewell_tts
        ):
            return
        self._multiturn_idle_anchor_monotonic = time.monotonic()

    async def _await_assistant_speaker_audio_queue_drained(self) -> None:
        """等播放线程消费完 ``audio_queue`` 中已入队的助手 TTS PCM（与 TTSEnded 解耦）。"""
        n_stable = 0
        deadline = time.monotonic() + 180.0
        while self.state.is_running and time.monotonic() < deadline:
            if self.audio_queue.empty():
                n_stable += 1
                if n_stable >= AUDIO_QUEUE_DRAIN_STABLE_POLLS:
                    return
            else:
                n_stable = 0
            await asyncio.sleep(AUDIO_QUEUE_DRAIN_POLL_SEC)
        if self.state.is_running:
            print(
                "[SESSION] 本地 audio_queue 180s 仍未稳定排空，仍写入静音计时锚（避免永久阻塞）"
            )

    def _maybe_write_multiturn_idle_anchor_after_agent_tts_round(self) -> None:
        idle_sec_cfg = self.config.multiturn_session_idle_sec
        if idle_sec_cfg is None or float(idle_sec_cfg) <= 0 or not self.state.is_running:
            return
        if self._playing_idle_farewell_tts:
            self._playing_idle_farewell_tts = False
            return
        if self._suppress_idle_anchor_until_next_user_inject:
            return
        if not self.config.multiturn_idle_anchor_after_react_turn_only:
            self._multiturn_idle_anchor_monotonic = time.monotonic()
            return
        if self._react_turn_finished_for_idle_anchor:
            self._multiturn_idle_anchor_monotonic = time.monotonic()
        else:
            self._idle_anchor_pending_until_react_finish = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        print("[BOOT] 启动 S2S TUI Agent App")
        await self.client.start()
        idle_sec_cfg = self.config.multiturn_session_idle_sec
        multiturn_idle_on = idle_sec_cfg is not None and float(idle_sec_cfg) > 0
        if self.config.say_hello:
            await self.client.send_say_hello(SayHelloRequest(content=self.config.say_hello))
            # 尚无 chat_tts 时，首场 TTSEnded（见 handle_server_response）落空闲锚以便 hello 后也计静音超时。
            if multiturn_idle_on:
                self._say_hello_idle_anchor_pending = True
        self.audio_device.open_output_stream()
        self._start_audio_threads()
        print("[BOOT] WebSocket已连接，音频读写线程已启动")

        multiturn_idle_on = (
            self.config.multiturn_session_idle_sec is not None
            and self.config.multiturn_session_idle_sec > 0
        )
        multiturn_kw_on = bool(self.config.multiturn_session_end_keyword)
        if multiturn_idle_on or multiturn_kw_on:
            print(
                "[MULTITURN] 已启用多轮边界追踪：首轮 finalized ASR 打「第N次多轮对话开始」，"
                "new_session 后打「第N次多轮对话结束」（同一次多轮内后续 ASR 不再打印开始）。"
            )

        idle_task: asyncio.Task[None] | None = None
        if (
            self.config.multiturn_session_idle_sec is not None
            and self.config.multiturn_session_idle_sec > 0
        ):

            async def _idle_watchdog() -> None:
                """轮询静默计时：仅在 ``_multiturn_idle_anchor_monotonic`` 已设置时递减语义上的剩余耐心。

                锚点必须由「上一轮 Agent TTS（或 hello）完结」写上；用户一开说（ASRInfo）即清除，
                避免「模型还在播报却判用户超时」或与「应从播完后计起」语义冲突。
                """
                idle_sec = float(self.config.multiturn_session_idle_sec or 0.0)
                while self.state.is_running:
                    await asyncio.sleep(0.5)
                    last = self._multiturn_idle_anchor_monotonic
                    if last is None:
                        continue
                    if time.monotonic() - last >= idle_sec:
                        print(
                            f"[SESSION] Agent 本轮 TTS 结束后已连续 {idle_sec:g}s "
                            "无用户发声，播报告别语后结束多轮会话并刷新火山记忆缓冲（new_session）"
                        )
                        await self._play_idle_session_farewell_and_wait()
                        self._suppress_idle_anchor_until_next_user_inject = True
                        await self.user_data_source.put(SESSION_RESET_INPUT)
                        self._multiturn_idle_anchor_monotonic = None

            idle_task = asyncio.create_task(_idle_watchdog())

        mic_or_file_ask = asyncio.create_task(
            self._audio_files_loop()
            if self.config.input_source == "audio_files"
            else self._microphone_loop()
        )
        recv_task = asyncio.create_task(self._receive_loop())
        self.runner_task = asyncio.create_task(self.runner.run())
        self.tts_task = asyncio.create_task(self._agent_tts_loop())
        if (
            self.config.mic_mode == "space_gate"
            and self.config.keyboard_control == "stdin"
            and self.config.input_source != "audio_files"
        ):
            keyboard_task = asyncio.create_task(self._keyboard_space_loop())
            worker_list = [mic_or_file_ask, keyboard_task, recv_task, self.runner_task, self.tts_task]
        else:
            worker_list = [mic_or_file_ask, recv_task, self.runner_task, self.tts_task]
        if idle_task is not None:
            worker_list.append(idle_task)
        workers = tuple(worker_list)
        print(f"[BOOT] {len(workers)} 个任务已启动")

        async def until_not_running() -> None:
            while self.state.is_running:
                await asyncio.sleep(0.1)

        guard = asyncio.create_task(until_not_running())
        await asyncio.wait([guard, *workers], return_when=asyncio.FIRST_COMPLETED)
        self.stop()

        await self.user_data_source.close()
        for task in workers:
            if not task.done():
                task.cancel()
        if not guard.done():
            guard.cancel()
        await asyncio.gather(guard, *workers, return_exceptions=True)

        self._join_audio_threads()

        await self.client.stop_session()
        await self.client.stop_connection()
        await self.client.close()
        self.audio_device.cleanup()
        print("[BOOT] 资源清理完成，app 退出")

    def _start_audio_threads(self) -> None:
        self.audio_player_thread = threading.Thread(
            target=self._audio_player_loop,
            name="s2s-audio-player",
            daemon=True,
        )
        self.audio_player_thread.start()
        self.microphone_reader_thread = None
        if self.config.input_source == "microphone":
            self._start_microphone_reader_thread()

    def _start_microphone_reader_thread(self) -> None:
        if self.microphone_reader_thread is not None and self.microphone_reader_thread.is_alive():
            return
        self.microphone_reader_thread = threading.Thread(
            target=self._microphone_reader_loop,
            name="s2s-microphone-reader",
            daemon=True,
        )
        self.microphone_reader_thread.start()

    def _join_audio_threads(self) -> None:
        for thread in (self.microphone_reader_thread, self.audio_player_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=0.5)


    # ------------------------------------------------------------------
    # Interrupt
    # ------------------------------------------------------------------

    def _interrupt_tts_output(self) -> None:
        """用户打断：禁播 TTS、清空待播音频和待发文本。"""
        self._cancel_tts_stream_end_debounce()
        self.state.agent_voice_only = True
        # 清空待播放的 TTS 音频（thread-safe queue）
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        # 清空待发送的 agent 文本（asyncio queue，同线程无竞态）
        while not self.agent_text_queue.empty():
            try:
                self.agent_text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    # ------------------------------------------------------------------
    # Microphone
    # ------------------------------------------------------------------

    def _audio_player_loop(self) -> None:
        """独立线程：从 audio_queue 取数据写入 PyAudio output stream（阻塞 I/O）。"""
        while self.state.is_running:
            try:
                # 播放文件上行音频
                audio = self.file_audio_queue.get_nowait()
            except queue.Empty:
                try:
                    audio = self.audio_queue.get(timeout=0.1)
                    audio = _scale_float32_pcm(audio, self.config.s2s_audio_gain)
                except queue.Empty:
                    continue
            stream = self.audio_device.output_stream
            if stream is not None:
                stream.write(audio)

    def _microphone_reader_loop(self) -> None:
        """独立线程：持续读取 PyAudio input stream（阻塞 I/O），线程内完整管理 stream 生命周期。"""
        input_stream = self.audio_device.open_input_stream()
        print("[MIC] 麦克风输入流已打开")
        try:
            while self.state.is_running:
                try:
                    audio = input_stream.read(input_audio_config.chunk, exception_on_overflow=False)
                except Exception as exc:
                    print(f"[red]麦克风读取失败:[/red] {exc}")
                    self.stop()
                    return
                if self.config.mic_mode == "space_gate" and not self.microphone_gate.is_open:
                    audio = self._silence_pcm
                # put_nowait 不会阻塞读线程；无 maxsize 的 Queue 不会抛 Full
                self.mic_audio_queue.put_nowait(audio)
        finally:
            try:
                input_stream.stop_stream()
                input_stream.close()
            except Exception:
                pass

    async def process_audio_file_input(self, audio_file_path: str) -> None:
        # 读取 WAV，按 input_audio_config.chunk（帧数）分块上行；二进制走 send_audio_chunk（无 task_request）
        with wave.open(audio_file_path, "rb") as wf:
            chunk_size = input_audio_config.chunk
            frame_duration = chunk_size / float(input_audio_config.sample_rate)
            print(f"开始处理音频文件: {audio_file_path}")
            while True:
                audio_data = wf.readframes(chunk_size)
                if not audio_data:
                    break
                await self.client.send_audio_chunk(audio_data)
                # 为了复用播放线程，将输入音频转换为输出音频的格式。
                play = _convert_input_to_output_audio(audio_data)
                if play:
                    self.file_audio_queue.put_nowait(play)
                await asyncio.sleep(frame_duration)
            print("音频文件处理完成，等待服务器响应...")

    async def _audio_files_loop(self) -> None:
        """有 audio_file_list 则顺序消费一轮 WAV；段间 gap_sec 用上行静音体现；消费完后切回麦克风输入。"""
        schedule = self.config.audio_file_list
        frame_duration = input_audio_config.chunk / float(input_audio_config.sample_rate)
        if schedule and self.config.audio_file_playback_mode == "manual":
            self._manual_audio_file_event = asyncio.Event()
            for path, _gap_sec in schedule:
                if not self.state.is_running:
                    break
                should_play = await self._wait_for_next_audio_file_trigger(frame_duration)
                if not should_play:
                    break
                await self.process_audio_file_input(path)
            self._manual_audio_file_event = None
            await self._switch_to_microphone_input()
            return

        if schedule:
            for path, gap_sec in schedule:
                if not self.state.is_running:
                    break
                await self.process_audio_file_input(path)
                if self.state.is_running and gap_sec > 0:
                    n = max(1, round(gap_sec / frame_duration))
                    for _ in range(n):
                        await self.client.send_audio_chunk(self._silence_pcm)
                        await asyncio.sleep(frame_duration)
        await self._switch_to_microphone_input()

    async def _wait_for_next_audio_file_trigger(self, frame_duration: float) -> bool:
        while self.state.is_running:
            if self._manual_audio_file_trigger_count > 0:
                self._manual_audio_file_trigger_count -= 1
                return True

            await self.client.send_audio_chunk(self._silence_pcm)
            event = self._manual_audio_file_event
            if event is None:
                await asyncio.sleep(frame_duration)
                continue
            try:
                await asyncio.wait_for(event.wait(), timeout=frame_duration)
            except TimeoutError:
                continue
            finally:
                event.clear()
        return False

    async def _switch_to_microphone_input(self) -> None:
        if not self.state.is_running:
            return
        self._audio_file_input_active = False
        self._start_microphone_reader_thread()
        if self.config.mic_mode == "space_gate":
            print("[MIC] 预设音频播放完成，空格键麦克风输入已启用")
        else:
            print("[MIC] 预设音频播放完成，切换到麦克风输入")
        await self._microphone_loop()

    async def _microphone_loop(self) -> None:
        """协程：从 mic_audio_queue 取音频帧发送到 WebSocket，用 run_in_executor 避免忙轮询。"""
        if self.config.mic_mode == "space_gate":
            print("[MIC] 等待空格键打开麦克风（空闲时发送静音保活）")
        loop = asyncio.get_running_loop()
        while self.state.is_running:
            try:
                audio = await loop.run_in_executor(
                    None, lambda: self.mic_audio_queue.get(timeout=0.1)
                )
            except queue.Empty:
                continue
            await self.client.send_audio_chunk(audio)

    # ------------------------------------------------------------------
    # Keyboard (space gate)
    # ------------------------------------------------------------------

    def _read_key_blocking(self) -> str | None:
        if _IS_WINDOWS:
            import msvcrt

            if msvcrt.kbhit():
                return msvcrt.getwch()
            return None

        import select

        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if readable:
            return sys.stdin.read(1)
        return None

    async def _keyboard_space_loop(self) -> None:
        if not sys.stdin.isatty():
            print("[KEYBOARD] 标准输入不是 TTY，空格麦克风触发已禁用")
            return

        if _IS_WINDOWS:
            print("[KEYBOARD] 按空格打开麦克风输入")
            while self.state.is_running:
                key = self._read_key_blocking()
                if key is not None:
                    self._handle_keyboard_key(key)
                await asyncio.sleep(0.05)
            return

        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        print("[KEYBOARD] 按空格打开麦克风输入")
        try:
            # macOS/Linux 需要设置 cbreak 模式才能逐键读取。
            tty.setcbreak(fd)
            while self.state.is_running:
                key = self._read_key_blocking()
                if key is not None:
                    self._handle_keyboard_key(key)
                await asyncio.sleep(0.05)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _handle_keyboard_key(self, key: str) -> None:
        if is_microphone_trigger_key(key):
            self.open_microphone_for_user_input(source="keyboard")
        elif key == "\x03":
            self.stop()

    def open_microphone_for_user_input(self, *, source: str = "external") -> bool:
        if self.config.mic_mode != "space_gate":
            return False
        if self._audio_file_input_active:
            return False
        if not self.microphone_gate.open_for_user_input():
            return False
        self._interrupt_tts_output()
        self._emit_microphone_state("opened", source=source)
        return True

    def close_microphone_after_user_input(self, *, source: str = "asr-ended") -> bool:
        if self.config.mic_mode != "space_gate" or not self.microphone_gate.is_open:
            return False
        self.microphone_gate.close_after_user_input()
        self._emit_microphone_state("closed", source=source)
        return True

    def _emit_microphone_state(self, state: str, *, source: str) -> None:
        if self.microphone_state_client is not None:
            self.microphone_state_client(state)
            return
        text = "打开" if state == "opened" else "关闭"
        print(f"[KEYBOARD] {source} 触发，麦克风已{text}")

    def _emit_user_ui(self, text: str, *, interim: bool) -> None:
        """用户侧 UI：交给 user_text_client"""
        if self.user_text_client is not None:
            self.user_text_client(text, interim)

    # ------------------------------------------------------------------
    # Server event handling
    # ------------------------------------------------------------------

    async def handle_server_response(self, server_notify: S2sServerNotify) -> None:
        self.server_event_printer(server_notify)
        s = self.state

        match server_notify:
            case TTSResponse():
                if not s.agent_voice_only:
                    # put_nowait 不阻塞事件循环；player 线程从队列取数据写入 PyAudio
                    self.audio_queue.put_nowait(server_notify.payload.data)

            case ServerErrorResponse():
                print(f"[red]服务端错误:[/red] {server_notify.payload}")
                self.stop()

            case TTSSentenceStart():
                tts_type = server_notify.payload.tts_type or ""
                if tts_type in ("chat_tts_text", "external_rag"):
                    s.agent_voice_only = False
                    # 仍有后续分句时新一轮合成已开始，取消『上一句 TTSEnded』触发的待定末段 flush。
                    self._cancel_tts_stream_end_debounce()

            case ASRInfo():
                s.is_user_querying = True
                s.latest_final_asr_text = ""
                self._interrupt_tts_output()
                self._emit_user_ui("", interim=True)
                # 用户开始新的一轮口述：立即停止「上一轮 TTS 后的静音倒计时」，直至下次锚点重写。
                idle_sec_cfg = self.config.multiturn_session_idle_sec
                if idle_sec_cfg is not None and float(idle_sec_cfg) > 0:
                    self._multiturn_idle_anchor_monotonic = None
                    self._say_hello_idle_anchor_pending = False
                    self._react_turn_finished_for_idle_anchor = False
                    self._idle_anchor_pending_until_react_finish = False

            case ASRDelta():
                t = server_notify.payload.text.strip()
                if t != "":
                    self._emit_user_ui(t, interim=True)

            case ASRFinal():
                text = server_notify.payload.text.strip()
                if text != "":
                    s.latest_final_asr_text = text
                    self._asr_inject_text_fallback = text

            case ASREnded():
                s.is_user_querying = False
                if self.config.mic_mode == "space_gate":
                    self.close_microphone_after_user_input()
                await self._inject_asr_to_runner_if_ready()
                s.latest_final_asr_text = ""
                s.agent_voice_only = True

            case TTSEnded():
                if self._expect_idle_farewell_tts:
                    self._expect_idle_farewell_tts = False
                    if self._idle_farewell_tts_barrier is not None:
                        self._idle_farewell_tts_barrier.set()
                else:
                    p = server_notify.payload
                    # 长文多句时可能多次 TTSEnded；仅末段（或防抖静默后）才视为整段结束，见模块头说明。
                    if p.no_content is True:
                        self._cancel_tts_stream_end_debounce()
                        self._flush_pending_tts_stream_end_signals()
                    else:
                        self._schedule_tts_stream_end_debounce()

            case SessionFinished() | SessionFailed():
                self.stop()

            case _:
                pass

    async def _receive_loop(self) -> None:
        while self.state.is_running:
            server_notify = await self.client.receive_event()
            await self.handle_server_response(server_notify)

    async def _inject_asr_to_runner_if_ready(self) -> None:
        text = self.state.latest_final_asr_text.strip()
        if text == "":
            text = self._asr_inject_text_fallback.strip()
        if text == "":
            self._emit_user_ui("", interim=True)
            return
        self._asr_inject_text_fallback = ""
        self._suppress_idle_anchor_until_next_user_inject = False
        self._react_turn_finished_for_idle_anchor = False
        self._idle_anchor_pending_until_react_finish = False
        self._emit_user_ui(text, interim=False)
        self._maybe_log_multiturn_session_begin()
        # 用户本条已敲定：静音计时暂不从此刻算起，应从「本条触发的 Agent 回复 TTS 播完」再起算。
        idle_sec_cfg = self.config.multiturn_session_idle_sec
        if idle_sec_cfg is not None and float(idle_sec_cfg) > 0:
            self._multiturn_idle_anchor_monotonic = None
        print(f"[ASR_FINAL] 注入 Runner: {text}")
        await self.user_data_source.put(text)
        keyword = self.config.multiturn_session_end_keyword
        if keyword and keyword in text:
            print(
                f"[SESSION] 用户语含「{keyword}」：待本轮 Agent 回复完成后 "
                "将执行 new_session 并开始新一轮多轮对话"
            )
            # QueueUserDataSource 顺序投递；Runner 对每一项会跑完整块 ``astream(...)`` 再取下一项，
            # 故哨兵在用户本条对应的整段模型输出结束之后才触发 ``new_session``。
            await self.user_data_source.put(SESSION_RESET_INPUT)
            self._multiturn_idle_anchor_monotonic = None
            self._react_turn_finished_for_idle_anchor = False
            self._idle_anchor_pending_until_react_finish = False
            # 须在 TTS 闭合写锚之前置位：否则「退下」回复播完后仍会落锚并误触静音超时。
            self._suppress_idle_anchor_until_next_user_inject = True

    def _resolved_idle_farewell_line(self) -> str:
        configured = self.config.multiturn_idle_session_farewell_text
        if configured is None:
            return DEFAULT_IDLE_SESSION_FAREWELL_LINE
        return configured.strip()

    async def _play_idle_session_farewell_and_wait(self) -> None:
        """静音超时路径：插队播报固定告别再走 ``SESSION_RESET_INPUT``。

        走与普通 Agent 一致的 ``emit_agent_text_*`` → ``_agent_tts_loop`` 出音；
        若有 ``synthetic_assistant_text_ui_client`` 则同时将定稿文案写入调试 UI（不走 Runner 事件流）。
        `_playing_idle_farewell_tts` 防止本条 TTS 播完后把空闲锚设为「告别刚结束」（避免重复计时）。
        `TTSEnded` 中与 `_idle_farewell_tts_barrier` 配合，阻塞到告别合成结束再放行 watchdog。
        """
        line = self._resolved_idle_farewell_line()
        if not line:
            return
        ui_cb = self.synthetic_assistant_text_ui_client
        if ui_cb is not None:
            ui_cb(line)
        self._playing_idle_farewell_tts = True
        self._idle_farewell_tts_barrier = asyncio.Event()
        self._expect_idle_farewell_tts = True
        self.emit_agent_text_start()
        self.emit_agent_text_delta(line)
        self.emit_agent_text_done()
        try:
            await asyncio.wait_for(self._idle_farewell_tts_barrier.wait(), timeout=60.0)
        except TimeoutError:
            print("[SESSION] 空闲告别语 TTS 等待超时，仍将执行 new_session")
        finally:
            self._expect_idle_farewell_tts = False
            self._idle_farewell_tts_barrier = None

    # ------------------------------------------------------------------
    # Agent TTS text → server
    # ------------------------------------------------------------------

    async def _chat_tts_gate_wait(self) -> None:
        self._cancel_tts_stream_end_debounce()
        self._chat_tts_gate = asyncio.Event()
        await self._chat_tts_gate.wait()
        self._chat_tts_gate = None

    async def _agent_tts_loop(self) -> None:
        sent_any = False

        while self.state.is_running:
            part = await self.agent_text_queue.get()
            if part is None:
                if sent_any:
                    if self.state.is_user_querying:
                        continue
                    print("[AGENT_TTS] end=True")
                    await self.client.send_chat_tts_text(
                        ChatTtsTextRequest(start=False, end=True, content="")
                    )
                    sent_any = False
                    # 等待前一段自定义文本的tts生成结束，再开始下一轮
                    await self._chat_tts_gate_wait()
                    # 多轮「静音超时」锚点：**仅**在正常 Agent chat_tts 一轮闭合后刷新；告别链路除外。
                    idle_sec_cfg = self.config.multiturn_session_idle_sec
                    if idle_sec_cfg is not None and float(idle_sec_cfg) > 0 and self.state.is_running:
                        await self._await_assistant_speaker_audio_queue_drained()
                        self._maybe_write_multiturn_idle_anchor_after_agent_tts_round()
                continue

            text = part.strip()
            if text == "":
                continue

            while self.state.is_user_querying and self.state.is_running:
                await asyncio.sleep(0.05)

            await self.client.send_chat_tts_text(
                ChatTtsTextRequest(start=not sent_any, end=False, content=text)
            )
            sent_any = True
