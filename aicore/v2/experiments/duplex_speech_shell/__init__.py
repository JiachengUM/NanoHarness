"""Duplex-backed ASR/TTS shell for the external v2 Agent."""

from aicore.v2.experiments.duplex_speech_shell.profile import (
    BROWSER_OUTPUT_FORMAT,
    DUPLEX_TRANSPORT_INSTRUCTIONS,
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
    build_browser_speech_shell_session_config,
    build_speech_shell_session_config,
    build_v2_duplex_session_config,
)

__all__ = [
    "BROWSER_OUTPUT_FORMAT",
    "DUPLEX_TRANSPORT_INSTRUCTIONS",
    "INPUT_SAMPLE_RATE",
    "OUTPUT_SAMPLE_RATE",
    "build_browser_speech_shell_session_config",
    "build_speech_shell_session_config",
    "build_v2_duplex_session_config",
]
