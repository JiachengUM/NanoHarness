"""Events emitted by the session-scoped streaming model API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from aicore.core.event import EventBase
from aicore.tools.run import ToolRunRequest


class StreamModelEventBase(EventBase):
    """Common correlation envelope for one stream-model session event."""

    session_id: str
    query_id: str | None = None
    root_query_id: str | None = None
    provider_event_id: str | None = None
    response_id: str | None = None
    item_id: str | None = None


class StreamQueryStartEvent(StreamModelEventBase):
    type: Literal["stream_model.query.start"] = Field(
        default="stream_model.query.start", init=False
    )  # type: ignore
    source: Literal["user", "tool_result", "placeholder"] = "user"


class StreamQueryDoneEvent(StreamModelEventBase):
    type: Literal["stream_model.query.done"] = Field(
        default="stream_model.query.done", init=False
    )  # type: ignore
    pending_tool_calls: int = 0


class StreamQueryErrorEvent(StreamModelEventBase):
    type: Literal["stream_model.query.error"] = Field(
        default="stream_model.query.error", init=False
    )  # type: ignore
    error: str


class StreamTextStartEvent(StreamModelEventBase):
    type: Literal["stream_model.text.start"] = Field(
        default="stream_model.text.start", init=False
    )  # type: ignore


class StreamTextDeltaEvent(StreamModelEventBase):
    type: Literal["stream_model.text.delta"] = Field(
        default="stream_model.text.delta", init=False
    )  # type: ignore
    delta: str


class StreamTextDoneEvent(StreamModelEventBase):
    type: Literal["stream_model.text.done"] = Field(
        default="stream_model.text.done", init=False
    )  # type: ignore
    text: str


class StreamStructuredDoneEvent(StreamModelEventBase):
    type: Literal["stream_model.structured.done"] = Field(
        default="stream_model.structured.done", init=False
    )  # type: ignore
    parsed: Any | None = None
    text: str | None = None
    error: str | None = None


class StreamContextRetrievedEvent(StreamModelEventBase):
    type: Literal["stream_model.context.retrieved"] = Field(
        default="stream_model.context.retrieved", init=False
    )  # type: ignore
    items: tuple[dict[str, Any], ...] = ()


class StreamToolCallEvent(StreamModelEventBase):
    type: Literal["stream_model.tool.call"] = Field(
        default="stream_model.tool.call", init=False
    )  # type: ignore
    tool_call: ToolRunRequest
    group_id: str | None = None
    group_size: int = 1
    input_error: str | None = None


class StreamToolResultEvent(StreamModelEventBase):
    type: Literal["stream_model.tool.result"] = Field(
        default="stream_model.tool.result", init=False
    )  # type: ignore
    call_id: str
    tool_name: str
    output: str
    success: bool


class StreamTranscriptionStartEvent(StreamModelEventBase):
    type: Literal["stream_model.transcription.start"] = Field(
        default="stream_model.transcription.start", init=False
    )  # type: ignore


class StreamTranscriptionDeltaEvent(StreamModelEventBase):
    type: Literal["stream_model.transcription.delta"] = Field(
        default="stream_model.transcription.delta", init=False
    )  # type: ignore
    delta: str


class StreamTranscriptionDoneEvent(StreamModelEventBase):
    type: Literal["stream_model.transcription.done"] = Field(
        default="stream_model.transcription.done", init=False
    )  # type: ignore
    transcript: str


class StreamAudioStartEvent(StreamModelEventBase):
    type: Literal["stream_model.audio.start"] = Field(
        default="stream_model.audio.start", init=False
    )  # type: ignore
    tts_type: str | None = None


class StreamAudioDeltaEvent(StreamModelEventBase):
    type: Literal["stream_model.audio.delta"] = Field(
        default="stream_model.audio.delta", init=False
    )  # type: ignore
    delta: bytes


class StreamAudioDoneEvent(StreamModelEventBase):
    type: Literal["stream_model.audio.done"] = Field(
        default="stream_model.audio.done", init=False
    )  # type: ignore
    status: str | None = None


class StreamResponseCanceledEvent(StreamModelEventBase):
    type: Literal["stream_model.response.canceled"] = Field(
        default="stream_model.response.canceled", init=False
    )  # type: ignore


class StreamModelErrorEvent(StreamModelEventBase):
    type: Literal["stream_model.error"] = Field(
        default="stream_model.error", init=False
    )  # type: ignore
    error: str
    details: Any | None = None


type StreamModelEvent = (
    StreamQueryStartEvent
    | StreamQueryDoneEvent
    | StreamQueryErrorEvent
    | StreamTextStartEvent
    | StreamTextDeltaEvent
    | StreamTextDoneEvent
    | StreamStructuredDoneEvent
    | StreamContextRetrievedEvent
    | StreamToolCallEvent
    | StreamToolResultEvent
    | StreamTranscriptionStartEvent
    | StreamTranscriptionDeltaEvent
    | StreamTranscriptionDoneEvent
    | StreamAudioStartEvent
    | StreamAudioDeltaEvent
    | StreamAudioDoneEvent
    | StreamResponseCanceledEvent
    | StreamModelErrorEvent
)


__all__ = [
    "StreamModelEvent",
    "StreamAudioDeltaEvent",
    "StreamAudioDoneEvent",
    "StreamAudioStartEvent",
    "StreamResponseCanceledEvent",
    "StreamContextRetrievedEvent",
    "StreamModelErrorEvent",
    "StreamQueryDoneEvent",
    "StreamQueryErrorEvent",
    "StreamQueryStartEvent",
    "StreamStructuredDoneEvent",
    "StreamTextDeltaEvent",
    "StreamTextDoneEvent",
    "StreamTextStartEvent",
    "StreamTranscriptionDeltaEvent",
    "StreamTranscriptionDoneEvent",
    "StreamTranscriptionStartEvent",
    "StreamToolCallEvent",
    "StreamToolResultEvent",
]
