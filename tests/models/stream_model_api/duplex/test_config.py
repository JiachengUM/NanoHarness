from __future__ import annotations

from aicore.models.stream_model_api.duplex.config import (
    DEFAULT_PCM,
    LEGACY_DUPLEX_ENDPOINT_URL,
    PCM_S16LE,
    DuplexConfig,
    build_duplex_session_config,
)


def test_config_owns_the_default_session_profile() -> None:
    config = DuplexConfig()

    assert config.api_key
    assert config.model == "1.2.6.1"
    assert config.speaker == "zh_female_xiaohe_jupiter_bigtts"
    assert config.asr_format == DEFAULT_PCM
    assert config.end_smooth_window_ms == 1500
    assert config.enable_custom_vad is True
    assert config.local_rule_vad_timeout_ms == 1000
    assert config.tts_format == PCM_S16LE
    assert config.endpoint_url == LEGACY_DUPLEX_ENDPOINT_URL


def test_config_projects_s2s_vad_settings_into_duplex_extension() -> None:
    config = DuplexConfig(
        end_smooth_window_ms=800,
        enable_custom_vad=False,
    )

    _, extension = build_duplex_session_config(config, session_id="session-1")

    assert extension["asr"]["extra"] == {
        "end_smooth_window_ms": 800,
        "enable_custom_vad": False,
    }
