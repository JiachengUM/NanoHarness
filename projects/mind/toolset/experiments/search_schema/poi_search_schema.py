"""POI 搜索领域 schema。

本模块定义声明式 POI 查询语言：它描述调用方「想找什么」，不描述为了满足
查询需要执行几跳、调用哪些地图接口或如何排序候选。

设计说明：这里没有把 POI 搜索直接建模成完整图搜索 DSL。普通 POI 查询本质
仍然是实体检索：根据 target 自身字段条件，以及可选的空间范围，找到一组目标
POI。只有当用户需求约束 POI 与 POI 之间的关系时，它才呈现图查询形态，例如
「附近有停车场的商场」「商场里面有宠物店」。第一版只把这类需求建模成浅层
关系约束：

- target：要返回的目标 POI，自身字段谓词。
- scope：target 的搜索范围，相对于地址、坐标、用户位置或另一个 POI 等固定锚点。
- relation_query：target 与相关 object POI 之间的布尔关系约束，目前只支持
  nearby 和 contains。

这是一种「轻图查询」建模，而不是通用的 nodes + edges + return_node 图 DSL。
这样 request 形态更容易由 LLM 生成，也更容易被高德实现层编译为关键字搜索、
周边搜索、子 POI/详情字段检查。递归 relation、路径规划、可达性查询暂不属于
这个 schema 版本；如果产品需要，应演进为独立的图查询或路线查询 schema。
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import Field

from projects.mind.toolset.experiments.search_schema.search_schema import (
    BoolQuery,
    DomainSchema,
    GeoPoint,
    Predicate,
    SearchFieldSpec,
    SearchSchemaModel,
    SearchValue,
    SortSpec,
)


PoiAnchorKind = Literal["user_location", "address", "geo_point", "poi"]
PoiRelationKind = Literal["nearby", "contains"]
PoiRelationCountOperator = Literal["eq", "gt", "gte", "lt", "lte"]

PoiSearchField = Literal[
    "text",
    "name",
    "type",
    "address",
    "city",
    "district",
    "distance",
    "commercial_area",
    "rating",
    "cost",
    "opening_hours",
    "feature",
    "floor",
]

PoiSearchQuery = Union["PoiSearchPredicate", "PoiSearchBoolQuery"]


class PoiSearchPredicate(Predicate):
    """Atomic predicate for a POI entity."""

    field: PoiSearchField = Field(..., description="POI search field")
    value: SearchValue | None = Field(default=None, description="POI field condition value")


class PoiSearchBoolQuery(BoolQuery):
    """Boolean predicate group for POI entity fields."""

    must: list[PoiSearchQuery] = Field(default_factory=list, description="Required predicates")
    should: list[PoiSearchQuery] = Field(default_factory=list, description="Preferred predicates")
    must_not: list[PoiSearchQuery] = Field(default_factory=list, description="Excluded predicates")


class PoiNodeQuery(PoiSearchBoolQuery):
    """Query for one POI node, either the returned target or a related object."""


class PoiAnchor(SearchSchemaModel):
    """Fixed spatial anchor for target recall."""

    kind: PoiAnchorKind = Field(..., description="Anchor type")
    address: str | None = Field(default=None, description="Address anchor")
    city: str | None = Field(default=None, description="City used to disambiguate address or POI anchor")
    location: GeoPoint | None = Field(default=None, description="Geo point anchor")
    poi_name: str | None = Field(default=None, description="POI name anchor")


class PoiSpatialScope(SearchSchemaModel):
    """Target search scope relative to a fixed anchor."""

    kind: Literal["around_anchor"] = Field(default="around_anchor", description="Scope type")
    anchor: PoiAnchor = Field(..., description="Fixed spatial anchor")
    radius_meters: int = Field(default=3000, ge=0, le=50000, description="Search radius in meters")


class PoiRelationQuantifier(SearchSchemaModel):
    """Count condition for related POI matches."""

    op: PoiRelationCountOperator = Field(default="gte", description="Count comparison operator")
    count: int = Field(default=1, ge=1, description="Related POI count")


class PoiRelationConstraint(SearchSchemaModel):
    """Relationship constraint between target POI and related object POIs."""

    kind: PoiRelationKind = Field(..., description="Relation type")
    object: PoiNodeQuery = Field(..., description="Related POI object query")
    radius_meters: int | None = Field(default=None, ge=0, le=50000, description="Relation radius in meters")
    quantifier: PoiRelationQuantifier = Field(
        default_factory=PoiRelationQuantifier,
        description="Required related POI count",
    )


class PoiRelationBoolQuery(SearchSchemaModel):
    """Boolean group for relationship constraints."""

    must: list[PoiRelationConstraint] = Field(default_factory=list, description="Required relations")
    should: list[PoiRelationConstraint] = Field(default_factory=list, description="Preferred relations")
    must_not: list[PoiRelationConstraint] = Field(default_factory=list, description="Excluded relations")
    minimum_should_match: int | None = Field(
        default=None,
        ge=0,
        description="Minimum number of should relations to satisfy",
    )


class PoiSearchRequest(SearchSchemaModel):
    """Structured POI search request."""

    domain: Literal["poi"] = Field(default="poi", description="Search domain")
    target: PoiNodeQuery = Field(..., description="Target POI query")
    scope: PoiSpatialScope | None = Field(default=None, description="Spatial scope for target recall")
    relation_query: PoiRelationBoolQuery | None = Field(default=None, description="Target-object relation constraints")
    sort: list[SortSpec] = Field(default_factory=list, description="Sort preferences")
    limit: int | None = Field(default=None, ge=1, description="Expected result count")


POI_SEARCH_DOMAIN_SCHEMA = DomainSchema(
    domain="poi",
    description="POI search domain with spatial scope and target-object relations",
    default_query_fields=["text", "name", "type", "address"],
    default_sort=[SortSpec(field="distance", order="asc")],
    fields={
        "text": SearchFieldSpec(
            name="text",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all"],
            description="Combined POI text field such as name, type, address, and tags",
            examples=["火锅店", "商场 停车"],
        ),
        "name": SearchFieldSpec(
            name="name",
            value_type="text",
            operators=["eq", "match", "match_phrase", "contains"],
            description="POI name",
            examples=["上海万象城", "海底捞"],
        ),
        "type": SearchFieldSpec(
            name="type",
            value_type="text",
            operators=["eq", "in", "match", "contains"],
            description="POI category name",
            examples=["商场", "停车场"],
        ),
        "address": SearchFieldSpec(
            name="address",
            value_type="text",
            operators=["eq", "match", "contains"],
            description="POI address",
            examples=["吴中路"],
        ),
        "city": SearchFieldSpec(
            name="city",
            value_type="keyword",
            operators=["eq", "in"],
            description="City name",
            examples=["上海"],
        ),
        "district": SearchFieldSpec(
            name="district",
            value_type="keyword",
            operators=["eq", "in"],
            description="District name",
            examples=["闵行区"],
        ),
        "distance": SearchFieldSpec(
            name="distance",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="Distance from scope anchor, in meters",
            examples=[500],
        ),
        "commercial_area": SearchFieldSpec(
            name="commercial_area",
            value_type="text",
            operators=["eq", "in", "match", "contains"],
            description="Commercial district or business area name",
            examples=["莘庄"],
        ),
        "rating": SearchFieldSpec(
            name="rating",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="Business rating",
            examples=[4.5],
        ),
        "cost": SearchFieldSpec(
            name="cost",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="Average cost",
            examples=[100],
        ),
        "opening_hours": SearchFieldSpec(
            name="opening_hours",
            value_type="text",
            operators=["exists", "match", "contains"],
            description="Opening hours",
            examples=["10:00-22:00"],
        ),
        "feature": SearchFieldSpec(
            name="feature",
            value_type="text",
            operators=["eq", "in", "match", "contains", "contains_all"],
            description="Feature or facility text, such as parking, family friendly, or charging",
            examples=["适合亲子", "停车方便", "充电"],
        ),
        "floor": SearchFieldSpec(
            name="floor",
            value_type="text",
            operators=["eq", "in", "match", "contains"],
            description="Indoor floor",
            examples=["B1", "L2"],
        ),
    },
)

PoiSearchRequest.domain_schema = POI_SEARCH_DOMAIN_SCHEMA

PoiSearchPredicate.model_rebuild()
PoiSearchBoolQuery.model_rebuild()
PoiNodeQuery.model_rebuild()
PoiRelationConstraint.model_rebuild()
PoiRelationBoolQuery.model_rebuild()
PoiSearchRequest.model_rebuild()


__all__ = [
    "PoiAnchor",
    "PoiAnchorKind",
    "PoiNodeQuery",
    "PoiRelationBoolQuery",
    "PoiRelationConstraint",
    "PoiRelationCountOperator",
    "PoiRelationKind",
    "PoiRelationQuantifier",
    "PoiSearchBoolQuery",
    "PoiSearchField",
    "PoiSearchPredicate",
    "PoiSearchQuery",
    "PoiSearchRequest",
    "PoiSpatialScope",
    "POI_SEARCH_DOMAIN_SCHEMA",
]
