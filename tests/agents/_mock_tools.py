"""``projects.mind.toolset.dag.get_default_tools`` 的 mock 版：**只换 worker，不换工具契约**。

工具名 / description / args_schema 一律沿用真实工具——planner 的 prompt 由它们生成，
换掉就等于换了实验对象；真正打网络的那一层替换成确定性假数据：

    真实网络调用                     → mock 数据
    Ark bot 联网搜索（WebSearch）     → 固定 references（可注入 empty / error 复现限流现场）
    高德 POI 检索（POISearch）        → 固定烤鸭店列表
    QQ 音乐 单曲/歌单/专辑            → 固定曲目
    火山天气插件（weather_agent）     → 固定北京/上海预报（明天 34℃，见 _WEATHER_DAYS）
    火山车控 / 导航 / 媒体            → 固定 success 回执（复述入参；导航额外带“解析到的门店”）
    后台记忆召回（MemoryRecall）      → 固定 facts

因此 plan 生成、DAG 执行、concept 投影、补救诊断、收尾都是真的，只有网络工具是假的。
离线跑（不打任何第三方接口，但模型调用仍是真机）：

    from tests.agents._mock_tools import get_mock_tools

    get_mock_tools(chat_id="User")                     # 正常路径
    get_mock_tools(chat_id="User", websearch="empty")  # 复现"搜索返回空"（限流被吞的现场）
    get_mock_tools(chat_id="User", websearch="error")  # 复现"工具真的抛错"

不在本模块做的事：不 mock 判定器（Jev/LLM judge）、不 mock model_api。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from projects.mind.toolset.dag import (
    CarControlTool,
    MediaTool,
    MemoryTool,
    NavigateTool,
    WebsearchTool,
    poi_search_tool,
    qq_music_album_search_tool,
    qq_music_playlist_search_tool,
    qq_music_song_search_tool,
)
from projects.mind.toolset.dag.car_control import CarControlOutput, CarControlStatus
from projects.mind.toolset.dag.compact import compact_tool_output
from projects.mind.toolset.dag.media import MediaOutput, MediaStatus
from projects.mind.toolset.dag.memory import MemoryRecallOutput
from projects.mind.toolset.dag.navigate_v2 import NavigateOutput, NavigateStatus
from projects.mind.toolset.weather import WeatherItem, WeatherOutput, WeatherTool

__all__ = ["get_mock_tools", "WEBSEARCH_MODES"]

# WebSearch 的三种 mock 行为：正常 / 空结果 / 抛异常。
WEBSEARCH_MODES = ("ok", "empty", "error")

_MOCK_TAG = "（mock）"


# ══════════════════════════════════════════════════════════════════════
# 固定数据（字段与真实工具返回对齐）
# ══════════════════════════════════════════════════════════════════════

# WebSearch 真实返回：list[dict]，每条 = Ark bot 的 reference
# （字段见 projects/mind/complex_reasoning/tools/Websearch.py:WebsearchReference）
_WEATHER_REFS: list[dict[str, Any]] = [
    {
        "site_name": "中国天气网",
        "title": "北京明天天气预报",
        "publish_time": "2026-09-21",
        "summary": "北京明天多云转晴，白天最高气温 34℃，夜间最低 24℃，东南风 2 级，"
        "紫外线强度较强，白天体感闷热，请注意防暑降温。",
    },
    {
        "site_name": "北京市气象局",
        "title": "北京明日天气实况预报",
        "publish_time": "2026-09-21",
        "summary": "明日北京城区最高气温可达 34℃，郊区 32～35℃，相对湿度 55%，"
        "午后有短时分散性阵雨可能。",
    },
]

_DUCK_REFS: list[dict[str, Any]] = [
    {
        "site_name": "大众点评",
        "title": "北京烤鸭店推荐榜",
        "publish_time": "2026-09-10",
        "summary": "北京烤鸭口碑榜：全聚德（前门店）4.6 分、四季民福（故宫店）4.8 分、"
        "大董（团结湖店）4.5 分，人均 150～300 元。",
    },
]

_GENERIC_REFS: list[dict[str, Any]] = [
    {
        "site_name": "示例站点",
        "title": "联网检索结果",
        "publish_time": "2026-09-21",
        "summary": "（mock 数据）未命中关键词，返回占位检索结果。",
    },
]

# POISearch 真实返回：list[PoiItem]（字段见 projects/mind/toolset/dag/amap.py:PoiItem）
# 排序约定：**按 rating 降序**返回。真实高德按相关性/距离返回、不保证按评分排，但计划里的
# "评分最高的那家" 只能靠下标引用（如 ``RoastDuckShop[0].address``），列表不按评分排就会
# 出现"导航到了 4.6 分那家、答案却写最高分那家"的错配。要刻意保留这个坑就改回原顺序。
_DUCK_POIS: list[dict[str, Any]] = [
    {
        "name": "四季民福烤鸭店(故宫店)",
        "distance": "3400",
        "type": "餐饮服务;中餐厅;中餐厅",
        "address": "南池子大街11号",
        "pname": "北京市",
        "cityname": "北京市",
        "adname": "东城区",
        "business": {
            "business_area": "王府井/故宫",
            "rating": "4.8",
            "cost": "160",
            "opentime_today": "10:00-22:00",
            "tel": "010-65267369",
            "tag": "烤鸭,京菜",
            "parking_type": "地面",
        },
    },
    {
        "name": "全聚德(前门店)",
        "distance": "2100",
        "type": "餐饮服务;中餐厅;中餐厅",
        "address": "前门大街30号",
        "pname": "北京市",
        "cityname": "北京市",
        "adname": "东城区",
        "business": {
            "business_area": "前门",
            "rating": "4.6",
            "cost": "180",
            "opentime_today": "10:30-21:00",
            "tel": "010-65112418",
            "tag": "百年老字号,烤鸭",
            "parking_type": "地下",
        },
    },
    {
        "name": "大董烤鸭(团结湖店)",
        "distance": "6200",
        "type": "餐饮服务;中餐厅;中餐厅",
        "address": "团结湖北口3号楼",
        "pname": "北京市",
        "cityname": "北京市",
        "adname": "朝阳区",
        "business": {
            "business_area": "团结湖",
            "rating": "4.5",
            "cost": "300",
            "opentime_today": "11:00-22:00",
            "tel": "010-65824003",
            "tag": "酥不腻烤鸭",
            "parking_type": "地面",
        },
    },
]

# SongSearch / PlaylistSearch / AlbumSearch 真实返回：{songs|playlists|albums: [...]}
_SONGS: list[dict[str, Any]] = [
    {
        "song_name": "晴天",
        "song_title": "晴天",
        "singer_name": "周杰伦",
        "singer_title": "周杰伦",
        "album_name": "叶惠美",
        "language": "国语",
        "genre": "流行",
        "author": "作词：周杰伦 作曲：周杰伦",
        "public_time": "2003-07-31",
        "match_lyric": "故事的小黄花 从出生那年就飘着",
    }
]

_PLAYLISTS: list[dict[str, Any]] = [
    {
        "dissname": "周杰伦经典歌曲精选",
        "creator_name": "QQ音乐",
        "song_count": 50,
        "diss_tags": "华语,流行",
        "intro": "（mock 数据）周杰伦经典歌曲合辑",
    }
]

_ALBUMS: list[dict[str, Any]] = [
    {
        "album_name": "叶惠美",
        "singer_name": "周杰伦",
        "public_time": "2003-07-31",
        "company": "杰威尔音乐",
        "genre": "流行",
        "language": "国语",
        "song_count": 11,
    }
]

# ── 天气（weather_agent）──────────────────────────────────────────────
# 真实返回：WeatherOutput(forecasts=[WeatherItem, ...])，**一天一条**（查一天给一条，查询
# 日期区间才有多条），字段与单位见 projects/mind/toolset/weather.py:WeatherItem——
# high / low / humidity / precip 都是不带单位的字符串（如 "34" 表示 34℃）。

# 城市 → (provinceName, cityName, districtName)
_WEATHER_CITIES: dict[str, tuple[str, str, str]] = {
    "北京": ("北京市", "北京市", "朝阳区"),
    "上海": ("上海市", "上海市", "徐汇区"),
}


def _day(
    text_day: str,
    text_night: str,
    high: str,
    low: str,
    *,
    precip: str = "0.00",
    wind_direction: str = "东南",
    wind_direction_degree: str = "135",
    wind_speed: str = "3.1",
    wind_scale: str = "2",
    humidity: str = "45",
) -> dict[str, str]:
    """一天预报的公共字段，省去每个城市重复抄一遍 wind/humidity。"""
    return {
        "textDay": text_day,
        "textNight": text_night,
        "high": high,
        "low": low,
        "precip": precip,
        "windDirection": wind_direction,
        "windDirectionDegree": wind_direction_degree,
        "windSpeed": wind_speed,
        "windScale": wind_scale,
        "humidity": humidity,
    }


# 城市 → 按“相对今天的天数偏移”索引的固定预报（0 今天 / 1 明天 / 2 后天）。
# 关键构造：北京**明天 34℃**（> 30℃）用来让 AB_QUERIES[0] 里“气温超过 30 度就把空调调到
# 22 度”的条件成立；而今天 28℃ / 后天 29℃ 都不够 30℃，
# 所以只有把“明天”解析对的计划才会走车控分支——日期没落地就会跑出错误结论。
_WEATHER_DAYS: dict[str, list[dict[str, str]]] = {
    "北京": [
        _day("多云", "晴", "28", "18", humidity="46"),
        _day("晴", "多云", "34", "22", humidity="41"),
        _day(
            "雷阵雨",
            "阴",
            "29",
            "21",
            precip="6.20",
            wind_direction="东",
            wind_direction_degree="90",
            wind_speed="4.4",
            wind_scale="3",
            humidity="68",
        ),
    ],
    "上海": [
        _day(
            "小雨",
            "多云",
            "33",
            "27",
            precip="0.53",
            wind_direction="西南",
            wind_direction_degree="225",
            wind_speed="3.0",
            wind_scale="1",
            humidity="93",
        ),
        _day(
            "小雨",
            "阴",
            "31",
            "26",
            precip="1.20",
            wind_direction="南",
            wind_direction_degree="180",
            wind_speed="3.4",
            humidity="88",
        ),
        _day("多云", "晴", "30", "25", humidity="72"),
    ],
}

# 查询里的日期词 → 天数偏移
_DAY_KEYS: dict[int, tuple[str, ...]] = {
    0: ("今天", "今日"),
    1: ("明天", "明日"),
    2: ("后天",),
}


def _day_offsets(query: str) -> list[int]:
    """查询点名了哪天就返回哪几天；未点名默认今天，提到“三天/未来/几天”则给三天。"""
    wanted = [off for off, keys in _DAY_KEYS.items() if any(k in query for k in keys)]
    if wanted:
        return sorted(wanted)
    return [0, 1, 2] if any(k in query for k in ("三天", "未来", "几天")) else [0]


_TEMPERATURE_RE = re.compile(r"(\d+)\s*度")


# ══════════════════════════════════════════════════════════════════════
# 各工具的 mock worker（签名 = 真实 worker 的签名）
# ══════════════════════════════════════════════════════════════════════


def _make_websearch(mode: str) -> Callable[..., Any]:
    """按 mode 造 WebSearch 的 mock worker（真实 worker 返回 list[dict]）。"""

    async def _ok(query: str) -> list[dict[str, Any]]:
        if "天气" in query or "气温" in query:
            return _WEATHER_REFS
        if "烤鸭" in query:
            return _DUCK_REFS
        return _GENERIC_REFS

    async def _empty(query: str) -> list[dict[str, Any]]:
        # 复现限流被吞后的现场：工具"成功"返回空列表，上层只能看到 0 条结果。
        return []

    async def _error(query: str) -> list[dict[str, Any]]:
        # 复现工具如实报错：抛出去，由 runner 记为 execution error 进诊断。
        raise RuntimeError(
            "Error code: 429 - RateLimitExceeded.EndpointRPMExceeded (mock)"
        )

    return {"ok": _ok, "empty": _empty, "error": _error}[mode]


async def _mock_poi(
    poi_type: str,
    address: Optional[str] = None,
    city: Optional[str] = None,
    radius: int = 3000,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """POISearch：按关键词选固定数据；radius / limit 不影响 mock 返回。

    返回顺序按 rating 降序（见 ``_DUCK_POIS`` 的排序约定），所以计划里的
    ``RoastDuckShop[0]`` 确实就是评分最高的那家。
    """
    return _DUCK_POIS if "烤鸭" in poi_type else []


def _resolve_poi(destination: str) -> dict[str, Any] | None:
    """把导航目的地解析回门店记录：地址或店名互为子串即算命中。

    计划可能传短地址（“南池子大街11号”）、拼好的全地址（“北京市东城区南池子大街11号”，
    概念投影会拼市/区/街）或直接传店名，三种都认。
    """
    dest = destination.strip()
    if not dest:
        return None
    for poi in _DUCK_POIS:
        for key in ("address", "name"):
            value = str(poi.get(key) or "")
            if value and (value in dest or dest in value):
                return poi
    return None


async def _mock_weather(query: str) -> WeatherOutput:
    """weather_agent：按 query 里的城市 + 日期词返回固定预报（一天一条，与真实插件同形）。

    日期按当前系统时间生成，与“明天”这类相对说法保持一致；城市不在表内时返回空 forecasts +
    说明，模型可据此如实告知用户，而不是拿到另一个城市的天气。
    """
    city = next((c for c in _WEATHER_CITIES if c in query), None)
    if city is None:
        return WeatherOutput(message=f"{_MOCK_TAG}天气数据未覆盖城市：{query}")

    province, city_name, district = _WEATHER_CITIES[city]
    days = _WEATHER_DAYS[city]
    today = datetime.now()
    forecasts = []
    for offset in _day_offsets(query):
        date = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        forecasts.append(
            WeatherItem(
                id=f"mock-{city}-{date}",
                provinceName=province,
                cityName=city_name,
                districtName=district,
                date=date,
                **days[offset],
            )
        )
    return WeatherOutput(
        forecasts=forecasts, message=f"{_MOCK_TAG}固定天气预报（{city}）"
    )


async def _mock_song_search(**_fields: Any) -> dict[str, Any]:
    """SongSearch：返回固定单曲。"""
    return {"songs": _SONGS}


async def _mock_playlist_search(**_fields: Any) -> dict[str, Any]:
    return {"playlists": _PLAYLISTS}


async def _mock_album_search(**_fields: Any) -> dict[str, Any]:
    return {"albums": _ALBUMS}


async def _mock_car_control(command: str) -> CarControlOutput:
    """CarControl：回执只复述入参（顺带把"XX度"抽成结构化字段）。"""
    observation: dict[str, Any] = {"command": command}
    if match := _TEMPERATURE_RE.search(command):
        observation["temperature"] = int(match.group(1))
    return CarControlOutput(
        status=CarControlStatus.SUCCESS,
        message=f"{_MOCK_TAG}已执行车控：{command}",
        observation=observation,
    )


async def _mock_navigate(
    destination: str,
    origin: Optional[str] = None,
    departure_time: Optional[str] = None,
    route_preference: Optional[str] = None,
) -> NavigateOutput:
    """Navigate：除回显入参，还夹带"目的地解析到的门店"。

    真实导航插件落地前会先地理编码，回的 JSON 里有 poiId / 名称 / 地址；只回显入参的话，
    “目的地与评分最高的烤鸭店地址一致”这类断言在工具产出里找不到可对照的门店字段，
    判定器只能判“无证据”→ 降级 → 最终回答被迫加一句“无法判定导航是否匹配门店位置”。

    ``matched=False`` 是要保留的可证伪信号：计划如果拿一个不在候选里的地址去导航，
    回执会如实说没匹配上，断言就能被判“被证伪”而不是“无证据”。
    """
    poi = _resolve_poi(destination)
    observation: dict[str, Any] = {
        "destination": destination,
        "origin": origin or "当前位置",
        "departure_time": departure_time or "现在",
        "route_preference": route_preference or "fastest",
        "distance": "3.2km",
        "duration": "12分钟",
        "status": "已开始导航",
        "resolved_poi": {
            "name": poi["name"] if poi else destination,
            "address": poi["address"] if poi else destination,
            "rating": poi["business"]["rating"] if poi else "",
            "cityname": poi["cityname"] if poi else "",
            "matched": poi is not None,
        },
    }
    return NavigateOutput(
        status=NavigateStatus.SUCCESS,
        message=f"{_MOCK_TAG}已开始导航：{destination}",
        observation=observation,
    )


async def _mock_media(command: str) -> MediaOutput:
    return MediaOutput(
        status=MediaStatus.SUCCESS,
        message=f"{_MOCK_TAG}已开始播放：{command}",
        observation={"command": command, "playing": True},
    )


async def _mock_memory(query: str) -> MemoryRecallOutput:
    return MemoryRecallOutput(
        facts=f"{_MOCK_TAG}常驻上海；空调常用 22 度；偏好本地老字号餐饮。"
    )


# ══════════════════════════════════════════════════════════════════════
# 工厂：与 get_default_tools 同序、同 compact 包装
# ══════════════════════════════════════════════════════════════════════


def get_mock_tools(chat_id: str, *, websearch: str = "ok") -> list[Any]:
    """``get_default_tools`` 的 mock 版：同一组工具、同一个 compact 包装。

    Args:
        chat_id: 需要请求火山的工具（车控/媒体/导航）用；mock worker 忽略它，仅为签名对齐。
        websearch: WebSearch 的行为，见 :data:`WEBSEARCH_MODES`。

    Returns:
        与 ``projects.mind.toolset.dag.get_default_tools`` 同序的工具列表。
    """
    if websearch not in WEBSEARCH_MODES:
        raise ValueError(f"websearch must be one of {WEBSEARCH_MODES}, got {websearch!r}")

    tools = [
        CarControlTool(chat_id, _mock_car_control),
        MediaTool(chat_id, _mock_media),
        MemoryTool(_mock_memory),
        NavigateTool(chat_id, _mock_navigate),
        qq_music_song_search_tool(_mock_song_search),
        qq_music_playlist_search_tool(_mock_playlist_search),
        qq_music_album_search_tool(_mock_album_search),
        poi_search_tool(_mock_poi),
        WeatherTool(chat_id, _mock_weather),
        WebsearchTool(_make_websearch(websearch)),
    ]
    # 与 get_default_tools 一致的 compact 包装（注册表内 5 个 search 工具走 compact + toon）
    return [compact_tool_output(t) for t in tools]
