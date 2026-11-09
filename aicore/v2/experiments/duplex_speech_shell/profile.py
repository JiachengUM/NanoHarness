"""Provider session profile for Duplex used strictly as an ASR/TTS shell."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from aicore.models.stream_model_api.duplex.config import (
    PCM_S16LE,
    DuplexConfig,
    build_duplex_session_config,
)

INPUT_SAMPLE_RATE = 16_000
OUTPUT_SAMPLE_RATE = 24_000
BROWSER_OUTPUT_FORMAT = "f32le"

DUPLEX_TRANSPORT_INSTRUCTIONS = (
    "You are a speech transport layer for an external v2 agent. "
    "Do not answer user audio by yourself. Keep server-side tools disabled. "
    "Only synthesize text that the client sends through speech_text_buffer events."
)


def build_v2_duplex_session_config(
    base_session: dict[str, Any],
    base_extension: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Disable native answers/tools without mutating a caller-owned profile."""

    session = deepcopy(base_session)
    extension = deepcopy(base_extension)
    session["instructions"] = DUPLEX_TRANSPORT_INSTRUCTIONS
    session["tools"] = []
    return session, extension


def build_browser_speech_shell_session_config(
    config: DuplexConfig,
    *,
    session_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the fixed PCM browser profile without changing ``config``."""

    browser_config = replace(
        config,
        asr_format=PCM_S16LE,
        tts_format=PCM_S16LE,
    )
    return build_speech_shell_session_config(
        browser_config,
        session_id=session_id,
    )


def build_speech_shell_session_config(
    config: DuplexConfig,
    *,
    session_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a transport-only profile while preserving configured formats."""

    session, extension = build_duplex_session_config(
        config,
        session_id=session_id,
    )
    return build_v2_duplex_session_config(session, extension)


__all__ = [
    "BROWSER_OUTPUT_FORMAT",
    "DUPLEX_TRANSPORT_INSTRUCTIONS",
    "INPUT_SAMPLE_RATE",
    "OUTPUT_SAMPLE_RATE",
    "build_browser_speech_shell_session_config",
    "build_speech_shell_session_config",
    "build_v2_duplex_session_config",
]
