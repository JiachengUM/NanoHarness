"""Generation-safe pump from external Agent text events to Duplex TTS."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, Protocol


class SpeechTextSink(Protocol):
    async def append_speech_text(self, speech_id: str, text: str) -> None: ...

    async def commit_speech_text(self, speech_id: str, text: str) -> None: ...


PumpCallback = Callable[[], Awaitable[None] | None]


SpeechItemKind = Literal["start", "delta", "done", "close"]


@dataclass(frozen=True, slots=True)
class SpeechItem:
    kind: SpeechItemKind
    message_id: str = ""
    generation: int = 0
    text: str = ""


class AgentTtsPump:
    """Serialize one external Agent text stream into provider TTS commands."""

    def __init__(
        self,
        sink: SpeechTextSink,
        *,
        speech_id_factory: Callable[[], str] | None = None,
        on_speech_submitted: PumpCallback | None = None,
        on_generation_finished: PumpCallback | None = None,
    ) -> None:
        self.sink = sink
        self.speech_id_factory = speech_id_factory or (lambda: str(uuid.uuid4()))
        self.on_speech_submitted = on_speech_submitted
        self.on_generation_finished = on_generation_finished
        self._queue: asyncio.Queue[SpeechItem] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._generation = 0
        self._active_generation = 0
        self._active_message_id: str | None = None
        self._interrupted_message_ids: set[str] = set()
        self._superseded_message_ids: set[str] = set()

    @property
    def active(self) -> bool:
        return self._active_generation != 0

    @property
    def active_message_id(self) -> str | None:
        return self._active_message_id

    @property
    def interrupted_message_ids(self) -> frozenset[str]:
        return frozenset(self._interrupted_message_ids)

    def start(self) -> asyncio.Task[None]:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self.run(),
                name="duplex-frontend-tts",
            )
        return self._task

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            self.reset()
            return
        self._queue.put_nowait(SpeechItem("close"))
        try:
            await task
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise
        finally:
            self.reset()

    def reset(self) -> None:
        self._clear_queue()
        self._generation += 1
        self._active_generation = 0
        self._active_message_id = None

    def interrupt(self) -> str | None:
        message_id = self._active_message_id
        if message_id is not None:
            self._interrupted_message_ids.add(message_id)
        self.reset()
        return message_id

    def accept_agent_event(
        self,
        event_type: str,
        *,
        message_id: str | None,
        text: str = "",
        user_speaking: bool = False,
    ) -> None:
        if (
            not message_id
            or user_speaking
            or message_id in self._interrupted_message_ids
            or message_id in self._superseded_message_ids
        ):
            return
        if event_type not in {
            "agent.out.text.start",
            "agent.out.text.delta",
            "agent.out.text.done",
        }:
            return

        if event_type == "agent.out.text.start":
            self._begin_generation(message_id)
            self._queue.put_nowait(
                SpeechItem(
                    "start",
                    message_id=message_id,
                    generation=self._active_generation,
                )
            )
            return

        if not self.active or self._active_message_id != message_id:
            self._begin_generation(message_id)

        kind: SpeechItemKind = (
            "delta" if event_type == "agent.out.text.delta" else "done"
        )
        if kind == "delta" and not text:
            return
        self._queue.put_nowait(
            SpeechItem(
                kind,
                message_id=message_id,
                generation=self._active_generation,
                text=text,
            )
        )

    def finish_response(self) -> None:
        self._active_generation = 0
        self._active_message_id = None

    async def run(self) -> None:
        speech_id: str | None = None
        pending_text: str | None = None
        stream_generation = 0
        while True:
            item = await self._queue.get()
            if item.kind == "close":
                return
            if not self._is_current(item):
                continue
            if stream_generation != item.generation:
                speech_id = self.speech_id_factory()
                pending_text = None
                stream_generation = item.generation

            if item.kind == "start":
                continue
            if item.kind == "delta":
                if pending_text is not None:
                    assert speech_id is not None
                    await self.sink.append_speech_text(speech_id, pending_text)
                    await self._notify(self.on_speech_submitted)
                pending_text = item.text
                continue

            # Duplex requires the final text fragment to use commit, not append.
            if pending_text is not None:
                assert speech_id is not None
                await self.sink.commit_speech_text(speech_id, pending_text)
                await self._notify(self.on_speech_submitted)
            else:
                self.finish_response()
                await self._notify(self.on_generation_finished)
            pending_text = None
            speech_id = None

    def _begin_generation(self, message_id: str) -> None:
        if (
            self._active_message_id is not None
            and self._active_message_id != message_id
        ):
            self._superseded_message_ids.add(self._active_message_id)
        self._clear_queue()
        self._generation += 1
        self._active_generation = self._generation
        self._active_message_id = message_id

    def _is_current(self, item: SpeechItem) -> bool:
        return (
            item.generation == self._active_generation
            and item.generation == self._generation
            and item.message_id == self._active_message_id
            and item.message_id not in self._interrupted_message_ids
        )

    def _clear_queue(self) -> None:
        while not self._queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()

    @staticmethod
    async def _notify(callback: PumpCallback | None) -> None:
        if callback is None:
            return
        result = callback()
        if inspect.isawaitable(result):
            await result


__all__ = ["AgentTtsPump", "SpeechItem", "SpeechTextSink"]
