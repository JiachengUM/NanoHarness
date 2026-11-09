"""浏览器音频适配：TTS/ASR 经 WebSocket 与前端交换，不依赖 PyAudio。

阅读顺序（同一类服务三条线，先看主故事再看管道）：
1. Bot 对话：speak_and_listen → speak → _wait_external_reply
2. WS 管道：feed_mic / on_playback_drained / push_event / out_queue + audio_out_queue
3. S2S 生命周期：start / ensure_framework_session / release_s2s / close
4. 后台与状态：_receive_loop / _mic_loop / _handle_server_event + AdapterState
5. 字段四袋：配置 · 一轮状态 · 管道 · _S2sSession

speak → listen 门槛（前端 playback_drained ack）：
1. TTSEnded：S2S 假人 TTS 生成结束
2. audio_out_queue 空：最后一包 PCM 已交给 WS 下发
3. await_playback_drain → 前端 WebAudio 播完 → playback_drained
4. 再进 listening / 等外部回复超时
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from websockets.exceptions import ConnectionClosed

from projects.voice_test.schemas.browser_schemas import (
    AsrDeltaEvent,
    AsrFinalEvent,
    AwaitPlaybackDrainEvent,
    BrowserJsonEvent,
    ConfigReplyEvent,
    LogEvent,
    OutMessage,
    PhaseEvent,
    ReadyEvent,
    UserQueryEvent,
    WsPhase,
)
from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.config.adapter_config import VoiceAdapterConfig, adapter_config
from projects.voice_test.adapter.adapter_state import (
    AdapterPhase,
    AdapterState,
    AsrEndedTimeout,
    build_start_session_req,
)
from projects.voice_test.config.core_config import input_audio_config
from projects.voice_test.schemas.events import (
    ASR451NoText,
    ASRDelta,
    ASREnded,
    ASRFinal,
    ASRInfo,
    S2sServerNotify,
    SessionStarted,
    TTSEnded,
    TTSResponse,
    TTSSentenceStart,
)
from projects.voice_test.core.realtime_dialog_client import (
    ChatTtsTextRequest,
    RealtimeClientOptions,
    RealtimeDialogClient,
    SayHelloRequest,
)

_base_log = get_vt_logger("adapter")

# _wait_audio_out_drained 的二次确认轮询参数
# 队列空时先睡 30ms 再复查一次，避免刚空就返回的误判
_DRAIN_RECHECK_SEC = 0.03
# 队列非空时的轮询间隔，20ms 平衡 CPU 与延迟
_DRAIN_LOOP_SEC = 0.02
# 浏览器 WebAudio 播放队列排空确认超时：长 TTS（如 30s 内容）前端需播完才能回 drained
_PLAYBACK_DRAIN_TIMEOUT_SEC = 120.0


class _SidLogAdapter(logging.LoggerAdapter):
    """给日志自动加 [sid=xxx][run=xxx] 前缀，方便 grep 全链路。

    extra 字段：
    - sid: WebSocket 连接级 id（断网定位哪次连接）
    - run: case 执行级 id（定位具体哪一轮 case，串音等问题精确到轮）
    """

    def process(self, msg, kwargs):
        sid = self.extra.get("sid") if self.extra else ""
        run = self.extra.get("run") if self.extra else ""
        parts = []
        if sid:
            parts.append(f"[sid={sid}]")
        if run:
            parts.append(f"[run={run}]")
        prefix = (" ".join(parts) + " ") if parts else ""
        return f"{prefix}{msg}", kwargs


@dataclass
class _S2sSession:
    """S2S 连接成套生命周期：start 时一起建，teardown 时一起清。"""

    client: RealtimeDialogClient | None = None
    running: bool = False
    receive_task: asyncio.Task[None] | None = None
    mic_task: asyncio.Task[None] | None = None


class BrowserVoiceAdapter:
    """假人 TTS 下行到浏览器播放，麦克风音频由浏览器上行。

    对外调用面（按调用方）：
    - BrowserVoiceBot：几乎只用 speak_and_listen
    - voice_test_api（WS）：feed_mic / on_playback_drained / apply_config /
      release_s2s_after_case / close / out_queue / audio_out_queue / push_event
    - voice_case_dialogues：push_event

    字段分四袋：配置 · 一轮状态 · 管道 · S2S 会话（见 __init__）。
    """

    def __init__(self, config: VoiceAdapterConfig = adapter_config) -> None:
        # ① 配置（连接级，apply_config 可覆盖）
        self.config = config
        # 日志带 sid/run 前缀，方便全链路 grep
        self._sid = ""
        self._case_run_id = ""
        self._log = _SidLogAdapter(_base_log, {"sid": "", "run": ""})

        # ② 一轮对话状态（相位 / TTS 门闩 / ASR 在 AdapterState；锁防并发轮次）
        # 把带 sid/run 前缀的 logger 透传给 state，所有 phase/gate 切换日志都带前缀
        self.state = AdapterState(log=self._log)
        self.lock = asyncio.Lock()
        # 与前端 playback_drained ack 绑定，仅 speak 等待播完时短暂存在
        self._playback_drained: asyncio.Event | None = None
        # TTS 空闲超时：记录最后收到 TTSResponse 的单调时间，speak 用它做"两帧间 5s 无数据"兜底
        self._last_tts_recv_monotonic: float = 0.0
        # 首轮响应耗时（ms）：speak_and_listen 内采集，take_last_first_response_ms 取走
        self._last_first_response_ms: float | None = None
        # case 级首轮响应耗时（ms）：voice_case_dialogues 写入，_run_test_session 取走
        self.case_first_response_ms: float | None = None

        # ③ 管道：事件与 PCM 分队列，避免音频堵住 phase/asr 等控数消息
        self.out_queue: asyncio.Queue[OutMessage] = asyncio.Queue()
        self.audio_out_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.mic_in_queue: asyncio.Queue[bytes] = asyncio.Queue()
        inp = input_audio_config
        self._silence_chunk = b"\x00" * (inp.chunk * inp.channels * 2)
        self._frame_sec = inp.chunk / inp.sample_rate

        # ④ S2S 会话（client + 后台 loop，成套生灭）
        self._s2s = _S2sSession()

    # ------------------------------------------------------------------
    # A. Bot 对话入口（BrowserVoiceBot.achat → 这里）
    # ------------------------------------------------------------------

    def set_sid(self, sid: str) -> None:
        """设置 WebSocket 连接级 sid，后续所有 _log 自动带 [sid=xxx] 前缀。"""
        self._sid = sid
        self._log = _SidLogAdapter(_base_log, {"sid": sid, "run": self._case_run_id})
        # 同步给 state，让 phase/gate/超时日志也带前缀
        self.state._log = self._log
        self.state.inject.log = self._log
        self.state.reply.log = self._log

    def set_case_run_id(self, run_id: str) -> None:
        """设置当前 case 执行级 run_id，后续所有 _log 自动带 [run=xxx] 前缀。

        每个 case 每轮执行开始时调用一次；case 结束时传空串清除。
        """
        self._case_run_id = run_id
        self._log = _SidLogAdapter(_base_log, {"sid": self._sid, "run": run_id})
        # 同步给 state，让 phase/gate/超时日志也带前缀
        self.state._log = self._log
        self.state.inject.log = self._log
        self.state.reply.log = self._log

    async def speak_and_listen(self, text: str, session_id: str) -> str:
        """一轮：假人说 text → 等播完 → 开麦等外部 ASR → 返回助手文本。"""
        async with self.lock:
            self._log.info("speak_and_listen enter session=%s text=%r", session_id, text)
            await self.ensure_framework_session(session_id)
            use_say_hello = self.state.use_say_hello
            prepend_wake = use_say_hello and not self.state.wake_up_used
            mode = "SayHello" if use_say_hello else "ChatTTSText"
            await self.push_event(
                UserQueryEvent(
                    text=text,
                    mode=mode,
                    wake_up_word=self.config.wake_up_word if prepend_wake else "",
                    session_id=session_id,
                )
            )
            self.state.clear_replies()
            # 记录首轮响应时间：T2 = begin_listening 时刻（drain + post_drain_wait 之后）
            # T3 = 首个 ASRDelta 时刻；first_response_ms 不含人为等待，纯测被测响应能力
            # 仅首轮（SayHello）采集；超时或无 ASR 则记 None
            t2_listen_start: float | None = None
            record_first_response = use_say_hello
            await self.speak(text, use_say_hello=use_say_hello)

            if self.config.is_goodbye_query(text):
                self._log.info("speak_and_listen goodbye skip session=%s", session_id)
                await self.push_event(LogEvent(message="告别语，跳过等待外部回复"))
                await self.push_event(ConfigReplyEvent(text=self.config.goodbye_reply))
                self.state.mark_s2s_ready()
                return self.config.goodbye_reply

            # T2 在 begin_listening 之前取：first_response_ms 不含人为等待
            if record_first_response:
                t2_listen_start = time.monotonic()

            reply, timed_out = await self._wait_external_reply()
            # 尚未立住时听麦超时：保持未 ready，下一句同连接再 SayHello
            if not (use_say_hello and timed_out):
                self.state.mark_s2s_ready()
            # 采集首轮响应时间：非超时且有 first_asr_at 才记录
            if record_first_response and not timed_out:
                t3_first_asr = self.state.reply.first_asr_at
                if t3_first_asr is not None and t2_listen_start is not None:
                    self._last_first_response_ms = round((t3_first_asr - t2_listen_start) * 1000.0)
                    self._log.info("first_response_ms=%.0f", self._last_first_response_ms)
            self._log.info("speak_and_listen exit session=%s reply=%r timed_out=%s", session_id, reply, timed_out)
            return reply

    def take_last_first_response_ms(self) -> float | None:
        """取走最近一次首轮响应耗时（ms）；非首轮或超时/无 ASR 返回 None。"""
        val = self._last_first_response_ms
        self._last_first_response_ms = None
        return val

    async def speak(self, text: str, *, use_say_hello: bool) -> None:
        """发送一段台词并等播完。拆分模式下分两次 SayHello 调用 _speak_once。"""
        assert self._s2s.client is not None
        opts = self.config
        await self.push_event(PhaseEvent(phase=WsPhase.SPEAKING))

        # 拆分发送：首轮唤醒词与首句分两次 SayHello，各自完整走 begin→PASS→SILENT
        if (
            use_say_hello
            and opts.split_wake_up_and_first_query
            and opts.wake_up_word
            and not self.state.wake_up_used
        ):
            # 第一次：唤醒词（不标记 wake_up_used，留给第二次）
            await self._speak_once(
                opts.wake_up_word,
                use_say_hello=True,
            )
            await asyncio.sleep(opts.split_wake_up_wait_ms / 1000.0)
            # 第二次：首句（标记 wake_up_used，后续不再拼唤醒词）
            self.state.wake_up_used = True
            await self._speak_once(
                text,
                use_say_hello=True,
            )
        else:
            # 默认：拼接发送（首轮）或 ChatTTSText（已立住）
            if use_say_hello and not self.state.wake_up_used and opts.wake_up_word:
                content = f"{opts.wake_up_word}{text}"
            else:
                content = text
            if use_say_hello:
                self.state.wake_up_used = True
            await self._speak_once(
                content,
                use_say_hello=use_say_hello,
            )

        await self.push_event(PhaseEvent(phase=WsPhase.IDLE))

    async def _speak_once(
        self,
        content: str,
        *,
        use_say_hello: bool,
    ) -> None:
        """单次发送：begin_speaking → send → on_inject_sent → 等 tts_done → 等 drain → end_speaking。"""
        injected_mode = "say_hello" if use_say_hello else "chat_tts_text"
        tts_done = self.state.begin_speaking(injected_mode=injected_mode)
        _t0 = time.monotonic()
        try:
            try:
                if use_say_hello:
                    self._log.info("send_say_hello content=%r", content)
                    await self._s2s.client.send_say_hello(SayHelloRequest(content=content))
                else:
                    self._log.info("send_chat_tts_text content=%r", content)
                    await self._s2s.client.send_chat_tts_text(
                        ChatTtsTextRequest(start=True, end=False, content=content.strip())
                    )
                    await self._s2s.client.send_chat_tts_text(
                        ChatTtsTextRequest(start=False, end=True, content="")
                    )
            except ConnectionClosed:
                # 连接已断：标记 running=False，跳过本轮播放，下一轮 ensure_framework_session 会重建
                self._s2s.running = False
                self._log.warning("speak send failed: s2s connection lost")
                await self.push_event(LogEvent(message="S2S 连接已断开，本轮播放跳过"))
                return
            self.state.on_inject_sent()
            self._log.info("after on_inject_sent gate=%s", self.state.inject.gate.name)
            # 空闲超时：两帧 TTSResponse 间隔超 5s 判定服务端异常；总时长不限，长音频不会误杀
            self._last_tts_recv_monotonic = time.monotonic()
            tts_idle_timeout = 5.0
            while not tts_done.is_set():
                done, _ = await asyncio.wait(
                    {asyncio.create_task(tts_done.wait())},
                    timeout=tts_idle_timeout,
                )
                if done:
                    break  # tts_done 已 set
                idle = time.monotonic() - self._last_tts_recv_monotonic
                if idle >= tts_idle_timeout:
                    await self.push_event(LogEvent(message=f"等待 TTS 空闲超时({tts_idle_timeout}s 无新数据)，跳过本轮播放"))
                    self._log.warning("tts_done idle timeout %ss, skip", tts_idle_timeout)
                    break
                for t in done:
                    t.cancel()
            _t1 = time.monotonic()
            self._log.info("tts_done wait done cost=%.2fs, await playback_drained", _t1 - _t0)
            await self._wait_frontend_playback_drained()
            self._log.info("playback_drained done total cost=%.2fs", time.monotonic() - _t0)
        finally:
            self.state.end_speaking()

    async def _wait_external_reply(self) -> tuple[str, bool]:
        """返回 (回复文本, 是否听麦超时)。"""
        self.state.begin_listening()
        await self.push_event(PhaseEvent(phase=WsPhase.LISTENING))
        timeout_sec = self.config.external_reply_timeout_sec
        asr_ended_timeout_sec = self.config.resolve_asr_ended_timeout_sec()
        try:
            return (
                await self.state.wait_for_external_reply(
                    timeout_sec,
                    asr_ended_timeout_sec=asr_ended_timeout_sec,
                ),
                False,
            )
        except AsrEndedTimeout as exc:
            # 不正常超时：把最后一帧 Delta 内容当 asr_final 发出去
            self.state.prepare_for_external_asr_end()
            text = exc.text.strip()
            if text:
                await self.push_event(AsrFinalEvent(text=text))
                return text, False
            reply = "（识别未正常结束）"
            await self.push_event(AsrFinalEvent(text=reply))
            return reply, True
        except TimeoutError:
            # 仅「开麦后完全没有任何 ASR」才走这句
            self.state.prepare_for_external_asr_end()
            reply = f"（等了{timeout_sec:g}秒，还没听到他回复）"
            await self.push_event(AsrFinalEvent(text=reply))
            return reply, True
        finally:
            self.state.end_listening()
            await self.push_event(PhaseEvent(phase=WsPhase.IDLE))
    # ------------------------------------------------------------------
    # B. WS 管道（voice_test_api 入站/出站）
    # ------------------------------------------------------------------

    async def push_event(self, event: BrowserJsonEvent) -> None:
        await self.out_queue.put(event)

    async def feed_mic(self, chunk: bytes) -> None:
        # 非 LISTENING 阶段丢弃 mic 音频，避免残留帧在 SPEAKING 阶段被服务端 ASR
        # 导致服务端把残留音频当用户输入，回复 default TTS 干扰注入流程
        if not self.state.is_listening:
            self._log.debug("feed_mic drop %d bytes (phase=%s)", len(chunk), self.state.phase.value)
            return
        # 前端可能攒多帧再发；按 S2S 帧长切开，避免单包过大
        frame_bytes = len(self._silence_chunk)
        if frame_bytes <= 0:
            await self.mic_in_queue.put(chunk)
            return
        offset = 0
        while offset < len(chunk):
            piece = chunk[offset : offset + frame_bytes]
            offset += len(piece)
            if len(piece) < frame_bytes:
                piece = piece + b"\x00" * (frame_bytes - len(piece))
            await self.mic_in_queue.put(piece)

    def on_playback_drained(self) -> None:
        if self._playback_drained is not None and not self._playback_drained.is_set():
            self._log.info("on_playback_drained set")
            self._playback_drained.set()

    def apply_config(self, config: VoiceAdapterConfig) -> None:
        self.config = config

    def reset_session_events(self) -> None:
        self.state.listening_asr_logged = False

    # ------------------------------------------------------------------
    # C. S2S 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._s2s.running:
            return

        session_id = (
            f"{self.config.session_id_prefix}-"
            f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        )
        self._s2s.client = RealtimeDialogClient(
            options=RealtimeClientOptions(session_id=session_id),
            start_session_req=build_start_session_req(self.config),
            log=self._log,
        )
        await self._s2s.client.start()
        self._s2s.running = True
        self.state.phase = AdapterPhase.IDLE
        self._s2s.receive_task = asyncio.create_task(self._receive_loop())
        self._s2s.mic_task = asyncio.create_task(self._mic_loop())
        await self.push_event(
            ReadyEvent(
                input_sample_rate=input_audio_config.sample_rate,
                output_sample_rate=24000,
                output_format="f32le",
            )
        )

    async def ensure_framework_session(self, session_id: str) -> None:
        # 检查 s2s 连接是否已断（receive_task 异常退出或连接丢失）
        if self._s2s.running and self._s2s.receive_task and self._s2s.receive_task.done():
            self._log.warning("s2s receive_task dead, reconnecting")
            await self.close()
        if session_id == self.state.framework_session_id:
            await self.start()
            return
        if self.state.framework_session_id:
            await self.close()
        self.state.switch_framework_session(session_id)
        await self.start()

    async def release_s2s_after_case(self) -> None:
        """case 对话结束：仅释放 S2S，adapter 仍可用于下一 case。"""
        if not self._s2s.running and self._s2s.client is None:
            return
        await self.push_event(LogEvent(message="当前 case 对话结束"))
        await self._teardown_s2s()

    async def close(self) -> None:
        await self._teardown_s2s()

    async def _teardown_s2s(self) -> None:
        client = self._s2s.client
        self._s2s.running = False
        self.state.end_listening()

        for task in (self._s2s.receive_task, self._s2s.mic_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(
                task
                for task in (self._s2s.receive_task, self._s2s.mic_task)
                if task is not None
            ),
            return_exceptions=True,
        )

        if client is not None:
            for step_name, coro in (
                ("stop_session", client.stop_session()),
                ("stop_connection", client.stop_connection()),
            ):
                try:
                    await coro
                except ConnectionClosed:
                    await self.push_event(
                        LogEvent(message=f"关闭时连接已断开 ({step_name})")
                    )
                except Exception as exc:
                    await self.push_event(
                        LogEvent(message=f"关闭失败 ({step_name}): {exc!r}")
                    )
            await client.close()

        self._s2s = _S2sSession()
        self.state.reset_on_close()

    # ------------------------------------------------------------------
    # D. 后台 loop + S2S 事件 → AdapterState
    # ------------------------------------------------------------------

    async def _mic_loop(self) -> None:
        assert self._s2s.client is not None
        while self._s2s.running:
            if self.state.is_listening:
                try:
                    chunk = await asyncio.wait_for(
                        self.mic_in_queue.get(),
                        timeout=self._frame_sec,
                    )
                except asyncio.TimeoutError:
                    chunk = self._silence_chunk
            else:
                while not self.mic_in_queue.empty():
                    self.mic_in_queue.get_nowait()
                chunk = self._silence_chunk
                await asyncio.sleep(self._frame_sec)
            try:
                await self._s2s.client.send_audio_chunk(chunk)
            except ConnectionClosed:
                # 连接已断，receive_loop 会处理重建标记
                return

    async def _receive_loop(self) -> None:
        assert self._s2s.client is not None
        while self._s2s.running:
            try:
                event = await self._s2s.client.receive_event()
            except ConnectionClosed:
                if self._s2s.running:
                    # 连接异常断开：标记已停，让上层（ensure_framework_session）感知并重建
                    self._s2s.running = False
                    self._log.warning("s2s connection lost, receive_loop exit")
                    await self.push_event(LogEvent(message="S2S 连接已断开，将在下一轮重建"))
                return
            except Exception as exc:
                if self._s2s.running:
                    self._s2s.running = False
                    self._log.warning("s2s receive_loop error: %r", exc)
                    await self.push_event(LogEvent(message=f"S2S 接收异常: {exc!r}"))
                return
            await self._handle_server_event(event)

    async def _handle_server_event(self, event: S2sServerNotify) -> None:
        # 记录所有收到的事件 + 当前 gate/phase 状态
        # 高频事件（TTSResponse/ASRDelta）降级 DEBUG，避免刷屏
        _evt_name = type(event).__name__
        _gate = self.state.inject.gate.name if hasattr(self.state.inject, 'gate') else '?'
        _phase = self.state.phase.name if hasattr(self.state.phase, 'name') else str(self.state.phase)
        _accept = self.state.accept_tts_audio
        if _evt_name in ("ASRDelta", "TTSResponse"):
            self._log.debug("recv=%s phase=%s gate=%s accept_tts=%s", _evt_name, _phase, _gate, _accept)
        else:
            self._log.info("recv=%s phase=%s gate=%s accept_tts=%s", _evt_name, _phase, _gate, _accept)
        match event:
            case SessionStarted():
                pass  # 服务端不发此事件，忽略
            case TTSResponse():
                self._last_tts_recv_monotonic = time.monotonic()
                if self.state.accept_tts_audio:
                    await self._push_bytes(event.payload.data)
                else:
                    self._log.debug("TTSResponse drop %d bytes (accept_tts=False gate=%s)", len(event.payload.data), _gate)
            case TTSSentenceStart():
                _tts_type = event.payload.tts_type or ""
                self._log.info("TTSSentenceStart tts_type=%r inject_mode=%r", _tts_type, self.state.inject.inject_mode)
                self.state.on_tts_sentence_start(_tts_type)
                self._log.info("after on_sentence_start gate=%s", self.state.inject.gate.name)
            case TTSEnded():
                # 守卫用 gate==PASS（注入轨已对齐），不用 accept_tts_audio
                # 否则 default 的 TTSEnded 会被 current_tts_type=default 干扰而 drop，tts_done 卡死
                # 也不能无条件触发，否则上一轮尾巴的 TTSEnded 会提前结束 speak（gate=WAIT_ALIGN 时）
                if self.state.inject.gate.name == "PASS":
                    self.state.on_tts_ended()
                    self._log.info("TTSEnded -> tts_done.set() gate=%s", self.state.inject.gate.name)
                else:
                    self._log.warning("TTSEnded drop (gate=%s, not aligned)", self.state.inject.gate.name)
            case ASRInfo():
                await self._log_asr_started_once()
            case ASRDelta():
                await self._emit_external_asr(event.payload.text, final=False)
            case ASRFinal():
                await self._emit_external_asr(event.payload.text, final=True)
            case ASREnded():
                was_listening = self.state.phase == AdapterPhase.LISTENING
                await self.state.on_asr_ended()
                if was_listening:
                    self.state.prepare_for_external_asr_end()
            case ASR451NoText():
                # 451 原始 dict 无可用文本，静默忽略，勿刷屏
                return
            case _:
                self._log.warning("unhandled event: %s", _evt_name)
                return

    async def _emit_external_asr(self, text: str, *, final: bool) -> None:
        """listening 阶段的外部 ASR：Delta 推实时文本 + 解除 N 秒超时；Final 落库并推完整句。"""
        content = text.strip()
        if not content or not self.state.is_listening:
            return
        await self._log_asr_started_once()
        if final:
            self.state.on_asr_final(content)
            self._log.info("ASR final text=%r", content)
            await self.push_event(AsrFinalEvent(text=content))
        else:
            self.state.note_got_asr(content)
            self._log.debug("ASR delta text=%r", content)
            await self.push_event(AsrDeltaEvent(text=content))

    async def _log_asr_started_once(self) -> None:
        if not self.state.is_listening or self.state.listening_asr_logged:
            return
        self.state.listening_asr_logged = True
        await self.push_event(LogEvent(message="ASR 开始，等待外部回复"))

    async def _push_bytes(self, payload: bytes) -> None:
        await self.audio_out_queue.put(payload)

    async def _wait_audio_out_drained(self, timeout_sec: float = 5.0) -> None:
        """等 PCM 都已交给泵（事件队列不参与，避免被控数消息干扰）。"""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.audio_out_queue.empty():
                await asyncio.sleep(_DRAIN_RECHECK_SEC)
                if self.audio_out_queue.empty():
                    return
            await asyncio.sleep(_DRAIN_LOOP_SEC)

    async def _wait_frontend_playback_drained(self) -> None:
        """S2S 下发完毕后，等浏览器确认 WebAudio 播放队列已播完。"""
        await self._wait_audio_out_drained()
        self._playback_drained = asyncio.Event()
        await self.push_event(AwaitPlaybackDrainEvent(type="await_playback_drain"))
        try:
            await asyncio.wait_for(self._playback_drained.wait(), timeout=_PLAYBACK_DRAIN_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            await self.push_event(
                LogEvent(message="浏览器播放完成确认超时，继续等待外部回复")
            )
        finally:
            self._playback_drained = None
