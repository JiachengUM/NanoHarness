"""火山 HTTP 单向 TTS 客户端（通用：text + speaker + resource_id）。"""

from __future__ import annotations

import array
import base64
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

import requests

from projects.voice_test.config.core_config import input_audio_config, output_audio_config, ws_connect_config

TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
TTS_RESOURCE_ID = "volc.service_type.10029"
TTS_FORMAT = "pcm"
TTS_SAMPLE_RATE = input_audio_config.sample_rate
OUTPUT_SAMPLE_RATE = output_audio_config.sample_rate
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "http_tts"
# (connect, read)：避免火山无响应时占死 asyncio.to_thread 线程池。
TTS_HTTP_TIMEOUT = (10.0, 60.0)


def _build_headers(resource_id: str) -> dict[str, str]:
    headers = ws_connect_config.headers
    return {
        "X-Api-App-Id": headers.x_api_app_id,
        "X-Api-Access-Key": headers.x_api_access_key,
        "X-Api-Resource-Id": resource_id,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }


def _build_payload(text: str, speaker: str, sample_rate: int) -> dict[str, Any]:
    return {
        "user": {"uid": f"tts-{uuid.uuid4().hex[:8]}"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": TTS_FORMAT,
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


def _collect_stream_audio(lines: Iterable[Any]) -> bytes:
    audio_data = bytearray()
    for chunk in lines:
        if not chunk:
            continue
        data = json.loads(chunk)
        code = data.get("code", 0)
        if code == 0 and data.get("data"):
            audio_data.extend(base64.b64decode(data["data"]))
            continue
        if code == 20000000:
            break
        if code > 0:
            raise RuntimeError(f"火山 TTS 错误: {data}")
    if not audio_data:
        raise RuntimeError("火山 TTS 未返回音频")
    return bytes(audio_data)


def _fetch_pcm_uncached(
    text: str,
    *,
    speaker: str,
    resource_id: str,
    sample_rate: int,
) -> bytes:
    session = requests.Session()
    response = session.post(
        TTS_URL,
        headers=_build_headers(resource_id),
        json=_build_payload(text, speaker, sample_rate),
        stream=True,
        timeout=TTS_HTTP_TIMEOUT,
    )
    response.raise_for_status()
    pcm = _collect_stream_audio(response.iter_lines(decode_unicode=True))
    response.close()
    session.close()
    return pcm


def _cache_path(
    text: str,
    speaker: str,
    resource_id: str,
    sample_rate: int,
    cache_dir: Path,
) -> Path:
    cache_key = {
        "text": text,
        "speaker": speaker,
        "resource_id": resource_id,
        "format": TTS_FORMAT,
        "sample_rate": sample_rate,
    }
    digest = hashlib.sha256(
        json.dumps(cache_key, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]
    return cache_dir / f"{digest}.pcm"


def _pcm_int16_to_f32le(pcm: bytes, *, in_rate: int) -> bytes:
    if not pcm:
        return b""
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    out_rate = OUTPUT_SAMPLE_RATE
    in_n = len(samples)
    if in_n == 0:
        return b""
    if in_rate == out_rate:
        out = array.array("f")
        for sample in samples:
            out.append(sample / 32768.0)
        return out.tobytes()
    out_n = max(1, int(in_n * out_rate / in_rate))
    out = array.array("f")
    for i in range(out_n):
        src = i * in_rate / out_rate
        idx = int(src)
        if idx >= in_n:
            idx = in_n - 1
        frac = src - idx
        s0 = samples[idx] / 32768.0
        s1 = samples[idx + 1] / 32768.0 if idx + 1 < in_n else s0
        out.append(s0 + (s1 - s0) * frac)
    return out.tobytes()


def synthesize_playback_f32le(
    text: str,
    speaker: str,
    *,
    resource_id: str = TTS_RESOURCE_ID,
    sample_rate: int = TTS_SAMPLE_RATE,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> bytes:
    content = (text or "").strip()
    spk = (speaker or "").strip()
    rid = (resource_id or "").strip()
    if not content or not spk or not rid:
        return b""

    cache_path = _cache_path(content, spk, rid, sample_rate, cache_dir)
    if cache_path.exists():
        pcm = cache_path.read_bytes()
    else:
        pcm = _fetch_pcm_uncached(
            content,
            speaker=spk,
            resource_id=rid,
            sample_rate=sample_rate,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(pcm)

    return _pcm_int16_to_f32le(pcm, in_rate=sample_rate)
