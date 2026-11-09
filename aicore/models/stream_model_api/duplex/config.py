from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PCM = "pcm"
PCM_S16LE = "pcm_s16le"
OGG_OPUS = "ogg_opus"
LEGACY_DUPLEX_ENDPOINT_URL = (
    "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
)


@dataclass(slots=True)
class DuplexConfig:
    api_key: str = "16wfbjmry6Bed5vsbXeLvWUcYBIG965p"
    model: str = "1.2.6.1"
    instructions: str = "You are a creative assistant that helps with design tasks."
    speaker: str = "zh_female_xiaohe_jupiter_bigtts"
    asr_format: str = DEFAULT_PCM
    # Provider-side endpointing settings, sent in ``extension.asr.extra``.
    end_smooth_window_ms: int = 1500
    enable_custom_vad: bool = True
    # Local rule-based VAD: commit when ASR starts but no first text delta
    # arrives within this window.
    local_rule_vad_timeout_ms: int = 3000
    tts_format: str = PCM_S16LE
    endpoint_url: str = LEGACY_DUPLEX_ENDPOINT_URL


def build_duplex_session_config(
    config: DuplexConfig,
    *,
    session_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the provider session profile owned by this configuration module.

    VAD, audit copy and media policy intentionally live beside
    ``DuplexConfig`` rather than in the reusable websocket client.
    """

    session = {
        "id": session_id,
        "model": config.model,
        "instructions": config.instructions,
        "audio": {
            "input": {
                "format": {"type": config.asr_format, "rate": 16000},
            },
            "output": {
                "format": {"type": config.tts_format, "rate": 24000},
                "voice": config.speaker,
            },
        },
    }
    extension = {
        "asr": {
            "extra": {
                "end_smooth_window_ms": config.end_smooth_window_ms,
                "enable_custom_vad": config.enable_custom_vad,
            }
        },
        "tts": {"extra": {}},
        "dialog": {
            "extra": {
                "audit_response": (
                    "抱歉，这个问题我无法回答，你可以换个其他话题，"
                    "我会尽力为你提供帮助。"
                ),
                "enable_loudness_norm": True,
                "enable_music": True,
            },
        },
    }
    return session, extension


__all__ = [
    "DEFAULT_PCM",
    "LEGACY_DUPLEX_ENDPOINT_URL",
    "OGG_OPUS",
    "PCM_S16LE",
    "DuplexConfig",
    "build_duplex_session_config",
]
