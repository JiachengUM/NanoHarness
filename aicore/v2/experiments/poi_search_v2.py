from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager, TaskProgress, TaskSuccess
from aicore.tools import TaskAStreamWorker
from aicore.v2.tools.async_task import Asyncable
from aicore.v2.tools.factory import create_tool

from projects.mind.toolset.poi_search import SGMPoiWorker


class PoiSearchInput(BaseModel):
    query: str = Field(..., description="地点类型或搜索关键词，例如酒店、川菜、停车场、咖啡店")
    city: str | None = Field(default=None, description="城市")
    address: str | None = Field(default=None, description="周边搜索中心点。用户说附近、周边、从某地出发时必须提供")
    criteria: list[str] = Field(default_factory=list, description="除地点关键词之外的筛选条件")
    radius: int = Field(default=3000, ge=100, le=50000, description="周边搜索半径，单位米")


class PoiItem(BaseModel):
    type: str = Field(default="", description="地点类型")
    name: str = Field(default="", description="地点名称")
    address: str = Field(default="", description="详细地址")
    distance: int | None = Field(default=None, description="离中心点距离，单位米")
    rating: str | None = Field(default=None, description="评分")
    cost: str | None = Field(default=None, description="人均消费")


class PoiSearchOutput(BaseModel):
    pois: list[PoiItem] = Field(default_factory=list, description="地点搜索结果")
    message: str = Field(default="", description="结果说明")


PoiSearchWorker = Callable[..., Awaitable[PoiSearchOutput | str]]
PoiSearchStreamWorker = TaskAStreamWorker[str, PoiSearchOutput | str, ...]


def _normalize_poi_output(value: object) -> PoiSearchOutput | str:
    if isinstance(value, str):
        return value

    raw_pois = getattr(value, "pois", None)
    if raw_pois is None:
        return PoiSearchOutput(message=str(value))

    pois: list[PoiItem] = []
    for raw in raw_pois:
        if isinstance(raw, PoiItem):
            pois.append(raw)
            continue
        raw_dict = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        pois.append(PoiItem.model_validate(raw_dict))

    return PoiSearchOutput(pois=pois)


class PoiSearchV2Worker:
    def __init__(self, worker: SGMPoiWorker | None = None):
        self.worker = worker or SGMPoiWorker()

    async def __call__(
        self,
        query: str,
        city: str | None = None,
        address: str | None = None,
        criteria: list[str] | None = None,
        radius: int = 3000,
    ) -> PoiSearchOutput | str:
        result = await self.worker(
            query=query,
            city=city,
            address=address,
            criteria=criteria or [],
            radius=radius,
        )
        return _normalize_poi_output(result)


class PoiSearchV2StreamWorker:
    def __init__(self, worker: PoiSearchWorker):
        self.worker = worker

    async def __call__(
        self,
        query: str,
        city: str | None = None,
        address: str | None = None,
        criteria: list[str] | None = None,
        radius: int = 3000,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[PoiSearchOutput | str], None]:
        yield TaskProgress(progress="开始地点搜索")
        yield TaskProgress(progress="执行周边搜索" if address else "执行文本地点搜索")
        if criteria:
            yield TaskProgress(progress="包含筛选条件: " + "；".join(criteria))
        result = await self.worker(query=query, city=city, address=address, criteria=criteria or [], radius=radius)
        yield TaskSuccess(result=result)


def poi_search_v2_tool(
    worker: PoiSearchWorker | PoiSearchStreamWorker | None = None,
    *,
    timeout: float | None = 20,
    task_manager: TaskManager,
    asyncable: Asyncable = "async",
):
    worker = worker or PoiSearchV2StreamWorker(PoiSearchV2Worker())
    return create_tool(
        name="地点搜索工具",
        description=(
            "搜索酒店、餐厅、停车场、咖啡店、景点等地点。"
            "用户要求找地点、附近地点、按距离/评分/预算筛选地点时使用。"
            "criteria 必须承载除 query 之外的所有筛选要求。"
        ),
        args_schema=PoiSearchInput,
        worker=worker,
        timeout=timeout,
        asyncable=asyncable,
        with_clarify=True,
        task_manager=task_manager,
    )


__all__ = [
    "PoiSearchInput",
    "PoiItem",
    "PoiSearchOutput",
    "PoiSearchWorker",
    "PoiSearchV2Worker",
    "PoiSearchV2StreamWorker",
    "poi_search_v2_tool",
]
