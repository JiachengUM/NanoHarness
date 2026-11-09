"""
POI 搜索多跳实验版。

目标：
1. 不改 planner，只在基础 poi_search 的执行模型上扩 nearby。
2. nearby 被视为一种结构化 criteria，和普通字符串 criteria 混用。
3. 只有在 criteria 中存在 nearby 条件时，才走二跳 around 搜索分支。
"""
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aicore.tools import create_tool
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


TextSearchFn = Callable[[TextSearchRequest], Awaitable[PoiSearchResponse]]
AroundSearchFn = Callable[[AroundSearchRequest], Awaitable[PoiSearchResponse]]
GeoFn = Callable[[GeoRequest], Awaitable[Any]]

MAX_OUTPUT_CANDIDATES = 10
MAX_RELATED_POIS_PER_EVIDENCE = 3


class NearbyCriterion(BaseModel):
    """结构化 nearby 条件。"""

    kind: str = Field(default="nearby", description="criteria 类型，固定为 nearby")
    keywords: str = Field(..., description="周边需要命中的 POI 类型或关键词，如书店、咖啡店")
    radius: int = Field(default=3000, ge=0, le=50000, description="周边搜索半径，单位米")
    min_count: int = Field(default=1, ge=1, description="至少需要命中的周边 POI 数量")


Criterion = str | NearbyCriterion


class CriteriaBundle(BaseModel):
    """归一化后的 criteria：普通文本条件和结构化 nearby 条件分开执行。"""

    text: list[str] = Field(default_factory=list)
    nearby: list[NearbyCriterion] = Field(default_factory=list)


class CriteriaParser:
    """把 agent 的宽松入参收敛成 worker 内部强类型条件。"""

    def parse(self, criteria: list[Criterion] | None) -> CriteriaBundle:
        text_criteria: list[str] = []
        nearby_criteria: list[NearbyCriterion] = []
        for item in criteria or []:
            # agent 真实调用时可能传 dict，而不是已经反序列化好的 NearbyCriterion。
            # parser 作为边界适配层，保证后续执行链路只面对强类型 nearby。
            if isinstance(item, str):
                text_criteria.append(item)
            elif isinstance(item, NearbyCriterion):
                nearby_criteria.append(item)
            elif isinstance(item, dict) and item.get("kind") == "nearby":
                nearby_criteria.append(NearbyCriterion.model_validate(item))
            else:
                text_criteria.append(str(item))
        return CriteriaBundle(text=text_criteria, nearby=nearby_criteria)


class PoiSearchMultiHopInput(BaseModel):
    """实验版多跳 POI 搜索输入。"""

    query: str | None = Field(default=None, description="搜索主目标的关键词，如公园、餐厅")
    city: str | None = Field(default=None, description="搜索城市名称")
    criteria: list[Criterion] | None = Field(
        default=None,
        description="普通文字条件或结构化 nearby 条件的混合列表",
    )
    address: str | None = Field(default=None, description="地址或地点；提供时优先走地址锚点周边搜索")
    radius: int = Field(default=3000, ge=0, le=50000, description="地址锚点周边搜索半径，单位米")
    show_fields: str = Field(default="", description="business、indoor、navi 可选，多个字段逗号分隔")


class RelatedPoiEvidence(BaseModel):
    """一个 nearby 条件命中的证据。"""

    keywords: str = Field(..., description="对应 NearbyCriterion.keywords")
    radius: int = Field(..., description="对应 NearbyCriterion.radius")
    matched_count: int = Field(..., description="指定半径内命中的相关 POI 数量")
    nearest_distance: int | None = Field(default=None, description="最近相关 POI 距离，单位米")
    pois: list[PoiItemRaw] = Field(default_factory=list, description="命中的相关 POI 列表")


class PoiSearchMultiHopItem(BaseModel):
    """实验版输出项：保留基础 POI 字段，并增加 nearby 证据。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str | None = None
    type: str | None = None
    name: str | None = None
    address: str | None = None
    location: str | None = None
    distance: int | None = None
    related: list[RelatedPoiEvidence] = Field(default_factory=list)
    score: float = 0.0
    reason: str = ""


class PoiSearchMultiHopOutput(BaseModel):
    """实验版输出。"""

    pois: list[PoiSearchMultiHopItem] = Field(default_factory=list)
    text_criteria: list[str] = Field(default_factory=list)
    nearby_criteria: list[NearbyCriterion] = Field(default_factory=list)
    message: str = ""


RelatedPoiEvidence.model_rebuild()
PoiSearchMultiHopItem.model_rebuild()
PoiSearchMultiHopOutput.model_rebuild()


def split_criteria(criteria: list[Criterion] | None) -> tuple[list[str], list[NearbyCriterion]]:
    """把混合 criteria 拆成普通文字条件和 nearby 条件。"""

    text_criteria: list[str] = []
    nearby_criteria: list[NearbyCriterion] = []
    for item in criteria or []:
        if isinstance(item, str):
            text_criteria.append(item)
        elif isinstance(item, NearbyCriterion):
            nearby_criteria.append(item)
        elif isinstance(item, dict) and item.get("kind") == "nearby":
            nearby_criteria.append(NearbyCriterion.model_validate(item))
        elif getattr(item, "kind", None) == "nearby":
            nearby_criteria.append(item if isinstance(item, NearbyCriterion) else NearbyCriterion.model_validate(item))
        else:
            text_criteria.append(str(item))
    return text_criteria, nearby_criteria


def _distance_of(poi: PoiItemRaw) -> int | None:
    try:
        return int(poi.distance)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_related_evidence(constraint: NearbyCriterion, related_pois: list[PoiItemRaw]) -> RelatedPoiEvidence:
    distances = [_distance_of(item) for item in related_pois]
    nearest = min((distance for distance in distances if distance is not None), default=None)
    sample_pois = sorted(related_pois, key=lambda item: _distance_of(item) or 50000)[:MAX_RELATED_POIS_PER_EVIDENCE]
    return RelatedPoiEvidence(
        keywords=constraint.keywords,
        radius=constraint.radius,
        matched_count=len(related_pois),
        nearest_distance=nearest,
        pois=sample_pois,
    )


def _to_output_item(
    poi: PoiItemRaw,
    *,
    related: list[RelatedPoiEvidence] | None = None,
    score: float = 0.0,
    reason: str = "",
) -> PoiSearchMultiHopItem:
    return PoiSearchMultiHopItem(
        id=poi.id,
        type=poi.type,
        name=poi.name,
        address=poi.address,
        location=poi.location,
        distance=_distance_of(poi),
        related=list(related or []),
        score=score,
        reason=reason,
    )


def _limit_candidates(candidates: list[PoiSearchMultiHopItem]) -> list[PoiSearchMultiHopItem]:
    return sorted(candidates, key=lambda item: item.score, reverse=True)[:MAX_OUTPUT_CANDIDATES]


class PoiSearchMultiHopWorker:
    """基础 poi_search 风格的多跳 worker。"""

    def __init__(
        self,
        *,
        text_search: TextSearchFn = amap_text_search,
        around_search: AroundSearchFn = amap_around_search,
        geo: GeoFn = amap_geo,
    ) -> None:
        self._text_search = text_search
        self._around_search = around_search
        self._geo = geo

    async def _recall(
        self,
        query: str | None,
        city: str | None,
        address: str | None,
        radius: int,
        show_fields: str,
    ) -> PoiSearchResponse:
        if address:
            geo_rsp = await self._geo(GeoRequest(address=address, city=city))
            location = geo_rsp.geocodes[0].location
            return await self._around_search(
                AroundSearchRequest(
                    location=location,
                    keywords=query or "",
                    radius=radius,
                    show_fields=show_fields,
                )
            )
        if not query:
            raise ValueError("text 搜索需要提供 query")
        return await self._text_search(
            TextSearchRequest(
                keywords=query,
                region=city,
                show_fields=show_fields,
            )
        )

    async def _evaluate_target(
        self,
        poi: PoiItemRaw,
        *,
        city: str | None,
        nearby_criteria: list[NearbyCriterion],
        show_fields: str,
    ) -> PoiSearchMultiHopItem | None:
        location = await self._target_location(poi, city)
        if not location:
            return None

        evidences: list[RelatedPoiEvidence] = []
        for constraint in nearby_criteria:
            rsp = await self._around_search(
                AroundSearchRequest(
                    location=location,
                    keywords=constraint.keywords,
                    radius=constraint.radius,
                    show_fields=show_fields,
                    page_size=25,
                )
            )
            related_pois = rsp.pois
            if len(related_pois) < constraint.min_count:
                return None

            evidences.append(_to_related_evidence(constraint, related_pois))

        nearest_values = [
            evidence.nearest_distance
            for evidence in evidences
            if evidence.nearest_distance is not None
        ]
        nearest = min(nearest_values, default=50000)
        related_count = sum(evidence.matched_count for evidence in evidences)
        target_distance = _distance_of(poi) or 50000
        score = related_count * 1000 - nearest - target_distance * 0.1
        parts = [
            f"{evidence.radius}米内有{evidence.matched_count}个{evidence.keywords}"
            + (f"，最近约{evidence.nearest_distance}米" if evidence.nearest_distance is not None else "")
            for evidence in evidences
        ]
        return _to_output_item(
            poi,
            related=evidences,
            score=score,
            reason="；".join(parts),
        )

    async def _filter_by_nearby(
        self,
        raw_pois: list[PoiItemRaw],
        *,
        city: str | None,
        nearby_criteria: list[NearbyCriterion],
        show_fields: str,
    ) -> list[PoiSearchMultiHopItem]:
        evaluated = await asyncio.gather(
            *(
                self._evaluate_target(
                    poi,
                    city=city,
                    nearby_criteria=nearby_criteria,
                    show_fields=show_fields,
                )
                for poi in raw_pois
                if poi.name and (poi.location or poi.address)
            ),
        )
        candidates = [item for item in evaluated if item is not None]
        return _limit_candidates(candidates)

    async def __call__(
        self,
        query: str | None = None,
        city: str | None = None,
        criteria: list[Criterion] | None = None,
        address: str | None = None,
        radius: int = 3000,
        show_fields: str = "children,business,indoor,navi",
    ) -> PoiSearchMultiHopOutput:
        rsp = await self._recall(query, city, address, radius, show_fields)
        text_criteria, nearby_criteria = split_criteria(criteria)

        if not nearby_criteria:
            return PoiSearchMultiHopOutput(
                pois=[_to_output_item(poi, reason="命中主目标关键词") for poi in rsp.pois],
                text_criteria=text_criteria,
                nearby_criteria=[],
                message=f"按原有单跳逻辑返回{len(rsp.pois)}个候选。",
            )

        candidates = await self._filter_by_nearby(
            rsp.pois,
            city=city,
            nearby_criteria=nearby_criteria,
            show_fields=show_fields,
        )
        if not candidates:
            keywords = "、".join(item.keywords for item in nearby_criteria)
            message = f"召回到{len(rsp.pois)}个主目标候选，但没有找到满足 nearby 条件「{keywords}」的结果。"
        else:
            message = f"找到{len(candidates)}个满足 nearby 条件的候选。"
        return PoiSearchMultiHopOutput(
            pois=candidates,
            text_criteria=text_criteria,
            nearby_criteria=nearby_criteria,
            message=message,
        )


def poi_search_multi_hop_tool(worker: PoiSearchMultiHopWorker | None = None):
    """创建实验版 tool。"""

    return create_tool(
        name="地点搜索工具-多跳实验版",
        description="基础 POI 搜索的多跳实验版。criteria 支持普通字符串和 nearby 结构化条件混合输入。",
        args_schema=PoiSearchMultiHopInput,
        worker=worker or PoiSearchMultiHopWorker(),
    )


__all__ = [
    "Criterion",
    "MAX_OUTPUT_CANDIDATES",
    "MAX_RELATED_POIS_PER_EVIDENCE",
    "NearbyCriterion",
    "PoiSearchMultiHopInput",
    "PoiSearchMultiHopItem",
    "PoiSearchMultiHopOutput",
    "PoiSearchMultiHopWorker",
    "RelatedPoiEvidence",
    "poi_search_multi_hop_tool",
]
