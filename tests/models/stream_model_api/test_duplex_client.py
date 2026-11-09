from __future__ import annotations

from typing import Any

import pytest

from aicore.models.stream_model_api.duplex.duplex_client import DuplexClient


class FakeTransport:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False
        self.sent: list[dict[str, Any]] = []
        self.received: list[dict[str, Any]] = []
        self.receive_calls = 0

    async def connect(self) -> object:
        self.connected = True
        return object()

    async def send_event(self, event: dict[str, Any]) -> None:
        self.sent.append(event)

    async def receive_event(self) -> dict[str, Any]:
        self.receive_calls += 1
        return self.received.pop(0)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_core_client_creates_injected_session_without_project_config() -> None:
    transport = FakeTransport()
    transport.received.append(
        {"type": "session.created", "session": {"id": "dialog-1"}}
    )
    client = DuplexClient(
        transport=transport,
        session_id="stream-session-1",
    )

    await client.connect()
    await client.session_create(
        {
            "id": client.session_id,
            "model": "duplex-demo",
            "instructions": "provider only",
            "tools": [],
        },
        {"asr": {"extra": {}}},
    )

    assert transport.connected is True
    assert transport.sent == [
        {
            "type": "session.create",
            "event_id": "event_1",
            "session": {
                "id": "stream-session-1",
                "model": "duplex-demo",
                "instructions": "provider only",
                "tools": [],
            },
            "extension": {"asr": {"extra": {}}},
        }
    ]
    assert client.dialog_id == "dialog-1"
    assert transport.receive_calls == 1


@pytest.mark.asyncio
async def test_close_does_not_compete_with_model_event_consumer() -> None:
    transport = FakeTransport()
    transport.received.append(
        {"type": "session.created", "session": {"id": "dialog-1"}}
    )
    client = DuplexClient(transport=transport)
    await client.connect()
    await client.session_create({"id": client.session_id}, {})

    await client.close()

    assert transport.receive_calls == 1
    assert transport.sent[-1] == {
        "type": "session.close",
        "event_id": "event_2",
    }
    assert transport.closed is True


@pytest.mark.asyncio
async def test_core_client_maps_audio_and_context_commands() -> None:
    transport = FakeTransport()
    client = DuplexClient(transport=transport)

    await client.input_audio_append(b"pcm")
    await client.input_audio_commit()
    await client.response_cancel()
    await client.conversation_item_update(
        [
            {
                "id": "question-1",
                "content": [{"type": "input_text", "text": "x"}],
            }
        ]
    )
    await client.conversation_item_retrieve()
    await client.conversation_item_retrieve([{"id": "question-1"}])

    assert transport.sent == [
        {"type": "input_audio_buffer.append", "audio": "cGNt"},
        {"type": "input_audio_buffer.commit", "event_id": "event_1"},
        {"type": "response.cancel"},
        {
            "type": "conversation.item.update",
            "event_id": "event_2",
            "items": [
                {
                    "id": "question-1",
                    "content": [{"type": "input_text", "text": "x"}],
                }
            ],
        },
        {
            "type": "conversation.item.retrieve",
            "event_id": "event_3",
            "items": [],
        },
        {
            "type": "conversation.item.retrieve",
            "event_id": "event_4",
            "items": [{"id": "question-1"}],
        },
    ]
