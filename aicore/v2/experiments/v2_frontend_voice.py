from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from projects.voice_test.adapter.adapter_state import build_start_session_req
from projects.voice_test.config.adapter_config import adapter_config
from projects.voice_test.config.core_config import input_audio_config, output_audio_config
from projects.voice_test.schemas.events import (
    ASRDelta,
    ASREnded,
    ASRFinal,
    ASRInfo,
    ServerErrorResponse,
    TTSSentenceStart,
    TTSEnded,
    TTSResponse,
)
from projects.voice_test.core.realtime_dialog_client import (
    ChatTextQueryRequest,
    ChatTtsTextRequest,
    RealtimeClientOptions,
    RealtimeDialogClient,
)

from aicore.v2.experiments.v2_frontend_utils import maybe_await
from aicore.v2.experiments.latency_trace import trace_latency

logger = logging.getLogger(__name__)

SendJson = Callable[[dict[str, Any]], Awaitable[None] | None]
SendAudio = Callable[[bytes], Awaitable[None] | None]
SubmitText = Callable[[str], Awaitable[dict[str, Any]] | dict[str, Any]]
CommitText = Callable[[dict[str, Any]], Awaitable[None] | None]

V2_VOICE_VAD_TIMEOUT_MS = 900
V2_VOICE_CLIENT_SHUTDOWN_TIMEOUT_SECONDS = 1.0

def voice_message(
    session_id: str,
    generation: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "v": 1,
        "kind": "voice",
        "session_id": session_id,
        "generation": generation,
        "type": event_type,
        "payload": payload or {},
    }


class FrontendVoiceBridge:
    def __init__(
        self,
        *,
        submit_text: SubmitText,
        send_json: SendJson,
        send_audio: SendAudio,
        session_id: Callable[[], str] | str,
        generation: Callable[[], int] | int,
        realtime_client_factory: Callable[[str], Any] | None = None,
        commit_text: CommitText | None = None,
    ) -> None:
        self.submit_text = submit_text
        self.commit_text = commit_text
        self.send_json = send_json
        self.send_audio = send_audio
        self.session_id = session_id
        self.generation = generation
        self.realtime_client_factory = (
            realtime_client_factory or self._default_client_factory
        )
        self._lifecycle_lock = asyncio.Lock()

        self.client: Any | None = None
        self.receive_task: asyncio.Task[None] | None = None
        self.mic_task: asyncio.Task[None] | None = None
        self._tts_task: asyncio.Task[None] | None = None
        self._tts_send_lock = asyncio.Lock()
        self._tts_text_stream_open = False
        self.running = False
        self.listening = False
        self._speech_generation = 0
        self._active_tts_generation = 0
        self._active_tts_message_id: str | None = None
        self._interrupted_message_ids: set[str] = set()
        self._traced_tts_message_ids: set[str] = set()
        self._tts_audio_generation = 0
        self._accept_chat_tts_audio = False
        self._pending_server_tts_generations: deque[int] = deque()
        self._registered_server_tts_generations: set[int] = set()
        self._server_tts_identifier_generations: dict[tuple[str, str], int] = {}
        self._anonymous_server_tts_generation: int | None = None
        self._server_tts_span_generation: int | None = None
        self._abandoned_server_tts_generations: set[int] = set()
        self._server_tts_end_order: deque[int] = deque()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._tts_text_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._latest_final_text = ""
        self._latest_delta_text = ""
        self._pending_playback_duck = False
        self._barge_in_confirmed = False
        self._frontend_playback_pending = False

        self._silence_chunk = b"\x00" * (
            input_audio_config.chunk * input_audio_config.channels * 2
        )
        self._frame_sec = input_audio_config.chunk / input_audio_config.sample_rate

    def _default_client_factory(self, s2s_session_id: str) -> RealtimeDialogClient:
        v2_adapter_config = adapter_config.model_copy(
            update={"vad_timeout_ms": V2_VOICE_VAD_TIMEOUT_MS}
        )
        return RealtimeDialogClient(
            options=RealtimeClientOptions(session_id=s2s_session_id),
            start_session_req=build_start_session_req(v2_adapter_config),
        )

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

    async def on_playback_ended(self) -> None:
        self._frontend_playback_pending = False
        await self._send_voice(
            "voice.phase",
            {"phase": "listening" if self.listening else "idle"},
        )

    async def start(self) -> dict[str, Any]:
        async with self._lifecycle_lock:
            return await self._start_runtime_locked()

    async def _start_runtime_locked(self) -> dict[str, Any]:
        ready_payload = {
            "input_sample_rate": input_audio_config.sample_rate,
            "output_sample_rate": output_audio_config.sample_rate,
            "output_format": "f32le",
        }
        if self.running:
            return ready_payload

        s2s_session_id = (
            f"{adapter_config.session_id_prefix}-"
            f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        )
        self.client = self.realtime_client_factory(s2s_session_id)
        try:
            await self.client.start()
            self.running = True
            self.receive_task = asyncio.create_task(self._receive_loop())
            self.mic_task = asyncio.create_task(self._mic_loop())
            self._tts_task = asyncio.create_task(self._tts_loop())
            await self._send_voice("voice.ready", ready_payload)
            return ready_payload
        except asyncio.CancelledError:
            cleanup_task = asyncio.create_task(
                self._shutdown_runtime_locked(close_client=True, reset_queues=True),
                name="voice-start-cleanup",
            )
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    continue
            cleanup_task.result()
            raise
        except Exception:
            await self._shutdown_runtime_locked(close_client=True, reset_queues=True)
            raise

    async def submit_text_query(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            raise ValueError("Voice text query must not be empty")

        await self.start()
        assert self.client is not None
        await self.client.send_chat_text(ChatTextQueryRequest(content=clean))

    async def open_microphone(self) -> None:
        await self.start()
        await self._restore_pending_playback()
        self.listening = True
        self._clear_asr_buffers()
        self._barge_in_confirmed = False
        await self._send_voice("voice.phase", {"phase": "listening"})

    async def close_microphone(self) -> None:
        self.listening = False
        await self._restore_pending_playback()
        await self._send_voice("voice.phase", {"phase": "idle"})

    async def feed_audio(self, chunk: bytes) -> None:
        if not self.running or not self.listening:
            return
        await self._audio_queue.put(chunk)

    async def _mic_loop(self) -> None:
        assert self.client is not None
        try:
            while self.running:
                if self.listening:
                    try:
                        chunk = await asyncio.wait_for(
                            self._audio_queue.get(),
                            timeout=self._frame_sec,
                        )
                    except asyncio.TimeoutError:
                        chunk = self._silence_chunk
                else:
                    while not self._audio_queue.empty():
                        with suppress(asyncio.QueueEmpty):
                            self._audio_queue.get_nowait()
                    chunk = self._silence_chunk
                    await asyncio.sleep(self._frame_sec)

                await self.client.send_audio_chunk(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._handle_background_error(error)

    async def _receive_loop(self) -> None:
        assert self.client is not None
        try:
            while self.running:
                event = await self.client.receive_event()
                await self._handle_server_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._handle_background_error(error)

    async def _tts_loop(self) -> None:
        assert self.client is not None
        sent_any = False
        loop_generation = 0
        try:
            while self.running:
                part = await self._tts_text_queue.get()
                if part is None:
                    if sent_any:
                        await self._close_tts_text_stream()
                        sent_any = False
                    continue

                if not part:
                    continue

                active_generation = self._active_tts_generation
                active_message_id = self._active_tts_message_id
                if (
                    active_generation == 0
                    or active_generation != self._speech_generation
                ):
                    continue

                if loop_generation != active_generation:
                    if self._tts_text_stream_open:
                        await self._close_tts_text_stream()
                    loop_generation = active_generation
                    sent_any = False
                    await self._send_voice("voice.phase", {"phase": "speaking"})

                if (
                    active_generation != self._active_tts_generation
                    or active_generation != self._speech_generation
                    or active_message_id != self._active_tts_message_id
                ):
                    sent_any = False
                    continue

                first_part = not sent_any
                if first_part:
                    self._register_server_tts_generation(active_generation)
                async with self._tts_send_lock:
                    if (
                        active_generation != self._active_tts_generation
                        or active_generation != self._speech_generation
                        or active_message_id != self._active_tts_message_id
                    ):
                        sent_any = False
                        continue
                    await self.client.send_chat_tts_text(
                        ChatTtsTextRequest(
                            start=first_part,
                            end=False,
                            content=part,
                        )
                    )
                    self._tts_text_stream_open = True
                sent_any = True
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._handle_background_error(error)

    async def _handle_background_error(self, error: Exception) -> None:
        if not self.running:
            return
        with suppress(Exception):
            await self._send_voice(
                "voice.error",
                {"message": f"{type(error).__name__}: {error}"},
            )
        await self._shutdown_runtime(close_client=True, reset_queues=True)

    async def _handle_server_event(self, event: Any) -> None:
        if isinstance(event, ServerErrorResponse):
            payload = getattr(event, "payload", None)
            message = getattr(payload, "message", None) or getattr(
                payload, "data", None
            )
            await self._send_voice(
                "voice.error", {"message": str(message or "S2S error")}
            )
            await self._shutdown_runtime(close_client=True, reset_queues=True)
            return

        if isinstance(event, ASRInfo):
            if (
                self._frontend_playback_pending
                or self._active_tts_generation != 0
                or self._active_tts_message_id is not None
            ):
                self._pending_playback_duck = False
                self._barge_in_confirmed = True
                await self.interrupt_tts_output(reason="barge_in")
                return
            if not self._pending_playback_duck and not self._barge_in_confirmed:
                self._pending_playback_duck = True
                await self._send_voice("voice.playback.duck")
            return

        if isinstance(event, ASRDelta):
            text = event.payload.text.strip()
            if text:
                self._latest_delta_text = text
                await self._confirm_barge_in()
                await self._send_voice("voice.asr.delta", {"text": text})
            return

        if isinstance(event, ASRFinal):
            text = event.payload.text.strip()
            if text:
                await self._confirm_barge_in()
                self._latest_final_text = text
            return

        if isinstance(event, ASREnded):
            await self._submit_asr_if_ready()
            return

        if isinstance(event, TTSResponse):
            await self.forward_tts_audio(
                event.payload.data,
                generation=self._tts_audio_generation,
            )
            return

        if isinstance(event, TTSSentenceStart):
            self._handle_tts_sentence_start(event)
            return

        if isinstance(event, TTSEnded):
            await self._handle_tts_ended(event)

    def _clear_asr_buffers(self) -> None:
        self._latest_final_text = ""
        self._latest_delta_text = ""

    async def _submit_asr_if_ready(self) -> None:
        text = (self._latest_final_text or self._latest_delta_text).strip()
        self._clear_asr_buffers()

        if not text:
            await self._restore_pending_playback()
            self._barge_in_confirmed = False
            await self._send_voice("voice.phase", {"phase": "listening"})
            return

        self._barge_in_confirmed = False
        self._pending_playback_duck = False
        submitted = await maybe_await(self.submit_text(text))
        submitted_payload = dict(submitted or {})
        payload = {
            "turn_id": submitted_payload.get("turn_id")
            or f"voice-turn-{uuid.uuid4().hex}",
            "user_message_id": submitted_payload.get("user_message_id"),
            "assistant_message_id": submitted_payload.get("assistant_message_id"),
            "text": text,
        }
        await self._send_voice("voice.asr.final", payload)
        await self._send_voice("voice.phase", {"phase": "processing"})
        if self.commit_text is None:
            return
        try:
            await maybe_await(self.commit_text(payload))
        except Exception:
            await self._send_voice(
                "voice.submit.failed",
                {
                    "turn_id": payload["turn_id"],
                    "user_message_id": payload["user_message_id"],
                    "assistant_message_id": payload["assistant_message_id"],
                    "code": "AGENT_SUBMIT_FAILED",
                },
            )
            await self._send_voice("voice.phase", {"phase": "listening"})

    async def _confirm_barge_in(self) -> None:
        if not self._pending_playback_duck:
            return
        self._pending_playback_duck = False
        self._barge_in_confirmed = True
        await self.interrupt_tts_output(reason="barge_in")

    async def _restore_pending_playback(self) -> None:
        if not self._pending_playback_duck:
            return
        self._pending_playback_duck = False
        await self._send_voice("voice.playback.restore")

    def _consume_task_exception(self, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is None:
            return
        logger.warning(
            "Voice background task failed: task=%s exception_type=%s",
            "voice-background",
            type(error).__name__,
        )

    async def interrupt_tts_output(self, reason: str = "microphone_opened") -> None:
        interrupted_message_id = self._active_tts_message_id
        interrupted_generation = self._active_tts_generation
        if interrupted_message_id is not None:
            self._interrupted_message_ids.add(interrupted_message_id)
        self._clear_tts_text_queue()
        self._speech_generation += 1
        self._active_tts_generation = 0
        self._active_tts_message_id = None
        self._tts_audio_generation = 0
        self._accept_chat_tts_audio = False
        self._frontend_playback_pending = False
        self._abandon_server_tts_generation(interrupted_generation)
        await self._close_tts_text_stream()
        payload: dict[str, Any] = {"reason": reason}
        if interrupted_message_id is not None:
            payload["message_id"] = interrupted_message_id
        trace_latency(
            "voice.interrupted",
            message_id=interrupted_message_id,
            session_id=self._session_id(),
            generation=self._generation(),
        )
        await self._send_voice(
            "voice.interrupted",
            payload,
        )

    async def _close_tts_text_stream(self) -> None:
        client = self.client
        if client is None:
            self._tts_text_stream_open = False
            return
        async with self._tts_send_lock:
            if not self._tts_text_stream_open:
                return
            try:
                await client.send_chat_tts_text(
                    ChatTtsTextRequest(start=False, end=True, content="")
                )
            finally:
                self._tts_text_stream_open = False

    async def forward_tts_audio(self, payload: bytes, *, generation: int) -> None:
        if generation == 0:
            return
        if not self._accept_chat_tts_audio:
            return
        if generation != self._tts_audio_generation:
            return
        if generation != self._speech_generation:
            return
        await maybe_await(self.send_audio(payload))
        self._frontend_playback_pending = True

    def _register_server_tts_generation(self, generation: int) -> None:
        if generation == 0 or generation in self._registered_server_tts_generations:
            return
        for registered_generation in tuple(
            self._registered_server_tts_generations
        ):
            if (
                registered_generation != generation
                and registered_generation
                not in self._abandoned_server_tts_generations
            ):
                self._retire_unbound_server_tts_generation(registered_generation)
        self._registered_server_tts_generations.add(generation)
        self._pending_server_tts_generations.append(generation)

    def _claim_pending_server_tts_generation(self) -> int:
        while self._pending_server_tts_generations:
            generation = self._pending_server_tts_generations.popleft()
            if generation in self._registered_server_tts_generations:
                return generation
        return 0

    def _retire_unbound_server_tts_generation(self, generation: int) -> None:
        if (
            generation == 0
            or generation not in self._registered_server_tts_generations
            or generation in self._abandoned_server_tts_generations
        ):
            return
        if generation == self._server_tts_span_generation:
            return
        if generation == self._anonymous_server_tts_generation:
            return
        if generation in self._server_tts_identifier_generations.values():
            return
        self._registered_server_tts_generations.discard(generation)
        self._pending_server_tts_generations = deque(
            pending_generation
            for pending_generation in self._pending_server_tts_generations
            if pending_generation != generation
        )

    def _clear_server_tts_generation(self, generation: int) -> None:
        if generation == 0:
            return
        self._registered_server_tts_generations.discard(generation)
        self._server_tts_identifier_generations = {
            identifier: mapped_generation
            for identifier, mapped_generation in (
                self._server_tts_identifier_generations.items()
            )
            if mapped_generation != generation
        }
        self._pending_server_tts_generations = deque(
            pending_generation
            for pending_generation in self._pending_server_tts_generations
            if pending_generation != generation
        )
        self._server_tts_end_order = deque(
            started_generation
            for started_generation in self._server_tts_end_order
            if started_generation != generation
        )
        self._abandoned_server_tts_generations.discard(generation)

    def _abandon_server_tts_generation(self, generation: int) -> None:
        if generation == 0:
            return
        if (
            generation in self._registered_server_tts_generations
            or generation == self._server_tts_span_generation
        ):
            self._abandoned_server_tts_generations.add(generation)
        if self._tts_audio_generation == generation:
            self._tts_audio_generation = 0
            self._accept_chat_tts_audio = False

    def _bind_server_tts_identifiers(
        self,
        generation: int,
        identifiers: frozenset[tuple[str, str]],
    ) -> None:
        bound_names = {
            name
            for (name, _), mapped_generation in (
                self._server_tts_identifier_generations.items()
            )
            if mapped_generation == generation
        }
        for identifier in sorted(identifiers):
            name, _ = identifier
            if name in bound_names:
                continue
            self._server_tts_identifier_generations[identifier] = generation
            bound_names.add(name)

    @staticmethod
    def _server_tts_identifiers(payload: Any) -> frozenset[tuple[str, str]]:
        identifiers: set[tuple[str, str]] = set()
        for name in ("tts_task_id", "reply_id", "question_id"):
            value = getattr(payload, name, None)
            if value:
                identifiers.add((name, str(value)))
        extra = getattr(payload, "extra", None)
        if isinstance(extra, dict):
            for name in ("tts_task_id", "reply_id", "question_id"):
                value = extra.get(name)
                if value:
                    identifiers.add((name, str(value)))
        return frozenset(identifiers)

    def _handle_tts_sentence_start(self, event: TTSSentenceStart) -> None:
        if event.payload.tts_type != "chat_tts_text":
            self._tts_audio_generation = 0
            self._accept_chat_tts_audio = False
            return

        identifiers = self._server_tts_identifiers(event.payload)
        current_span_generation = self._server_tts_span_generation
        current_span_abandoned = (
            current_span_generation in self._abandoned_server_tts_generations
        )
        generation = 0
        if identifiers:
            known_generations = {
                self._server_tts_identifier_generations[identifier]
                for identifier in identifiers
                if identifier in self._server_tts_identifier_generations
            }
            if known_generations:
                generation = min(known_generations)
            elif current_span_generation is None or current_span_abandoned:
                generation = self._claim_pending_server_tts_generation()
            if generation:
                self._bind_server_tts_identifiers(generation, identifiers)
        else:
            if current_span_generation is None or current_span_abandoned:
                claimed = self._claim_pending_server_tts_generation()
                generation = claimed or current_span_generation or 0
            else:
                generation = current_span_generation
            self._anonymous_server_tts_generation = generation or None

        if generation and generation not in self._server_tts_end_order:
            self._server_tts_end_order.append(generation)
        if current_span_generation is None and generation:
            self._server_tts_span_generation = generation
        elif (
            current_span_abandoned
            and generation
            and generation not in self._abandoned_server_tts_generations
        ):
            self._server_tts_span_generation = generation
        effective_generation = self._server_tts_span_generation or 0

        self._tts_audio_generation = effective_generation
        self._accept_chat_tts_audio = (
            generation != 0
            and generation not in self._abandoned_server_tts_generations
            and generation == effective_generation
            and effective_generation == self._active_tts_generation
            and effective_generation == self._speech_generation
        )

    async def _handle_tts_ended(self, event: TTSEnded) -> None:
        identifiers = self._server_tts_identifiers(event.payload)
        ended_generation = 0
        if identifiers:
            known_generations = {
                self._server_tts_identifier_generations[identifier]
                for identifier in identifiers
                if identifier in self._server_tts_identifier_generations
            }
            if known_generations:
                ended_generation = min(known_generations)
        else:
            while self._server_tts_end_order:
                ended_generation = self._server_tts_end_order.popleft()
                if ended_generation:
                    break
            if ended_generation == 0:
                ended_generation = (
                    self._anonymous_server_tts_generation
                    or self._server_tts_span_generation
                    or 0
                )

        if ended_generation == 0:
            return

        ends_current_span = (
            ended_generation != 0
            and ended_generation == self._server_tts_span_generation
        )
        self._clear_server_tts_generation(ended_generation)
        if ended_generation == self._anonymous_server_tts_generation:
            self._anonymous_server_tts_generation = None
        if ends_current_span:
            self._server_tts_span_generation = None
            self._tts_audio_generation = 0
            self._accept_chat_tts_audio = False
        if ended_generation != self._active_tts_generation:
            return

        await self._send_voice(
            "voice.phase",
            {"phase": "listening" if self.listening else "idle"},
        )
        if self._active_tts_generation != ended_generation:
            return
        self._active_tts_message_id = None
        self._active_tts_generation = 0

    async def stop(self) -> None:
        await self._shutdown_runtime(close_client=True, reset_queues=True)

    async def _shutdown_runtime(
        self, *, close_client: bool, reset_queues: bool
    ) -> None:
        async with self._lifecycle_lock:
            await self._shutdown_runtime_locked(
                close_client=close_client,
                reset_queues=reset_queues,
            )

    async def _shutdown_runtime_locked(
        self, *, close_client: bool, reset_queues: bool
    ) -> None:
        client = self.client
        self.running = False
        self.listening = False
        self._active_tts_generation = 0
        self._active_tts_message_id = None
        self._tts_text_stream_open = False
        self._interrupted_message_ids.clear()
        self._traced_tts_message_ids.clear()
        self._tts_audio_generation = 0
        self._accept_chat_tts_audio = False
        self._pending_server_tts_generations.clear()
        self._registered_server_tts_generations.clear()
        self._server_tts_identifier_generations.clear()
        self._anonymous_server_tts_generation = None
        self._server_tts_span_generation = None
        self._abandoned_server_tts_generations.clear()
        self._server_tts_end_order.clear()
        self._pending_playback_duck = False
        self._barge_in_confirmed = False
        self._frontend_playback_pending = False
        self._clear_asr_buffers()

        current_task = asyncio.current_task()
        tasks = list(
            dict.fromkeys(
                task
                for task in (
                    self.receive_task,
                    self.mic_task,
                    self._tts_task,
                )
                if task is not None and task is not current_task
            )
        )
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if close_client and client is not None:
            await self._run_client_shutdown_stage(
                "stop_session",
                client.stop_session,
            )
            await self._run_client_shutdown_stage(
                "stop_connection",
                client.stop_connection,
            )
            await self._run_client_shutdown_stage(
                "close",
                client.close,
            )

        self.receive_task = None
        self.mic_task = None
        self._tts_task = None
        self.client = None
        if reset_queues:
            self._audio_queue = asyncio.Queue()
            self._tts_text_queue = asyncio.Queue()

    async def _run_client_shutdown_stage(
        self,
        stage: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> None:
        stage_task = asyncio.create_task(
            operation(),
            name=f"voice-client-{stage}",
        )
        try:
            done, _ = await asyncio.wait(
                {stage_task},
                timeout=V2_VOICE_CLIENT_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            stage_task.cancel()
            stage_task.add_done_callback(self._consume_task_exception)
            raise
        if stage_task not in done:
            stage_task.cancel()
            stage_task.add_done_callback(self._consume_task_exception)
            logger.warning(
                "Voice client shutdown stage failed: stage=%s exception_type=%s",
                stage,
                "TimeoutError",
            )
            return
        if stage_task.cancelled():
            return
        error = stage_task.exception()
        if error is not None:
            logger.warning(
                "Voice client shutdown stage failed: stage=%s exception_type=%s",
                stage,
                type(error).__name__,
            )

    def on_agent_event(self, event: Any, *, message_id: str | None) -> None:
        event_type = str(
            getattr(event, "type", None) or getattr(event, "name", None) or ""
        )

        if event_type not in {
            "agent.out.text.start",
            "agent.out.text.delta",
            "agent.out.text.done",
        }:
            return
        if not message_id:
            logger.warning(
                "Dropping agent text event without message_id: %s", event_type
            )
            return
        if message_id in self._interrupted_message_ids:
            return

        if event_type == "agent.out.text.start":
            self._active_tts_message_id = message_id
            self._begin_tts_generation()
            return

        if event_type == "agent.out.text.delta":
            text = self._agent_text_delta(event)
            if text:
                if message_id not in self._traced_tts_message_ids:
                    self._traced_tts_message_ids.add(message_id)
                    trace_latency(
                        "tts.text.first",
                        message_id=message_id,
                        session_id=self._session_id(),
                        generation=self._generation(),
                    )
                if (
                    self._active_tts_generation == 0
                    or self._active_tts_message_id != message_id
                ):
                    self._active_tts_message_id = message_id
                    self._begin_tts_generation()
                self._tts_text_queue.put_nowait(text)
            return

        if (
            event_type == "agent.out.text.done"
            and self._active_tts_message_id == message_id
        ):
            self._tts_text_queue.put_nowait(None)

    def _agent_text_delta(self, event: Any) -> str:
        value = getattr(event, "delta", None)
        if value is None:
            payload = getattr(event, "payload", None)
            value = (
                getattr(payload, "delta", None)
                or getattr(payload, "text", None)
                or getattr(payload, "content", None)
            )
        return str(value or "")

    def _begin_tts_generation(self) -> None:
        self._clear_tts_text_queue()
        self._speech_generation += 1
        self._active_tts_generation = self._speech_generation

    def _clear_tts_text_queue(self) -> None:
        while not self._tts_text_queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._tts_text_queue.get_nowait()
