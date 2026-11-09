"""Structured POI search implementation.

The public input is a declarative PoiSearchRequest. Multi-hop work is compiled
and executed internally as an implementation detail.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

import anyio
from pydantic import BaseModel, ConfigDict, Field

from aicore.tools import create_tool
from projects.mind.toolset.amap import (
    AroundSearchRequest,
    ChildrenItem,
    GeoRequest,
    PoiItem as PoiItemRaw,
    PoiSearchResponse,
    TextSearchRequest,
    amap_around_search,
    amap_geo,
    amap_text_search,
)
from projects.mind.toolset.experiments.search_schema.poi_search_schema import (
    PoiAnchor,
    PoiNodeQuery,
    PoiRelationBoolQuery,
    PoiRelationConstraint,
    PoiRelationQuantifier,
    PoiSearchBoolQuery,
    PoiSearchPredicate,
    PoiSearchQuery,
    PoiSearchRequest,
    PoiSpatialScope,
)
from projects.mind.toolset.experiments.search_schema.search_schema import RangeValue, SearchValue, SortSpec


TextSearchFn = Callable[[TextSearchRequest], Awaitable[PoiSearchResponse]]
AroundSearchFn = Callable[[AroundSearchRequest], Awaitable[PoiSearchResponse]]
GeoFn = Callable[[GeoRequest], Awaitable[Any]]

RECALL_FIELDS = {"text", "name", "type", "address", "commercial_area", "feature"}
NEGATIVE_OPERATORS = {"ne", "not_in"}
DEFAULT_RECALL_KEYWORD = "地点"
DEFAULT_LIMIT = 10
MAX_PAGE_SIZE = 25
DEFAULT_RELATION_RADIUS_METERS = 1000
DEFAULT_AMAP_SHOW_FIELDS = "children,business,indoor,navi"


class PoiRecallStep(BaseModel):
    """Internal target recall step."""

    mode: Literal["text", "around"] = Field(..., description="Recall mode")
    keywords: str = Field(..., description="Recall keywords")
    city: str | None = Field(default=None, description="Search city")
    scope: PoiSpatialScope | None = Field(default=None, description="Spatial scope for around recall")
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_PAGE_SIZE)


class PoiExecutionPlan(BaseModel):
    """Internal execution plan generated from PoiSearchRequest."""

    target_recall: PoiRecallStep
    target_filter: PoiNodeQuery
    relation_query: PoiRelationBoolQuery | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int = DEFAULT_LIMIT


class PoiRelationEvidence(BaseModel):
    """Evidence for one evaluated POI relation."""

    kind: str
    keywords: str = ""
    radius_meters: int | None = None
    matched_count: int = 0
    nearest_distance: int | None = None
    satisfied: bool = False
    reason: str = ""
    pois: list[PoiItemRaw] = Field(default_factory=list)


class StructuredPoiCandidate(BaseModel):
    """POI candidate returned by the structured POI worker."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str | None = None
    type: str | None = None
    name: str | None = None
    address: str | None = None
    location: str | None = None
    distance: int | None = None
    related: list[PoiRelationEvidence] = Field(default_factory=list)
    score: float = 0.0
    reason: str = ""


class StructuredPoiSearchOutput(BaseModel):
    """Structured POI search output."""

    pois: list[StructuredPoiCandidate] = Field(default_factory=list)
    message: str = ""


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _as_list(value: SearchValue | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, RangeValue):
        return " ".join(str(item) for item in [value.start, value.end] if item is not None)
    return str(value).strip()


def _distance_of(poi: PoiItemRaw) -> int | None:
    try:
        return int(poi.distance)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_output_item(
    poi: PoiItemRaw,
    *,
    related: list[PoiRelationEvidence] | None = None,
    score: float = 0.0,
    reason: str = "",
) -> StructuredPoiCandidate:
    return StructuredPoiCandidate(
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


def _recall_keywords(query: PoiSearchQuery) -> str:
    terms = _dedupe_keep_order(_extract_recall_terms(query))
    return " ".join(terms) if terms else DEFAULT_RECALL_KEYWORD


def _extract_recall_terms(query: PoiSearchQuery) -> list[str]:
    if isinstance(query, PoiSearchPredicate):
        if query.field not in RECALL_FIELDS or query.op in NEGATIVE_OPERATORS:
            return []
        return [_stringify_value(item) for item in _as_list(query.value) if _stringify_value(item)]

    terms: list[str] = []
    for item in query.must:
        terms.extend(_extract_recall_terms(item))
    for item in query.should:
        terms.extend(_extract_recall_terms(item))
    return terms


def _city_hint(query: PoiSearchQuery) -> str | None:
    if isinstance(query, PoiSearchPredicate):
        if query.field == "city" and query.value is not None:
            return _stringify_value(query.value)
        return None
    for item in [*query.must, *query.should]:
        city = _city_hint(item)
        if city:
            return city
    return None


class PoiSearchCompiler:
    """Compile declarative POI query into an internal execution plan."""

    def compile(self, request: PoiSearchRequest) -> PoiExecutionPlan:
        limit = min(request.limit or DEFAULT_LIMIT, MAX_PAGE_SIZE)
        keywords = _recall_keywords(request.target)
        mode: Literal["text", "around"] = "around" if request.scope else "text"
        city = request.scope.anchor.city if request.scope else _city_hint(request.target)
        recall = PoiRecallStep(
            mode=mode,
            keywords=keywords,
            city=city,
            scope=request.scope,
            limit=limit,
        )
        return PoiExecutionPlan(
            target_recall=recall,
            target_filter=request.target,
            relation_query=request.relation_query,
            sort=request.sort,
            limit=limit,
        )


class PoiCandidateResolver:
    """Resolve a candidate POI to a coordinate string."""

    def __init__(
        self,
        *,
        text_search: TextSearchFn,
        geo: GeoFn,
    ) -> None:
        self._text_search = text_search
        self._geo = geo

    async def resolve_location(self, poi: PoiItemRaw, city: str | None = None) -> str | None:
        if poi.location:
            return poi.location
        if not poi.address:
            return None
        geo_rsp = await self._geo(GeoRequest(address=poi.address, city=city))
        geocodes = getattr(geo_rsp, "geocodes", [])
        if not geocodes:
            return None
        return geocodes[0].location

    async def resolve_anchor(self, anchor: PoiAnchor) -> str | None:
        if anchor.location:
            return f"{anchor.location.lon},{anchor.location.lat}"
        if anchor.address:
            geo_rsp = await self._geo(GeoRequest(address=anchor.address, city=anchor.city))
            geocodes = getattr(geo_rsp, "geocodes", [])
            return geocodes[0].location if geocodes else None
        if anchor.poi_name:
            rsp = await self._text_search(
                TextSearchRequest(keywords=anchor.poi_name, region=anchor.city, page_size=1)
            )
            if not rsp.pois:
                return None
            return await self.resolve_location(rsp.pois[0], anchor.city)
        return None


class PoiNodeMatcher:
    """Small deterministic matcher for POI predicates after recall."""

    def matches_node(self, item: PoiItemRaw | ChildrenItem, query: PoiSearchQuery) -> bool:
        if isinstance(query, PoiSearchPredicate):
            return self.matches_predicate(item, query)

        if any(not self.matches_node(item, subquery) for subquery in query.must):
            return False
        if any(self.matches_node(item, subquery) for subquery in query.must_not):
            return False

        should_count = sum(1 for subquery in query.should if self.matches_node(item, subquery))
        minimum = query.minimum_should_match
        if minimum is None:
            minimum = 1 if query.should and not query.must else 0
        return should_count >= minimum

    def matches_predicate(self, item: PoiItemRaw | ChildrenItem, predicate: PoiSearchPredicate) -> bool:
        actual = self._field_value(item, predicate.field)
        if predicate.op == "exists":
            return actual is not None and actual != ""
        if predicate.op == "ne":
            return not self._compare(actual, "eq", predicate.value)
        if predicate.op == "not_in":
            return not self._compare(actual, "in", predicate.value)
        return self._compare(actual, predicate.op, predicate.value)

    def _compare(self, actual: Any, op: str, expected: SearchValue | None) -> bool:
        if actual is None:
            return False
        if op == "eq":
            return self._as_text(actual) == self._as_text(expected)
        if op == "in":
            return self._as_text(actual) in {self._as_text(item) for item in _as_list(expected)}
        if op == "prefix":
            return self._as_text(actual).startswith(self._as_text(expected))
        if op in {"match", "contains", "match_phrase"}:
            return self._matches_text(actual, expected, require_all=False)
        if op == "contains_all":
            return self._matches_text(actual, expected, require_all=True)
        if op in {"gt", "gte", "lt", "lte"}:
            return self._compare_number(actual, op, expected)
        if op == "between" and isinstance(expected, RangeValue):
            return self._between(actual, expected)
        return False

    def _matches_text(self, actual: Any, expected: SearchValue | None, *, require_all: bool) -> bool:
        actual_text = self._as_text(actual).lower()
        terms: list[str] = []
        for value in _as_list(expected):
            terms.extend(term.lower() for term in self._as_text(value).split() if term)
        if not terms:
            return False
        if require_all:
            return all(term in actual_text for term in terms)
        return any(term in actual_text for term in terms)

    def _compare_number(self, actual: Any, op: str, expected: SearchValue | None) -> bool:
        left = self._as_float(actual)
        right = self._as_float(expected)
        if left is None or right is None:
            return False
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        if op == "lte":
            return left <= right
        return False

    def _between(self, actual: Any, expected: RangeValue) -> bool:
        left = self._as_float(actual)
        if left is None:
            return False
        if expected.start is not None:
            start = self._as_float(expected.start)
            if start is not None and (left < start if expected.include_start else left <= start):
                return False
        if expected.end is not None:
            end = self._as_float(expected.end)
            if end is not None and (left > end if expected.include_end else left >= end):
                return False
        return True

    def _field_value(self, item: PoiItemRaw | ChildrenItem, field: str) -> Any:
        if isinstance(item, ChildrenItem):
            values = {
                "text": " ".join(
                    str(value)
                    for value in [item.name, item.address, item.subtype, item.sname]
                    if value
                ),
                "name": item.name,
                "type": item.subtype or item.sname,
                "address": item.address,
            }
            return values.get(field)

        business = item.business
        indoor = item.indoor
        values = {
            "text": " ".join(
                str(value)
                for value in [
                    item.name,
                    item.type,
                    item.address,
                    item.cityname,
                    item.adname,
                    business.business_area if business else None,
                    business.tag if business else None,
                    business.parking_type if business else None,
                ]
                if value
            ),
            "name": item.name,
            "type": item.type,
            "address": item.address,
            "city": item.cityname,
            "district": item.adname,
            "distance": _distance_of(item),
            "commercial_area": business.business_area if business else None,
            "rating": business.rating if business else None,
            "cost": business.cost if business else None,
            "opening_hours": self._join_text(
                business.opentime_today if business else None,
                business.opentime_week if business else None,
            ),
            "feature": self._join_text(
                business.tag if business else None,
                business.parking_type if business else None,
            ),
            "floor": indoor.truefloor or indoor.floor if indoor else None,
        }
        return values.get(field)

    def _join_text(self, *values: Any) -> str:
        return " ".join(str(value) for value in values if value)

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _as_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class PoiRelationEvaluator:
    """Evaluate target-object relation constraints for one target candidate."""

    def __init__(
        self,
        *,
        around_search: AroundSearchFn,
        resolver: PoiCandidateResolver,
        matcher: PoiNodeMatcher,
    ) -> None:
        self._around_search = around_search
        self._resolver = resolver
        self._matcher = matcher

    async def evaluate_query(
        self,
        poi: PoiItemRaw,
        relation_query: PoiRelationBoolQuery | None,
        *,
        city: str | None,
    ) -> tuple[bool, list[PoiRelationEvidence]]:
        if relation_query is None:
            return True, []

        evidences: list[PoiRelationEvidence] = []
        for relation in relation_query.must:
            satisfied, evidence = await self.evaluate_relation(poi, relation, city=city)
            evidences.append(evidence)
            if not satisfied:
                return False, evidences

        for relation in relation_query.must_not:
            satisfied, evidence = await self.evaluate_relation(poi, relation, city=city)
            evidences.append(evidence)
            if satisfied:
                return False, evidences

        should_results: list[tuple[bool, PoiRelationEvidence] | None] = [None] * len(relation_query.should)

        async def evaluate_should(index: int, relation: PoiRelationConstraint) -> None:
            should_results[index] = await self.evaluate_relation(poi, relation, city=city)

        async with anyio.create_task_group() as task_group:
            for index, relation in enumerate(relation_query.should):
                task_group.start_soon(evaluate_should, index, relation)

        should_satisfied = 0
        for result in should_results:
            if result is None:
                continue
            satisfied, evidence = result
            evidences.append(evidence)
            if satisfied:
                should_satisfied += 1

        minimum = relation_query.minimum_should_match
        if minimum is None:
            minimum = 1 if relation_query.should and not relation_query.must else 0
        return should_satisfied >= minimum, evidences

    async def evaluate_relation(
        self,
        poi: PoiItemRaw,
        relation: PoiRelationConstraint,
        *,
        city: str | None,
    ) -> tuple[bool, PoiRelationEvidence]:
        if relation.kind == "nearby":
            return await self._evaluate_nearby(poi, relation, city=city)
        return self._evaluate_contains(poi, relation)

    async def _evaluate_nearby(
        self,
        poi: PoiItemRaw,
        relation: PoiRelationConstraint,
        *,
        city: str | None,
    ) -> tuple[bool, PoiRelationEvidence]:
        location = await self._resolver.resolve_location(poi, city)
        keywords = _recall_keywords(relation.object)
        radius = relation.radius_meters or DEFAULT_RELATION_RADIUS_METERS
        if not location:
            evidence = PoiRelationEvidence(
                kind=relation.kind,
                keywords=keywords,
                radius_meters=radius,
                reason="target location unavailable",
            )
            return False, evidence

        rsp = await self._around_search(
            AroundSearchRequest(
                location=location,
                keywords=keywords,
                radius=radius,
                region=city,
                show_fields=DEFAULT_AMAP_SHOW_FIELDS,
                page_size=MAX_PAGE_SIZE,
            )
        )
        matched = [item for item in rsp.pois if self._matcher.matches_node(item, relation.object)]
        distances = [_distance_of(item) for item in matched]
        nearest = min((distance for distance in distances if distance is not None), default=None)
        satisfied = self._matches_quantifier(len(matched), relation.quantifier)
        evidence = PoiRelationEvidence(
            kind=relation.kind,
            keywords=keywords,
            radius_meters=radius,
            matched_count=len(matched),
            nearest_distance=nearest,
            satisfied=satisfied,
            reason=f"{len(matched)} related POIs matched",
            pois=matched[:5],
        )
        return satisfied, evidence

    def _evaluate_contains(
        self,
        poi: PoiItemRaw,
        relation: PoiRelationConstraint,
    ) -> tuple[bool, PoiRelationEvidence]:
        keywords = _recall_keywords(relation.object)
        children = poi.children or []
        matched = [child for child in children if self._matcher.matches_node(child, relation.object)]
        satisfied = self._matches_quantifier(len(matched), relation.quantifier)
        reason = f"{len(matched)} child POIs matched" if poi.children is not None else "children field unavailable"
        evidence = PoiRelationEvidence(
            kind=relation.kind,
            keywords=keywords,
            matched_count=len(matched),
            satisfied=satisfied,
            reason=reason,
        )
        return satisfied, evidence

    def _matches_quantifier(self, matched_count: int, quantifier: PoiRelationQuantifier) -> bool:
        if quantifier.op == "eq":
            return matched_count == quantifier.count
        if quantifier.op == "gt":
            return matched_count > quantifier.count
        if quantifier.op == "gte":
            return matched_count >= quantifier.count
        if quantifier.op == "lt":
            return matched_count < quantifier.count
        if quantifier.op == "lte":
            return matched_count <= quantifier.count
        return False


class PoiSearchExecutor:
    """Execute compiled POI plans."""

    def __init__(
        self,
        *,
        text_search: TextSearchFn = amap_text_search,
        around_search: AroundSearchFn = amap_around_search,
        geo: GeoFn = amap_geo,
    ) -> None:
        self._text_search = text_search
        self._around_search = around_search
        self.compiler = PoiSearchCompiler()
        self.resolver = PoiCandidateResolver(text_search=text_search, geo=geo)
        self.matcher = PoiNodeMatcher()
        self.relation_evaluator = PoiRelationEvaluator(
            around_search=around_search,
            resolver=self.resolver,
            matcher=self.matcher,
        )

    async def execute(self, request: PoiSearchRequest) -> StructuredPoiSearchOutput:
        plan = self.compiler.compile(request)
        recalled = await self._recall(plan.target_recall)
        filtered = [poi for poi in recalled if self.matcher.matches_node(poi, plan.target_filter)]
        candidates = await self._apply_relations(filtered, plan)
        self._rank(candidates, plan.sort)
        limited = candidates[: plan.limit]
        message = f"found {len(limited)} POIs" if limited else "no POIs matched"
        return StructuredPoiSearchOutput(pois=limited, message=message)

    async def _recall(self, step: PoiRecallStep) -> list[PoiItemRaw]:
        if step.mode == "text":
            rsp = await self._text_search(
                TextSearchRequest(
                    keywords=step.keywords,
                    region=step.city,
                    show_fields=DEFAULT_AMAP_SHOW_FIELDS,
                    page_size=step.limit,
                )
            )
            return rsp.pois

        if step.scope is None:
            return []
        location = await self.resolver.resolve_anchor(step.scope.anchor)
        if not location:
            return []
        rsp = await self._around_search(
            AroundSearchRequest(
                location=location,
                keywords=step.keywords,
                radius=step.scope.radius_meters,
                region=step.city,
                show_fields=DEFAULT_AMAP_SHOW_FIELDS,
                page_size=step.limit,
            )
        )
        return rsp.pois

    async def _apply_relations(
        self,
        pois: list[PoiItemRaw],
        plan: PoiExecutionPlan,
    ) -> list[StructuredPoiCandidate]:
        if not plan.relation_query:
            return [_to_output_item(poi, reason="target matched") for poi in pois]

        city = plan.target_recall.city
        evaluated: list[tuple[bool, list[PoiRelationEvidence]] | None] = [None] * len(pois)

        async def evaluate_candidate(index: int, poi: PoiItemRaw) -> None:
            evaluated[index] = await self.relation_evaluator.evaluate_query(
                poi,
                plan.relation_query,
                city=city,
            )

        async with anyio.create_task_group() as task_group:
            for index, poi in enumerate(pois):
                task_group.start_soon(evaluate_candidate, index, poi)

        candidates: list[StructuredPoiCandidate] = []
        for poi, result in zip(pois, evaluated, strict=False):
            if result is None:
                continue
            satisfied, evidences = result
            if not satisfied:
                continue
            score = self._score(poi, evidences)
            reason = "; ".join(evidence.reason for evidence in evidences if evidence.satisfied)
            candidates.append(_to_output_item(poi, related=evidences, score=score, reason=reason))
        return candidates

    def _score(self, poi: PoiItemRaw, evidences: list[PoiRelationEvidence]) -> float:
        matched_count = sum(evidence.matched_count for evidence in evidences if evidence.satisfied)
        nearest = min(
            (evidence.nearest_distance for evidence in evidences if evidence.nearest_distance is not None),
            default=50000,
        )
        distance = _distance_of(poi) or 50000
        return matched_count * 1000 - nearest - distance * 0.1

    def _rank(self, candidates: list[StructuredPoiCandidate], sort: list[SortSpec]) -> None:
        if not sort:
            candidates.sort(key=lambda item: item.score, reverse=True)
            return
        for spec in reversed(sort):
            reverse = spec.order == "desc"
            if spec.field == "distance":
                candidates.sort(key=lambda item: item.distance if item.distance is not None else 50000, reverse=reverse)
            elif spec.field == "score":
                candidates.sort(key=lambda item: item.score, reverse=reverse)
            else:
                candidates.sort(key=lambda item: item.score, reverse=True)


StructuredPoiSearchWorker = Callable[..., Awaitable[StructuredPoiSearchOutput]]


class StructuredPoiSearchWorkerImpl:
    """Tool worker for structured POI search."""

    def __init__(
        self,
        executor: PoiSearchExecutor | None = None,
        *,
        text_search: TextSearchFn = amap_text_search,
        around_search: AroundSearchFn = amap_around_search,
        geo: GeoFn = amap_geo,
    ) -> None:
        self.executor = executor or PoiSearchExecutor(
            text_search=text_search,
            around_search=around_search,
            geo=geo,
        )

    async def __call__(self, **kwargs: Any) -> StructuredPoiSearchOutput:
        request = PoiSearchRequest.model_validate(kwargs)
        return await self.executor.execute(request)


def structured_poi_search_tool(
    worker: StructuredPoiSearchWorker | None = None,
    *,
    timeout: float | None = None,
):
    """Create the structured POI search tool."""

    return create_tool(
        name="structured_poi_search",
        description="Structured POI search with target predicates, spatial scope, and POI relations.",
        args_schema=PoiSearchRequest,
        worker=worker or StructuredPoiSearchWorkerImpl(),
        timeout=timeout,
    )


__all__ = [
    "PoiCandidateResolver",
    "PoiExecutionPlan",
    "PoiRecallStep",
    "PoiRelationEvaluator",
    "PoiRelationEvidence",
    "PoiSearchCompiler",
    "PoiSearchExecutor",
    "StructuredPoiCandidate",
    "StructuredPoiSearchOutput",
    "StructuredPoiSearchWorker",
    "StructuredPoiSearchWorkerImpl",
    "structured_poi_search_tool",
]
