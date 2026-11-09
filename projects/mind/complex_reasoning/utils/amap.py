from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
from pydantic import BaseModel, Field

from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.complex_reasoning.utils.http_client import HttpClient

__all__ = ["AmapGeoInfo", "AmapPoiItem", "amap_request", "amap_geo", "amap_text_search", "amap_around_search"]

logger = logging.getLogger(__name__)

AMAP_GEO_PATH = "/v3/geocode/geo"
AMAP_TEXT_SEARCH_PATH = "/v5/place/text"
AMAP_AROUND_SEARCH_PATH = "/v5/place/around"


@dataclass(slots=True, frozen=True)
class AmapGeoInfo:
    """高德地理编码结果（共享最小字段集）。"""
    city: str = ""
    location: str = ""


class AmapPoiItem(BaseModel):
    """高德 POI 归一化结构（共享模型，供业务工具复用）。"""
    poi_id: str = Field(default="")
    amap_poi_id: str = Field(default="")
    name: str = Field(default="")
    province: str = Field(default="")
    city: str = Field(default="")
    district: str = Field(default="")
    address: str = Field(default="")
    has_video: bool = Field(default=False)
    longitude: str = Field(default="")
    latitude: str = Field(default="")
    type_name: str = Field(default="")
    cover_url: str = Field(default="")
    rate: str = Field(default="")
    cost: str = Field(default="")
    tags: str = Field(default="")

    def dedup_key(self) -> str:
        return self.amap_poi_id or f"{self.name}|{self.address}"


async def amap_request(path: str, query_param: dict[str, Any]) -> dict[str, Any] | None:
    """
    高德 HTTP 调用公共封装：
    - 自动补 key
    - 固定超时
    - 最多 2 次尝试（1 次重试）
    """
    cfg = get_app_config()
    assert cfg.AMAP_API_KEY, "AMAP_API_KEY 未配置"

    # 统一在这里补 key，调用方只关心业务参数。
    params = {**query_param, "key": cfg.AMAP_API_KEY}
    url = f"{cfg.AMAP_API_URL}{path}"
    timeout = aiohttp.ClientTimeout(total=10)

    for retry in range(2):
        try:
            # 复用项目内 HttpClient（底层连接池复用，避免每次新建 session）。
            client = await HttpClient.get_instance()
            resp = await client.get(url, params=params, timeout=timeout)
            # 高德大多数接口返回 JSON；这里仅接受 dict，其他形态统一视为失败。
            if isinstance(resp.json, dict):
                return resp.json
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("高德请求异常 %s, 重试 %s/2", e, retry + 1)
        if retry < 1:
            # 简单指数退避，避免瞬时网络抖动导致连续失败。
            await asyncio.sleep(0.5 * (2**retry))
    return None


async def amap_geo(address: str, city: str = "") -> AmapGeoInfo | None:
    """高德地理编码：仅返回后续检索常用字段（city/location）。"""
    data = await amap_request(AMAP_GEO_PATH, {"address": address, "city": city})
    # geocodes 为空表示地理编码失败或无匹配结果。
    if not data or "geocodes" not in data or not data["geocodes"]:
        return None
    # 仅取第一个候选，足够支撑当前 Weather/POI 的后续检索流程。
    g = data["geocodes"][0]
    return AmapGeoInfo(
        city=str(g.get("city", "") or ""),
        location=str(g.get("location", "") or ""),
    )


def _parse_pois(data: dict[str, Any] | None) -> list[AmapPoiItem] | None:
    """将高德 POI 响应归一化；返回 None 表示响应结构不符合预期。"""
    if not data or "pois" not in data:
        return None

    result: list[AmapPoiItem] = []
    for poi in data["pois"]:
        # 高德 location 是 "lon,lat" 字符串；拆分后保留字符串格式，避免精度/序列化差异。
        lon, lat = "", ""
        if "location" in poi:
            parts = str(poi["location"]).split(",")
            if len(parts) >= 2:
                lon, lat = parts[0], parts[1]

        # type/rectag 都可能描述类别，优先使用 business.rectag（更贴近推荐标签）。
        type_name = str(poi.get("type", "") or "")
        cover_url = ""
        if poi.get("photos"):
            cover_url = str(poi["photos"][0].get("url", "") or "")

        # business 字段可选：评分/消费/标签没有时统一回空字符串，保证输出 schema 稳定。
        rate = cost = tags = ""
        if "business" in poi:
            b = poi["business"]
            rate = str(b.get("rating", "") or "")
            cost = str(b.get("cost", "") or "")
            tags = str(b.get("tag", "") or "")
            if "rectag" in b:
                type_name = str(b.get("rectag", "") or "") or type_name

        result.append(
            AmapPoiItem(
                poi_id=str(poi.get("id", "") or ""),
                amap_poi_id=str(poi.get("id", "") or ""),
                name=str(poi.get("name", "") or ""),
                province=str(poi.get("pname", "") or ""),
                city=str(poi.get("cityname", "") or ""),
                district=str(poi.get("adname", "") or ""),
                address=str(poi.get("address", "") or ""),
                longitude=lon,
                latitude=lat,
                type_name=type_name,
                cover_url=cover_url,
                rate=rate,
                cost=cost,
                tags=tags,
            )
        )
    return result


async def amap_text_search(
    keywords: str,
    city: str = "",
    citylimit: bool = False,
) -> list[AmapPoiItem] | None:
    # 文本检索：适合“城市 + 关键词”的 POI 搜索。
    data = await amap_request(
        AMAP_TEXT_SEARCH_PATH,
        {
            "keywords": keywords,
            "region": city,
            "citylimit": "1" if (citylimit and city) else "0",
            "show_fields": "business,photos",
            "page_size": 3,
        },
    )
    return _parse_pois(data)


async def amap_around_search(
    keywords: str,
    location: str,
    radius: str = "2000",
) -> list[AmapPoiItem] | None:
    # 周边检索：基于经纬度 + 半径搜索。
    data = await amap_request(
        AMAP_AROUND_SEARCH_PATH,
        {
            "keywords": keywords,
            "location": location,
            "radius": radius,
            "show_fields": "business,photos",
            "page_size": 3,
        },
    )
    return _parse_pois(data)
