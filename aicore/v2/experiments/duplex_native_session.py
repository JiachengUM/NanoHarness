"""Browser-facing AsyncSession adapter for the Duplex-native Agent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from aicore.events.agent import (
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.events.task import (
    TaskEvent,
)
from aicore.models.stream_model_api import (
    StreamAudioDeltaEvent,
    StreamAudioDoneEvent,
    StreamAudioStartEvent,
    StreamModelEvent,
    StreamTextDeltaEvent,
    StreamTextDoneEvent,
    StreamTextStartEvent,
    StreamTranscriptionDeltaEvent,
    StreamTranscriptionDoneEvent,
    StreamTranscriptionStartEvent,
)
from aicore.models.stream_model_api.duplex import (
    BrowserDuplexMediaPort,
    DuplexAgentSession,
)
from aicore.models.stream_model_api.duplex.async_backfill import BackfillActivation
from aicore.runtime.task import TaskManager
from aicore.session import (
    SessionOutput,
)
from aicore.v2.experiments.duplex_speech_shell.frontend_bridge import (
    pcm_s16le_to_f32le,
)


@dataclass(frozen=True, slots=True)
class NativeVoiceEvent:
    event_type: str
    payload: dict[str, Any]


NativeOutputListener = Callable[[SessionOutput], Awaitable[None] | None]
NativeAgentSessionFactory = Callable[..., DuplexAgentSession]
logger = logging.getLogger("uvicorn.error")


class DuplexNativeSession:
    """Own one Duplex-native provider, tool runtime, and browser media port."""

    def __init__(
        self,
        *,
        session_id: str,
        agent_session_factory: NativeAgentSessionFactory,
        output_listener: NativeOutputListener | None = None,
    ) -> None:
        self._id = session_id
        self.task_manager = TaskManager(max_concurrency=10)
        self.media_port = BrowserDuplexMediaPort()
        self.output_listener = output_listener
        self._question_turns: dict[str, str] = {}
        self._pending_activation: BackfillActivation | None = None
        self._active_output_run_id: str | None = None
        self._active_conversation_turn_id: str | None = None
        self._active_triggering_task_ids: tuple[str, ...] = ()
        self._current_turn_id: str | None = None
        self._text_stream_open = False
        self._listening = False
        self._closed = False
        self._start_lock = asyncio.Lock()
        self.run_task: asyncio.Task[None] | None = None
        self.agent_session = agent_session_factory(
            media_port=self.media_port,
            model_event_observer=self._observe_model_event,
            task_event_observer=self._observe_task_event,
            backfill_activation_observer=self._observe_backfill_activation,
            task_manager=self.task_manager,
        )

    @property
    def id(self) -> str:
        return self._id

    @property
    def restart_required(self) -> bool:
        return self._closed or (
            self.run_task is not None and self.run_task.done()
        )

    async def start(self) -> dict[str, Any]:
        async with self._start_lock:
            if self._closed:
                raise RuntimeError("Duplex native session is closed")
            if self.run_task is not None and self.run_task.done():
                if self.run_task.cancelled():
                    raise RuntimeError("Duplex native session ended")
                error = self.run_task.exception()
                if error is not None:
                    raise RuntimeError("Duplex native session ended") from error
                raise RuntimeError("Duplex native session ended")
            if self.run_task is None:
                await self.agent_session.model_api.start()
                self.run_task = asyncio.create_task(
                    self.agent_session.run(),
                    name=f"duplex-native-{self.id}",
                )
        self._listening = True
        return {
            "input_sample_rate": 16000,
            "output_sample_rate": 24000,
            "output_format": "f32le",
        }

    async def stop(self) -> None:
        await self.close()

    async def open_microphone(self) -> None:
        await self.start()
        self._listening = True
        await self._publish_voice("voice.phase", {"phase": "listening"})

    async def close_microphone(self) -> None:
        self._listening = False
        await self._publish_voice("voice.phase", {"phase": "idle"})

    async def feed_audio(self, chunk: bytes) -> None:
        if self._listening and not self._closed:
            await self.agent_session.submit_audio_chunk(chunk)

    async def on_playback_ended(self) -> None:
        if self.media_port.playback_ended():
            await self._publish_voice(
                "voice.phase",
                {"phase": "listening" if self._listening else "idle"},
            )

    async def _observe_model_event(self, event: StreamModelEvent) -> None:
        if (
            isinstance(
                event,
                (
                    StreamTranscriptionStartEvent,
                    StreamTranscriptionDeltaEvent,
                    StreamTranscriptionDoneEvent,
                ),
            )
            and self.agent_session.is_synthetic_transcription_pending()
        ):
            # The async-backfill trigger audio owns the ASR lane right now.
            # Its transcription is an internal activation signal, not a user
            # turn; it must not create history turns or browser ASR output.
            return
        turn_id = self._resolve_turn(event)
        if isinstance(event, StreamTranscriptionStartEvent):
            if self.media_port.realtime_playback_active:
                cancel_sent = await self.agent_session.interrupt_response()
                if cancel_sent:
                    logger.info(
                        "[DUPLEX NATIVE] response_cancel.sent turn_id=%s",
                        turn_id,
                    )
                else:
                    logger.info(
                        "[DUPLEX NATIVE] playback.cleared "
                        "turn_id=%s provider_response_active=false",
                        turn_id,
                    )
                await self._publish_voice(
                    "voice.interrupted",
                    {"reason": "barge_in"},
                    turn_id,
                )
            await self._publish_voice("voice.phase", {"phase": "listening"}, turn_id)
        elif isinstance(event, StreamTranscriptionDeltaEvent):
            await self._publish_voice("voice.asr.delta", {"text": event.delta}, turn_id)
        elif isinstance(event, StreamTranscriptionDoneEvent):
            await self._publish_voice(
                "voice.asr.final",
                {
                    "turn_id": turn_id,
                    "user_message_id": f"native-user-{turn_id}",
                    "assistant_message_id": f"native-assistant-{turn_id}",
                    "text": event.transcript,
                },
                turn_id,
            )
            await self._publish_voice("voice.phase", {"phase": "processing"}, turn_id)
        elif isinstance(event, StreamTextStartEvent):
            self._start_output_run(event, turn_id)
            self._text_stream_open = True
            await self._publish_event(AgentOutTextStartEvent(), turn_id)
        elif isinstance(event, StreamTextDeltaEvent):
            if not self._text_stream_open:
                self._start_output_run(event, turn_id)
                self._text_stream_open = True
                await self._publish_event(AgentOutTextStartEvent(), turn_id)
            await self._publish_event(
                AgentOutTextDeltaEvent(delta=event.delta), turn_id
            )
        elif isinstance(event, StreamTextDoneEvent):
            if not self._text_stream_open:
                self._start_output_run(event, turn_id)
                await self._publish_event(AgentOutTextStartEvent(), turn_id)
            self._text_stream_open = False
            await self._publish_event(AgentOutTextDoneEvent(), turn_id)
            self._finish_output_run()
        elif isinstance(event, StreamAudioStartEvent):
            await self._publish_voice("voice.phase", {"phase": "speaking"}, turn_id)
        elif isinstance(event, StreamAudioDeltaEvent):
            await self._publish_output(
                SessionOutput(
                    turn_id=turn_id,
                    data=pcm_s16le_to_f32le(event.delta),
                    metadata={"kind": "audio"},
                )
            )
        elif isinstance(event, StreamAudioDoneEvent):
            return

    def _resolve_turn(self, event: StreamModelEvent) -> str:
        if isinstance(event, StreamTranscriptionStartEvent):
            turn_id = f"native-turn-{event.item_id or uuid4()}"
            self._current_turn_id = turn_id
        turn_id = self._current_turn_id or f"native-session-{self.id}"
        if event.item_id:
            self._question_turns.setdefault(event.item_id, turn_id)
            turn_id = self._question_turns[event.item_id]
        return turn_id

    def _observe_task_event(self, event: TaskEvent) -> None:
        task = self.task_manager.get_task(event.task_id)
        question_id = (
            str(task.metadata.get("duplex_question_id"))
            if task is not None and task.metadata.get("duplex_question_id")
            else None
        )
        turn_id = (
            (self._question_turns.get(question_id) if question_id is not None else None)
            or self._current_turn_id
            or f"native-session-{self.id}"
        )
        output = SessionOutput(
            turn_id=turn_id,
            data=event,
            metadata={"source_task_id": event.task_id, "question_id": question_id},
        )
        if self.output_listener is not None:
            result = self.output_listener(output)
            if result is not None:
                asyncio.create_task(result)

    def _observe_backfill_activation(self, activation: BackfillActivation) -> None:
        self._pending_activation = activation

    def _start_output_run(self, event: StreamModelEvent, turn_id: str) -> None:
        activation = self._pending_activation
        self._pending_activation = None
        if activation is None:
            self._active_output_run_id = event.response_id or f"native-output-{uuid4()}"
            self._active_conversation_turn_id = turn_id
            self._active_triggering_task_ids = ()
            return

        mapped_turns = tuple(
            self._question_turns.get(question_id)
            for question_id in activation.question_ids
        )
        turns = {turn for turn in mapped_turns if turn is not None}
        all_turns_known = bool(mapped_turns) and all(
            turn is not None for turn in mapped_turns
        )
        self._active_output_run_id = activation.activation_id
        self._active_conversation_turn_id = (
            next(iter(turns)) if all_turns_known and len(turns) == 1 else None
        )
        self._active_triggering_task_ids = activation.task_ids

    def _finish_output_run(self) -> None:
        self._active_output_run_id = None
        self._active_conversation_turn_id = None
        self._active_triggering_task_ids = ()

    async def _publish_voice(
        self,
        event_type: str,
        payload: dict[str, Any],
        turn_id: str | None = None,
    ) -> None:
        await self._publish_output(
            SessionOutput(
                turn_id=turn_id or self._current_turn_id or f"native-session-{self.id}",
                data=NativeVoiceEvent(event_type, payload),
                metadata={"kind": "voice"},
            )
        )

    async def _publish_event(self, event: Any, turn_id: str) -> None:
        await self._publish_output(
            SessionOutput(
                turn_id=turn_id,
                data=event,
                metadata={
                    "message_id": f"native-assistant-{turn_id}",
                    "conversation_turn_id": self._active_conversation_turn_id,
                    "output_run_id": self._active_output_run_id,
                    "triggering_task_ids": self._active_triggering_task_ids,
                },
            )
        )

    async def _publish_output(self, output: SessionOutput) -> None:
        if self.output_listener is not None:
            result = self.output_listener(output)
            if result is not None:
                await result

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        task = self.run_task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.agent_session.model_api.aclose()


def default_native_agent_session_factory(**kwargs: Any) -> DuplexAgentSession:
    from aicore.models.stream_model_api.duplex.duplex_agent_app import (
        build_browser_duplex_agent_session,
    )

    return build_browser_duplex_agent_session(**kwargs)


__all__ = [
    "DuplexNativeSession",
    "NativeAgentSessionFactory",
    "NativeVoiceEvent",
    "default_native_agent_session_factory",
]
