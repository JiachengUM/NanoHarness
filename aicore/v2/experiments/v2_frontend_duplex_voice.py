"""Compatibility exports for the v2 Duplex browser speech shell.

The implementation lives in :mod:`aicore.v2.experiments.duplex_speech_shell`.
This module remains so the existing backend injection path and external imports
do not change during the refactor.
"""

from aicore.v2.experiments.duplex_speech_shell.backend import (
    build_default_duplex_client,
)
from aicore.v2.experiments.duplex_speech_shell.frontend_bridge import (
    BrowserAudioOutput,
    DuplexFrontendVoiceBridge,
    FrontendVoiceBridge,
    pcm_s16le_to_f32le,
)

__all__ = [
    "BrowserAudioOutput",
    "DuplexFrontendVoiceBridge",
    "FrontendVoiceBridge",
    "build_default_duplex_client",
    "pcm_s16le_to_f32le",
]
