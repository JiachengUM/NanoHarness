"""Small adapter around the existing v2 text Agent runner."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal

from aicore.core.event import EventBase
from aicore.events.task import TaskSuccessEvent
from aicore.runtime.task import TaskManager
from aicore.simulation.user_env.data_source import UserDataSourceBase

type AgentMode = Literal["react", "plact"]
AgentFactory = Callable[[TaskManager, AgentMode], Any]
RunnerFactory = Callable[..., Any]


@dataclass(frozen=True)
class QueuedUserInput:
    query: str
    message_id: str


@dataclass(frozen=True)
class EventContext:
    message_id: str | None = None
    origin_message_id: str | None = None
    source_task_id: str | None = None
    round: int | None = None


class QueueUserDataSource(UserDataSourceBase):
    def __init__(
        self,
        on_dequeued: Callable[[QueuedUserInput], None] | None = None,
    ) -> None:
        self._queue: asyncio.Queue[QueuedUserInput | None] = asyncio.Queue()
        self._on_dequeued = on_dequeued
        self._closed = False

    async def put(self, query: str, message_id: str) -> None:
        if self._closed:
            raise RuntimeError("v2 Agent session input is closed")
        await self._queue.put(QueuedUserInput(query=query, message_id=message_id))

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(None)

    async def __call__(self):
        while True:
            data = await self._queue.get()
            if data is None:
                return
            if self._on_dequeued is not None:
                self._on_dequeued(data)
            yield data


class SessionBoundAgent:
    """Attach frontend turn/task correlation to events from an existing Agent."""

    def __init__(self, inner: Any, *, task_manager: TaskManager) -> None:
        self._inner = inner
        self._task_manager = task_manager
        self._last_message_id: str | None = None
        self._event_contexts: dict[str, EventContext] = {}

    def context_for(self, event: EventBase) -> EventContext:
        event_id = getattr(event, "event_id", None)
        if event_id is None:
            return EventContext()
        return self._event_contexts.pop(str(event_id), EventContext())

    async def astream(self, input_event: Any, **kwargs: Any):
        from aicore.agents.plan.events import PlActRoundStartEvent

        if isinstance(input_event, QueuedUserInput):
            query = input_event.query
            message_id = input_event.message_id
            self._last_message_id = message_id
            submission_origin_message_id = message_id
            origin_message_id = None
            source_task_id = None
        elif isinstance(input_event, TaskSuccessEvent):
            query = input_event
            task = self._task_manager.get_task(input_event.task_id)
            origin_message_id = (
                str(task.metadata.get("origin_message_id"))
                if task is not None and task.metadata.get("origin_message_id")
                else None
            )
            submission_origin_message_id = origin_message_id
            source_task_id = input_event.task_id
            message_id = f"task-result-{input_event.task_id}"
        else:
            query = input_event
            message_id = self._last_message_id
            submission_origin_message_id = message_id
            origin_message_id = None
            source_task_id = None

        current_round: int | None = None
        submission_metadata = (
            {"origin_message_id": submission_origin_message_id}
            if submission_origin_message_id is not None
            else {}
        )
        with self._task_manager.submission_context(submission_metadata):
            async for event in self._inner.astream(query, **kwargs):
                if isinstance(event, PlActRoundStartEvent):
                    current_round = event.round
                event_id = getattr(event, "event_id", None)
                if event_id is not None:
                    self._event_contexts[str(event_id)] = EventContext(
                        message_id=message_id,
                        origin_message_id=origin_message_id,
                        source_task_id=source_task_id,
                        round=current_round,
                    )
                yield event


class V2AgentSession:
    """Own the text Agent runner resources used by one frontend connection."""

    def __init__(
        self,
        *,
        agent_mode: AgentMode,
        agent_factory: AgentFactory,
        runner_factory: RunnerFactory,
        on_input_dequeued: Callable[[QueuedUserInput], None] | None = None,
        output_listener: Callable[[EventBase, EventContext], None] | None = None,
    ) -> None:
        self.agent_mode = agent_mode
        self.agent_factory = agent_factory
        self.runner_factory = runner_factory
        self.output_listener = output_listener
        self.task_manager = TaskManager()
        self.user_data = QueueUserDataSource(on_dequeued=on_input_dequeued)
        self.agent: SessionBoundAgent | None = None
        self.runner_task: asyncio.Task[None] | None = None
        self._start_lock = asyncio.Lock()
        self._closed = False

    async def start(self) -> None:
        async with self._start_lock:
            if self._closed:
                raise RuntimeError("v2 Agent session is closed")
            if self.runner_task is not None and not self.runner_task.done():
                return
            self.agent = SessionBoundAgent(
                self.agent_factory(self.task_manager, self.agent_mode),
                task_manager=self.task_manager,
            )
            runner = self.runner_factory(
                user_data=self.user_data,
                agent=self.agent,
                task_manager=self.task_manager,
                client=self._publish_event,
            )
            self.runner_task = asyncio.create_task(runner.run())

    async def submit(self, query: str, *, message_id: str) -> None:
        if self._closed:
            raise RuntimeError("v2 Agent session is closed")
        if not query.strip():
            raise ValueError("V2AgentSession input must be non-empty text")
        await self.start()
        await self.user_data.put(query, message_id)

    def _publish_event(self, event: EventBase) -> None:
        context = (
            self.agent.context_for(event) if self.agent is not None else EventContext()
        )
        if self.output_listener is not None:
            self.output_listener(event, context)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.user_data.close()
        if self.runner_task is not None:
            self.runner_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self.runner_task


__all__ = [
    "AgentFactory",
    "AgentMode",
    "EventContext",
    "QueueUserDataSource",
    "QueuedUserInput",
    "RunnerFactory",
    "SessionBoundAgent",
    "V2AgentSession",
]
