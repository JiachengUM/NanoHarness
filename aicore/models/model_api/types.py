"""Provider-neutral data types for the Model API domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, Mapping, Sequence, Union

from pydantic import BaseModel, Field

from aicore.tools.run import ToolRunRequest, ToolRunResult


class SystemMessage(BaseModel):
    type: Literal["system"] = "system"
    text: str


class UserMessage(BaseModel):
    type: Literal["user"] = "user"
    text: str


class AssistantMessage(BaseModel):
    type: Literal["assistant"] = "assistant"
    text: str
    tool_calls: list[ToolRunRequest] = Field(default_factory=list)


class ToolResultsMessage(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    results: list[ToolRunResult] = Field(..., min_length=1)


type ModelMessage = Annotated[
    Union[
        SystemMessage,
        UserMessage,
        AssistantMessage,
        ToolResultsMessage,
    ],
    Field(discriminator="type"),
]


type ModelInputMessage = Annotated[
    Union[
        UserMessage,
        ToolResultsMessage,
    ],
    Field(discriminator="type"),
]


type ModelInput = ModelInputMessage | Sequence[ModelInputMessage]


class ModelCallParams(BaseModel):
    """Provider-neutral per-call model generation parameters."""

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    thinking: Literal["enabled", "disabled", "auto"] | None = "disabled"

    extra: dict[str, object] = Field(default_factory=dict)


class ModelParams(BaseModel):
    """Provider-neutral model identity and default call parameters."""


    model: str = Field(..., description="模型名称")
    params: ModelCallParams = Field(
        default_factory=ModelCallParams,
        description="默认模型调用参数",
    )


class ModelState(BaseModel):
    """Base class for provider-owned state used to continue a model interaction.

    Concrete adapters own their state schema. Agent code may pass, store, dump,
    and restore state values, but should not inspect provider-specific fields
    for flow control.
    """


class ModelStateDump(BaseModel):
    """Opaque serializable dump of provider-owned model state.

    Agent code may store and pass this value. The top-level fields are a
    stable envelope for routing and audit; provider-specific payloads inside
    serialized remain adapter-owned and opaque to agent core.
    """

    object: Literal["model_state_dump"] = "model_state_dump"
    format: str = Field(
        ...,
        description=(
            "Adapter-owned payload format identifier, e.g. chat.messages."
        ),
    )
    format_version: int = Field(
        ...,
        description="Schema version of serialized payload for this format.",
    )
    dumped_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC time when the dump was materialized.",
    )
    serialized: str = Field(
        ...,
        description=(
            "Opaque adapter-owned serialized state dump payload. Store or "
            "pass it unchanged; do not inspect, mutate, or construct it in "
            "agent core."
        ),
    )
    metadata: Mapping[str, object] = Field(
        default_factory=dict,
        description=(
            "Adapter diagnostics and audit hints. Restore must not require "
            "these values."
        ),
    )


class ModelResponse[StateT: ModelState](BaseModel):
    """Provider-neutral completed model call result."""

    text: str | None = None
    tool_calls: list[ToolRunRequest] = Field(default_factory=list)
    state: StateT
    metadata: Mapping[str, object] = Field(
        default_factory=dict,
        description=(
            "Provider diagnostics and extensions for logging or debugging. "
            "Agent core must not rely on these values for flow control."
        ),
    )


class StructuredModelResponse[T, StateT: ModelState](ModelResponse[StateT]):
    """Model response with an optional parsed structured output."""

    parsed: T | None = Field(
        default=None,
        description=(
            "Structured output parsed as the requested type. None means the "
            "model response was produced but parsing or validation failed."
        ),
    )
