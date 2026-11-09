from __future__ import annotations

import json
import re
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, Field

from aicore.models.model_api import ModelAPI, UserMessage
from aicore.tools import TaskAStreamWorker, TaskAWorker, TaskToolType, create_tool
from aicore.utils._concepts.meta import (
    ArrayType,
    Attribute,
    Concept,
    ObjectType,
    PrimitiveAttributeType,
    ValueType,
)


class EntitySearchToolInput(BaseModel):
    query: str = Field(description="当前搜索步骤的小目标或用户查询")
    tool_name: str = Field(description="当前搜索工具名称，如 web_search/poi_search/music_search")
    output_schema: dict[str, Any] = Field(description="当前工具的全量输出 JSON Schema")


type EntitySearchToolOutputLike = Concept
type EntitySearchWorker = TaskAWorker[EntitySearchToolOutputLike]
type EntitySearchStreamWorker = TaskAStreamWorker[str, EntitySearchToolOutputLike, ...]


def create_entity_search_tool(
    worker: EntitySearchWorker | EntitySearchStreamWorker,
) -> TaskToolType[EntitySearchToolInput, EntitySearchToolOutputLike, str, ...]:
    """创建 entity_search_tool，用于基于 query 选择搜索工具输出字段子集。"""

    description = "根据用户 query 和当前工具全量 output_schema，生成合理的动态 output_schema 字段子集。"

    return create_tool(
        name="entity_search_tool",
        description=description,
        args_schema=EntitySearchToolInput,
        worker=worker,
        with_clarify=False,
    )


# ---------------------------------------------------------------------------
# Concept ↔ Schema 转换
# ---------------------------------------------------------------------------


def concept_to_schema(concept: Concept) -> dict[str, Any]:
    """将嵌套 Concept 转换为 JSON Schema dict。"""
    schema: dict[str, Any] = {
        "title": concept.name,
        "type": "object",
        "properties": {},
    }
    for attr in concept.attributes:
        schema["properties"][attr.name] = _attr_to_schema(attr)
    return schema


def flatten_concept_paths(concept: Concept, prefix: str = "") -> list[str]:
    """从嵌套 Concept 中提取所有叶子节点的 dot-separated 路径。

    嵌套对象用 '.' 分隔，数组用 '[]' 标记，与 collect_schema_attributes 的 key 格式一致。
    例如: ["name", "business.rating", "songs[].song_name"]
    """
    paths: list[str] = []
    for attr in concept.attributes:
        current = f"{prefix}.{attr.name}" if prefix else attr.name
        paths.extend(_flatten_value_type_paths(attr.type, current))
    return paths


def _flatten_value_type_paths(value_type: ValueType, current: str) -> list[str]:
    if isinstance(value_type, ArrayType):
        return _flatten_value_type_paths(value_type.item_type, f"{current}[]")

    if isinstance(value_type, ObjectType):
        paths: list[str] = []
        for prop in value_type.properties:
            child_path = f"{current}.{prop.name}"
            paths.extend(_flatten_value_type_paths(prop.type, child_path))
        return paths

    return [current]


# ---------------------------------------------------------------------------
# collect_schema_attributes — 从 BaseModel 收集所有叶子字段（eval 验证用）
# ---------------------------------------------------------------------------


def collect_schema_attributes(model: type[BaseModel]) -> dict[str, Attribute]:
    """收集 BaseModel 的所有叶子字段为 flat path → Attribute 映射。"""
    attributes: dict[str, Attribute] = {}
    _collect_model_attributes(model, parent_path="", attributes=attributes)
    return attributes


def full_output_schema_payload(model: type[BaseModel]) -> dict[str, Any]:
    """生成给 LLM / 人工审查用的全量 schema 信息。"""
    return {
        "model": model.__name__,
        "json_schema": model.model_json_schema(),
    }


def compact_output_schema(model: type[BaseModel]) -> dict[str, Any]:
    """将 Pydantic model 的 JSON Schema 压缩为仅含 name → description 的紧凑格式。

    - 叶子字段: ``{"field_name": "description"}``
    - 嵌套对象: ``{"field_name": {"child": "desc", ...}}``
    - 数组(元素为对象): ``{"field_name[]": {"child": "desc", ...}}``
    - 数组(元素为标量): ``{"field_name[]": "description"}``
    """
    full_schema = model.model_json_schema()
    defs = full_schema.get("$defs", {})
    return _compact_properties(full_schema.get("properties", {}), defs)


# ---------------------------------------------------------------------------
# EntitySearchSchemaWorker — LLM 驱动的 schema 子集生成
# ---------------------------------------------------------------------------


class EntitySearchSchemaWorker:
    def __init__(self, model_api: ModelAPI[Any]):
        self._model_api = model_api

    async def __call__(
        self,
        query: str,
        tool_name: str,
        output_schema: dict[str, Any],
    ) -> Concept:
        tool_input = EntitySearchToolInput(
            query=query,
            tool_name=tool_name,
            output_schema=output_schema,
        )
        state = self._model_api.initial_state()
        response = await self._model_api.structured_output(
            UserMessage(text=_build_prompt(tool_input)),
            output_type=Concept,
            state=state,
        )
        if response.parsed is None:
            raise ValueError(
                f"entity_search_tool failed to generate Concept: {response.metadata}"
            )
        return response.parsed


# ---------------------------------------------------------------------------
# Prompt（仅基于 JSON Schema，引导 LLM 输出嵌套 Concept）
# ---------------------------------------------------------------------------


def _build_prompt(tool_input: EntitySearchToolInput) -> str:
    schema = tool_input.output_schema
    if _is_full_json_schema(schema):
        return _build_prompt_full(tool_input)
    return _build_prompt_compact(tool_input)


def _is_full_json_schema(schema: dict[str, Any]) -> bool:
    return "properties" in schema or "$defs" in schema


def _build_prompt_full(tool_input: EntitySearchToolInput) -> str:
    return (
        "你是一个 schema 字段选择器。根据用户的 query 和工具的全量 output JSON Schema，"
        "从中选择与 query 相关的字段子集。\n\n"
        "请直接输出一个 JSON 对象（不要嵌套额外的 key），包含以下字段：\n"
        "- name（string）：英文 PascalCase，如 SelectedPOIOutput\n"
        "- definition（string）：简述选择了哪些字段及原因\n"
        "- attributes（array）：选中的字段列表，每个元素包含：\n"
        "  - name：必须与 JSON Schema 中的字段名完全一致\n"
        "  - type：字段类型。叶子字段直接填 string / integer / float / boolean；"
        "对象字段填 {\"properties\": [...]}；数组字段填 {\"item_type\": ...}\n"
        "  - title：属性的中文名称\n"
        "  - description：沿用或概括原字段含义\n"
        "  - is_required（bool）：是否必需，通常为 false\n"
        "对象 type.properties 内的元素格式同 attributes；数组 type.item_type 描述元素类型。\n\n"
        f"工具名称: {tool_input.tool_name}\n"
        f"用户 query: {tool_input.query}\n"
        "全量 output JSON Schema:\n"
        f"{json.dumps(tool_input.output_schema, ensure_ascii=False, indent=2)}"
    )


def _build_prompt_compact(tool_input: EntitySearchToolInput) -> str:
    return (
        "你是一个 schema 字段选择器。根据用户的 query 和工具的全量输出字段列表，"
        "从中选择与 query 相关的字段子集。\n\n"
        "下方的字段列表格式说明：\n"
        "- 值为字符串的条目是叶子字段，字符串内容是该字段的含义\n"
        "- 值为嵌套对象 {} 的条目是对象字段，对象内的 key 是它的子字段\n"
        "- key 以 \"[]\" 结尾的条目是数组字段，每个数组元素包含其内部的子字段\n\n"
        "请直接输出一个 JSON 对象（不要嵌套额外的 key），包含以下字段：\n"
        "- name（string）：英文 PascalCase，如 SelectedPOIOutput\n"
        "- definition（string）：简述选择了哪些字段及原因\n"
        "- attributes（array）：选中的字段列表，每个元素包含：\n"
        "  - name：字段名，必须与字段列表中的 key 完全一致（不含 [] 后缀）\n"
        "  - type：字段类型。叶子字段统一填 string；"
        "对象字段填 {\"properties\": [...]}；数组字段填 {\"item_type\": ...}\n"
        "  - title：属性的中文名称\n"
        "  - description：沿用字段列表中的含义描述\n"
        "  - is_required（bool）：是否必需，通常为 false\n"
        "对象 type.properties 内的元素格式同 attributes；数组 type.item_type 描述元素类型。\n\n"
        f"工具名称: {tool_input.tool_name}\n"
        f"用户 query: {tool_input.query}\n"
        "全量输出字段列表:\n"
        f"{json.dumps(tool_input.output_schema, ensure_ascii=False, indent=2)}"
    )


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _attr_to_schema(attr: Attribute) -> dict[str, Any]:
    """将单个 Attribute 转换为 JSON Schema 属性。"""
    schema = _value_type_to_schema(attr.type)
    if attr.description:
        schema = {**schema, "description": attr.description}
    return schema


def _value_type_to_schema(value_type: ValueType) -> dict[str, Any]:
    if isinstance(value_type, PrimitiveAttributeType):
        return {"type": _json_type_for(value_type)}

    if isinstance(value_type, ObjectType):
        child_schema: dict[str, Any] = {
            "type": "object",
            "properties": {},
        }
        for child in value_type.properties:
            child_schema["properties"][child.name] = _attr_to_schema(child)
        return child_schema

    if isinstance(value_type, ArrayType):
        return {"type": "array", "items": _value_type_to_schema(value_type.item_type)}

    raise TypeError(f"Unsupported value type: {value_type!r}")


def _collect_model_attributes(
    model: type[BaseModel],
    *,
    parent_path: str,
    attributes: dict[str, Attribute],
) -> None:
    for field_name, field_info in model.model_fields.items():
        path = f"{parent_path}.{field_name}" if parent_path else field_name
        annotation = _strip_optional(field_info.annotation)
        nested_model = _as_basemodel_type(annotation)
        list_item = _list_item_type(annotation)
        description = field_info.description or ""

        if nested_model is not None:
            _collect_model_attributes(nested_model, parent_path=path, attributes=attributes)
            continue

        if list_item is not None:
            list_model = _as_basemodel_type(_strip_optional(list_item))
            if list_model is not None:
                _collect_model_attributes(
                    list_model,
                    parent_path=f"{path}[]",
                    attributes=attributes,
                )
            else:
                attributes[path] = _make_attribute(path, list_item, description)
            continue

        attributes[path] = _make_attribute(path, annotation, description)


def _make_attribute(path: str, annotation: Any, description: str) -> Attribute:
    attr_type = _attribute_type_for(annotation)
    return Attribute(
        name=_safe_field_name(path),
        type=attr_type,
        title=path,
        description=description,
        is_required=False,
    )


def _strip_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _list_item_type(annotation: Any) -> Any | None:
    origin = get_origin(annotation)
    if origin in (list, tuple):
        args = get_args(annotation)
        return args[0] if args else Any
    return None


def _as_basemodel_type(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _attribute_type_for(annotation: Any) -> PrimitiveAttributeType:
    annotation = _strip_optional(annotation)
    if annotation is bool:
        return PrimitiveAttributeType.BOOLEAN
    if annotation is int:
        return PrimitiveAttributeType.INTEGER
    if annotation is float:
        return PrimitiveAttributeType.FLOAT
    return PrimitiveAttributeType.STRING


def _json_type_for(attr_type: PrimitiveAttributeType) -> str:
    if attr_type == PrimitiveAttributeType.BOOLEAN:
        return "boolean"
    if attr_type == PrimitiveAttributeType.INTEGER:
        return "integer"
    if attr_type == PrimitiveAttributeType.FLOAT:
        return "number"
    return "string"


def _safe_field_name(path: str) -> str:
    name = path.replace("[]", "_items")
    name = re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_").lower()
    if not name:
        name = "field"
    if name[0].isdigit():
        name = f"field_{name}"
    return name


def _compact_properties(
    properties: dict[str, Any],
    defs: dict[str, Any],
) -> dict[str, Any]:
    """递归将 JSON Schema properties 转为紧凑 {name: desc} 格式。"""
    result: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        resolved = _resolve_ref(field_schema, defs)
        desc = resolved.get("description", "")

        # array
        if resolved.get("type") == "array":
            items = _resolve_ref(resolved.get("items", {}), defs)
            if items.get("type") == "object" and "properties" in items:
                result[f"{field_name}[]"] = _compact_properties(items["properties"], defs)
            else:
                result[f"{field_name}[]"] = items.get("description", desc)
            continue

        # nested object
        if resolved.get("type") == "object" and "properties" in resolved:
            result[field_name] = _compact_properties(resolved["properties"], defs)
            continue

        # leaf (including anyOf nullable)
        result[field_name] = desc
    return result


def _resolve_ref(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """解析 $ref 和 anyOf（nullable wrapper）引用。"""
    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        return defs.get(ref_name, schema)
    # anyOf nullable: [{"$ref": "..."}, {"type": "null"}] or [{"type": "X"}, {"type": "null"}]
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if len(non_null) == 1:
            resolved = _resolve_ref(non_null[0], defs)
            # 保留外层 description
            if "description" in schema and "description" not in resolved:
                resolved = {**resolved, "description": schema["description"]}
            return resolved
    # allOf with single item (Pydantic nested model reference)
    if "allOf" in schema and len(schema["allOf"]) == 1:
        resolved = _resolve_ref(schema["allOf"][0], defs)
        if "description" in schema and "description" not in resolved:
            resolved = {**resolved, "description": schema["description"]}
        return resolved
    return schema


__all__ = [
    "EntitySearchSchemaWorker",
    "EntitySearchToolInput",
    "EntitySearchToolOutputLike",
    "EntitySearchWorker",
    "EntitySearchStreamWorker",
    "collect_schema_attributes",
    "compact_output_schema",
    "concept_to_schema",
    "create_entity_search_tool",
    "flatten_concept_paths",
    "full_output_schema_payload",
]
