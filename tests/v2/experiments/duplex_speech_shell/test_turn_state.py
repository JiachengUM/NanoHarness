import pytest

from aicore.v2.experiments.duplex_speech_shell.turn_state import VoiceTurnState


def test_microphone_and_asr_lifecycle() -> None:
    state = VoiceTurnState()

    assert not state.asr_started(output_active=True)
    assert not state.user_speaking

    state.open_microphone()
    assert state.asr_started(output_active=False) is False
    assert state.user_speaking
    assert not state.barge_in_confirmed

    state.asr_finished()
    assert not state.user_speaking
    assert not state.barge_in_confirmed

    state.close_microphone()
    assert not state.listening


@pytest.mark.parametrize("output_active", [True, False])
def test_asr_started_interrupts_active_or_pending_output(output_active: bool) -> None:
    state = VoiceTurnState(listening=True, playback_pending=not output_active)

    assert state.asr_started(output_active=output_active)
    assert state.barge_in_confirmed
    assert not state.should_interrupt_for_final(output_active=True)


def test_final_asr_confirms_late_barge_in_only_once() -> None:
    state = VoiceTurnState(listening=True)

    assert not state.asr_started(output_active=False)
    assert state.should_interrupt_for_final(output_active=True)
    assert not state.should_interrupt_for_final(output_active=True)

    state.asr_finished()
    assert not state.barge_in_confirmed


@pytest.mark.parametrize("tts_type", ["chat_tts_text", "external_rag"])
def test_accepts_only_custom_tts_for_active_agent_output(tts_type: str) -> None:
    state = VoiceTurnState()

    assert state.accept_tts_started("response-1", tts_type, output_active=True)
    assert state.current_response_id == "response-1"
    assert state.accepted_response_ids == {"response-1"}


@pytest.mark.parametrize(
    ("response_id", "tts_type", "output_active", "user_speaking"),
    [
        ("", "chat_tts_text", True, False),
        ("response-1", "native", True, False),
        ("response-1", "chat_tts_text", False, False),
        ("response-1", "chat_tts_text", True, True),
    ],
)
def test_rejects_unowned_tts(
    response_id: str,
    tts_type: str,
    output_active: bool,
    user_speaking: bool,
) -> None:
    state = VoiceTurnState(user_speaking=user_speaking)

    assert not state.accept_tts_started(
        response_id,
        tts_type,
        output_active=output_active,
    )
    assert not state.accepted_response_ids
    assert state.current_response_id is None


def test_audio_and_done_fall_back_to_current_response() -> None:
    state = VoiceTurnState()
    assert state.accept_tts_started(
        "response-1",
        "chat_tts_text",
        output_active=True,
    )

    assert state.accept_tts_audio(None)
    state.mark_playback_pending()
    assert state.complete_tts(None)
    assert state.current_response_id is None
    assert not state.accepted_response_ids
    assert state.playback_pending

    state.playback_ended()
    assert not state.playback_pending


def test_old_or_speaking_audio_is_rejected() -> None:
    state = VoiceTurnState()
    assert state.accept_tts_started(
        "response-old",
        "external_rag",
        output_active=True,
    )
    assert state.accept_tts_started(
        "response-current",
        "external_rag",
        output_active=True,
    )

    assert state.accepted_response_ids == {"response-current"}
    assert not state.accept_tts_audio("response-old")
    state.user_speaking = True
    assert not state.accept_tts_audio("response-current")
    assert not state.complete_tts("response-old")


def test_interrupt_clears_output_but_preserves_turn_and_microphone_state() -> None:
    state = VoiceTurnState(listening=True, user_speaking=True)
    assert state.accept_tts_started(
        "response-1",
        "chat_tts_text",
        output_active=True,
    ) is False

    state.user_speaking = False
    assert state.accept_tts_started(
        "response-1",
        "chat_tts_text",
        output_active=True,
    )
    state.mark_playback_pending()
    state.barge_in_confirmed = True

    state.interrupt_output()

    assert state.listening
    assert state.barge_in_confirmed
    assert not state.accepted_response_ids
    assert state.current_response_id is None
    assert not state.playback_pending


def test_reset_clears_all_session_state() -> None:
    state = VoiceTurnState(
        listening=True,
        user_speaking=True,
        barge_in_confirmed=True,
        accepted_response_ids={"response-1"},
        current_response_id="response-1",
        playback_pending=True,
    )

    state.reset()

    assert state == VoiceTurnState()
