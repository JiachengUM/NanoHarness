"""voice_test 默认 TOS 配置（case 音频上传）。"""
from __future__ import annotations

from projects.voice_test.utils.tos_client import TosSettings, VolcTosClient

TosConfig = TosSettings

tos_config = TosSettings(
    bucket_name="mb-voice-test",
    access_key_id="REDACTED",
    access_key_secret="REDACTED",
    endpoint="https://tos-cn-beijing.volces.com",
    base_path="dev/BenZ_test",
    region="cn-beijing",
)

tos_client = VolcTosClient(tos_config)


def upload_bytes(
    cfg: TosSettings,
    object_key: str,
    body: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> str:
    return VolcTosClient(cfg).put_bytes(object_key, body, content_type=content_type)


def presigned_get_url(cfg: TosSettings, object_key: str, *, expires_sec: int = 3600) -> str:
    return VolcTosClient(cfg).presigned_get_url(object_key, expires_sec=expires_sec)


def upload_case_audio_wav(cfg: TosSettings, object_key: str, wav_bytes: bytes) -> str:
    return VolcTosClient(cfg).put_bytes(object_key, wav_bytes, content_type="audio/wav")
