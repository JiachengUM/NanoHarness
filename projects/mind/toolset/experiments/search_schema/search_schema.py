"""通用查找任务表达 schema。

这里先只定义「要找什么」的抽象语言，不负责翻译成 ES/SQL/Google query string，
也不负责执行。Web、Music、POI 等 domain 只是在这套语言上声明自己的字段 meta。
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchSchemaModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    domain_schema: ClassVar["DomainSchema | None"] = None

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        schema = super().model_json_schema(*args, **kwargs)
        if cls.domain_schema is None:
            return schema
        return _attach_domain_schema_to_json_schema(schema, cls.domain_schema)


# ========== 抽象层：值、操作符、表达式 ==========

PrimitiveValue = str | int | float | bool
ScalarType = Literal["text", "keyword", "number", "bool", "enum", "date", "datetime", "duration", "geo_point"]
SortOrder = Literal["asc", "desc"]

SearchOperator = Literal[
    # 精确/枚举类
    "eq",
    "ne",
    "in",
    "not_in",
    "exists",
    # 大小/范围类
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    # 文本检索类
    # match: 分词/语义相关匹配，例如“周杰伦 晴天”可命中相关标题、歌手或正文。
    "match",
    # match_phrase: 短语匹配，要求词序和邻近关系更严格，例如歌词中连续出现“我一路向北”。
    "match_phrase",
    "contains",
    "contains_all",
    "prefix",
    "wildcard",
    "regex",
    # 地理类
    "geo_distance",
    "geo_bounding_box",
]


class RangeValue(SearchSchemaModel):
    """标准范围值。

    数字、日期、时间都统一用这个结构表达。具体 domain 再决定怎么翻译成后端语法。
    """

    start: PrimitiveValue | None = Field(default=None, description="范围起点")
    end: PrimitiveValue | None = Field(default=None, description="范围终点")
    include_start: bool = Field(default=True, description="是否包含起点")
    include_end: bool = Field(default=True, description="是否包含终点")


class GeoPoint(SearchSchemaModel):
    lat: float = Field(..., description="纬度")
    lon: float = Field(..., description="经度")


class GeoDistanceValue(SearchSchemaModel):
    center: GeoPoint = Field(..., description="中心点")
    distance_meters: int = Field(..., ge=0, description="距离半径，单位米")


class GeoBoundingBoxValue(SearchSchemaModel):
    top_left: GeoPoint = Field(..., description="左上角坐标")
    bottom_right: GeoPoint = Field(..., description="右下角坐标")


SearchValue = (
    PrimitiveValue
    | list[PrimitiveValue]
    | RangeValue
    | GeoPoint
    | GeoDistanceValue
    | GeoBoundingBoxValue
)

QueryExpression = Union["Predicate", "BoolQuery"]


class Predicate(SearchSchemaModel):
    """领域无关的原子查找条件。

    约定：
    - eq/ne/gt/gte/lt/lte/contains/match/match_phrase/prefix/wildcard/regex 使用单值。
    - in/not_in/contains_all 使用列表值。
    - between 使用 RangeValue。
    - exists 可不填 value。
    - geo_distance 使用 GeoDistanceValue，geo_bounding_box 使用 GeoBoundingBoxValue。
    """

    field: str = Field(..., description="领域字段名，例如 artist、title、site、genre、location")
    op: SearchOperator = Field(..., description="字段和值之间的匹配关系")
    value: SearchValue | None = Field(default=None, description="条件值；exists 可不填")
    note: str | None = Field(default=None, description="可选自然语言补充说明，保留用户原意")


class BoolQuery(SearchSchemaModel):
    """ES/Lucene 风格的布尔查询结构。

    must: 必须满足。
    should: 最好满足，可作为偏好或加分项。
    must_not: 必须排除。
    """

    must: list[QueryExpression] = Field(default_factory=list, description="必须满足")
    should: list[QueryExpression] = Field(default_factory=list, description="最好满足，可作为偏好")
    must_not: list[QueryExpression] = Field(default_factory=list, description="必须排除")
    minimum_should_match: int | None = Field(
        default=None,
        ge=0,
        description="should 至少需要满足的数量；为空时由 domain/compiler 决定",
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_predicate_like_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and ("field" in data or "op" in data or "value" in data):
            raise ValueError("Predicate-like payload must validate as Predicate")
        return data


class SortSpec(SearchSchemaModel):
    field: str = Field(..., description="排序字段")
    order: SortOrder = Field(default="desc", description="排序方向")


class SearchRequest(SearchSchemaModel):
    """领域无关的查找请求。"""

    query: QueryExpression = Field(..., description="查找表达式，支持 Predicate 或 BoolQuery 递归组合")
    sort: list[SortSpec] = Field(default_factory=list, description="排序偏好")
    limit: int | None = Field(default=None, ge=1, description="期望返回数量")


# ========== 抽象层：domain meta ==========

class SearchFieldSpec(SearchSchemaModel):
    """领域字段说明。

    这类似 ES mapping / table schema / index schema 的上层描述：
    它不仅告诉模型字段是什么，也告诉校验器和编译器这个字段能做什么。
    """

    name: str = Field(..., description="字段名")
    value_type: ScalarType = Field(..., description="字段值类型")
    operators: list[SearchOperator] = Field(..., description="字段支持的操作符")
    description: str = Field(..., description="字段语义")
    sortable: bool = Field(default=False, description="是否支持排序")
    values: list[str] | None = Field(default=None, description="枚举字段的可选值")
    examples: list[Any] = Field(default_factory=list, description="字段取值示例")
    derived_from: list[str] = Field(default_factory=list, description="派生字段依赖的原始字段")
    notes: str | None = Field(default=None, description="领域实现或语义归一化说明")


class DomainSchema(SearchSchemaModel):
    domain: str = Field(..., description="领域名，例如 web、music、poi")
    description: str = Field(default="", description="领域说明")
    fields: dict[str, SearchFieldSpec] = Field(..., description="该领域支持的字段")
    default_query_fields: list[str] = Field(default_factory=list, description="无显式字段时默认检索字段")
    default_sort: list[SortSpec] = Field(default_factory=list, description="领域默认排序")


def _sortable_fields(domain_schema: DomainSchema) -> list[str]:
    return [
        field_name
        for field_name, spec in domain_schema.fields.items()
        if spec.sortable
    ]


def _scalar_json_type(value_type: ScalarType) -> str | list[str]:
    if value_type in {"number", "duration"}:
        return "number"
    if value_type == "bool":
        return "boolean"
    if value_type == "geo_point":
        return "object"
    return "string"


def _scalar_value_schema(spec: SearchFieldSpec) -> dict[str, Any]:
    if spec.value_type == "geo_point":
        schema = _geo_point_schema()
        schema["description"] = spec.description
        return schema

    schema: dict[str, Any] = {
        "type": _scalar_json_type(spec.value_type),
        "description": spec.description,
    }
    if spec.value_type == "date":
        schema["format"] = "date"
    if spec.value_type == "datetime":
        schema["format"] = "date-time"
    if spec.values:
        schema["enum"] = spec.values
    if spec.examples:
        schema["examples"] = spec.examples
    return schema


def _array_value_schema(spec: SearchFieldSpec) -> dict[str, Any]:
    item_schema = _scalar_value_schema(spec)
    item_schema.pop("examples", None)
    schema: dict[str, Any] = {
        "type": "array",
        "items": item_schema,
        "minItems": 1,
        "description": f"{spec.description}列表",
    }
    if spec.examples:
        schema["examples"] = [spec.examples]
    return schema


def _range_value_schema(spec: SearchFieldSpec) -> dict[str, Any]:
    scalar_schema = _scalar_value_schema(spec)
    scalar_schema.pop("description", None)
    scalar_schema.pop("examples", None)
    return {
        "type": "object",
        "description": f"{spec.description}范围",
        "properties": {
            "start": scalar_schema,
            "end": scalar_schema,
            "include_start": {"type": "boolean", "default": True},
            "include_end": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    }


def _geo_point_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
        },
        "required": ["lat", "lon"],
        "additionalProperties": False,
    }


def _geo_distance_value_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "center": _geo_point_schema(),
            "distance_meters": {"type": "integer", "minimum": 0},
        },
        "required": ["center", "distance_meters"],
        "additionalProperties": False,
    }


def _geo_bounding_box_value_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "top_left": _geo_point_schema(),
            "bottom_right": _geo_point_schema(),
        },
        "required": ["top_left", "bottom_right"],
        "additionalProperties": False,
    }


def _value_schema_for_operator(spec: SearchFieldSpec, operator: SearchOperator) -> dict[str, Any]:
    if operator == "exists":
        return {"type": "null", "description": "exists 操作符不需要 value，请填 null"}
    if operator in {"in", "not_in", "contains_all"}:
        return _array_value_schema(spec)
    if operator == "between":
        return _range_value_schema(spec)
    if operator == "geo_distance":
        return _geo_distance_value_schema()
    if operator == "geo_bounding_box":
        return _geo_bounding_box_value_schema()
    return _scalar_value_schema(spec)


def _predicate_variant(field_name: str, spec: SearchFieldSpec, operator: SearchOperator) -> dict[str, Any]:
    return {
        "title": f"{field_name} {operator} predicate",
        "properties": {
            "field": {"const": field_name},
            "op": {"const": operator},
            "value": _value_schema_for_operator(spec, operator),
        },
        "required": ["field", "op", "value"],
    }


def _inject_predicate_domain_schema(
    predicate_schema: dict[str, Any],
    domain_schema: DomainSchema,
) -> None:
    predicate_schema["oneOf"] = [
        _predicate_variant(field_name, spec, operator)
        for field_name, spec in domain_schema.fields.items()
        for operator in spec.operators
    ]


def _inject_sort_domain_schema(sort_schema: dict[str, Any], domain_schema: DomainSchema) -> None:
    sortable_fields = _sortable_fields(domain_schema)
    if not sortable_fields:
        return
    properties = sort_schema.get("properties", {})
    field_schema = properties.get("field")
    if not field_schema:
        return
    field_schema["enum"] = sortable_fields


def _attach_domain_schema_to_json_schema(
    schema: dict[str, Any],
    domain_schema: DomainSchema,
) -> dict[str, Any]:
    defs = schema.get("$defs", {})
    for def_schema in defs.values():
        def_properties = def_schema.get("properties", {})
        if "field" in def_properties and "op" in def_properties:
            _inject_predicate_domain_schema(def_schema, domain_schema)
        if "field" in def_properties and "order" in def_properties:
            _inject_sort_domain_schema(def_schema, domain_schema)

    return schema


__all__ = [
    "PrimitiveValue",
    "ScalarType",
    "SearchValue",
    "SearchOperator",
    "SortOrder",
    "RangeValue",
    "GeoPoint",
    "GeoDistanceValue",
    "GeoBoundingBoxValue",
    "Predicate",
    "BoolQuery",
    "QueryExpression",
    "SortSpec",
    "SearchRequest",
    "SearchFieldSpec",
    "DomainSchema",
]
