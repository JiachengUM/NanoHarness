"""Entity Search Tool V2 — 基于 flat path 的 schema 字段子集选择。

与 V1 的区别：
- V1: LLM 从嵌套 JSON Schema 生成嵌套 Concept（结构负担大、易出错）
- V2: 将 schema 展平为 dot-path 列表，LLM 直接输出 SimpleConcept

路径约定：
- "." 表示嵌套（如 business.rating）
- "[]" 表示数组（如 songs[].song_name）
- SimpleConcept 中每个 PrimitiveAttribute.name 即完整 dot-path
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aicore.models.model_api import ModelAPI, UserMessage
from aicore.tools import TaskAWorker, TaskToolType, create_tool
from aicore.utils._concepts.meta import (
    Attribute,
    PrimitiveAttributeType,
    SimpleConcept,
)


# ---------------------------------------------------------------------------
# Tool Input / Output
# ---------------------------------------------------------------------------


class EntitySearchToolInputV2(BaseModel):
    """V2 工具输入。

    用 flat path 映射替代 V1 的嵌套 JSON Schema：
    - fields:  {dot-path: 字段描述}
    - field_types: {dot-path: 类型字符串}（可选）
    """

    query: str = Field(description="当前搜索步骤的小目标或用户查询")
    tool_name: str = Field(description="当前搜索工具名称")
    fields: dict[str, str] = Field(
        description="全量字段路径 → 描述映射，如 {'business.rating': '评分'}"
    )
    field_types: dict[str, str] = Field(
        default_factory=dict,
        description="全量字段路径 → 类型映射，如 {'business.rating': 'string'}",
    )


type EntitySearchToolOutputV2 = SimpleConcept
type EntitySearchWorkerV2 = TaskAWorker[EntitySearchToolOutputV2]


def create_entity_search_tool_v2(
    worker: EntitySearchWorkerV2,
) -> TaskToolType[EntitySearchToolInputV2, EntitySearchToolOutputV2, str, ...]:
    """创建 V2 entity_search_tool。

    worker 签名: ``(query, tool_name, fields, field_types) -> SimpleConcept``
    """
    return create_tool(
        name="entity_search_tool_v2",
        description="根据用户 query 从 flat path 列表中选择搜索工具输出字段子集（V2）。",
        args_schema=EntitySearchToolInputV2,
        worker=worker,
        with_clarify=False,
    )


# ---------------------------------------------------------------------------
# Attribute → Tool Input 转换
# ---------------------------------------------------------------------------


def attributes_to_fields(attrs: dict[str, Attribute]) -> dict[str, str]:
    """从 ``collect_schema_attributes()`` 结果提取 ``{path: description}`` 映射。

    用于构造 ``EntitySearchToolInputV2.fields``。
    """
    return {path: attr.description for path, attr in attrs.items()}


def attributes_to_field_types(attrs: dict[str, Attribute]) -> dict[str, str]:
    """从 ``collect_schema_attributes()`` 结果提取 ``{path: type_str}`` 映射。

    用于构造 ``EntitySearchToolInputV2.field_types``。
    非原始类型统一降级为 ``"string"``。
    """
    result: dict[str, str] = {}
    for path, attr in attrs.items():
        if isinstance(attr.type, PrimitiveAttributeType):
            result[path] = str(attr.type)
        else:
            result[path] = "string"
    return result


# ---------------------------------------------------------------------------
# SimpleConcept 查询工具
# ---------------------------------------------------------------------------


def flatten_simple_concept_paths(sc: SimpleConcept) -> list[str]:
    """提取 SimpleConcept 中所有 attribute 的 dot-path 列表。"""
    return [attr.name for attr in sc.attributes]


def simple_concept_to_schema(sc: SimpleConcept) -> dict[str, Any]:
    """将 SimpleConcept 转为 flat JSON Schema dict（用于 eval 对比）。"""
    return {
        "title": sc.name,
        "type": "object",
        "properties": {
            attr.name: {"type": str(attr.type), "description": attr.description}
            for attr in sc.attributes
        },
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def build_prompt_v2(
    query: str,
    tool_name: str,
    fields: dict[str, str],
    field_types: dict[str, str] | None = None,
) -> str:
    """构造 V2 prompt，引导 LLM 从字段列表中选择子集并输出 SimpleConcept。

    字段列表格式: ``path (type): description``
    """
    _types = field_types or {}
    lines = []
    for path, desc in fields.items():
        t = _types.get(path, "string")
        lines.append(f"  {path} ({t}): {desc}") # type: ignore
    field_text = "\n".join(lines) # type: ignore
    return (
        "你是一个 schema 字段选择器。根据用户的 query，"
        "从下方字段路径列表中选择与 query 相关的字段子集。\n\n"
        "输出说明：\n"
        "- 每个选中的字段作为一个 attribute\n"
        '- attribute.name 直接复制下方列表中的完整路径字符串（包含 "." 和 "[]"），不做任何转换\n'
        "- attribute.type 使用括号中标注的类型\n"
        "- is_required 统一设为 false\n\n"
        f"工具名称: {tool_name}\n"
        f"用户 query: {query}\n\n"
        f"全量字段路径列表:\n{field_text}"
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class EntitySearchSchemaWorkerV2:
    """LLM 驱动的 V2 worker，直接输出 SimpleConcept。

    典型用法::

        model_api = create_model_api(backend="chat", model="...")
        worker = EntitySearchSchemaWorkerV2(model_api)
        tool = create_entity_search_tool_v2(worker)
    """

    def __init__(self, model_api: ModelAPI[Any]) -> None:
        self._model_api = model_api

    async def __call__(
        self,
        query: str,
        tool_name: str,
        fields: dict[str, str],
        field_types: dict[str, str] | None = None,
    ) -> SimpleConcept:
        prompt = build_prompt_v2(query, tool_name, fields, field_types)
        state = self._model_api.initial_state()
        response = await self._model_api.structured_output(
            UserMessage(text=prompt),
            output_type=SimpleConcept,
            state=state,
        )
        if response.parsed is None:
            raise ValueError(
                f"entity_search_tool_v2 failed to parse SimpleConcept: {response.metadata}"
            )
        return response.parsed


__all__ = [
    "EntitySearchSchemaWorkerV2",
    "EntitySearchToolInputV2",
    "EntitySearchToolOutputV2",
    "EntitySearchWorkerV2",
    "attributes_to_field_types",
    "attributes_to_fields",
    "build_prompt_v2",
    "create_entity_search_tool_v2",
    "flatten_simple_concept_paths",
    "simple_concept_to_schema",
]
