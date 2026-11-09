"""Local microphone/playback adapters for the speech shell."""

from __future__ import annotations

import asyncio
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from aicore.models.stream_model_api.duplex.config import DuplexConfig
from aicore.models.stream_model_api.duplex.local_audio import DuplexLocalAudio
from aicore.v2.experiments.duplex_speech_shell.backend import SpeechShellBackend

FILE_CHUNK_BYTES = 640
FILE_CHUNK_INTERVAL_SECONDS = 0.02


@dataclass(slots=True)
class BackendAudioInputSink:
    """Expose the method name expected by ``DuplexLocalAudio``."""

    backend: SpeechShellBackend

    async def input_audio_append(self, data: bytes) -> None:
        await self.backend.append_audio(data)


def build_local_audio(
    backend: SpeechShellBackend,
    config: DuplexConfig,
    *,
    file_mode: bool,
) -> DuplexLocalAudio:
    """Build realtime device I/O or a headless output accumulator."""

    return DuplexLocalAudio(
        client=BackendAudioInputSink(backend),
        config=config,
        accumulate_output=file_mode,
    )


def read_pcm16_mono_16khz(path_value: str) -> bytes:
    """Read raw PCM or validate and extract a WAV payload."""

    path = Path(path_value)
    if path.suffix.lower() != ".wav":
        data = path.read_bytes()
        if len(data) % 2:
            raise ValueError("Raw input must contain complete PCM16 samples")
        return data
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() != 16_000
            or source.getcomptype() != "NONE"
        ):
            raise ValueError("WAV input must be mono PCM16 at 16000 Hz")
        return source.readframes(source.getnframes())


async def send_audio_file(
    backend: SpeechShellBackend,
    path: str,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Stream one finite PCM file and commit its final input buffer once."""

    data = read_pcm16_mono_16khz(path)
    for position in range(0, len(data), FILE_CHUNK_BYTES):
        await backend.append_audio(data[position : position + FILE_CHUNK_BYTES])
        await sleep(FILE_CHUNK_INTERVAL_SECONDS)
    await backend.commit_audio()


__all__ = [
    "BackendAudioInputSink",
    "FILE_CHUNK_BYTES",
    "FILE_CHUNK_INTERVAL_SECONDS",
    "build_local_audio",
    "read_pcm16_mono_16khz",
    "send_audio_file",
]
