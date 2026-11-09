from __future__ import annotations

from typing import Any

from aicore.models.stream_model_api.duplex.config import DuplexConfig
from aicore.v2.experiments.duplex_speech_shell.profile import (
    BROWSER_OUTPUT_FORMAT,
    DUPLEX_TRANSPORT_INSTRUCTIONS,
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
    build_browser_speech_shell_session_config,
    build_speech_shell_session_config,
    build_v2_duplex_session_config,
)


def test_compatibility_transform_disables_server_tools_without_mutation() -> None:
    base_session: dict[str, Any] = {
        "instructions": "old",
        "tools": [{"type": "function", "name": "server_tool"}],
        "audio": {"input": {}, "output": {}},
    }
    base_extension = {"dialog": {"extra": {"keep": True}}}

    session, extension = build_v2_duplex_session_config(
        base_session,
        base_extension,
    )

    assert session["instructions"] == DUPLEX_TRANSPORT_INSTRUCTIONS
    assert session["tools"] == []
    assert extension == base_extension
    assert session is not base_session
    assert extension is not base_extension
    assert base_session["instructions"] == "old"
    assert base_session["tools"] == [
        {"type": "function", "name": "server_tool"}
    ]


def test_generic_profile_preserves_configured_audio_formats() -> None:
    config = DuplexConfig(
        instructions="native answer",
        asr_format="ogg_opus",
        tts_format="pcm",
    )

    session, extension = build_speech_shell_session_config(
        config,
        session_id="local-session",
    )

    assert session["id"] == "local-session"
    assert session["instructions"] == DUPLEX_TRANSPORT_INSTRUCTIONS
    assert session["tools"] == []
    assert session["audio"]["input"]["format"] == {
        "type": "ogg_opus",
        "rate": 16_000,
    }
    assert session["audio"]["output"]["format"] == {
        "type": "pcm",
        "rate": 24_000,
    }
    assert extension["asr"]["extra"]["enable_custom_vad"] is True
    assert config.instructions == "native answer"
    assert config.asr_format == "ogg_opus"
    assert config.tts_format == "pcm"


def test_browser_profile_delegates_to_fixed_pcm_formats_without_mutation() -> None:
    config = DuplexConfig(
        instructions="native answer",
        asr_format="ogg_opus",
        tts_format="ogg_opus",
    )

    session, _ = build_browser_speech_shell_session_config(
        config,
        session_id="browser-session",
    )

    assert INPUT_SAMPLE_RATE == 16_000
    assert OUTPUT_SAMPLE_RATE == 24_000
    assert BROWSER_OUTPUT_FORMAT == "f32le"
    assert session["id"] == "browser-session"
    assert session["instructions"] == DUPLEX_TRANSPORT_INSTRUCTIONS
    assert session["tools"] == []
    assert session["audio"]["input"]["format"] == {
        "type": "pcm_s16le",
        "rate": 16_000,
    }
    assert session["audio"]["output"]["format"] == {
        "type": "pcm_s16le",
        "rate": 24_000,
    }
    assert config.asr_format == "ogg_opus"
    assert config.tts_format == "ogg_opus"
