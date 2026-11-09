from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from aicore.models.stream_model_api.duplex.duplex_events import encode_client_event
from aicore.models.stream_model_api.duplex.websocket_transport import (
    DuplexWebSocketTransport,
    build_app_auth_headers,
    get_websocket_response_header,
)
from aicore.models.stream_model_api.duplex.diagnostics import print_duplex_event


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.received: list[str | bytes] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str | bytes:
        return self.received.pop(0)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_connect_uses_websockets_15_arguments() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    websocket = FakeWebSocket()

    async def connect(uri: str, **kwargs: Any) -> FakeWebSocket:
        calls.append((uri, kwargs))
        return websocket

    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        auth_mode="x-api-key",
        connect_func=connect,
    )

    assert await transport.connect() is websocket
    assert calls == [
        (
            "wss://example.invalid",
            {
                "additional_headers": {"X-Api-Key": "key"},
                "ping_interval": None,
                "proxy": None,
            },
        )
    ]


@pytest.mark.asyncio
async def test_connect_logs_server_log_id(caplog: pytest.LogCaptureFixture) -> None:
    websocket = FakeWebSocket()
    websocket.response = SimpleNamespace(headers={"X-Tt-Logid": "dialog-log-1"})

    async def connect(_uri: str, **_kwargs: Any) -> FakeWebSocket:
        return websocket

    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        connect_func=connect,
    )

    with caplog.at_level("INFO"):
        await transport.connect()

    assert "Duplex connected log_id=dialog-log-1" in caplog.text


@pytest.mark.asyncio
async def test_auto_auth_retries_only_after_401() -> None:
    calls: list[dict[str, str]] = []
    websocket = FakeWebSocket()

    class Unauthorized(RuntimeError):
        response = SimpleNamespace(status_code=401)

    async def connect(_uri: str, **kwargs: Any) -> FakeWebSocket:
        headers = kwargs["additional_headers"]
        calls.append(headers)
        if len(calls) < 3:
            raise Unauthorized("HTTP 401")
        return websocket

    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="REDACTED",
        auth_mode="auto",
        connect_func=connect,
        connect_id_factory=lambda: "connect-1",
    )

    assert await transport.connect() is websocket
    assert calls[0] == build_app_auth_headers(
        access_key="REDACTED",
        connect_id_factory=lambda: "connect-1",
    )
    assert calls[1] == {"X-Api-Key": "access-key"}
    assert calls[2] == {"Authorization": "Bearer access-key"}


@pytest.mark.asyncio
async def test_send_and_receive_json_objects() -> None:
    websocket = FakeWebSocket()
    websocket.received.append(b'{"type":"session.created"}')
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    await transport.send_event({"type": "session.close"})

    assert websocket.sent == ['{"type":"session.close"}']
    assert await transport.receive_event() == {"type": "session.created"}


@pytest.mark.asyncio
async def test_receive_observer_gets_original_provider_payload() -> None:
    websocket = FakeWebSocket()
    payload = '{ "type": "session.created", "session": {"id": "s1"} }'
    websocket.received.append(payload)
    observed: list[tuple[str, dict[str, Any], str]] = []
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=lambda direction, event, raw: observed.append(
            (direction, event, raw)
        ),
    )

    event = await transport.receive_event()

    assert observed == [("downstream", event, payload)]


@pytest.mark.asyncio
async def test_send_logs_serialized_non_audio_event_after_write(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )
    event = {
        "type": "conversation.item.create",
        "items": [
            {
                "role": "tool",
                "call_id": "call-1",
                "content": [{"type": "input_text", "text": "result"}],
            }
        ],
    }

    await transport.send_event(event)

    assert websocket.sent == [
        '{"type":"conversation.item.create","items":[{"role":"tool",'
        '"call_id":"call-1","content":[{"type":"input_text",'
        '"text":"result"}]}]}'
    ]
    payload = websocket.sent[0]
    assert capsys.readouterr().out == (
        "\033[1;32m[UP -> DUPLEX]\033[0m "
        f"type=conversation.item.create bytes={len(payload.encode('utf-8'))} "
        f"{payload}\n"
    )


@pytest.mark.asyncio
async def test_send_does_not_log_audio_chunks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    await transport.send_event(
        {"type": "input_audio_buffer.append", "audio": "AAAA"}
    )

    assert websocket.sent == [
        '{"type":"input_audio_buffer.append","audio":"AAAA"}'
    ]
    assert capsys.readouterr().out == ""


@pytest.mark.asyncio
async def test_context_retrieve_request_uses_distinct_log_color(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    await transport.send_event(
        {
            "type": "conversation.item.retrieve",
            "event_id": "event-1",
            "items": [{"id": "question-1"}],
        }
    )

    output = capsys.readouterr().out
    assert "\033[1;35m[DUPLEX CONTEXT]\033[0m" in output
    assert "type=conversation.item.retrieve" in output
    assert '"id": "question-1"' in output


@pytest.mark.asyncio
async def test_receive_highlights_non_delta_server_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    websocket.received.append(
        '{"type":"response.function_call_arguments.done","items":[]}'
    )
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    event = await transport.receive_event()

    payload = encode_client_event(event)
    assert capsys.readouterr().out == (
        "\033[1;34m[DOWN <- DUPLEX]\033[0m "
        "type=response.function_call_arguments.done "
        f"bytes={len(payload.encode('utf-8'))} {payload}\n"
    )


@pytest.mark.asyncio
async def test_retrieved_context_uses_distinct_log_color_and_full_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    websocket.received.append(
        '{"type":"conversation.item.retrieved","items":['
        '{"id":"question-1","role":"user","content":['
        '{"type":"input_text","text":"查天气"}]}]}'
    )
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    event = await transport.receive_event()

    assert event["items"][0]["id"] == "question-1"
    output = capsys.readouterr().out
    assert "\033[1;35m[DUPLEX CONTEXT]\033[0m" in output
    assert "type=conversation.item.retrieved" in output
    assert '"text": "查天气"' in output
    assert "[DOWN <- DUPLEX]" not in output


@pytest.mark.asyncio
async def test_receive_does_not_log_delta_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    websocket.received.append(
        '{"type":"response.output_text.delta","delta":"sun"}'
    )
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    assert await transport.receive_event() == {
        "type": "response.output_text.delta",
        "delta": "sun",
    }
    assert capsys.readouterr().out == ""


@pytest.mark.asyncio
async def test_receive_logs_input_audio_transcription_delta(
    capsys: pytest.CaptureFixture[str],
) -> None:
    websocket = FakeWebSocket()
    websocket.received.append(
        '{"type":"conversation.item.input_audio_transcription.delta",'
        '"item_id":"item-1","delta":"查"}'
    )
    transport = DuplexWebSocketTransport(
        endpoint_url="wss://example.invalid",
        api_key="key",
        websocket=websocket,
        event_observer=print_duplex_event,
    )

    event = await transport.receive_event()

    payload = encode_client_event(event)
    assert capsys.readouterr().out == (
        "\033[1;34m[DOWN <- DUPLEX]\033[0m "
        "type=conversation.item.input_audio_transcription.delta "
        f"bytes={len(payload.encode('utf-8'))} {payload}\n"
    )


def test_get_websocket_response_header_supports_both_layouts() -> None:
    legacy = SimpleNamespace(response_headers={"X-Tt-Logid": "legacy"})
    current = SimpleNamespace(
        response=SimpleNamespace(headers={"X-Tt-Logid": "current"})
    )

    assert get_websocket_response_header(legacy, "X-Tt-Logid") == "legacy"
    assert get_websocket_response_header(current, "X-Tt-Logid") == "current"
