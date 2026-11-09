"""concept_tool_outputs_v2：concept 投影的兼容版实现。

与 v1（concept_outputs.py）的差异：
- is_list=True 不再要求 raw 本身是 list：v1 会先 ``isinstance(raw, list)`` 校验，
  raw 为 dict/str 时直接判 ``is_list=True but output is not a list`` 投影失败。
  实际工具（如带 criteria 的 poi/music 搜索、天气 forecasts 包在 dict 里）常把列表
  藏在某个字段里、甚至返回一段纯文本，v1 因此频繁误判。
- is_list=True 不再对每个元素并发调 LLM：v2 把「概念 BaseModel」包一层
  ``{items: list[ConceptModel]}`` wrapper，**一次** structured_output 让模型在完整 raw
  语境下一并抽出整个列表。省调用、也让模型能跨元素对齐字段语义。

is_list=False 的路径与 v1 完全一致（复用 v1 的 _extract_instance）。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, create_model

from aicore.models.model_api import ModelAPI, SystemMessage, UserMessage
from aicore.tools.concept_outputs import (
    ConceptItemError,
    ConceptOutput,
    _extract_instance,
    _normalize,
    _structured_output_failure_message,
)
from aicore.utils._concepts.meta import Concept

_EXTRACT_LIST_MAX_ATTEMPTS = 3


async def concept_tool_outputs_v2(
    raw: Any,
    concept: Concept,
    is_list: bool,
    model_api: ModelAPI[Any] | None,
    tool_name: str = "",
) -> ConceptOutput:
    """将工具原始输出转换为 Concept 定义的概念实例（兼容版）。

    Args:
        raw:        工具原始返回值（任意类型：dict / list / str / BaseModel，内部自动 normalize）。
        concept:    描述目标输出结构的 Concept 定义。
        is_list:    True 时一次性抽出整个列表（不要求 raw 是 list）；False 时整体抽一个实例。
        model_api:  用于 LLM 推导的模型 API；为 None 时所有字段填 None。
        tool_name:  工具名称，仅用于日志/提示。
    """
    normalized = _normalize(raw)

    if not is_list:
        try:
            result = await _extract_instance(concept, normalized, model_api, tool_name)
        except Exception as exc:
            return ConceptOutput(data={}, error=str(exc))
        return ConceptOutput(data=result or {})

    try:
        items = await _extract_list(concept, normalized, model_api, tool_name)
    except Exception as exc:
        return ConceptOutput(data=[], error=str(exc))
    return ConceptOutput(data=items)


def _build_list_wrapper(concept: Concept) -> type[BaseModel]:
    """把 ConceptModel 包一层 {items: list[ConceptModel]}，供一次性 list 抽取。"""
    ConceptModel = concept.to_pydantic_model(enforce_none_type=True)
    return create_model(
        f"{concept.name}List",
        items=(
            list[ConceptModel],  # type: ignore[valid-type]
            Field(
                default_factory=list,
                description=f"从原始输出中抽取的全部 {concept.name} 实例列表。",
            ),
        ),
    )


async def _extract_list(
    concept: Concept,
    raw: Any,
    model_api: ModelAPI[Any] | None,
    tool_name: str,
) -> list[dict[str, Any]]:
    """一次 LLM 调用从 raw 中抽出整个 Concept 实例列表；全部重试失败后抛异常。"""
    if model_api is None:
        empty = {a.name: None for a in concept.attributes}
        return [empty]

    WrapperModel = _build_list_wrapper(concept)
    context_json = json.dumps(raw, ensure_ascii=False, indent=2, default=str)

    system_msg = SystemMessage(
        text=(
            "你是一个结构化数据提取助手。"
            "你会收到某个工具的原始输出和一个目标概念名称。"
            "原始输出中可能包含多个目标概念实例（可能是一个列表，也可能藏在某个字段里，"
            "或以自然语言文本形式描述）。"
            "请根据原始输出的语义，把其中所有目标概念实例逐一提取到 items 列表中；"
            "每个实例按目标概念的属性结构填写。"
            "字段名与原始输出的 key 可能不完全一致，需要根据语义进行对应。"
            "原始输出若包含筛选条件、逐项满足情况、排除结论或推荐结论，必须把它们当作"
            "提取范围的约束：明确不符合任一核心筛选条件、明确写有“排除/不推荐/不优先/"
            "完全不满足”等结论的候选项，必须从 items 过滤掉，绝不能因为名称、地址或"
            "评分存在就原样输出。"
            "例如，亲子出游候选被明确说明不适合老人少走路、无午睡环境、停车不便或"
            "没有快充，且综合建议为“暂不优先推荐”或“需排除”时，不得出现在 items 中。"
            "对信息只是缺失、但原始输出没有明确判定不符合的候选项，可以保留，并将"
            "无法确认的属性填 null 或忠实保留“不明确”。"
            "若原始输出有多个结果，输出非 list 结构，一般情况下取第一个原始输出处理。"
            "若原始输出中没有任何目标概念实例，items 返回空列表。"
        )
    )
    user_msg = UserMessage(
        text=(
            f"工具名称：{tool_name}\n\n"
            f"目标概念：{concept.name}\n\n"
            f"原始输出：\n```json\n{context_json}\n```\n\n"
        )
    )

    failures: list[str] = []
    last_exc: Exception | None = None
    for attempt in range(1, _EXTRACT_LIST_MAX_ATTEMPTS + 1):
        state = model_api.initial_state(system_prompt=system_msg.text)
        try:
            result: Any = await model_api.structured_output(  # type: ignore[call-overload]
                user_msg, output_type=WrapperModel, state=state
            )
            if result.parsed is not None:
                return [item.model_dump() for item in result.parsed.items]
            failures.append(
                f"attempt {attempt}: "
                + _structured_output_failure_message(result, "parsed output is None")
            )
        except Exception as exc:
            last_exc = exc
            failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")

    message = (
        f"concept list extraction failed after {_EXTRACT_LIST_MAX_ATTEMPTS} attempts: "
        + "; ".join(failures)
    )
    raise RuntimeError(message) from last_exc


__all__ = ["concept_tool_outputs_v2", "ConceptOutput", "ConceptItemError"]
