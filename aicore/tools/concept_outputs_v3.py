"""concept_tool_outputs_v3：passthrough 优先 + LLM fallback 的投影调度器。

投影策略：
1. **passthrough**：将 raw 归一化为 dict 后，按 concept 的 attribute name 严格匹配 key。
   所有 required attribute 都找到即命中，跳过 LLM 调用。适用于执行类工具
   （CarControl / AudioPlay / Navigation 等），其输出本身就是确定性的状态反馈。
2. **LLM fallback**：passthrough 未命中时，退化到 concept_tool_outputs_v2 的语义投影。
   适用于搜索类工具，raw 的字段名与 concept attribute 存在语义 gap。

调度是自动的：不需要硬编码工具名单或标记 projection_policy，
由 raw 的 key 与 concept attributes 的匹配度决定。
"""

from __future__ import annotations

import logging
from typing import Any

from aicore.tools.concept_outputs import ConceptOutput, _normalize
from aicore.tools.concept_outputs_v2 import concept_tool_outputs_v2
from aicore.models.model_api import ModelAPI
from aicore.utils._concepts.meta import SimpleConcept

logger = logging.getLogger(__name__)


def _match_fields(data: dict[str, Any], concept: SimpleConcept) -> dict[str, Any] | None:
    """逐字段严格匹配：concept 每个 required attribute 都必须在 data 的 key 中找到。

    匹配成功返回投影后的 dict，失败返回 None。
    不做类型强转，raw 给什么就透传什么，由 success_check 负责验证。
    """
    result: dict[str, Any] = {}
    for attr in concept.attributes:
        if attr.name in data:
            result[attr.name] = data[attr.name]
        elif not attr.is_required:
            result[attr.name] = attr.default_value
        else:
            return None
    return result


def _try_passthrough(
    raw: Any,
    concept: SimpleConcept,
    is_list: bool,
) -> ConceptOutput | None:
    """尝试 passthrough 投影。全部 required attribute 匹配才成功，否则返回 None。"""
    normalized = _normalize(raw)

    if not is_list:
        if not isinstance(normalized, dict):
            return None
        projected = _match_fields(normalized, concept)
        if projected is None:
            return None
        return ConceptOutput(data=projected)

    # is_list: raw 必须是 list，每个元素都能匹配
    if not isinstance(normalized, list):
        return None
    items: list[dict[str, Any]] = []
    for element in normalized:
        if not isinstance(element, dict):
            return None
        projected = _match_fields(element, concept)
        if projected is None:
            return None
        items.append(projected)
    return ConceptOutput(data=items)

# 对于POI、Music，底层工具有明确输出字段定义
async def concept_tool_outputs_v3(
    raw: Any,
    concept: SimpleConcept,
    is_list: bool,
    model_api: ModelAPI[Any] | None,
    tool_name: str = "",
) -> ConceptOutput:
    """passthrough 优先、LLM fallback 的投影调度器。

    签名与 concept_tool_outputs_v2 完全一致，可直接替换 import。
    """
    passthrough_result = _try_passthrough(raw, concept, is_list)
    if passthrough_result is not None:
        logger.info(
            "passthrough hit: tool=%s concept=%s is_list=%s",
            tool_name, concept.name, is_list,
        )
        return passthrough_result

    logger.info(
        "passthrough miss, falling back to LLM: tool=%s concept=%s is_list=%s",
        tool_name, concept.name, is_list,
    )
    return await concept_tool_outputs_v2(raw, concept, is_list, model_api, tool_name)


__all__ = ["concept_tool_outputs_v3", "ConceptOutput"]
