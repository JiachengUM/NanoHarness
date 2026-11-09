#!/usr/bin/env python3
"""CaseAudioRecorder 最小单测。"""
from __future__ import annotations

import io
import struct
import time
import wave

from projects.voice_test.adapter.case_audio_recorder import (
    CASE_AUDIO_FILENAME,
    CaseAudioRecorder,
)
from projects.voice_test.adapter.case_audio_tos import tos_config


def _tone_f32(n: int, freq: float = 440.0, rate: int = 24000) -> bytes:
    import math

    buf = []
    for i in range(n):
        v = math.sin(2 * math.pi * freq * i / rate)
        buf.append(struct.pack("<f", v * 0.5))
    return b"".join(buf)


def _silence_int16(n: int) -> bytes:
    return b"\x00\x00" * n


def test_case_audio_recorder_timeline() -> None:
    rec = CaseAudioRecorder.begin()
    rec.write_tts(_tone_f32(2400))
    rec.write_tts(_tone_f32(2400))
    time.sleep(0.05)
    rec.begin_listening()
    mic_chunk = _silence_int16(3200)
    rec.write_mic(mic_chunk)
    rec.write_mic(mic_chunk)
    rec.write_mic(mic_chunk)
    body = rec._take_wav_bytes()
    assert body is not None
    assert rec.recording_id
    base = tos_config.base_path.strip("/")
    relative = rec.object_key.removeprefix(f"{base}/")
    assert "/" not in relative
    assert relative == f"{rec.recording_id}_{CASE_AUDIO_FILENAME}"

    with wave.open(io.BytesIO(body), "rb") as wf:
        assert wf.getframerate() == 24000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() >= 15000


if __name__ == "__main__":
    test_case_audio_recorder_timeline()
    print("ok")
