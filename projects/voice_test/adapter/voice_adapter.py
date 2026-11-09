"""物理语音适配：连接评测框架与扬声器/麦克风/S2S。"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
import uuid

import pyaudio
from rich import print
from rich.text import Text
from websockets.exceptions import ConnectionClosed

from projects.voice_test.adapter.adapter_state import (
    AdapterPhase,
    AdapterState,
    AsrEndedTimeout,
    build_start_session_req,
)
from projects.voice_test.config.adapter_config import adapter_config
from projects.voice_test.core.audio_manager import AudioDeviceManager
from projects.voice_test.config.core_config import input_audio_config, output_audio_config
from projects.voice_test.schemas.events import (
    ASRDelta,
    ASREnded,
    ASRFinal,
    ASRInfo,
    ServerErrorResponse,
    S2sServerNotify,
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


class _AsrLogStyle:
    START = "bold green"
    STREAM = "bright_blue"
    DONE = "bold green"


class AsrEventPrinter:
    def __init__(self, *, show_delta: bool = True) -> None:
        self.show_delta = show_delta

    def __call__(self, event: S2sServerNotify) -> None:
        match event:
            case ASRInfo():
                print(Text("🎙️ ASR 开始", style=_AsrLogStyle.START))
            case ASRDelta():
                if self.show_delta:
                    print(Text(f"  … {event.payload.text}", style=_AsrLogStyle.STREAM))
            case ASRFinal():
                print(Text(f"  ✓ {event.payload.text}", style=_AsrLogStyle.STREAM))
            case ASREnded():
                print(Text("⏹️ ASR 结束", style=_AsrLogStyle.DONE))
            case _:
                return


class PhysicalVoiceAdapter:
    """把「假人 TTS 播报 + 外部设备 ASR」适配成评测框架的一次 achat。"""

    def __init__(self) -> None:
        self.config = adapter_config
        self.state = AdapterState()
        self.client: RealtimeDialogClient | None = None
        self.audio_device: AudioDeviceManager | None = None
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self._asr_printer = (
            AsrEventPrinter(show_delta=self.config.log_asr_delta)
            if self.config.log_asr_events
            else None
        )
        self.lock = asyncio.Lock()
        self.receive_task: asyncio.Task[None] | None = None
        self.mic_task: asyncio.Task[None] | None = None
        self.player_thread: threading.Thread | None = None
        self.running = False

    async def _handle_server_event(self, event: S2sServerNotify) -> None:
        if self._asr_printer is not None:
            self._asr_printer(event)

        if isinstance(event, ServerErrorResponse):
            raise RuntimeError(f"S2S 服务端错误: {event.payload.data}")

        if isinstance(event, TTSResponse):
            if self.state.accept_tts_audio:
                self.audio_queue.put_nowait(event.payload.data)
            return

        if isinstance(event, TTSSentenceStart):
            self.state.on_tts_sentence_start(event.payload.tts_type or "")
            return

        if isinstance(event, TTSEnded):
            if self.state.accept_tts_audio:
                self.state.on_tts_ended()
            return

        if isinstance(event, ASRFinal):
            text = event.payload.text.strip()
            if text:
                self.state.on_asr_final(text)
            return

        if isinstance(event, ASREnded):
            was_listening = self.state.phase == AdapterPhase.LISTENING
            await self.state.on_asr_ended()
            if was_listening:
                self.state.prepare_for_external_asr_end()

    async def start(self) -> None:
        if self.running:
            return

        session_id = (
            f"{self.config.session_id_prefix}-"
            f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        )
        self.client = RealtimeDialogClient(
            options=RealtimeClientOptions(session_id=session_id),
            start_session_req=build_start_session_req(self.config),
        )
        self.audio_device = AudioDeviceManager(input_audio_config, output_audio_config)
        self.audio_device.open_output_stream()
        self.audio_device.open_input_stream()

        await self.client.start()
        self.running = True
        self.state.phase = AdapterPhase.IDLE

        self.player_thread = threading.Thread(target=self._play_audio_loop, daemon=True)
        self.player_thread.start()
        self.receive_task = asyncio.create_task(self._receive_loop())
        self.mic_task = asyncio.create_task(self._mic_loop())
        print("[voice_test] 适配层已启动")

    async def ensure_framework_session(self, session_id: str) -> None:
        if session_id == self.state.framework_session_id:
            await self.start()
            return
        if self.state.framework_session_id:
            print(
                f"[voice_test] session 切换，重建连接: "
                f"{self.state.framework_session_id[:8]}… -> {session_id[:8]}…"
            )
            await self.close()
        self.state.switch_framework_session(session_id)
        await self.start()

    def _play_audio_loop(self) -> None:
        while self.running:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self.audio_device is not None and self.audio_device.output_stream is not None:
                self.audio_device.output_stream.write(chunk)

    async def _mic_loop(self) -> None:
        assert self.audio_device is not None
        assert self.client is not None
        inp = self.audio_device.input_config
        input_stream = self.audio_device.input_stream
        silence = b"\x00" * (
            inp.chunk * inp.channels * pyaudio.get_sample_size(inp.bit_size)
        )
        frame_sec = inp.chunk / inp.sample_rate
        loop = asyncio.get_running_loop()
        while self.running:
            if self.state.is_listening and input_stream is not None:
                chunk = await loop.run_in_executor(
                    None,
                    lambda: input_stream.read(inp.chunk, exception_on_overflow=False),
                )
            else:
                chunk = silence
                await asyncio.sleep(frame_sec)
            await self.client.send_audio_chunk(chunk)

    async def _receive_loop(self) -> None:
        assert self.client is not None
        while self.running:
            try:
                event = await self.client.receive_event()
            except ConnectionClosed:
                if self.running:
                    raise
                return
            await self._handle_server_event(event)

    async def _wait_output_drained(self) -> None:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.audio_queue.empty():
                await asyncio.sleep(0.25)
                return
            await asyncio.sleep(0.05)

    async def speak(self, text: str, *, use_say_hello: bool) -> None:
        assert self.client is not None
        injected_mode = "say_hello" if use_say_hello else "chat_tts_text"
        tts_done = self.state.begin_speaking(injected_mode=injected_mode)
        opts = self.config
        try:
            if use_say_hello:
                # 唤醒词只拼真正首句；同连接后续再 SayHello 不重复拼。
                if not self.state.wake_up_used and opts.wake_up_word:
                    content = f"{opts.wake_up_word}{text}"
                else:
                    content = text
                self.state.wake_up_used = True
                await self.client.send_say_hello(SayHelloRequest(content=content))
            else:
                await self.client.send_chat_tts_text(
                    ChatTtsTextRequest(start=True, end=False, content=text.strip())
                )
                await self.client.send_chat_tts_text(
                    ChatTtsTextRequest(start=False, end=True, content="")
                )
            self.state.on_inject_sent()
            await tts_done.wait()
            await self._wait_output_drained()
        finally:
            self.state.end_speaking()

    async def _wait_external_reply(self) -> tuple[str, bool]:
        """返回 (回复文本, 是否听麦超时)。"""
        self.state.begin_listening()
        print("[等待外部回复]")
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
            self.state.prepare_for_external_asr_end()
            if exc.text.strip():
                print(f"[ASREnded 超时收束] {exc.text}")
                return exc.text, False
            print("[ASREnded 超时] 有 ASR 活动但无可用文本")
            return "（识别未正常结束）", True
        except TimeoutError:
            # 仅「开麦后完全没有任何 ASR」
            self.state.prepare_for_external_asr_end()
            timeout_reply = f"（等了{timeout_sec:g}秒，还没听到他回复）"
            print(f"[外部回复超时] {timeout_reply}")
            return timeout_reply, True
        finally:
            self.state.end_listening()

    async def speak_and_listen(self, text: str, session_id: str) -> str:
        async with self.lock:
            await self.ensure_framework_session(session_id)
            use_say_hello = self.state.use_say_hello
            prepend_wake = use_say_hello and not self.state.wake_up_used
            mode = "SayHello" if use_say_hello else "ChatTTSText"
            if prepend_wake and self.config.wake_up_word:
                print(f"[唤醒词] {self.config.wake_up_word}")
            print(f"[假人朗读/{mode}] {text}")
            self.state.clear_replies()
            await self.speak(text, use_say_hello=use_say_hello)

            if self.config.is_goodbye_query(text):
                print(f"[告别语] 不等待外部回复，返回: {self.config.goodbye_reply}")
                self.state.mark_s2s_ready()
                return self.config.goodbye_reply

            reply, timed_out = await self._wait_external_reply()
            # 尚未立住时听麦超时：保持未 ready，下一句同连接再 SayHello
            if not (use_say_hello and timed_out):
                self.state.mark_s2s_ready()
            print(f"[外部回复] {reply}")
            return reply

    async def _teardown_s2s(self) -> None:
        client = self.client
        self.running = False
        self.state.end_listening()

        # 先停后台循环，避免 stop_connection 的 recv 与 _receive_loop 冲突
        for task in (self.receive_task, self.mic_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self.receive_task, self.mic_task) if task is not None),
            return_exceptions=True,
        )

        if client is not None:
            for step_name, coro in (
                ("stop_session", client.stop_session()),
                ("stop_connection", client.stop_connection()),
            ):
                try:
                    await coro
                except ConnectionClosed as exc:
                    print(f"[voice_test] 关闭时连接已断开 ({step_name}): {exc}")
                except Exception as exc:
                    print(f"[voice_test] 关闭失败 ({step_name}): {exc!r}")
            await client.close()

        self.client = None
        self.receive_task = None
        self.mic_task = None
        self.state.reset_on_close()

    async def release_s2s_after_case(self) -> None:
        """case 对话结束：释放 S2S，保留 PyAudio 供下一 case 使用。"""
        if not self.running and self.client is None:
            return
        print("[voice_test] case 对话结束，释放 S2S 连接")
        await self._teardown_s2s()

    async def close(self) -> None:
        await self._teardown_s2s()
        if self.audio_device is not None:
            self.audio_device.cleanup()
        if self.player_thread is not None and self.player_thread.is_alive():
            self.player_thread.join(timeout=0.5)
        self.audio_device = None
        self.player_thread = None
