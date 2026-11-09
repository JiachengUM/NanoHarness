"""Duplex implementation of the public ``StreamModelAPI`` protocol.

This module owns only the provider session boundary: session creation,
upstream input mapping and downstream Duplex-event mapping. Audio devices, tool
execution, TaskManager integration and async backfill policy belong to
``duplex_agent_session.py``.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator, Sequence
from copy import deepcopy
from typing import Any, Protocol

import anyio
from pydantic import BaseModel

from aicore.models.stream_model_api.events import (
    StreamAudioDeltaEvent,
    StreamAudioDoneEvent,
    StreamAudioStartEvent,
    StreamContextRetrievedEvent,
    StreamModelErrorEvent,
    StreamModelEvent,
    StreamResponseCanceledEvent,
    StreamTextDeltaEvent,
    StreamTextDoneEvent,
    StreamToolCallEvent,
    StreamTranscriptionDeltaEvent,
    StreamTranscriptionDoneEvent,
    StreamTranscriptionStartEvent,
)
from aicore.models.stream_model_api.inputs import (
    AudioChunkInput,
    AudioCommitInput,
    ContextItemRetrieveInput,
    ContextItemUpdateInput,
    StreamModelInput,
    ToolResultBatchInput,
    ToolResultInput,
)
from aicore.tools.protocol import ToolProtocol
from aicore.tools.run import ToolRunRequest

from .duplex_events import (
    TYPE_CONVERSATION_ITEM_RETRIEVED,
    TYPE_ERROR,
    TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE,
    TYPE_RESPONSE_CANCELED,
    TYPE_RESPONSE_OUTPUT_AUDIO_DELTA,
    TYPE_RESPONSE_OUTPUT_AUDIO_DONE,
    TYPE_RESPONSE_OUTPUT_AUDIO_STARTED,
    TYPE_RESPONSE_OUTPUT_TEXT_DELTA,
    TYPE_RESPONSE_OUTPUT_TEXT_DONE,
    TYPE_SESSION_CLOSED,
    TYPE_TRANSCRIPTION_COMPLETED,
    TYPE_TRANSCRIPTION_DELTA,
    TYPE_TRANSCRIPTION_FAILED,
    TYPE_TRANSCRIPTION_STARTED,
)


class DuplexToolSpecSource(Protocol):
    """Structural tool surface needed to build one Duplex function schema."""

    name: str
    description: str
    args_schema: type[BaseModel]


class DuplexClientProtocol(Protocol):
    """Low-level Duplex command surface consumed by the provider adapter."""

    session_id: str

    async def connect(self) -> None: ...

    async def session_create(
        self,
        session: dict[str, Any],
        extension: dict[str, Any],
    ) -> None: ...

    async def input_audio_append(self, data: bytes) -> None: ...

    async def input_audio_commit(self) -> None: ...

    async def response_cancel(self) -> None: ...

    async def conversation_item_create(self, items: list[dict[str, Any]]) -> None: ...

    async def conversation_item_update(self, items: list[dict[str, Any]]) -> None: ...

    async def conversation_item_retrieve(
        self,
        items: list[dict[str, Any]] | None = None,
    ) -> None: ...

    async def recv_event(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...


def build_duplex_tool_spec(tool: DuplexToolSpecSource) -> dict[str, Any]:
    """Convert an AICore tool schema to the Duplex session tool shape."""

    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.args_schema.model_json_schema(),
    }


def build_duplex_tool_result_item(result: ToolResultInput) -> dict[str, Any]:
    """Build one Duplex function-call result item.

    Duplex identifies an FC result by ``role="tool"`` plus ``call_id``.
    Unlike ordinary conversation messages, this item deliberately has no
    ``type`` field.
    """

    return {
        "role": "tool",
        "call_id": result.call_id,
        "content": [{"type": "input_text", "text": result.output}],
    }


def build_duplex_context_update_item(
    item_id: str,
    text: str,
) -> dict[str, Any]:
    """Build a Duplex in-place text replacement for an existing item.

    ``conversation.item.update`` replaces the selected question/reply text; it
    does not append a new observation. Although server events expose the target
    as ``item_id``/``question_id``, the request's ``items[]`` schema calls the
    same identifier ``id``. The caller is responsible for carrying forward the
    original text when replacement would otherwise destroy it.
    """

    return {
        "id": item_id,
        "content": [{"type": "input_text", "text": text}],
    }


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


class DuplexStreamModelAPI:
    """Expose one Duplex provider session as ``submit() + events()``.

    ``events()`` is a direct, single-consumer projection of the provider receive
    lane. It does not introduce another queue or own any business runtime.
    """

    def __init__(
        self,
        *,
        client: DuplexClientProtocol,
        session: dict[str, Any] | None = None,
        extension: dict[str, Any] | None = None,
        tools: Sequence[ToolProtocol[BaseModel]] = (),
    ) -> None:
        self.client = client
        self.tools = list(tools)
        self.session_id = str(getattr(client, "session_id", "") or uuid.uuid4())
        self._session = session if session is not None else {"id": self.session_id}
        self._extension = extension if extension is not None else {}
        self._start_lock = anyio.Lock()
        self._started = False
        self._closed = False
        self._server_closed = False
        self._events_claimed = False

    async def __aenter__(self) -> DuplexStreamModelAPI:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def start(self) -> None:
        async with self._start_lock:
            if self._closed:
                raise RuntimeError("Duplex stream model session is closed")
            if self._server_closed:
                raise RuntimeError("Duplex stream model session ended")
            if self._started:
                return

            await self.client.connect()
            session = self._session
            extension = self._extension
            session.setdefault("id", self.session_id)
            session["tools"] = [build_duplex_tool_spec(tool) for tool in self.tools]
            await self.client.session_create(session, extension)
            self._started = True

    async def submit(self, input: StreamModelInput) -> str | None:
        """Map one provider-neutral input onto the Duplex upstream lane."""

        await self.start()
        if isinstance(input, ContextItemUpdateInput):
            await self.client.conversation_item_update(
                [build_duplex_context_update_item(input.item_id, input.text)]
            )
        elif isinstance(input, str):
            raise TypeError("Duplex user queries require audio")
        elif isinstance(input, AudioChunkInput):
            await self.client.input_audio_append(input.data)
        elif isinstance(input, AudioCommitInput):
            await self.client.input_audio_commit()
        elif isinstance(input, ContextItemRetrieveInput):
            items = [{"id": input.item_id}] if input.item_id is not None else None
            await self.client.conversation_item_retrieve(items)
        elif isinstance(input, ToolResultInput):
            await self.client.conversation_item_create(
                [build_duplex_tool_result_item(input)]
            )
        elif isinstance(input, ToolResultBatchInput):
            await self.client.conversation_item_create(
                [build_duplex_tool_result_item(result) for result in input.results]
            )
        else:
            raise TypeError(
                f"DuplexStreamModelAPI does not accept {type(input).__name__} input"
            )
        return None

    async def cancel_response(self) -> None:
        """Cancel the active Duplex response, if the provider still has one."""

        await self.start()
        await self.client.response_cancel()

    async def events(self) -> AsyncIterator[StreamModelEvent]:
        """Yield mapped Duplex events to exactly one external consumer."""

        await self.start()
        if self._closed or self._server_closed:
            raise RuntimeError("Duplex stream model session is closed")
        if self._events_claimed:
            raise RuntimeError("Duplex stream model events already have a consumer")

        self._events_claimed = True
        try:
            while not self._closed:
                raw_event = await self.client.recv_event()
                if raw_event.get("type") == TYPE_SESSION_CLOSED:
                    self._server_closed = True
                    return
                for event in self._map_server_event(raw_event):
                    yield event
        finally:
            self._events_claimed = False

    async def aclose(self) -> None:
        async with self._start_lock:
            if self._closed:
                return
            self._closed = True
            await self.client.close()
            self._started = False

    def _map_server_event(self, event: dict[str, Any]) -> list[StreamModelEvent]:
        event_type = str(event.get("type") or "")
        common = self._common_event_fields(event)

        if event_type == TYPE_TRANSCRIPTION_STARTED:
            return [StreamTranscriptionStartEvent(**common)]
        if event_type == TYPE_TRANSCRIPTION_DELTA:
            return [
                StreamTranscriptionDeltaEvent(
                    delta=str(event.get("delta") or ""),
                    **common,
                )
            ]
        if event_type == TYPE_TRANSCRIPTION_COMPLETED:
            return [
                StreamTranscriptionDoneEvent(
                    transcript=str(event.get("transcript") or event.get("text") or ""),
                    **common,
                )
            ]
        if event_type == TYPE_TRANSCRIPTION_FAILED:
            return [self._error_event(event, "Duplex transcription failed")]
        if event_type == TYPE_RESPONSE_CANCELED:
            return [StreamResponseCanceledEvent(**common)]
        if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DELTA:
            return [
                StreamTextDeltaEvent(
                    delta=str(event.get("delta") or ""),
                    **common,
                )
            ]
        if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DONE:
            return [
                StreamTextDoneEvent(
                    text=str(event.get("text") or ""),
                    **common,
                )
            ]
        if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_STARTED:
            return [
                StreamAudioStartEvent(
                    tts_type=_optional_string(event.get("tts_type")),
                    **common,
                )
            ]
        if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DELTA:
            try:
                audio = base64.b64decode(event.get("delta") or "", validate=True)
            except Exception as error:
                return [
                    StreamModelErrorEvent(
                        error=f"invalid Duplex audio payload: {error}",
                        details=event,
                        **common,
                    )
                ]
            return [StreamAudioDeltaEvent(delta=audio, **common)]
        if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DONE:
            return [
                StreamAudioDoneEvent(
                    status=_optional_string(event.get("status_code")),
                    **common,
                )
            ]
        if event_type == TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            return self._map_function_calls(event)
        if event_type == TYPE_CONVERSATION_ITEM_RETRIEVED:
            raw_items = event.get("items") or []
            if not isinstance(raw_items, list) or not all(
                isinstance(item, dict) for item in raw_items
            ):
                return [self._error_event(event, "invalid Duplex context payload")]
            return [
                StreamContextRetrievedEvent(
                    items=tuple(deepcopy(raw_items)),
                    **common,
                )
            ]
        if event_type == TYPE_ERROR:
            return [self._error_event(event, "Duplex server error")]
        return []

    def _map_function_calls(
        self,
        event: dict[str, Any],
    ) -> list[StreamModelEvent]:
        raw_items = event.get("items") or []
        if not raw_items and event.get("call_id"):
            raw_items = [event]
        if not isinstance(raw_items, list):
            return [self._error_event(event, "invalid Duplex function-call items")]

        parsed: list[tuple[ToolRunRequest, str | None]] = []
        errors: list[StreamModelEvent] = []
        for item in raw_items:
            if not isinstance(item, dict):
                errors.append(
                    self._error_event(event, "invalid Duplex function-call item")
                )
                continue
            call_id = str(item.get("call_id") or "")
            name = str(item.get("name") or "")
            raw_arguments = str(item.get("arguments") or "")
            if not call_id:
                errors.append(
                    self._error_event(
                        event,
                        "invalid Duplex function call: missing call_id",
                    )
                )
                continue

            input_error: str | None = None
            try:
                arguments = json.loads(raw_arguments) if raw_arguments else {}
                if not isinstance(arguments, dict):
                    raise ValueError("function-call arguments must be a JSON object")
            except Exception as error:
                arguments = {}
                input_error = (
                    "invalid Duplex function-call arguments: "
                    f"{type(error).__name__}: {error}"
                )
            if not name:
                input_error = "invalid Duplex function call: missing tool name"

            parsed.append(
                (
                    ToolRunRequest(
                        run_id=call_id,
                        tool_name=name or "<invalid-tool>",
                        arguments=arguments,
                        raw_arguments=raw_arguments,
                    ),
                    input_error,
                )
            )

        if not parsed:
            return errors

        # Duplex declares one complete concurrent FC batch in this event's
        # ``items`` array. Real service events may omit both ``response_id`` and
        # ``question_id``; use the provider event id only as the local grouping
        # key and let the session fall back to its latest completed ASR item.
        group_id = str(
            event.get("response_id")
            or event.get("event_id")
            or parsed[0][0].run_id
        )
        common = self._common_event_fields(event)
        size = len(parsed)
        return [
            *errors,
            *[
                StreamToolCallEvent(
                    tool_call=request,
                    input_error=input_error,
                    group_id=group_id,
                    group_size=size,
                    **common,
                )
                for request, input_error in parsed
            ],
        ]

    def _common_event_fields(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "provider_event_id": _optional_string(event.get("event_id")),
            "response_id": _optional_string(event.get("response_id")),
            "item_id": _optional_string(
                event.get("item_id") or event.get("question_id")
            ),
        }

    def _error_event(
        self,
        event: dict[str, Any],
        fallback: str,
    ) -> StreamModelErrorEvent:
        raw_error = event.get("error")
        if isinstance(raw_error, dict):
            message = str(raw_error.get("message") or raw_error)
        else:
            message = str(raw_error or fallback)
        return StreamModelErrorEvent(
            error=message,
            details=event,
            **self._common_event_fields(event),
        )


__all__ = [
    "DuplexClientProtocol",
    "DuplexStreamModelAPI",
    "DuplexToolSpecSource",
    "build_duplex_tool_result_item",
    "build_duplex_tool_spec",
    "build_duplex_context_update_item",
]
