"""Explicit synchronous state transitions for one speech-shell session."""

from __future__ import annotations

from dataclasses import dataclass, field


CUSTOM_TTS_TYPES = frozenset({"chat_tts_text", "external_rag"})


@dataclass(slots=True)
class VoiceTurnState:
    """Own mutable ASR, TTS-response, and client-playback state.

    The class deliberately performs no I/O. Callers use the returned booleans
    to decide whether to interrupt an Agent TTS generation or forward audio.
    """

    listening: bool = False
    user_speaking: bool = False
    barge_in_confirmed: bool = False
    accepted_response_ids: set[str] = field(default_factory=set)
    current_response_id: str | None = None
    playback_pending: bool = False

    def reset(self) -> None:
        """Return the session to its initial, stopped state."""

        self.listening = False
        self.user_speaking = False
        self.barge_in_confirmed = False
        self.accepted_response_ids.clear()
        self.current_response_id = None
        self.playback_pending = False

    def open_microphone(self) -> None:
        self.listening = True

    def close_microphone(self) -> None:
        self.listening = False
        self.user_speaking = False
        self.barge_in_confirmed = False

    def asr_started(self, output_active: bool) -> bool:
        """Record ASR start and report whether current output must be interrupted."""

        if not self.listening:
            return False

        self.user_speaking = True
        self.barge_in_confirmed = output_active or self.playback_pending
        return self.barge_in_confirmed

    def asr_finished(self) -> None:
        self.user_speaking = False
        self.barge_in_confirmed = False

    def should_interrupt_for_final(self, output_active: bool) -> bool:
        """Confirm a late barge-in once, before final-ASR cleanup."""

        if self.barge_in_confirmed:
            return False
        if not output_active:
            return False
        self.barge_in_confirmed = True
        return True

    def interrupt_output(self) -> None:
        """Forget locally accepted output without sending provider cancellation."""

        self.accepted_response_ids.clear()
        self.current_response_id = None
        self.playback_pending = False

    def accept_tts_started(
        self,
        response_id: str,
        tts_type: str,
        output_active: bool,
    ) -> bool:
        """Accept only active external-Agent TTS, never native Duplex output."""

        if (
            not response_id
            or tts_type not in CUSTOM_TTS_TYPES
            or not output_active
            or self.user_speaking
        ):
            return False

        self.accepted_response_ids.clear()
        self.accepted_response_ids.add(response_id)
        self.current_response_id = response_id
        return True

    def accept_tts_audio(self, response_id: str | None) -> bool:
        """Return whether an audio chunk belongs to the accepted response."""

        accepted_id = response_id or self.current_response_id
        return bool(
            accepted_id
            and not self.user_speaking
            and accepted_id in self.accepted_response_ids
        )

    def complete_tts(self, response_id: str | None) -> bool:
        """Finish an accepted response while leaving browser playback pending."""

        completed_id = response_id or self.current_response_id
        if not completed_id or completed_id not in self.accepted_response_ids:
            return False

        self.accepted_response_ids.discard(completed_id)
        if self.current_response_id == completed_id:
            self.current_response_id = None
        return True

    def mark_playback_pending(self) -> None:
        self.playback_pending = True

    def playback_ended(self) -> None:
        self.playback_pending = False
