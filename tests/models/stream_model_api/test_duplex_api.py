from __future__ import annotations

import base64
from typing import Any

import pytest
from pydantic import BaseModel

from aicore.models.stream_model_api import (
    AudioChunkInput,
    AudioCommitInput,
    ContextItemRetrieveInput,
    ContextItemUpdateInput,
    DuplexStreamModelAPI,
    StreamAudioDeltaEvent,
    StreamContextRetrievedEvent,
    StreamToolCallEvent,
    ToolResultBatchInput,
    ToolResultInput,
)
from aicore.models.stream_model_api.events import StreamResponseCanceledEvent
from aicore.v2.tools.factory import create_tool


class DemoInput(BaseModel):
    value: int


async def demo_worker(value: int) -> int:
    return value * 2


class FakeDuplexClient:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.session_id = "duplex-session"
        self.events = list(events or [])
        self.connected = False
        self.closed = False
        self.created_session: dict[str, Any] | None = None
        self.created_extension: dict[str, Any] | None = None
        self.audio_chunks: list[bytes] = []
        self.audio_commits = 0
        self.response_cancels = 0
        self.conversation_items: list[list[dict[str, Any]]] = []
        self.updated_conversation_items: list[list[dict[str, Any]]] = []
        self.retrieved_conversation_items: list[list[dict[str, Any]] | None] = []

    async def connect(self) -> None:
        self.connected = True

    async def session_create(
        self,
        session: dict[str, Any],
        extension: dict[str, Any],
    ) -> None:
        self.created_session = session
        self.created_extension = extension

    async def input_audio_append(self, data: bytes) -> None:
        self.audio_chunks.append(data)

    async def input_audio_commit(self) -> None:
        self.audio_commits += 1

    async def response_cancel(self) -> None:
        self.response_cancels += 1

    async def conversation_item_create(self, items: list[dict[str, Any]]) -> None:
        self.conversation_items.append(items)

    async def conversation_item_update(self, items: list[dict[str, Any]]) -> None:
        self.updated_conversation_items.append(items)

    async def conversation_item_retrieve(
        self,
        items: list[dict[str, Any]] | None = None,
    ) -> None:
        self.retrieved_conversation_items.append(items)

    async def recv_event(self) -> dict[str, Any]:
        return self.events.pop(0)

    async def close(self) -> None:
        self.closed = True


def make_demo_tool():
    return create_tool(
        name="demo_tool",
        description="double one value",
        args_schema=DemoInput,
        worker=demo_worker,
        asyncable="sync",
    )


def make_session(
    client: FakeDuplexClient,
    *,
    tools: list[Any] | None = None,
    session: dict[str, Any] | None = None,
) -> DuplexStreamModelAPI:
    return DuplexStreamModelAPI(
        client=client,  # type: ignore[arg-type]
        session=session,
        tools=tools or (),
    )


@pytest.mark.asyncio
async def test_duplex_start_attaches_local_tool_specs() -> None:
    client = FakeDuplexClient()
    api = make_session(
        client,
        tools=[make_demo_tool()],
        session={"id": client.session_id, "model": "duplex-demo", "tools": []},
    )

    await api.start()

    assert client.connected is True
    assert client.created_session is not None
    assert client.created_extension == {}
    assert client.created_session["tools"] == [
        {
            "type": "function",
            "name": "demo_tool",
            "description": "double one value",
            "parameters": DemoInput.model_json_schema(),
        }
    ]
    await api.aclose()


@pytest.mark.asyncio
async def test_duplex_submit_maps_audio_and_batched_tool_results() -> None:
    client = FakeDuplexClient()
    api = make_session(client)

    await api.submit(AudioChunkInput(data=b"pcm"))
    await api.submit(AudioCommitInput())
    await api.submit(ContextItemRetrieveInput())
    await api.submit(ContextItemRetrieveInput(item_id="question-1"))
    await api.submit(
        ContextItemUpdateInput(
            item_id="question-1",
            text="原问题\n验证标记：CANARY-1234",
        )
    )
    await api.submit(
        ToolResultBatchInput(
            results=(
                ToolResultInput(call_id="call-1", output="one"),
                ToolResultInput(call_id="call-2", output="two"),
            )
        )
    )

    assert client.audio_chunks == [b"pcm"]
    assert client.audio_commits == 1
    assert client.retrieved_conversation_items == [None, [{"id": "question-1"}]]
    assert client.updated_conversation_items == [
        [
            {
                "id": "question-1",
                "content": [
                    {
                        "type": "input_text",
                        "text": "原问题\n验证标记：CANARY-1234",
                    }
                ],
            }
        ]
    ]
    assert client.conversation_items == [
        [
            {
                "role": "tool",
                "call_id": "call-1",
                "content": [{"type": "input_text", "text": "one"}],
            },
            {
                "role": "tool",
                "call_id": "call-2",
                "content": [{"type": "input_text", "text": "two"}],
            },
        ]
    ]
    await api.aclose()


@pytest.mark.asyncio
async def test_duplex_cancels_response_and_maps_ack() -> None:
    client = FakeDuplexClient()
    api = make_session(client)

    await api.cancel_response()

    mapped = api._map_server_event(
        {"type": "response.canceled", "event_id": "event_17"}
    )

    assert len(mapped) == 1
    assert client.response_cancels == 1
    assert isinstance(mapped[0], StreamResponseCanceledEvent)
    assert mapped[0].provider_event_id == "event_17"


@pytest.mark.asyncio
async def test_duplex_rejects_text_as_an_ordinary_user_query() -> None:
    api = make_session(FakeDuplexClient())

    with pytest.raises(TypeError, match="user queries require audio"):
        await api.submit("普通文本问题")

    await api.aclose()


def test_duplex_maps_question_id_from_transcription() -> None:
    api = make_session(FakeDuplexClient())

    mapped = api._map_server_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "question_id": "question-1",
            "transcript": "查天气",
        }
    )

    assert len(mapped) == 1
    assert mapped[0].item_id == "question-1"


def test_duplex_maps_provider_items_as_one_batch_without_response_id() -> None:
    api = make_session(FakeDuplexClient())

    mapped = api._map_server_event(
        {
            "type": "response.function_call_arguments.done",
            "event_id": "event-fc",
            "items": [
                {
                    "call_id": "call-1",
                    "name": "demo_tool",
                    "arguments": '{"value":2}',
                },
                {
                    "call_id": "call-2",
                    "name": "demo_tool",
                    "arguments": '{"value":3}',
                },
            ],
        }
    )

    assert len(mapped) == 2
    assert all(isinstance(event, StreamToolCallEvent) for event in mapped)
    assert [event.group_id for event in mapped] == ["event-fc", "event-fc"]
    assert [event.group_size for event in mapped] == [2, 2]
    assert [event.item_id for event in mapped] == [None, None]


def test_duplex_maps_retrieved_context_to_public_event() -> None:
    api = make_session(FakeDuplexClient())

    mapped = api._map_server_event(
        {
            "type": "conversation.item.retrieved",
            "event_id": "event-context",
            "items": [{"id": "question-1", "role": "user"}],
        }
    )

    assert len(mapped) == 1
    event = mapped[0]
    assert isinstance(event, StreamContextRetrievedEvent)
    assert event.items == ({"id": "question-1", "role": "user"},)


def test_duplex_events_map_function_calls_and_audio() -> None:
    api = make_session(FakeDuplexClient())

    mapped = api._map_server_event(
        {
            "type": "response.function_call_arguments.done",
            "event_id": "event-fc",
            "response_id": "response-1",
            "items": [
                {
                    "call_id": "call-1",
                    "name": "demo_tool",
                    "arguments": '{"value":2}',
                }
            ],
        }
    ) + api._map_server_event(
        {
            "type": "response.output_audio.delta",
            "response_id": "response-1",
            "delta": base64.b64encode(b"audio").decode("ascii"),
        }
    )

    assert len(mapped) == 2
    tool_event = mapped[0]
    assert isinstance(tool_event, StreamToolCallEvent)
    assert tool_event.group_id == "response-1"
    assert tool_event.group_size == 1
    assert tool_event.tool_call.run_id == "call-1"
    assert tool_event.tool_call.tool_name == "demo_tool"
    assert tool_event.tool_call.arguments == {"value": 2}
    audio_event = mapped[1]
    assert isinstance(audio_event, StreamAudioDeltaEvent)
    assert audio_event.delta == b"audio"


def test_duplex_keeps_recoverable_invalid_function_call_for_failed_output() -> None:
    api = make_session(FakeDuplexClient())

    mapped = api._map_server_event(
        {
            "type": "response.function_call_arguments.done",
            "response_id": "response-1",
            "items": [
                {
                    "call_id": "call-invalid",
                    "name": "demo_tool",
                    "arguments": "{invalid-json",
                }
            ],
        }
    )

    assert len(mapped) == 1
    event = mapped[0]
    assert isinstance(event, StreamToolCallEvent)
    assert event.tool_call.run_id == "call-invalid"
    assert event.input_error is not None


@pytest.mark.asyncio
async def test_duplex_events_is_the_single_mapped_provider_lane() -> None:
    client = FakeDuplexClient(
        events=[
            {
                "type": "response.output_audio.delta",
                "response_id": "response-1",
                "delta": base64.b64encode(b"audio").decode("ascii"),
            },
            {"type": "session.closed"},
        ]
    )
    api = make_session(client)

    events = [event async for event in api.events()]

    assert len(events) == 1
    assert isinstance(events[0], StreamAudioDeltaEvent)
    assert events[0].delta == b"audio"
    await api.aclose()
