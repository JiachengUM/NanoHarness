from __future__ import annotations

import wave
from pathlib import Path

import pytest

from aicore.models.stream_model_api.duplex.config import DuplexConfig
from aicore.v2.experiments.duplex_speech_shell.local_audio import (
    BackendAudioInputSink,
    build_local_audio,
    read_pcm16_mono_16khz,
)

class FakeBackend:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    async def append_audio(self, data: bytes) -> None:
        self.chunks.append(data)


@pytest.mark.asyncio
async def test_backend_audio_sink_adapts_local_audio_method_name() -> None:
    backend = FakeBackend()

    await BackendAudioInputSink(backend).input_audio_append(b"pcm")  # type: ignore[arg-type]

    assert backend.chunks == [b"pcm"]


def test_file_audio_accumulates_but_realtime_audio_does_not() -> None:
    backend = FakeBackend()
    config = DuplexConfig()

    file_audio = build_local_audio(backend, config, file_mode=True)  # type: ignore[arg-type]
    realtime_audio = build_local_audio(backend, config, file_mode=False)  # type: ignore[arg-type]

    assert file_audio.accumulate_output is True
    assert realtime_audio.accumulate_output is False
    assert isinstance(file_audio.client, BackendAudioInputSink)


def test_wav_reader_validates_pcm16_mono_16khz(tmp_path: Path) -> None:
    valid = tmp_path / "valid.wav"
    with wave.open(str(valid), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x01\x02")
    assert read_pcm16_mono_16khz(str(valid)) == b"\x01\x02"

    invalid = tmp_path / "invalid.wav"
    with wave.open(str(invalid), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00" * 4)
    with pytest.raises(ValueError, match="mono PCM16"):
        read_pcm16_mono_16khz(str(invalid))
