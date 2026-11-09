"""Inputs accepted by session-scoped stream model backends."""

from __future__ import annotations

from dataclasses import dataclass

from aicore.models.model_api import ModelInput


type QueryInput = str | ModelInput


@dataclass(frozen=True, slots=True)
class AudioChunkInput:
    """One raw audio chunk in the format configured for the model session."""

    data: bytes


@dataclass(frozen=True, slots=True)
class AudioCommitInput:
    """Commit the current audio buffer when client-side turn detection is used."""


@dataclass(frozen=True, slots=True)
class ContextItemRetrieveInput:
    """Retrieve one item, or the provider's recent context when id is omitted."""

    item_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContextItemUpdateInput:
    """Replace the text of one existing provider context item.

    This is mutation, not append: callers must preserve any original text that
    should remain visible. Duplex's DynamicTask compatibility layer uses this
    to project completed async results onto their originating question.
    """

    item_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("context item id cannot be empty")


@dataclass(frozen=True, slots=True)
class ToolResultInput:
    """One terminal result for a provider-issued function call."""

    call_id: str
    output: str
    success: bool = True


@dataclass(frozen=True, slots=True)
class ToolResultBatchInput:
    """Terminal results that belong to one provider function-call group."""

    results: tuple[ToolResultInput, ...]

    def __post_init__(self) -> None:
        if not self.results:
            raise ValueError("tool result batch cannot be empty")


type StreamModelInput = (
    QueryInput
    | AudioChunkInput
    | AudioCommitInput
    | ContextItemRetrieveInput
    | ContextItemUpdateInput
    | ToolResultInput
    | ToolResultBatchInput
)


__all__ = [
    "AudioChunkInput",
    "AudioCommitInput",
    "ContextItemRetrieveInput",
    "ContextItemUpdateInput",
    "QueryInput",
    "StreamModelInput",
    "ToolResultBatchInput",
    "ToolResultInput",
]
