"""
带 inputtips fallback 的实验版 POI 搜索工具。

目标：
1. 保持和 aicore/tools/experiments/poi_search.py 接近的写法；
2. 仅做 planning 版的最小增强；
3. 当 text / around 搜索没有结果时，用高德 inputtips 给出候选项。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field
from rich import print

from aicore.tools import TaskToolType, create_tool
from aicore.tools.experiments.goal_planner import StructuredGoal
from aicore.runtime.task.worker import TaskSuccess
from projects.mind.toolset.amap import (
    AroundSearchRequest,
    GeoRequest,
    InputTip,
    InputTipsResponse,
    PoiItem as PoiItemRaw,
    PoiSearchResponse,
    TextSearchRequest,
    amap_around_search,
    amap_geo,
    amap_inputtips,
    amap_text_search,
    InputTipsRequest,
)

__all__ = [
    "PoiSearchInput",
    "PoiSearchGoal",
    "PoiItem",
    "PoiSearchOutput",
    "PoiSearchOutputLike",
    "InputTipsPoiWorker",
    "poi_search_tool_with_planning",
    "test_poi_search_tool_with_planning_fallback",
]


class PoiSearchInput(BaseModel):
    query: str = Field(..., description="地点名称、品牌名或地点类型，例如海底捞、咖啡店、公园")
    city: str | None = Field(default=None, description="搜索城市名称，可选")
    address: str | None = Field(default=None, description="周边搜索锚点地址，可选")
    radius: int = Field(default=3000, ge=0, le=50000, description="周边搜索半径，单位米")
    criteria: list[str] | None = Field(default=None, description="其它搜索条件")


class PoiSearchGoal(StructuredGoal, PoiSearchInput):
    criteria: list[str] | None = Field(default=None, description="地点搜索条件列表")


class PoiItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = Field(..., title="类型", description="类型")
    name: str = Field(..., title="名称", description="名称")
    address: str = Field(..., title="详细地址", description="详细地址")
    distance: int | None = Field(default=None, title="离中心点距离", description="离中心点距离，单位米")


class PoiSearchOutput(BaseModel):
    pois: list[PoiItem] = Field(..., description="符合条件的地点列表")


type PoiSearchOutputLike = PoiSearchOutput | str
type PoiSearchWorker = Callable[..., Awaitable[PoiSearchOutputLike]]


def _to_poi_item(raw: PoiItemRaw) -> PoiItem | None:
    if not raw.type or not raw.name or not raw.address:
        return None

    try:
        distance = int(raw.distance) if raw.distance else None
    except (TypeError, ValueError):
        distance = None

    return PoiItem(
        type=raw.type,
        name=raw.name,
        address=raw.address,
        distance=distance,
    )


def _format_inputtips(query: str, tips: list[InputTip]) -> str:
    lines = [f"没有找到“{query}”的精确结果。你可能想找以下地点，请选择更接近的一项："]
    for index, tip in enumerate(tips[:5], start=1):
        name = tip.name or "未知地点"
        district = tip.district or ""
        address = tip.address or ""
        detail = " ".join(part for part in [district, address] if part).strip()
        if detail:
            lines.append(f"{index}. {name}（{detail}）")
        else:
            lines.append(f"{index}. {name}")
    return "\n".join(lines)


class InputTipsPoiWorker:
    """最小实验版 worker：主搜索失败时退回 inputtips。"""

    @staticmethod
    def _to_output(raw_pois: list[PoiItemRaw]) -> PoiSearchOutput:
        pois: list[PoiItem] = []
        for raw in raw_pois:
            item = _to_poi_item(raw)
            if item is not None:
                pois.append(item)
        return PoiSearchOutput(pois=pois)

    async def _suggest_from_inputtips(self, query: str, city: str | None = None) -> str:
        tips_rsp = await amap_inputtips(
            InputTipsRequest(
                keywords=query,
                city=city,
                citylimit=bool(city),
                datatype="poi",
            )
        )
        tips = [tip for tip in tips_rsp.tips if tip.name]
        if not tips:
            return f"没有找到和“{query}”相关的地点，请换个更完整的名称再试。"
        return _format_inputtips(query, tips)

    async def __call__(
        self,
        query: str,
        city: str | None = None,
        address: str | None = None,
        radius: int = 3000,
        criteria: list[str] | None = None,
    ) -> PoiSearchOutputLike:
        del criteria

        if address:
            try:
                geo_rsp = await amap_geo(GeoRequest(address=address, city=city))
            except ValueError:
                return await self._suggest_from_inputtips(address, city)

            around_rsp = await amap_around_search(
                AroundSearchRequest(
                    location=geo_rsp.geocodes[0].location,
                    keywords=query,
                    radius=radius,
                )
            )
            if around_rsp.pois:
                return self._to_output(around_rsp.pois)
            return await self._suggest_from_inputtips(query, city)

        text_rsp = await amap_text_search(TextSearchRequest(keywords=query, region=city))
        if text_rsp.pois:
            return self._to_output(text_rsp.pois)
        return await self._suggest_from_inputtips(query, city)


def poi_search_tool_with_planning(
    worker: PoiSearchWorker,
) -> TaskToolType[PoiSearchGoal, PoiSearchOutputLike, None, ...]:
    return create_tool(
        name="通用地点搜索工具",
        description="""基于用户表达的需求，生成地点搜索所需的信息: 城市、地点类型、搜索条件等，并执行搜索，返回符合条件的地点。
如缺少关键信息，无法执行搜索，该工具会返回向用户的提问。
当地点名称较模糊、未命中精确结果时，工具会返回若干候选地点供用户选择。""",
        args_schema=PoiSearchGoal,
        worker=worker,
        with_clarify=True,
    )


async def test_poi_search_tool_with_planning_fallback():
    print("\ntest_poi_search_tool_with_planning_fallback")

    async def fake_text_search(request: TextSearchRequest):
        del request
        return PoiSearchResponse.model_validate(
            {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "0",
                "pois": [],
            }
        )

    async def fake_inputtips(request: InputTipsRequest):
        del request
        return InputTipsResponse.model_validate(
            {
                "status": "1",
                "info": "OK",
                "count": "2",
                "tips": [
                    {
                        "name": "海底捞火锅",
                        "district": "上海市浦东新区",
                        "address": "张杨路店",
                    },
                    {
                        "name": "海底世界",
                        "district": "上海市浦东新区",
                        "address": "陆家嘴环路",
                    },
                ],
            }
        )

    global amap_text_search, amap_inputtips
    original_text_search = amap_text_search
    original_inputtips = amap_inputtips

    amap_text_search = fake_text_search
    amap_inputtips = fake_inputtips

    try:
        tool = poi_search_tool_with_planning(InputTipsPoiWorker())
        factory = tool.stream_worker_factory(
            description="帮我找海底",
            clarify=None,
            query="海底",
            city="上海",
            address=None,
            radius=3000,
            criteria=None,
        )

        async for event in factory():
            print(event)
            if isinstance(event, TaskSuccess):
                print(event.result)
    finally:
        amap_text_search = original_text_search
        amap_inputtips = original_inputtips


if __name__ == "__main__":
    asyncio.run(test_poi_search_tool_with_planning_fallback())
