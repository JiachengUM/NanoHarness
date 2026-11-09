"""case 对话音频：录制、编码、TOS 上传。"""
from __future__ import annotations

import array
import io
import logging
import struct
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime

from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.adapter.case_audio_tos import tos_client, tos_config
from projects.voice_test.utils.tos_client import TosSettings, VolcTosClient
from projects.voice_test.config.core_config import input_audio_config, output_audio_config

_log = get_vt_logger("recorder")

_IN_RATE = input_audio_config.sample_rate
_OUT_RATE = output_audio_config.sample_rate
CASE_AUDIO_FILENAME = "case_audio.wav"


@dataclass(frozen=True)
class CaseAudioPublishResult:
    download_url: str


def _new_recording_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _floats_to_int16_bytes(samples: array.array) -> bytes:
    if len(samples) == 0:
        return b""
    out = array.array("h")
    for value in samples:
        clamped = max(-1.0, min(1.0, value))
        out.append(int(clamped * 32767.0))
    return out.tobytes()


def _encode_wav_bytes(samples: array.array, *, end_index: int | None = None) -> bytes:
    if end_index is not None:
        need = end_index - len(samples)
        if need > 0:
            samples = array.array("f", samples)
            samples.extend([0.0] * need)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_OUT_RATE)
        wf.writeframes(_floats_to_int16_bytes(samples))
    return buf.getvalue()


def _mic_bytes_to_floats(chunk: bytes) -> array.array:
    n_in = len(chunk) // 2
    if n_in == 0:
        return array.array("f")
    samples_in = struct.unpack(f"<{n_in}h", chunk)
    n_out = n_in * _OUT_RATE // _IN_RATE
    out = array.array("f", [0.0] * n_out)
    if n_out == 0:
        return out
    ratio = _IN_RATE / _OUT_RATE
    for i in range(n_out):
        src = i * ratio
        j = int(src)
        frac = src - j
        s0 = samples_in[j] / 32768.0
        s1 = samples_in[j + 1] / 32768.0 if j + 1 < n_in else s0
        out[i] = s0 + (s1 - s0) * frac
    return out


def _tts_bytes_to_floats(payload: bytes) -> array.array:
    n = len(payload) // 4
    if n == 0:
        return array.array("f")
    floats = array.array("f")
    floats.frombytes(payload[: n * 4])
    return floats


class CaseAudioRecorder:
    """TTS / mic 顺序拼接；id / key / 内存编码 / TOS 上传均由本类维护。"""

    def __init__(
        self,
        recording_id: str,
        object_key: str,
        log: logging.Logger | logging.LoggerAdapter | None = None,
    ) -> None:
        self.recording_id = recording_id
        self.object_key = object_key
        self._t0: float | None = None
        self._samples = array.array("f")
        self._tts_cursor = 0
        self._mic_cursor = 0
        # 接受外部 logger（带 sid/run 前缀）；未传入时回退到模块默认 logger
        self._log = log if log is not None else _log

    @classmethod
    def begin(
        cls,
        *,
        tos_cfg: TosSettings = tos_config,
        log: logging.Logger | logging.LoggerAdapter | None = None,
    ) -> CaseAudioRecorder:
        recording_id = _new_recording_id()
        filename = f"{recording_id}_{CASE_AUDIO_FILENAME}"
        object_key = VolcTosClient(tos_cfg).build_object_key(filename)
        recorder = cls(recording_id, object_key, log=log)
        recorder.start()
        recorder._log.info("begin recording_id=%s key=%s", recording_id, object_key)
        return recorder

    @property
    def active(self) -> bool:
        return self._t0 is not None

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._samples = array.array("f")
        self._tts_cursor = 0
        self._mic_cursor = 0

    def begin_speaking(self) -> None:
        if self._t0 is None:
            return
        wall = self._wall_sample_index()
        if wall > self._tts_cursor:
            self._ensure_length(wall)
            self._tts_cursor = wall

    def begin_listening(self) -> None:
        if self._t0 is None:
            return
        wall = self._wall_sample_index()
        if wall > self._mic_cursor:
            self._ensure_length(wall)
            self._mic_cursor = wall

    def write_tts(self, payload: bytes) -> None:
        floats = _tts_bytes_to_floats(payload)
        if self._t0 is None or len(floats) == 0:
            return
        if self._wall_sample_index() > self._tts_cursor:
            self.begin_speaking()
        start = self._tts_cursor
        self._write_range(start, floats)
        self._tts_cursor = start + len(floats)

    def write_mic(self, chunk: bytes) -> None:
        floats = _mic_bytes_to_floats(chunk)
        if self._t0 is None or len(floats) == 0:
            return
        if self._wall_sample_index() > self._mic_cursor:
            self.begin_listening()
        start = self._mic_cursor
        self._write_range(start, floats)
        self._mic_cursor = start + len(floats)

    def finish(
        self,
        *,
        tos: VolcTosClient | None = None,
        presign_sec: int = 86400,
    ) -> CaseAudioPublishResult | None:
        body = self._take_wav_bytes()
        if body is None:
            self._log.info("finish skip (no body) recording_id=%s", self.recording_id)
            return None
        client = tos or tos_client
        uploaded = client.put_bytes(self.object_key, body, content_type="audio/wav")
        download_url = client.presigned_get_url(uploaded, expires_sec=presign_sec)
        self._log.info(
            "finish upload recording_id=%s bytes=%d url=%s",
            self.recording_id, len(body), "yes" if download_url else "no",
        )
        if not download_url:
            return None
        return CaseAudioPublishResult(download_url=download_url)

    def _take_wav_bytes(self) -> bytes | None:
        if self._t0 is None:
            return None
        end_index = max(
            self._wall_sample_index(),
            self._tts_cursor,
            self._mic_cursor,
        )
        body = _encode_wav_bytes(self._samples, end_index=end_index)
        self._t0 = None
        self._tts_cursor = 0
        self._mic_cursor = 0
        self._samples = array.array("f")
        return body

    def _wall_sample_index(self) -> int:
        assert self._t0 is not None
        return int((time.monotonic() - self._t0) * _OUT_RATE)

    def _ensure_length(self, end_index: int) -> None:
        need = end_index - len(self._samples)
        if need > 0:
            self._samples.extend([0.0] * need)

    def _write_range(self, start: int, floats: array.array) -> None:
        end = start + len(floats)
        self._ensure_length(end)
        for i, value in enumerate(floats):
            self._samples[start + i] = value
