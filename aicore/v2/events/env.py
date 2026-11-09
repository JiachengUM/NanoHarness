from typing import Literal, Any

from pydantic import Field

from aicore.core.event import EventBase


class EnvEventBase(EventBase):
    type: Literal["env.base"] = Field(default="env.base", init=False)  # type: ignore


class EnvTaskFinishedEvent(EnvEventBase):
    type: Literal["env.task.finished"] = Field(default="env.task.finished", init=False)  # type: ignore

    result: Any
