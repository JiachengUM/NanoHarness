"""Lifecycle adapter for the external v2 Agent used by the local CLI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from aicore.events.agent import AgentOutTextDeltaEvent
from aicore.simulation.user_env.data_source import UserDataSourceBase
from aicore.v2.experiments.duplex_speech_shell.agent_tts import AgentTtsPump


class AgentRunnerLike(Protocol):
    async def run(self) -> None: ...


class QueueUserDataSource(UserDataSourceBase):
    """Async user-text source consumed by ``AgentRunner``."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._closed = False

    async def put(self, text: str) -> None:
        if not self._closed:
            await self._queue.put(text)

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(None)

    async def __call__(self):
        while True:
            data = await self._queue.get()
            if data is None:
                return
            yield data


class LocalAgentRuntime:
    """Own the external Agent task and its generation-safe TTS pump."""

    def __init__(
        self,
        *,
        runner: AgentRunnerLike,
        user_data: QueueUserDataSource,
        tts_pump: AgentTtsPump,
        event_logger: Callable[[Any], None] | None = None,
    ) -> None:
        self.runner = runner
        self.user_data = user_data
        self.tts_pump = tts_pump
        self.event_logger = event_logger
        self._runner_task: asyncio.Task[None] | None = None
        self._message_sequence = 0
        self._message_id: str | None = None

    @property
    def output_active(self) -> bool:
        return self.tts_pump.active

    @property
    def runner_task(self) -> asyncio.Task[None] | None:
        return self._runner_task

    async def start(self) -> None:
        if self._runner_task is None or self._runner_task.done():
            self._runner_task = asyncio.create_task(
                self.runner.run(),
                name="duplex-local-agent",
            )
        self.tts_pump.start()

    async def submit_user_text(self, text: str) -> None:
        clean = text.strip()
        if clean:
            await self.user_data.put(clean)

    def accept_agent_event(self, event: Any) -> None:
        if self.event_logger is not None:
            self.event_logger(event)
        event_type = str(getattr(event, "type", "") or "")
        if event_type == "agent.out.text.start":
            self._message_id = self._new_message_id()
        elif self._message_id is None and event_type in {
            "agent.out.text.delta",
            "agent.out.text.done",
        }:
            self._message_id = self._new_message_id()
        self.tts_pump.accept_agent_event(
            event_type,
            message_id=self._message_id,
            text=str(getattr(event, "delta", "") or ""),
        )
        if event_type == "agent.out.text.done":
            self._message_id = None

    def interrupt_speech(self) -> None:
        self.tts_pump.interrupt()
        self._message_id = None

    async def stop(self) -> None:
        await self.stop_tts()
        await self.stop_runner()

    async def stop_tts(self) -> None:
        await self.tts_pump.stop()

    async def stop_runner(self) -> None:
        await self.user_data.close()
        task = self._runner_task
        self._runner_task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._message_id = None

    def _new_message_id(self) -> str:
        self._message_sequence += 1
        return f"local-speech-{self._message_sequence}"


def print_non_delta_agent_event(event: Any) -> None:
    if not isinstance(event, AgentOutTextDeltaEvent):
        print(event)


__all__ = [
    "LocalAgentRuntime",
    "QueueUserDataSource",
    "print_non_delta_agent_event",
]
