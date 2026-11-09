"""Local-device frontend for the provider-independent speech shell."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from aicore.models.stream_model_api.duplex.local_audio import DuplexLocalAudio
from aicore.v2.experiments.duplex_speech_shell.backend import SpeechShellBackend
from aicore.v2.experiments.duplex_speech_shell.events import (
    AsrCompleted,
    AsrDelta,
    AsrFailed,
    AsrStarted,
    SpeechShellClosed,
    SpeechShellError,
    SpeechShellEvent,
    TtsAudioDelta,
    TtsCompleted,
    TtsStarted,
)
from aicore.v2.experiments.duplex_speech_shell.local_audio import (
    send_audio_file,
)
from aicore.v2.experiments.duplex_speech_shell.local_runtime import (
    LocalAgentRuntime,
)
from aicore.v2.experiments.duplex_speech_shell.turn_state import VoiceTurnState

MicMode = Literal["space_gate", "continuous"]


class _MicrophoneGate:
    """Small local gate; closed microphone frames are replaced with silence."""

    def __init__(self, *, is_open: bool) -> None:
        self.is_open = is_open

    def open(self) -> bool:
        if self.is_open:
            return False
        self.is_open = True
        return True

    def close(self) -> bool:
        if not self.is_open:
            return False
        self.is_open = False
        return True


class LocalSpeechShell:
    """Own one local microphone/file speech-shell session and all of its tasks."""

    def __init__(
        self,
        *,
        backend: SpeechShellBackend,
        runtime: LocalAgentRuntime,
        audio: DuplexLocalAudio | Any,
        audio_file: str = "",
        mic_mode: MicMode = "space_gate",
        output_audio_path: Path | str = "output.pcm",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.backend = backend
        self.runtime = runtime
        self.audio = audio
        self.audio_file = audio_file
        self.file_mode = bool(audio_file)
        self.mic_mode = mic_mode
        self.output_audio_path = Path(output_audio_path)
        self.sleep = sleep
        self.state = VoiceTurnState()
        self.microphone_gate = _MicrophoneGate(
            is_open=mic_mode == "continuous"
        )
        self.running = False
        self._started = False
        self._closed = False
        self._shutdown_lock = asyncio.Lock()
        self._finished: asyncio.Future[None] | None = None
        self._terminal_error: BaseException | None = None
        self._shutdown_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._file_task: asyncio.Task[None] | None = None
        self._runner_watch_task: asyncio.Task[None] | None = None
        self._tts_watch_task: asyncio.Task[None] | None = None
        self.audio.input_transform = self._transform_microphone_audio
        self.audio.playback_drained_callback = self.state.playback_ended
        self.runtime.tts_pump.on_generation_finished = (
            self._on_generation_finished
        )

    async def start(self) -> None:
        """Connect and start owned tasks without blocking on session completion."""

        if self._started:
            return
        self._started = True
        self._finished = asyncio.get_running_loop().create_future()
        try:
            if not self.file_mode:
                self.audio.ensure_realtime_audio_supported()
            await self.backend.connect()
            await self.runtime.start()
            runner_task = getattr(self.runtime, "runner_task", None)
            if runner_task is not None:
                self._runner_watch_task = asyncio.create_task(
                    self._watch_owned_task(
                        runner_task,
                        "external Agent runner",
                    ),
                    name="duplex-local-agent-watch",
                )
            tts_task = getattr(self.runtime.tts_pump, "task", None)
            if tts_task is not None:
                self._tts_watch_task = asyncio.create_task(
                    self._watch_owned_task(
                        tts_task,
                        "Agent TTS pump",
                    ),
                    name="duplex-local-tts-watch",
                )
            self.running = True
            if self.file_mode:
                self.state.open_microphone()
            else:
                self.audio.start(asyncio.get_running_loop())
                if self.mic_mode == "continuous":
                    self.state.open_microphone()
            self._receive_task = asyncio.create_task(
                self._receive_loop(),
                name="duplex-local-receive",
            )
            if self.file_mode:
                self._file_task = asyncio.create_task(
                    self._send_audio_file(),
                    name="duplex-local-file-input",
                )
        except BaseException as error:
            self._terminal_error = error
            await self.stop()
            if self._finished is not None:
                self._finished.exception()
            raise

    async def stop(self) -> None:
        """Close resources once in device, pump, backend, Agent-runner order."""

        async with self._shutdown_lock:
            if self._closed:
                return
            self._closed = True
            self.running = False

            cleanup_error: BaseException | None = None

            def run_cleanup(action: Callable[[], None]) -> None:
                nonlocal cleanup_error
                try:
                    action()
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error

            # Device threads must stop before their async sinks are dismantled.
            run_cleanup(self.audio.stop_capture)
            run_cleanup(self.audio.wake_playback)
            run_cleanup(self.audio.join_threads)
            run_cleanup(self.audio.close_devices)

            current = asyncio.current_task()
            tasks = []
            for task in (
                self._file_task,
                self._receive_task,
                self._runner_watch_task,
                self._tts_watch_task,
            ):
                if task is not None and task is not current:
                    if not task.done():
                        task.cancel()
                    tasks.append(task)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._file_task = None
            self._receive_task = None
            self._runner_watch_task = None
            self._tts_watch_task = None

            for cleanup in (
                self.runtime.stop_tts,
                self.backend.close,
                self.runtime.stop_runner,
            ):
                try:
                    await cleanup()
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
            self.state.reset()
            if self.file_mode and self.audio.output_audio:
                try:
                    self.output_audio_path.write_bytes(self.audio.output_audio)
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
            if self._terminal_error is None and cleanup_error is not None:
                self._terminal_error = cleanup_error
            self._complete_finished()

    async def wait_finished(self) -> None:
        if self._finished is None:
            raise RuntimeError("LocalSpeechShell.start() must be called first")
        await asyncio.shield(self._finished)

    def open_microphone(self, *, source: str = "keyboard") -> bool:
        del source
        if self.file_mode or self.mic_mode != "space_gate":
            return False
        if not self.microphone_gate.open():
            return False
        self.runtime.interrupt_speech()
        self.state.interrupt_output()
        self.state.open_microphone()
        self.audio.clear_playback()
        return True

    def on_agent_event(self, event: Any) -> None:
        self.runtime.accept_agent_event(event)

    def _close_microphone_after_user_input(self) -> bool:
        if self.file_mode or self.mic_mode != "space_gate":
            return False
        if not self.microphone_gate.close():
            return False
        self.state.close_microphone()
        return True

    def _transform_microphone_audio(self, data: bytes) -> bytes:
        if self.mic_mode == "continuous" or self.microphone_gate.is_open:
            return data
        return b"\x00" * len(data)

    async def _send_audio_file(self) -> None:
        try:
            await send_audio_file(
                self.backend,
                self.audio_file,
                sleep=self.sleep,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            self._request_finish(error)

    async def _receive_loop(self) -> None:
        try:
            while self.running:
                event = await self.backend.receive_event()
                if isinstance(event, SpeechShellClosed):
                    error = (
                        RuntimeError("Duplex closed before file reply completed")
                        if self.file_mode
                        else None
                    )
                    self._request_finish(error)
                    return
                await self._handle_event(event)
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            self._request_finish(error)

    async def _watch_owned_task(
        self,
        task: asyncio.Task[None],
        label: str,
    ) -> None:
        try:
            await asyncio.shield(task)
            if self.running:
                self._request_finish(RuntimeError(f"{label} stopped unexpectedly"))
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            if self.running:
                self._request_finish(error)

    async def _handle_event(self, event: SpeechShellEvent) -> None:
        if isinstance(event, AsrStarted):
            if self.state.asr_started(self._output_active):
                self.runtime.interrupt_speech()
                self.state.interrupt_output()
                self.audio.clear_playback()
        elif isinstance(event, AsrDelta):
            return
        elif isinstance(event, AsrCompleted):
            self.state.asr_finished()
            if self.file_mode and not event.text.strip():
                self._request_finish(RuntimeError("Duplex returned empty ASR text"))
                return
            await self.runtime.submit_user_text(event.text)
            self._close_microphone_after_user_input()
        elif isinstance(event, AsrFailed):
            self.state.asr_finished()
            self._close_microphone_after_user_input()
            if self.file_mode:
                self._request_finish(
                    RuntimeError(event.message or "Duplex ASR failed")
                )
        elif isinstance(event, TtsStarted):
            self.state.accept_tts_started(
                event.response_id,
                event.tts_type,
                self.runtime.output_active,
            )
        elif isinstance(event, TtsAudioDelta):
            if self.state.accept_tts_audio(event.response_id):
                self.audio.enqueue_playback(event.pcm_s16le)
                self.state.mark_playback_pending()
        elif isinstance(event, TtsCompleted):
            if self.state.complete_tts(event.response_id):
                self.runtime.tts_pump.finish_response()
                if self.file_mode:
                    self._request_finish(None)
                else:
                    self.audio.enqueue_playback_boundary()
        elif isinstance(event, SpeechShellError):
            self._request_finish(RuntimeError(event.message))

    def _on_generation_finished(self) -> None:
        if self.file_mode:
            self._request_finish(None)

    @property
    def _output_active(self) -> bool:
        return bool(
            self.runtime.output_active
            or self.state.accepted_response_ids
            or self.state.playback_pending
        )

    def _request_finish(self, error: BaseException | None) -> None:
        if self._closed or self._shutdown_task is not None:
            return
        self._terminal_error = error
        self._shutdown_task = asyncio.create_task(
            self.stop(),
            name="duplex-local-shutdown",
        )

    def _complete_finished(self) -> None:
        finished = self._finished
        if finished is None or finished.done():
            return
        if self._terminal_error is None:
            finished.set_result(None)
        else:
            finished.set_exception(self._terminal_error)

__all__ = [
    "LocalSpeechShell",
    "MicMode",
]
