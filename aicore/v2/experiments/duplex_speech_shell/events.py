"""Provider-independent events emitted by a speech-shell backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class AsrStarted:
    """The speech service started transcribing a user utterance."""


@dataclass(frozen=True, slots=True)
class AsrDelta:
    """An incremental user transcription."""

    text: str


@dataclass(frozen=True, slots=True)
class AsrCompleted:
    """The final user transcription."""

    text: str


@dataclass(frozen=True, slots=True)
class AsrFailed:
    """The current transcription failed."""

    message: str = ""


@dataclass(frozen=True, slots=True)
class TtsStarted:
    """A TTS response started producing audio."""

    response_id: str
    tts_type: str


@dataclass(frozen=True, slots=True)
class TtsAudioDelta:
    """A decoded PCM16 audio chunk for a TTS response."""

    response_id: str | None
    pcm_s16le: bytes


@dataclass(frozen=True, slots=True)
class TtsCompleted:
    """A TTS response reached its authoritative audio terminal."""

    response_id: str | None


@dataclass(frozen=True, slots=True)
class SpeechShellClosed:
    """The speech backend connection closed."""


@dataclass(frozen=True, slots=True)
class SpeechShellError:
    """The speech backend reported an error."""

    message: str


SpeechShellEvent: TypeAlias = (
    AsrStarted
    | AsrDelta
    | AsrCompleted
    | AsrFailed
    | TtsStarted
    | TtsAudioDelta
    | TtsCompleted
    | SpeechShellClosed
    | SpeechShellError
)
