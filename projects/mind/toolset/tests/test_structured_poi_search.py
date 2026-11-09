from __future__ import annotations

import pytest

from projects.mind.toolset.amap import (
    BusinessItem,
    ChildrenItem,
    GeocodeResult,
    GeoRequest,
    GeoResponse,
    PoiItem,
    PoiSearchResponse,
)
from projects.mind.toolset.experiments.search_schema.poi_search_schema import PoiSearchRequest
from projects.mind.toolset.experiments.structured_poi_search import (
    PoiSearchCompiler,
    PoiSearchExecutor,
)


def _response(pois: list[PoiItem]) -> PoiSearchResponse:
    return PoiSearchResponse(status="1", info="OK", infocode="10000", count=str(len(pois)), pois=pois)


def _geo(location: str) -> GeoResponse:
    return GeoResponse(
        status="1",
        info="OK",
        count="1",
        geocodes=[GeocodeResult(location=location)],
    )


class FakeAmapService:
    def __init__(self) -> None:
        self.text_requests = []
        self.around_requests = []
        self.geo_requests = []

    async def text_search(self, request):
        self.text_requests.append(request)
        if request.keywords == "闵行万象城":
            return _response([PoiItem(name="闵行万象城", type="商场", address="吴中路", location="120.0,30.0")])
        if request.keywords == "带宠物店商场":
            return _response(
                [
                    PoiItem(
                        id="mall-with-pet",
                        name="带宠物店商场",
                        type="商场",
                        address="C 路",
                        location="123.0,33.0",
                        children=[
                            ChildrenItem(name="萌宠店", subtype="宠物店", address="L2"),
                            ChildrenItem(name="咖啡店", subtype="咖啡店", address="L1"),
                        ],
                    )
                ]
            )
        return _response(
            [
                PoiItem(
                    id="mall-1",
                    name="A 商场",
                    type="商场",
                    address="A 路",
                    location="121.0,31.0",
                    business=BusinessItem(rating="4.6"),
                ),
                PoiItem(
                    id="mall-2",
                    name="B 商场",
                    type="商场",
                    address="B 路",
                    business=BusinessItem(rating="4.8"),
                ),
            ]
        )

    async def around_search(self, request):
        self.around_requests.append(request)
        if "火锅店" in (request.keywords or ""):
            return _response(
                [
                    PoiItem(
                        id="hotpot-1",
                        name="好吃火锅",
                        type="火锅店",
                        address="火锅路",
                        location="120.1,30.1",
                        distance="300",
                        business=BusinessItem(rating="4.5"),
                    )
                ]
            )
        if "停车场" in (request.keywords or ""):
            if request.location == "121.0,31.0":
                return _response(
                    [PoiItem(id="parking-1", name="A 停车场", type="停车场", address="P 路", distance="200")]
                )
            if request.location == "122.0,32.0":
                return _response(
                    [PoiItem(id="parking-2", name="B 停车场", type="停车场", address="P2 路", distance="120")]
                )
            return _response([])
        if "酒吧" in (request.keywords or ""):
            if request.location == "121.0,31.0":
                return _response([PoiItem(id="bar-1", name="A 酒吧", type="酒吧", address="Bar 路", distance="80")])
            return _response([])
        return _response([])

    async def geo(self, request: GeoRequest):
        self.geo_requests.append(request)
        if request.address == "B 路":
            return _geo("122.0,32.0")
        return _geo("120.0,30.0")


def _executor(service: FakeAmapService) -> PoiSearchExecutor:
    return PoiSearchExecutor(
        text_search=service.text_search,
        around_search=service.around_search,
        geo=service.geo,
    )


def test_compiler_generates_text_and_around_recall_steps():
    compiler = PoiSearchCompiler()
    text_request = PoiSearchRequest.model_validate(
        {"domain": "poi", "target": {"must": [{"field": "type", "op": "match", "value": "商场"}]}}
    )
    text_plan = compiler.compile(text_request)
    assert text_plan.target_recall.mode == "text"
    assert text_plan.target_recall.keywords == "商场"

    around_request = PoiSearchRequest.model_validate(
        {
            "domain": "poi",
            "target": {"must": [{"field": "text", "op": "match", "value": "火锅店"}]},
            "scope": {
                "kind": "around_anchor",
                "anchor": {"kind": "address", "address": "上海市闵行区平金中心", "city": "上海"},
                "radius_meters": 3000,
            },
        }
    )
    around_plan = compiler.compile(around_request)
    assert around_plan.target_recall.mode == "around"
    assert around_plan.target_recall.scope is not None


@pytest.mark.asyncio
async def test_executor_nearby_relation_and_geo_fallback():
    service = FakeAmapService()
    executor = _executor(service)
    request = PoiSearchRequest.model_validate(
        {
            "domain": "poi",
            "target": {"must": [{"field": "type", "op": "match", "value": "商场"}]},
            "relation_query": {
                "must": [
                    {
                        "kind": "nearby",
                        "object": {"must": [{"field": "type", "op": "match", "value": "停车场"}]},
                        "radius_meters": 500,
                        "quantifier": {"op": "gte", "count": 1},
                    }
                ]
            },
            "limit": 10,
        }
    )
    output = await executor.execute(request)
    assert {item.id for item in output.pois} == {"mall-1", "mall-2"}
    assert any(req.address == "B 路" for req in service.geo_requests)
    assert all(item.related[0].matched_count == 1 for item in output.pois)


@pytest.mark.asyncio
async def test_executor_must_not_relation_excludes_candidate():
    executor = _executor(FakeAmapService())
    request = PoiSearchRequest.model_validate(
        {
            "domain": "poi",
            "target": {"must": [{"field": "type", "op": "match", "value": "商场"}]},
            "relation_query": {
                "must_not": [
                    {
                        "kind": "nearby",
                        "object": {"must": [{"field": "type", "op": "match", "value": "酒吧"}]},
                        "radius_meters": 200,
                    }
                ]
            },
        }
    )
    output = await executor.execute(request)
    assert [item.id for item in output.pois] == ["mall-2"]


@pytest.mark.asyncio
async def test_executor_quantifier_filters_insufficient_relation_matches():
    executor = _executor(FakeAmapService())
    request = PoiSearchRequest.model_validate(
        {
            "domain": "poi",
            "target": {"must": [{"field": "type", "op": "match", "value": "商场"}]},
            "relation_query": {
                "must": [
                    {
                        "kind": "nearby",
                        "object": {"must": [{"field": "type", "op": "match", "value": "停车场"}]},
                        "radius_meters": 500,
                        "quantifier": {"op": "gte", "count": 2},
                    }
                ]
            },
        }
    )
    output = await executor.execute(request)
    assert output.pois == []


@pytest.mark.asyncio
async def test_executor_address_scope_uses_geo_then_around_recall():
    service = FakeAmapService()
    executor = _executor(service)
    request = PoiSearchRequest.model_validate(
        {
            "domain": "poi",
            "target": {
                "must": [
                    {"field": "text", "op": "match", "value": "火锅店"},
                    {"field": "rating", "op": "gte", "value": 4.0},
                ]
            },
            "scope": {
                "kind": "around_anchor",
                "anchor": {"kind": "address", "address": "上海市闵行区平金中心", "city": "上海"},
                "radius_meters": 3000,
            },
            "sort": [{"field": "distance", "order": "asc"}],
        }
    )
    output = await executor.execute(request)
    assert [item.id for item in output.pois] == ["hotpot-1"]
    assert service.geo_requests[0].address == "上海市闵行区平金中心"
    assert service.around_requests[0].keywords == "火锅店"


@pytest.mark.asyncio
async def test_executor_contains_relation_uses_children():
    executor = _executor(FakeAmapService())
    request = PoiSearchRequest.model_validate(
        {
            "domain": "poi",
            "target": {"must": [{"field": "name", "op": "match", "value": "带宠物店商场"}]},
            "relation_query": {
                "must": [
                    {
                        "kind": "contains",
                        "object": {"must": [{"field": "type", "op": "match", "value": "宠物店"}]},
                        "quantifier": {"op": "gte", "count": 1},
                    }
                ]
            },
        }
    )
    output = await executor.execute(request)
    assert [item.id for item in output.pois] == ["mall-with-pet"]
    assert output.pois[0].related[0].matched_count == 1
