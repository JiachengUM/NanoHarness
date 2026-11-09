"""
POI 搜索工具（单文件实现）：
1. 定义输入/输出模型
2. 定义召回+筛选 worker
3. 提供普通版和 planning 版两个 Tool
"""

from collections.abc import Awaitable
from typing import Callable, Optional

from pydantic import BaseModel, Field

from aicore.tools import create_tool
from projects.mind.toolset.dag.amap import (
    AroundSearchRequest,
    GeoRequest,
    PoiItem,
    PoiSearchResponse,
    TextSearchRequest,
    amap_around_search,
    amap_geo,
    amap_text_search,
)
class PoiSearchInput(BaseModel):
    """POI 搜索参数 - 原子能力：周边检索、关键词搜索"""
    poi_type: str = Field(description="POI或POI类型，多个用|分割")
    address: Optional[str] = Field(default=None, description="地址（默认包含城市）")
    city: Optional[str] = Field(default=None, description="城市名称")
    radius: Optional[int] = Field(default=3000, ge=0, le=5000, description="搜索中心半径(米)，0表示不限制距离")
    limit: Optional[int] = Field(default=10, ge=1, le=25, description="期望返回的结果数量，范围 1-25")


PoiSearchWorker = Callable[..., Awaitable[list[PoiItem]]]

class SGMPoiWorker:

    async def _recall(
        self,
        poi_type: str | None,
        city: str | None,
        address: str | None,
        radius: int,
        show_fields: str,
        page_size: int = 10,
    ) -> PoiSearchResponse:
        if address:
            geo_rsp = await amap_geo(GeoRequest(address=address, city=city))
            if not geo_rsp.geocodes:
                return PoiSearchResponse(status="1")
            location = geo_rsp.geocodes[0].location
            return await amap_around_search(
                AroundSearchRequest(location=location, keywords=poi_type, radius=radius, show_fields=show_fields, page_size=page_size)
            )
        if not poi_type:
            raise ValueError("text 搜索需要提供 keywords")
        return await amap_text_search(TextSearchRequest(keywords=poi_type, region=city, show_fields=show_fields, page_size=page_size))

    async def __call__(
        self,
        poi_type: str | None = None,
        city: str | None = None,
        address: str | None = None,
        radius: int = 3000,
        show_fields: str = "business",
        limit: int = 10,
    ) -> list[PoiItem]:
        rsp = await self._recall(poi_type, city, address, radius, show_fields, page_size=limit)
        return rsp.pois


def poi_search_tool(worker: PoiSearchWorker=SGMPoiWorker(), *, timeout: float | None = None):
    # """普通版 POI 搜索工具（无 planning）。"""
    return create_tool(
        name="POISearch",
        description=(
            "poi周边检索、poi关键词搜索。"
            "输出：POI名称、离中心点距离(米)、POI类型、详细地址、所属省份、所属城市、所属区县、"
            "所属商圈、评分、人均消费、今日营业时间、每周营业时间、联系电话、"
            "POI别名、特色内容、停车场类型（地下、地面、路边）、楼层、室内地图标志"
        ),
        args_schema=PoiSearchInput,
        worker=worker,
        timeout=timeout,
    )


__all__ = [
    "PoiSearchInput",
    "SGMPoiWorker",
    "poi_search_tool"
]
