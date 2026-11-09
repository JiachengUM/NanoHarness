from __future__ import annotations

import os
from dataclasses import dataclass

# 与 SGM/common/engine_api.py 中 volcengine_intent、_prepare_volcengine_querystr、_prepare_volcengine_headers 一致
_SGM_AK = "extourProgxg75g0lfzvlgrc6mvg4ceh"
_SGM_SK = "pgsff17eh892wall893ky7lttz3boze8"
_SGM_CHANNEL = "extour-pro"
_SGM_APP_ID = 99431
_SGM_X_TT_ENV = "ppe_extour_pro_test"
_SGM_VOLCANO_BASE = "https://api-vehicle.volcengine.com"


@dataclass
class _AppConfig:
    VOLCANO_API_URL: str = _SGM_VOLCANO_BASE
    AK: str = _SGM_AK
    SK: str = _SGM_SK
    PLUGIN_CHANEL: str = _SGM_CHANNEL
    PLUGIN_APP_ID: int = _SGM_APP_ID
    PLUGIN_X_Tt_Env: str = _SGM_X_TT_ENV
    RESPONSE_TIMEOUT: int = 120
    KEEP_ALIVE_TIMEOUT: int = 180
    MAX_CONCURRENT_REQUESTS: int = 120

    # 高德地图 POI（可选，未配置时 PoiSearch 可回退 mock）
    AMAP_API_URL: str = "https://restapi.amap.com"
    AMAP_API_KEY: str = "a53f6c8c2e40a2dc7436260d2f4bdb10"

    # 天气 API（与 complex_reasoning_agent weather_client 一致：内部服务；高德天气为备选）
    WEATHER_API_URL: str = "http://118.31.22.57:9081/llmapi_test/openapi/weather/info"
    AMAP_WEATHER_API_URL: str = "https://restapi.amap.com/v3/weather/weatherInfo"

    # 联网检索：火山 Ark Bot（与 complex_reasoning_agent config VOLCANO_API_KEY / WEB_SEARCH_BOT_ID 一致）
    WEBSEARCH_BOT_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3/bots"
    WEBSEARCH_BOT_API_KEY: str = "REDACTED"
    WEBSEARCH_BOT_MODEL: str = "bot-20250805172047-8sctw"

    # QQ 音乐开放 API
    QQ_MUSIC_APP_ID: str = "2000000834"
    QQ_MUSIC_APP_KEY: str = "KVPKtXafMTWrOzMm"
    QQ_MUSIC_BASE_URL: str = "https://qplaycloud.y.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg"
    QQ_MUSIC_DEVICE_ID: str = "python_api_client_001"

    def __post_init__(self) -> None:
        if os.environ.get("VOLC_AK"):
            object.__setattr__(self, "AK", os.environ["VOLC_AK"])
        if os.environ.get("VOLC_SK"):
            object.__setattr__(self, "SK", os.environ["VOLC_SK"])
        if os.environ.get("AMAP_API_KEY"):
            object.__setattr__(self, "AMAP_API_KEY", os.environ["AMAP_API_KEY"])
        if os.environ.get("WEBSEARCH_BOT_API_KEY"):
            object.__setattr__(self, "WEBSEARCH_BOT_API_KEY", os.environ["WEBSEARCH_BOT_API_KEY"])
        if os.environ.get("WEBSEARCH_BOT_MODEL"):
            object.__setattr__(self, "WEBSEARCH_BOT_MODEL", os.environ["WEBSEARCH_BOT_MODEL"])
        if os.environ.get("WEATHER_API_URL"):
            object.__setattr__(self, "WEATHER_API_URL", os.environ["WEATHER_API_URL"])
        if os.environ.get("QQ_MUSIC_APP_ID"):
            object.__setattr__(self, "QQ_MUSIC_APP_ID", os.environ["QQ_MUSIC_APP_ID"])
        if os.environ.get("QQ_MUSIC_APP_KEY"):
            object.__setattr__(self, "QQ_MUSIC_APP_KEY", os.environ["QQ_MUSIC_APP_KEY"])
        if os.environ.get("QQ_MUSIC_BASE_URL"):
            object.__setattr__(self, "QQ_MUSIC_BASE_URL", os.environ["QQ_MUSIC_BASE_URL"])
        if os.environ.get("QQ_MUSIC_DEVICE_ID"):
            object.__setattr__(self, "QQ_MUSIC_DEVICE_ID", os.environ["QQ_MUSIC_DEVICE_ID"])


_config: _AppConfig | None = None


def get_app_config() -> _AppConfig:
    global _config
    if _config is None:
        _config = _AppConfig()
    return _config