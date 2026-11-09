from __future__ import annotations

import pytest

from aicore.models.stream_model_api.duplex.duplex_events import (
    TYPE_INPUT_AUDIO_BUFFER_APPEND,
    TYPE_SESSION_CREATE,
    build_input_audio_append_event,
    build_session_create_event,
    decode_server_event,
)


def test_build_input_audio_append_event_base64_encodes_payload() -> None:
    assert build_input_audio_append_event(b"pcm") == {
        "type": TYPE_INPUT_AUDIO_BUFFER_APPEND,
        "audio": "cGNt",
    }


def test_build_session_create_event_keeps_session_and_extension() -> None:
    assert build_session_create_event(
        event_id="event_1",
        session={"id": "session-1"},
        extension={"dialog": {"extra": {}}},
    ) == {
        "type": TYPE_SESSION_CREATE,
        "event_id": "event_1",
        "session": {"id": "session-1"},
        "extension": {"dialog": {"extra": {}}},
    }


def test_decode_server_event_accepts_text_and_bytes() -> None:
    assert decode_server_event('{"type":"session.created"}') == {
        "type": "session.created"
    }
    assert decode_server_event(b'{"type":"session.closed"}') == {
        "type": "session.closed"
    }


def test_decode_server_event_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        decode_server_event("[]")
