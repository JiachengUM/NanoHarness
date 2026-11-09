from typing import Literal, Any, TypeIs

from pydantic import Field

from aicore.core.event import EventBase

from aicore.events.task import TaskCreatedEvent,TaskSuccessEvent

__all__ = [
    "AgentOutEventBase",
    "AgentOutTextStartEvent",
    "AgentOutTextDeltaEvent",
    "AgentOutTextDoneEvent",
    "TaskCreatedEvent",
    "TaskSuccessEvent",
]

class AgentOutEventBase(EventBase):
    type: Literal["agent.out.base"] = Field(default="agent.out.base", init=False)  # type: ignore


class AgentOutTextStartEvent(AgentOutEventBase):
    type: Literal["agent.out.text.start"] = Field(default="agent.out.text.start", init=False)  # type: ignore

    meta_data: Any = Field(default=None)

class AgentOutTextDeltaEvent(AgentOutEventBase):
    type: Literal["agent.out.text.delta"] = Field(default="agent.out.text.delta", init=False)  # type: ignore

    delta: str

class AgentOutTextDoneEvent(AgentOutEventBase):
    type: Literal["agent.out.text.done"] = Field(default="agent.out.text.done", init=False)  # type: ignore
    
    # text: str  # 所有delta的连接


# AgentOutEvent仅用于静态类型检查，不用于运行时类型检查
type AgentOutEvent = AgentOutTextStartEvent | AgentOutTextDeltaEvent | AgentOutTextDoneEvent | TaskCreatedEvent

# 运行时类型检查
def is_agent_out_event(obj: Any) -> TypeIs[AgentOutEvent]:
    return isinstance(obj, (AgentOutTextStartEvent, AgentOutTextDeltaEvent, AgentOutTextDoneEvent, TaskCreatedEvent))
