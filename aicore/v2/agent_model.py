from typing import AsyncGenerator, Any

from aicore.core.event import EventGenerator

from aicore.events.agent import (
    AgentOutEvent,
    TaskCreatedEvent,
    TaskSuccessEvent,
)

from aicore.runtime.task import TaskAStreamWorkerGeneral, TaskSuccess

type AgentInputEvent = str | TaskSuccessEvent[Any]

__all__ = [
    "AgentInputEvent",
    "AgentOutEvent",
    "TaskCreatedEvent",
    "TaskSuccessEvent",
    "TaskAStreamWorkerGeneral",
    "TaskSuccess",
    "AgentBase",
]

class AgentBase(EventGenerator[AgentOutEvent]):

    async def astream(self, input: AgentInputEvent, /, **kwargs: Any) -> AsyncGenerator[AgentOutEvent, None]:
        raise NotImplementedError
        yield AgentOutEvent()
