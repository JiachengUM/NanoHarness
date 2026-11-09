from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest

from aicore.v2.experiments.duplex_speech_shell.backend import (
    RawDuplexSpeechBackend,
    build_backend_for_client,
)
from aicore.v2.experiments.duplex_speech_shell.events import (
    AsrCompleted,
    AsrDelta,
    AsrFailed,
    AsrStarted,
    SpeechShellClosed,
    SpeechShellError,
    TtsAudioDelta,
    TtsCompleted,
    TtsStarted,
)


class FakeRawDuplexClient:
    session_id = "session-1"

    def __init__(self) -> None:
        self.calls: list[object] = []
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def connect(self) -> None:
        self.calls.append("connect")

    async def session_create(
        self,
        session: dict[str, Any],
        extension: dict[str, Any],
    ) -> None:
        self.calls.append(("session_create", session, extension))

    async def recv_event(self) -> dict[str, Any]:
        self.calls.append("receive")
        return await self.events.get()

    async def input_audio_append(self, data: bytes) -> None:
        self.calls.append(("audio", data))

    async def input_audio_commit(self) -> None:
        self.calls.append("audio-commit")

    async def speech_text_append(self, speech_id: str, text: str) -> None:
        self.calls.append(("append", speech_id, text))

    async def speech_text_commit(self, speech_id: str, text: str) -> None:
        self.calls.append(("commit", speech_id, text))

    async def close(self) -> None:
        self.calls.append("close")


def make_backend() -> tuple[RawDuplexSpeechBackend, FakeRawDuplexClient]:
    client = FakeRawDuplexClient()
    return (
        RawDuplexSpeechBackend(
            client,
            session={"instructions": "transport", "tools": []},
            extension={"dialog": {"continuous": True}},
        ),
        client,
    )


def test_compatibility_raw_client_factory_gets_browser_profile() -> None:
    client = FakeRawDuplexClient()

    backend = build_backend_for_client(client)

    assert backend.session["id"] == "session-1"
    assert backend.session["tools"] == []
    assert backend.session["audio"]["input"]["format"] == {
        "type": "pcm_s16le",
        "rate": 16_000,
    }
    assert backend.session["audio"]["output"]["format"] == {
        "type": "pcm_s16le",
        "rate": 24_000,
    }


@pytest.mark.asyncio
async def test_connect_finishes_handshake_before_receive_and_close_is_idempotent() -> None:
    backend, client = make_backend()

    await backend.connect()
    await backend.connect()
    client.events.put_nowait(
        {"type": "conversation.item.input_audio_transcription.started"}
    )
    assert await backend.receive_event() == AsrStarted()
    await backend.close()
    await backend.close()

    assert client.calls[:3] == [
        "connect",
        (
            "session_create",
            {"instructions": "transport", "tools": []},
            {"dialog": {"continuous": True}},
        ),
        "receive",
    ]
    assert client.calls.count("close") == 1
    assert client.calls.count("connect") == 1
    assert sum(
        isinstance(call, tuple) and call[0] == "session_create"
        for call in client.calls
    ) == 1


@pytest.mark.asyncio
async def test_forwards_only_the_raw_commands_required_by_speech_shell() -> None:
    backend, client = make_backend()

    await backend.append_audio(b"pcm")
    await backend.commit_audio()
    await backend.append_speech_text("speech-1", "前半句")
    await backend.commit_speech_text("speech-1", "末句")

    assert client.calls == [
        ("audio", b"pcm"),
        "audio-commit",
        ("append", "speech-1", "前半句"),
        ("commit", "speech-1", "末句"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            {"type": "conversation.item.input_audio_transcription.started"},
            AsrStarted(),
        ),
        (
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "delta": " 增量 ",
            },
            AsrDelta("增量"),
        ),
        (
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": " 最终文本 ",
            },
            AsrCompleted("最终文本"),
        ),
        (
            {
                "type": "conversation.item.input_audio_transcription.failed",
                "error": {"message": "bad asr"},
            },
            AsrFailed("{'message': 'bad asr'}"),
        ),
        (
            {
                "type": "response.output_audio.started",
                "response_id": "response-1",
                "tts_type": "chat_tts_text",
            },
            TtsStarted("response-1", "chat_tts_text"),
        ),
        (
            {
                "type": "response.output_audio.delta",
                "response_id": "response-1",
                "delta": base64.b64encode(b"pcm").decode(),
            },
            TtsAudioDelta("response-1", b"pcm"),
        ),
        (
            {
                "type": "response.output_audio.done",
                "response_id": "response-1",
            },
            TtsCompleted("response-1"),
        ),
        ({"type": "session.closed"}, SpeechShellClosed()),
        ({"type": "error", "error": "boom"}, SpeechShellError("boom")),
    ],
)
async def test_maps_raw_provider_events_to_narrow_values(
    raw: dict[str, Any],
    expected: object,
) -> None:
    backend, client = make_backend()
    client.events.put_nowait(raw)

    assert await backend.receive_event() == expected


@pytest.mark.asyncio
async def test_ignores_summary_native_and_invalid_payload_inside_adapter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend, client = make_backend()
    for raw in (
        {"type": "response.done", "response_id": "response-1"},
        {"type": "response.output_text.done", "text": "native answer"},
        {"type": "response.function_call_arguments.done", "name": "tool"},
        {"type": "response.output_audio.delta", "delta": "not-base64"},
        {"type": "unknown.provider.event"},
        {"type": "conversation.item.input_audio_transcription.completed", "text": "ok"},
    ):
        client.events.put_nowait(raw)

    assert await backend.receive_event() == AsrCompleted("ok")
    assert client.calls.count("receive") == 6
    assert "invalid output audio payload" in caplog.text


@pytest.mark.asyncio
async def test_response_done_cannot_hide_the_audio_terminal() -> None:
    backend, client = make_backend()
    client.events.put_nowait({"type": "response.done", "response_id": "response-1"})
    client.events.put_nowait(
        {"type": "response.output_audio.done", "response_id": "response-1"}
    )

    assert await backend.receive_event() == TtsCompleted("response-1")
    assert client.calls.count("receive") == 2
