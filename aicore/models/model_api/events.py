"""Domain events emitted by Model API streams."""

from __future__ import annotations

from typing import Literal, TypeIs

from pydantic import Field

from aicore.core.event import EventBase
from aicore.tools.run import ToolRunRequest

__all__ = [
    "ModelTextStartEvent",
    "ModelTextDeltaEvent",
    "ModelTextDoneEvent",
    "ModelToolCallEvent",
    "ModelEvent",
    "is_model_event",
]


class ModelTextStartEvent(EventBase):
    """A model started emitting a text segment."""

    type: Literal["model.text.start"] = Field(default="model.text.start", init=False)  # type: ignore


class ModelTextDeltaEvent(EventBase):
    """A model emitted a text delta."""

    type: Literal["model.text.delta"] = Field(default="model.text.delta", init=False)  # type: ignore
    delta: str


class ModelTextDoneEvent(EventBase):
    """A model completed a text segment."""

    type: Literal["model.text.done"] = Field(default="model.text.done", init=False)  # type: ignore
    text: str


class ModelToolCallEvent(EventBase):
    """A model requested a tool call."""

    type: Literal["model.tool_call"] = Field(default="model.tool_call", init=False)  # type: ignore
    tool_call: ToolRunRequest


type ModelEvent = (
    ModelTextStartEvent
    | ModelTextDeltaEvent
    | ModelTextDoneEvent
    | ModelToolCallEvent
)


def is_model_event(event: object) -> TypeIs[ModelEvent]:
    return isinstance(
        event,
        (
            ModelTextStartEvent,
            ModelTextDeltaEvent,
            ModelTextDoneEvent,
            ModelToolCallEvent,
        ),
    )
