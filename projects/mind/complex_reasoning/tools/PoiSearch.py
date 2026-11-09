"""
POI 查询工具：对应原 complex_reasoning_agent poi_agent。
使用 LLM 抽取 slot（关键词、地点、是否周边、半径）后调高德地图 API。
"""
from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import Awaitable, List, cast

from pydantic import BaseModel, Field, model_validator

from aicore.tools import BaseTool

from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.complex_reasoning.utils.amap import (
    AmapGeoInfo,
    AmapPoiItem,
    amap_around_search,
    amap_geo,
    amap_text_search,
)

__all__ = ["PoiSearchInput", "PoiSearchTool"]

logger = logging.getLogger(__name__)

DEFAULT_RADIUS = 5000
MAX_RADIUS = 50000

POI_SLOT_PROMPT = """你是个好用的本地生活服务助手，你可以根据用户的问题，提取出用户需要的服务类型和服务地点。
## 输出字段说明
搜索关键字：具体poi名称或者类型，输出为字符串数组（JSON list）；
搜索地点：用户指定的服务地点，只是xx路、xx商场等多个地方都有的地名时，需要预测用户最有可能说的是哪个城市的地点，然后将城市名称输出到搜索地点中。比如'南京路'，'万达广场'等；
搜索城市：用户希望检索的城市（无法确定时可留空）；
是否是区域范围搜索：输出布尔值，true表示是，false表示否；
搜索半径：用户指定的搜索半径，取值范围:0-50000，单位为米；
## 输出格式
请按调用方提供的 JSON Schema 输出结构化字段，不要输出额外解释文字。

## 注意事项
- 当用户意图是周边LBS查询或者某个地址周边LBS查询时,是否是区域范围搜索为1。
- 搜索关键词要去掉修饰内容。比如'免费'等。
- 当用户意图是某地美食时，先回想当地有哪些特色美食，以特色美食的名称为关键词进行查询。比如合肥有吴山贡鹅、庐州烤鸭、三河米饺等。
- 用户意图是查询【某地】或【自身附近】的苍蝇小馆、米其林餐厅、米其林*星餐厅、必吃榜餐厅、宝藏小店、本地人常去吃的餐厅等人为排行榜单时，先理解用户的意图，基于10km范围思考有哪些此类型店铺，提出5个具体店铺名称作为关键词。
- 用户搜索POI类型模糊时，需要理解意图，总结关键词。比如：`适合全家老小一起去的地方`，需要搜索公园、动物园、游乐园等适合全家游玩的地点。`卖烟的地方`，需要搜索便利店、烟酒店等通常是卖烟的地方。

## 特殊关键词keywords转换
- `可以刷医保的药店` -> `医保药店`。
- `智己售后``智己售后中心` -> `智己用户中心`。
- 用户只表达有什么好玩的，`keywords`是`休闲娱乐`。
- `打开拍照的地方 -> `打卡地`。
"""


# ---------- POI slot 抽取 + 搜索（原 poi_agent/poi_agent.poi_search_new） ----------
class PoiSearchStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class PoiErrorCode(StrEnum):
    CONFIG_MISSING = "CONFIG_MISSING"
    SLOT_PARSE_ERROR = "SLOT_PARSE_ERROR"
    GEO_NOT_FOUND = "GEO_NOT_FOUND"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"


class PoiSlot(BaseModel):
    """POI slot（同时作为 LLM 结构化输出 schema 与内部业务模型）。"""
    keywords: list[str] = Field(description="搜索关键字列表；每项为一个具体 POI 名称或类型")
    address: str = Field(description="搜索地点/地址")
    city: str = Field(default="", description="搜索城市；无法确定可留空")
    is_around: bool = Field(default=False, description="是否区域范围搜索（true 表示周边搜索）")
    radius: int | None = Field(default=None, description=f"搜索半径（米），范围 0-{MAX_RADIUS}；不确定可留空")

    @model_validator(mode="after")
    def normalize(self) -> "PoiSlot":
        address = self.address.strip()
        if not address:
            raise ValueError("poi_slot empty address")

        keywords = [k.strip() for k in self.keywords if isinstance(k, str) and k.strip()]
        if not keywords:
            keywords = [address]

        city = self.city.strip()
        radius = self.radius if self.radius is not None else DEFAULT_RADIUS
        radius = max(0, min(MAX_RADIUS, radius))

        object.__setattr__(self, "address", address)
        object.__setattr__(self, "city", city)
        object.__setattr__(self, "keywords", keywords)
        object.__setattr__(self, "radius", radius)
        return self


class PoiSearchToolOutput(BaseModel):
    """POI 工具统一输出（内部搜索结果与工具返回共用同一模型）。"""
    slot: PoiSlot | None = Field(description="POI slot 抽取结果")
    """poi search的输入，放在这里方便看而已"""

    list: List[AmapPoiItem] = Field(default_factory=list, description="去重后的 POI 结果列表")
    message: str = Field(description="结果说明或错误信息")
    status: PoiSearchStatus = Field(description="执行状态：ok/error")
    error_code: PoiErrorCode | None = Field(default=None, description="错误码；成功时为空")


async def _poi_slot_completion(query: str) -> PoiSlot:
    """用 Chat API + 结构化输出抽取并归一化 POI slot。"""
    from aicore.models.credentials import AsyncArk, ModelName, create_client
    from aicore.models.chat import ainvoke_output_by_schema

    client, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    res = await ainvoke_output_by_schema(
        f"{POI_SLOT_PROMPT}\n\n用户问题：{query}",
        output_type=PoiSlot,
        client=client,
        model=model,
    )
    return PoiSlot.model_validate(res.output)


def _build_search_tasks(
    slot: PoiSlot,
    geo: AmapGeoInfo,
) -> list[Awaitable[list[AmapPoiItem] | None]]:
    # around 模式按经纬度查周边；否则按城市做文本检索。
    if slot.is_around:
        return [amap_around_search(kw, geo.location, str(slot.radius)) for kw in slot.keywords]
    return [amap_text_search(kw, geo.city) for kw in slot.keywords]


def _merge_and_dedup(
    results: list[list[AmapPoiItem] | None],
) -> tuple[list[AmapPoiItem], bool]:
    '''将多个关键词的搜索结果聚合并去重。
     返回值：
    1) merged: 去重后的 POI 列表（保持首次出现顺序）
    2) has_upstream_parse_error: 是否至少有一个上游搜索返回了 None（响应缺失/解析失败）
    去重键策略：
    - 优先使用高德 POI ID（稳定）
    - 若无 ID，则退化为 name+address，减少重复结果'''
    merged: list[AmapPoiItem] = []
    seen: set[str] = set()
    has_upstream_parse_error = False
    for group in results:
        if group is None:
            # 某个关键词的请求失败或返回结构不完整：记录标记，但不中断其他关键词结果的聚合。
            has_upstream_parse_error = True
            continue
        for poi in group:
            key = poi.dedup_key()
            if key in seen:
                continue
            seen.add(key)
            merged.append(poi)
    return merged, has_upstream_parse_error


async def poi_search(query: str) -> PoiSearchToolOutput:
    """根据用户查询进行 POI 搜索（LLM slot + 高德 API）。"""
    # 1) 配置校验：无 key 直接返回结构化错误
    cfg = get_app_config()
    if not cfg.AMAP_API_KEY:
        logger.warning("AMAP_API_KEY 未配置，POI 搜索不可用")
        return PoiSearchToolOutput(slot=None, list=[], status=PoiSearchStatus.ERROR, error_code=PoiErrorCode.CONFIG_MISSING, message="POI 服务未配置（需 AMAP_API_KEY）")

    # 2) LLM 结构化抽槽 + 归一化。
    try:
        slot = await _poi_slot_completion(query)
        logger.info("poi_search slot: query=%s, slot=%s", query, slot)
    except Exception as e:
        logger.warning("poi_slot 解析失败: %s", e)
        return PoiSearchToolOutput(slot=None, list=[], status=PoiSearchStatus.ERROR, error_code=PoiErrorCode.SLOT_PARSE_ERROR, message="无法解析检索关键词与地点")

    # 3) 地址地理编码，拿 city/location 供后续检索。
    geo = await amap_geo(slot.address, slot.city)
    if geo is None or not geo.location:
        logger.warning("maps_geo 无结果: address=%s", slot.address)
        return PoiSearchToolOutput(slot=slot, list=[], status=PoiSearchStatus.ERROR, error_code=PoiErrorCode.GEO_NOT_FOUND, message="未解析到有效地点")

    # 4) 并发检索多个关键词，并聚合去重。
    tasks = _build_search_tasks(slot, geo)
    try:
        results = await asyncio.gather(*tasks)
    except Exception as e:
        logger.exception("poi_search upstream error: %s", e)
        return PoiSearchToolOutput(slot=slot, list=[], status=PoiSearchStatus.ERROR, error_code=PoiErrorCode.UPSTREAM_ERROR, message=f"POI 查询异常: {e}")

    pois, has_parse_error = _merge_and_dedup(results)
    if not pois and has_parse_error:
        return PoiSearchToolOutput(slot=slot, list=[], status=PoiSearchStatus.ERROR, error_code=PoiErrorCode.UPSTREAM_ERROR, message="POI 查询异常: pois_missing")
    logger.info("poi_search 返回 %s 条", len(pois))
    return PoiSearchToolOutput(slot=slot, list=pois, status=PoiSearchStatus.OK, message=f"共 {len(pois)} 条结果" if pois else "未找到结果")


# ---------- Tool 定义 ----------
class PoiSearchInput(BaseModel):
    """POI 检索描述。可为具体地点或「某地附近的某类 POI」。"""
    query: str = Field(description="要检索的 POI 描述，如：北京望京的咖啡店、人民大道221号附近3公里内的酒店")


class PoiSearchTool(BaseTool):
    """POI 信息查询工具。使用 LLM 抽 slot + 高德地图 API。"""
    name: str = "poi_search"
    description: str = "搜索具体 POI 点信息。支持：1）某地+类型，如「北京望京的咖啡店」；2）某地址周边范围，如「人民大道221号附近3公里内的酒店」。须提供城市或具体地址，不要仅用「附近」「周边」等模糊词。"
    args_schema: type[BaseModel] = PoiSearchInput

    def _run(self, query: str) -> dict:
        """同步路径不支持，请使用 ainvoke/astream。"""
        raise NotImplementedError("POI 搜索请使用异步调用 ainvoke/astream")

    async def _arun(self, query: str) -> PoiSearchToolOutput:
        try:
            return await poi_search(query)
        except Exception as e:
            logger.exception("poi_search_new error: %s", e)
            return PoiSearchToolOutput(slot=None, list=[], status=PoiSearchStatus.ERROR, error_code=PoiErrorCode.UPSTREAM_ERROR, message=f"检索异常: {e}")
