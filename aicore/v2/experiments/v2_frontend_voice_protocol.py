"""Typed browser-voice capabilities shared by v2 frontend sessions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrowserVoiceSession(Protocol):
    """Provider-neutral browser media lifecycle.

    Implementations deliberately keep their provider-specific ASR/TTS state
    machines behind this facade.
    """

    async def start(self) -> dict[str, Any]: ...

    async def stop(self) -> None: ...

    async def open_microphone(self) -> None: ...

    async def close_microphone(self) -> None: ...

    async def feed_audio(self, chunk: bytes) -> None: ...

    async def on_playback_ended(self) -> None: ...


@runtime_checkable
class VoiceTextQueryCapability(Protocol):
    """Optional legacy voice-owned text query submission."""

    async def submit_text_query(self, text: str) -> None: ...


@runtime_checkable
class ExternalAgentSpeechSink(Protocol):
    """Optional sink used when an external Agent supplies TTS text."""

    def on_agent_event(self, event: Any, *, message_id: str | None) -> None: ...


__all__ = [
    "BrowserVoiceSession",
    "ExternalAgentSpeechSink",
    "VoiceTextQueryCapability",
]
