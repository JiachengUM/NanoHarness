"""
POI 搜索工具（单文件实现）：
1. 定义输入/输出模型
2. 定义召回+筛选 worker
3. 提供普通版和 planning 版两个 Tool
"""

from collections.abc import Awaitable
from functools import cached_property
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams, ainvoke
from aicore.tools import create_tool
from aicore.tools.experiments.goal_planner import StructuredGoal
from aicore.utils.nl_repr import nl_repr
from projects.mind.toolset.amap import (
    AroundSearchRequest,
    GeoRequest,
    PoiItem as PoiItemRaw,
    PoiSearchResponse,
    TextSearchRequest,
    amap_around_search,
    amap_geo,
    amap_text_search,
)


class PoiSearchInput(BaseModel):
    # POI 搜索输入参数。

    query: str | None = Field(
        default=None, description="根据内容自动映射至高德API的types或keywords"
    )
    city: str | None = Field(default=None, description="搜索城市名称")
    criteria: list[str] | None = Field(
        default=None, description="criteria是除了query之外的任何其它信息"
    )
    address: str | None = Field(default=None, description="地址或地点，周边搜索必填")
    radius: int = Field(
        default=3000, ge=0, le=50000, description="周边搜索半径，周边搜必填，单位米"
    )
    show_fields: str = Field(
        default="children,business,indoor,navi",
        description="children、business、indoor、navi，可以多选用逗号分割",
    )


class PoiItem(BaseModel):
    """地点项。"""

    model_config = ConfigDict(frozen=True)

    type: str = Field(..., title="类型", description="类型")
    name: str = Field(..., title="名称", description="名称")
    address: str = Field(..., title="详细地址", description="详细地址")
    distance: int | None = Field(
        default=None, title="离中心点距离", description="离中心点距离，单位米"
    )
    # rating: str | None = Field(default=None, title="评分", description="评分")
    # cost: str | None = Field(default=None, title="人均消费", description="人均消费")


class PoiSearchOutput(BaseModel):
    """POI 搜索输出参数。"""

    pois: list[PoiItem] = Field(..., description="符合条件的地点列表")


PoiSearchOutputLike = PoiSearchOutput | str
PoiSearchWorker = Callable[..., Awaitable[PoiSearchOutputLike]]


class PoiSearchGoal(StructuredGoal, PoiSearchInput):
    # POI 搜索目标（planning 输入）。

    criteria: list[str] | None = Field(
        default=None, description="地点搜索条件列表，每条是一个自然语言约束"
    )


def _to_poi_item(raw: PoiItemRaw) -> PoiItem:
    assert raw.type is not None
    assert raw.name is not None
    assert raw.address is not None

    try:
        distance = int(raw.distance)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        distance = None

    business = raw.business

    return PoiItem(
        type=raw.type,
        name=raw.name,
        address=raw.address,
        distance=distance,
        rating=business.rating if business else None,
        cost=business.cost if business else None,
    )


class PoiSearchParams(BaseModel):
    """POI 搜索算法参数。"""

    model: str = Field(default=ModelName.SEED_1_6_FLASH_250828)
    max_turns: int = Field(default=2)

    @cached_property
    def client(self) -> AsyncArk:
        m = ModelName(self.model)
        client, _ = create_client(m, AsyncArk)
        return client


async def filter_pois_by_text_criteria(
    raw_pois: list[PoiItemRaw],
    criteria: list[str],
    params: PoiSearchParams,
) -> str:
    """复用原始 POI 的 LLM criteria 筛选路径。"""

    prompt = f"""你需要从下述给出的地点中筛选出符合条件的。
{nl_repr(raw_pois)}
筛选条件：
{nl_repr(criteria)}
筛选规则：
一、当有多个筛选条件并且不能同时满足时，满足部分关键筛选条件也可以作为推荐建议返回。
二、当全部筛选条件均不满足时，可适当做常识性推理作为推荐建议返回。
三、当POI列表为空时，停止筛选，说明原因。
无论怎样都必须在结果中展示所有POI内容并说明所有筛选条件的通过和未通过原因。
"""
    rsp = await ainvoke(
        prompt,
        client=params.client,
        model=params.model,
        params=ResponseParams(thinking={"type": "disabled"}),
    )
    return rsp.raw_text


class SGMPoiWorker:
    """组合 text + around + criteria 筛选的 POI worker。"""

    def __init__(self, params: PoiSearchParams | None = None):
        self.params = params or PoiSearchParams()

    async def _recall(
        self,
        poi_type: str | None,
        city: str | None,
        address: str | None,
        radius: int,
        show_fields: str,
    ) -> PoiSearchResponse:
        if address:
            geo_rsp = await amap_geo(GeoRequest(address=address, city=city))
            location = geo_rsp.geocodes[0].location
            return await amap_around_search(
                AroundSearchRequest(
                    location=location,
                    keywords=poi_type,
                    radius=radius,
                    show_fields=show_fields,
                )
            )
        if not poi_type:
            raise ValueError("text 搜索需要提供 keywords")
        return await amap_text_search(
            TextSearchRequest(keywords=poi_type, region=city, show_fields=show_fields)
        )

    @staticmethod
    def _to_output(raw_pois: list[PoiItemRaw]) -> PoiSearchOutput:
        pois: list[PoiItem] = []
        for item in raw_pois:
            try:
                pois.append(_to_poi_item(item))
            except AssertionError:
                continue
        return PoiSearchOutput(pois=pois)

    async def _filter_by_criteria(
        self, raw_pois: list[PoiItemRaw], criteria: list[str]
    ) -> str:
        return await filter_pois_by_text_criteria(raw_pois, criteria, self.params)

    async def __call__(
        self,
        query: str | None = None,
        city: str | None = None,
        criteria: list[str] | None = None,
        address: str | None = None,
        radius: int = 3000,
        show_fields: str = "children,business,indoor,navi",
    ) -> PoiSearchOutputLike:
        rsp = await self._recall(query, city, address, radius, show_fields)
        criteria = criteria or []
        if not criteria:
            return self._to_output(rsp.pois)
        return await self._filter_by_criteria(rsp.pois, criteria)


def poi_search_tool(worker: PoiSearchWorker, *, timeout: float | None = None):
    """普通版 POI 搜索工具（无 planning）。"""
    return create_tool(
        name="地点搜索工具",
        description="""完全遵循用户要求搜索poi，必须按criteria筛选，criteria是除了query之外的任何其它信息；
        business：poi所属商圈、营业时间、联系电话、特色内容、停车场类型、评分和人均消费；
        indoor：楼层索引、所在楼层；
        navi：导航引导点坐标包括各类poi出入口；
        返回的结果列表默认按距离从近到远排序。""",
        args_schema=PoiSearchInput,
        worker=worker,
        timeout=timeout,
    )


def poi_search_tool_with_planning(worker: PoiSearchWorker):
    """带 planning 的 POI 搜索工具。"""
    return create_tool(
        name="地点搜索工具",
        description="""基于用户需求搜索地点，支持按 criteria 筛选，criteria可以是任何搜索条件；
        business：设置后返回poi所属商圈、营业时间、联系电话、特色内容（关键词：美食）、停车场类型（地下、地面、路边，关键词：停车场）、评分和人均消费（关键词：餐饮、酒店、景点、影院）；indoor：设置后返回室内相关信息包括楼层索引、所在楼层；navi：设置后返回导航引导点坐标包括各类poi出入口；""",
        args_schema=PoiSearchGoal,
        worker=worker,
        with_clarify=True,
    )


__all__ = [
    "PoiSearchInput",
    "PoiSearchGoal",
    "PoiSearchOutput",
    "PoiSearchOutputLike",
    "PoiSearchParams",
    "SGMPoiWorker",
    "filter_pois_by_text_criteria",
    "poi_search_tool",
    "poi_search_tool_with_planning",
]
