from __future__ import annotations

import base64
import hashlib
import json
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

from projects.experiments.s2s.config import input_audio_config, ws_connect_config

INPUT_SAMPLE_WIDTH_BYTES = 2
DEFAULT_CACHE_DIR = Path("projects/experiments/demo_case/tts_cache")
DEFAULT_AUDIO_FILE_DIR = Path("projects/experiments/demo_case/audio_files")

TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
TTS_APP_ID = ws_connect_config.headers.x_api_app_id
TTS_ACCESS_KEY = ws_connect_config.headers.x_api_access_key
TTS_RESOURCE_ID = "volc.service_type.10029"
TTS_SPEAKER = "zh_male_aojiaobazong_emo_v2_mars_bigtts"
TTS_UID = "s2s-demo-replay"
TTS_FORMAT = "pcm"
TTS_SAMPLE_RATE = input_audio_config.sample_rate
DEFAULT_AUDIO_GAIN = 0.5


@dataclass(frozen=True)
class TextTurn:
    text: str
    delay: float = 0.0


def build_tts_headers(*, app_id: str, access_key: str, resource_id: str) -> dict[str, str]:
    return {
        "X-Api-App-Id": app_id,
        "X-Api-Access-Key": access_key,
        "X-Api-Resource-Id": resource_id,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }


def build_tts_payload(
    *,
    text: str,
    speaker: str,
    audio_format: str,
    sample_rate: int,
    uid: str = TTS_UID,
) -> dict[str, Any]:
    return {
        "user": {
            "uid": uid,
        },
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": sample_rate,
                "enable_timestamp": False,
            },
            "additions": json.dumps(
                {
                    "explicit_language": "zh",
                    "disable_markdown_filter": True,
                    "enable_timestamp": False,
                },
                ensure_ascii=False,
            ),
        },
    }


def collect_tts_stream_audio(chunks: Iterable[str]) -> bytes:
    audio_data = bytearray()
    for chunk in chunks:
        if not chunk:
            continue
        data = json.loads(chunk)

        if data.get("code", 0) == 0 and data.get("data"):
            audio_data.extend(base64.b64decode(data["data"]))
            continue
        if data.get("code", 0) == 0 and data.get("sentence"):
            print("sentence_data:", data)
            continue
        if data.get("code", 0) == 20000000:
            if "usage" in data:
                print("usage:", data["usage"])
            break
        if data.get("code", 0) > 0:
            raise RuntimeError(f"Volc TTS error response: {data}")

    if not audio_data:
        raise RuntimeError("Volc TTS finished without audio data")
    return bytes(audio_data)


def tts_http_stream(url: str, headers: dict[str, str], params: dict[str, Any]) -> bytes:
    session = requests.Session()
    response: requests.Response | None = None
    try:
        print("请求的url:", url)
        print("请求的headers:", headers)
        print("请求的params:\n", params)
        response = session.post(url, headers=headers, json=params, stream=True)
        print(response)
        print(f"code: {response.status_code} header: {response.headers}")
        print(f"X-Tt-Logid: {response.headers.get('X-Tt-Logid')}")
        response.raise_for_status()
        return collect_tts_stream_audio(response.iter_lines(decode_unicode=True))
    finally:
        if response is not None:
            response.close()
        session.close()


def tts_cache_path(text: str, *, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    payload = {
        "text": text,
        "speaker": TTS_SPEAKER,
        "resource_id": TTS_RESOURCE_ID,
        "format": TTS_FORMAT,
        "sample_rate": TTS_SAMPLE_RATE,
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return cache_dir / f"{digest}.pcm"


def synthesize_text_to_pcm(
    text: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    synthesize: Callable[[str], bytes] | None = None,
) -> bytes:
    cache_path = tts_cache_path(text, cache_dir=cache_dir)
    if cache_path.exists():
        return cache_path.read_bytes()

    audio = synthesize(text) if synthesize is not None else _synthesize_text_to_pcm_uncached(text)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(audio)
    return audio


def text_turn_wav_path(
    turn: TextTurn,
    *,
    cache_dir: Path = DEFAULT_AUDIO_FILE_DIR,
    sample_rate: int = TTS_SAMPLE_RATE,
    audio_gain: float = DEFAULT_AUDIO_GAIN,
) -> Path:
    payload = {
        "text": turn.text,
        "delay": turn.delay,
        "audio_gain": audio_gain,
        "speaker": TTS_SPEAKER,
        "resource_id": TTS_RESOURCE_ID,
        "format": TTS_FORMAT,
        "sample_rate": sample_rate,
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return cache_dir / f"{digest}.wav"


def write_text_turn_wav(
    turn: TextTurn,
    *,
    cache_dir: Path = DEFAULT_AUDIO_FILE_DIR,
    synthesize: Callable[[str], bytes] = synthesize_text_to_pcm,
    sample_rate: int = TTS_SAMPLE_RATE,
    audio_gain: float = DEFAULT_AUDIO_GAIN,
) -> Path:
    wav_path = text_turn_wav_path(
        turn,
        cache_dir=cache_dir,
        sample_rate=sample_rate,
        audio_gain=audio_gain,
    )
    if wav_path.exists():
        return wav_path

    pcm = silence_pcm_bytes(turn.delay, sample_rate=sample_rate) + apply_pcm_gain(
        synthesize(turn.text),
        audio_gain,
    )
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(input_audio_config.channels)
        wf.setsampwidth(INPUT_SAMPLE_WIDTH_BYTES)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return wav_path


def build_audio_file_list(
    turns: list[TextTurn],
    *,
    cache_dir: Path = DEFAULT_AUDIO_FILE_DIR,
    synthesize: Callable[[str], bytes] = synthesize_text_to_pcm,
    sample_rate: int = TTS_SAMPLE_RATE,
    audio_gain: float = DEFAULT_AUDIO_GAIN,
) -> list[tuple[str, float]]:
    return [
        (
            str(
                write_text_turn_wav(
                    turn,
                    cache_dir=cache_dir,
                    synthesize=synthesize,
                    sample_rate=sample_rate,
                    audio_gain=audio_gain,
                )
            ),
            0.0,
        )
        for turn in turns
    ]


def _synthesize_text_to_pcm_uncached(text: str) -> bytes:
    return tts_http_stream(
        url=TTS_URL,
        headers=build_tts_headers(
            app_id=TTS_APP_ID,
            access_key=TTS_ACCESS_KEY,
            resource_id=TTS_RESOURCE_ID,
        ),
        params=build_tts_payload(
            text=text,
            speaker=TTS_SPEAKER,
            audio_format=TTS_FORMAT,
            sample_rate=TTS_SAMPLE_RATE,
        ),
    )


def silence_pcm_bytes(
    duration_sec: float,
    *,
    sample_rate: int = input_audio_config.sample_rate,
    sample_width: int = INPUT_SAMPLE_WIDTH_BYTES,
    channels: int = input_audio_config.channels,
) -> bytes:
    if duration_sec <= 0:
        return b""
    byte_count = int(duration_sec * sample_rate) * sample_width * channels
    return b"\x00" * byte_count


def apply_pcm_gain(pcm: bytes, gain: float) -> bytes:
    if gain < 0:
        raise ValueError("audio gain must be >= 0")
    if gain == 1.0 or not pcm:
        return pcm
    if len(pcm) % INPUT_SAMPLE_WIDTH_BYTES != 0:
        raise ValueError("pcm byte length must align to int16 samples")

    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()

    for index, sample in enumerate(samples):
        scaled = int(sample * gain)
        samples[index] = max(-32768, min(32767, scaled))

    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def build_pcm_timeline(
    turns: list[TextTurn],
    *,
    synthesize: Callable[[str], bytes] = synthesize_text_to_pcm,
    sample_rate: int = input_audio_config.sample_rate,
    sample_width: int = INPUT_SAMPLE_WIDTH_BYTES,
    channels: int = input_audio_config.channels,
    audio_gain: float = DEFAULT_AUDIO_GAIN,
) -> bytes:
    parts: list[bytes] = []
    for turn in turns:
        parts.append(
            silence_pcm_bytes(
                turn.delay,
                sample_rate=sample_rate,
                sample_width=sample_width,
                channels=channels,
            )
        )
        parts.append(apply_pcm_gain(synthesize(turn.text), audio_gain))
    return b"".join(parts)
