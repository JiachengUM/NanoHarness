"""Browser orchestration for the Duplex-backed external-Agent speech shell."""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from array import array
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aicore.v2.experiments.duplex_speech_shell.agent_tts import AgentTtsPump
from aicore.v2.experiments.duplex_speech_shell.backend import (
    RawDuplexClient,
    SpeechShellBackend,
    build_backend_for_client,
    build_default_speech_backend,
)
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
from aicore.v2.experiments.duplex_speech_shell.profile import (
    BROWSER_OUTPUT_FORMAT,
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
)
from aicore.v2.experiments.duplex_speech_shell.turn_state import VoiceTurnState
from aicore.v2.experiments.v2_frontend_utils import maybe_await
from aicore.v2.experiments.v2_frontend_voice import voice_message

logger = logging.getLogger(__name__)

SubmitText = Callable[[str], Awaitable[dict[str, str]] | dict[str, str]]
CommitText = Callable[[dict[str, str]], Awaitable[None] | None]
SendJson = Callable[[dict[str, Any]], Awaitable[None] | None]
SendAudio = Callable[[bytes], Awaitable[None] | None]
SpeechBackendFactory = Callable[[], SpeechShellBackend]
DuplexClientFactory = Callable[[], RawDuplexClient]


def pcm_s16le_to_f32le(payload: bytes) -> bytes:
    """Convert complete little-endian signed PCM16 samples to Float32 PCM."""

    if len(payload) % 2:
        raise ValueError("PCM s16le payload must contain complete 16-bit samples")

    samples = array("h")
    samples.frombytes(payload)
    if sys.byteorder != "little":
        samples.byteswap()
    floats = array("f", (sample / 32768.0 for sample in samples))
    if sys.byteorder != "little":
        floats.byteswap()
    return floats.tobytes()


class BrowserAudioOutput:
    """Convert provider PCM16 and forward browser-compatible Float32 chunks."""

    def __init__(self, send_audio: SendAudio) -> None:
        self.send_audio = send_audio

    async def send_pcm_s16le(self, payload: bytes) -> None:
        await maybe_await(self.send_audio(pcm_s16le_to_f32le(payload)))


class FrontendVoiceBridge:
    """Compose the backend, TTS pump, turn state, and browser callbacks."""

    def __init__(
        self,
        *,
        submit_text: SubmitText,
        commit_text: CommitText | None,
        send_json: SendJson,
        send_audio: SendAudio,
        session_id: Callable[[], str] | str,
        generation: Callable[[], int] | int,
        speech_backend_factory: SpeechBackendFactory | None = None,
        duplex_client_factory: DuplexClientFactory | None = None,
    ) -> None:
        if speech_backend_factory is not None and duplex_client_factory is not None:
            raise ValueError(
                "speech_backend_factory and duplex_client_factory are mutually exclusive"
            )
        if speech_backend_factory is None and duplex_client_factory is not None:
            speech_backend_factory = lambda: build_backend_for_client(
                duplex_client_factory()
            )

        self.submit_text = submit_text
        self.commit_text = commit_text
        self.send_json = send_json
        self.session_id = session_id
        self.generation = generation
        self.speech_backend_factory = (
            speech_backend_factory or build_default_speech_backend
        )
        self.audio_output = BrowserAudioOutput(send_audio)
        self.state = VoiceTurnState()

        self.backend: SpeechShellBackend | None = None
        self.running = False
        self.receive_task: asyncio.Task[None] | None = None
        self._tts_watch_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self.tts_pump: AgentTtsPump | None = None

    @property
    def client(self) -> RawDuplexClient | None:
        backend = self.backend
        return getattr(backend, "client", None) if backend is not None else None

    @property
    def listening(self) -> bool:
        return self.state.listening

    @listening.setter
    def listening(self, value: bool) -> None:
        self.state.listening = value

    @property
    def tts_task(self) -> asyncio.Task[None] | None:
        return self.tts_pump.task if self.tts_pump is not None else None

    def _session_id(self) -> str:
        value = self.session_id() if callable(self.session_id) else self.session_id
        return str(value)

    def _generation(self) -> int:
        value = self.generation() if callable(self.generation) else self.generation
        return int(value)

    async def _send_voice(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await maybe_await(
            self.send_json(
                voice_message(
                    self._session_id(),
                    self._generation(),
                    event_type,
                    payload,
                )
            )
        )

    async def start(self) -> dict[str, Any]:
        async with self._lifecycle_lock:
            ready_payload = {
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE,
                "output_format": BROWSER_OUTPUT_FORMAT,
            }
            if self.running:
                return ready_payload

            backend = self.speech_backend_factory()
            pump = AgentTtsPump(
                backend,
                on_speech_submitted=self._send_speaking_phase,
                on_generation_finished=self._send_resting_phase,
            )
            self.backend = backend
            self.tts_pump = pump
            try:
                await backend.connect()
                self.running = True
                self.state.open_microphone()
                self.receive_task = asyncio.create_task(
                    self._receive_loop(),
                    name="duplex-frontend-receive",
                )
                pump_task = pump.start()
                self._tts_watch_task = asyncio.create_task(
                    self._watch_tts_task(pump_task),
                    name="duplex-frontend-tts-watch",
                )
                await self._send_voice("voice.ready", ready_payload)
                await self._send_resting_phase()
                return ready_payload
            except BaseException:
                await self._shutdown_locked()
                raise

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            await self._shutdown_locked()

    async def _shutdown_locked(self) -> None:
        self.running = False
        self.state.reset()
        receive_task = self.receive_task
        self.receive_task = None
        if receive_task is not None and receive_task is not asyncio.current_task():
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)

        watch_task = self._tts_watch_task
        self._tts_watch_task = None
        if watch_task is not None and watch_task is not asyncio.current_task():
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)

        pump = self.tts_pump
        self.tts_pump = None
        if pump is not None:
            with suppress(Exception):
                await pump.stop()

        backend = self.backend
        self.backend = None
        if backend is not None:
            with suppress(Exception):
                await backend.close()

    async def open_microphone(self) -> None:
        await self.start()
        self.state.open_microphone()
        await self._send_resting_phase()

    async def close_microphone(self) -> None:
        self.state.close_microphone()
        await self._send_resting_phase()

    async def on_playback_ended(self) -> None:
        self.state.playback_ended()
        await self._send_resting_phase()

    async def submit_text_query(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            raise ValueError("Voice text query must not be empty")
        prepared = dict(await maybe_await(self.submit_text(clean)))
        if self.commit_text is None:
            raise RuntimeError("Voice bridge has no commit_text callback")
        await maybe_await(self.commit_text(prepared))

    async def feed_audio(self, chunk: bytes) -> None:
        if not self.running or not self.state.listening or self.backend is None:
            return
        await self.backend.append_audio(chunk)

    def on_agent_event(self, event: Any, *, message_id: str | None = None) -> None:
        pump = self.tts_pump
        if pump is None:
            return
        pump.accept_agent_event(
            str(getattr(event, "type", "") or ""),
            message_id=message_id,
            text=str(getattr(event, "delta", "") or ""),
            user_speaking=self.state.user_speaking,
        )

    async def interrupt_tts_output(self, reason: str) -> None:
        pump = self.tts_pump
        message_id = pump.interrupt() if pump is not None else None
        self.state.interrupt_output()
        payload: dict[str, Any] = {"reason": reason}
        if message_id is not None:
            payload["message_id"] = message_id
        # Interruption is local filtering only. There is intentionally no
        # provider cancel or external-Agent cancellation in this operation.
        await self._send_voice("voice.interrupted", payload)

    async def _receive_loop(self) -> None:
        assert self.backend is not None
        autonomous_shutdown = False
        try:
            while self.running:
                event = await self.backend.receive_event()
                if isinstance(event, SpeechShellClosed):
                    autonomous_shutdown = True
                    break
                await self._handle_speech_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if self.running:
                autonomous_shutdown = True
                logger.exception("[DUPLEX] receive loop failed")
                await self._send_voice(
                    "voice.error",
                    {"message": f"{type(error).__name__}: {error}"},
                )
        finally:
            if autonomous_shutdown:
                await self._shutdown_after_receive()

    async def _handle_speech_event(self, event: SpeechShellEvent) -> None:
        if isinstance(event, AsrStarted):
            await self._handle_asr_started()
        elif isinstance(event, AsrDelta):
            await self._send_voice("voice.asr.delta", {"text": event.text})
        elif isinstance(event, AsrCompleted):
            await self._handle_asr_completed(event.text)
        elif isinstance(event, AsrFailed):
            self.state.asr_finished()
            await self._send_resting_phase()
        elif isinstance(event, TtsStarted):
            self.state.accept_tts_started(
                event.response_id,
                event.tts_type,
                output_active=self._output_active,
            )
        elif isinstance(event, TtsAudioDelta):
            if self.state.accept_tts_audio(event.response_id):
                try:
                    await self.audio_output.send_pcm_s16le(event.pcm_s16le)
                except ValueError:
                    logger.warning("[DUPLEX] invalid output audio payload")
                else:
                    self.state.mark_playback_pending()
        elif isinstance(event, TtsCompleted):
            if self.state.complete_tts(event.response_id):
                if self.tts_pump is not None:
                    self.tts_pump.finish_response()
                await self._send_resting_phase()
        elif isinstance(event, SpeechShellError):
            await self._send_voice("voice.error", {"message": event.message})

    async def _shutdown_after_receive(self) -> None:
        async with self._lifecycle_lock:
            if self.receive_task is asyncio.current_task():
                await self._shutdown_locked()

    async def _watch_tts_task(self, task: asyncio.Task[None]) -> None:
        autonomous_shutdown = False
        try:
            await asyncio.shield(task)
            autonomous_shutdown = self.running
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if self.running:
                autonomous_shutdown = True
                logger.exception("[DUPLEX] TTS loop failed")
                await self._send_voice(
                    "voice.error",
                    {"message": f"{type(error).__name__}: {error}"},
                )
        finally:
            if autonomous_shutdown:
                await self._shutdown_after_tts()

    async def _shutdown_after_tts(self) -> None:
        async with self._lifecycle_lock:
            if self._tts_watch_task is asyncio.current_task():
                await self._shutdown_locked()

    async def _handle_asr_started(self) -> None:
        if not self.state.listening:
            return
        logger.warning("[DUPLEX ASR] started")
        if self.state.asr_started(output_active=self._output_active):
            await self.interrupt_tts_output(reason="barge_in")
        await self._send_resting_phase()

    async def _handle_asr_completed(self, text: str) -> None:
        logger.warning("[DUPLEX ASR] completed text=%s", text)
        if not text:
            self.state.asr_finished()
            await self._send_resting_phase()
            return

        if self.state.should_interrupt_for_final(output_active=self._output_active):
            await self.interrupt_tts_output(reason="barge_in")
        self.state.asr_finished()
        prepared = dict(await maybe_await(self.submit_text(text)))
        turn_id = prepared.get("turn_id") or f"voice-turn-{uuid.uuid4().hex}"
        await self._send_voice(
            "voice.asr.final",
            {
                "turn_id": turn_id,
                "user_message_id": prepared.get("user_message_id"),
                "assistant_message_id": prepared.get("assistant_message_id"),
                "text": text,
            },
        )
        if self.commit_text is None:
            raise RuntimeError("Voice bridge has no commit_text callback")
        prepared["text"] = text
        await self._send_voice("voice.phase", {"phase": "processing"})
        await maybe_await(self.commit_text(prepared))

    @property
    def _output_active(self) -> bool:
        return bool(
            (self.tts_pump is not None and self.tts_pump.active)
            or self.state.playback_pending
            or self.state.accepted_response_ids
        )

    async def _send_resting_phase(self) -> None:
        await self._send_voice(
            "voice.phase",
            {"phase": "listening" if self.state.listening else "idle"},
        )

    async def _send_speaking_phase(self) -> None:
        if self.running:
            await self._send_voice("voice.phase", {"phase": "speaking"})


DuplexFrontendVoiceBridge = FrontendVoiceBridge

__all__ = [
    "BrowserAudioOutput",
    "DuplexFrontendVoiceBridge",
    "FrontendVoiceBridge",
    "pcm_s16le_to_f32le",
]
