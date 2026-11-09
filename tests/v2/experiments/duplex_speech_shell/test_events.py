from dataclasses import FrozenInstanceError

import pytest

from aicore.v2.experiments.duplex_speech_shell.events import (
    AsrDelta,
    AsrFailed,
    TtsAudioDelta,
)


def test_speech_shell_event_values_are_immutable_and_keep_decoded_pcm() -> None:
    event = AsrDelta(text="你好")

    assert not hasattr(event, "__dict__")
    with pytest.raises(FrozenInstanceError):
        event.text = "changed"  # type: ignore[misc]
    assert AsrFailed().message == ""
    assert TtsAudioDelta("response-1", b"pcm").pcm_s16le == b"pcm"
