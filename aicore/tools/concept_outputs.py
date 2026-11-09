"""concept_tool_outputs：将工具原始输出按 Concept 定义结构化为概念实例。

根据 is_list 决定输出形态：
- False：整体提取一个 Concept 实例，返回 ConceptOutput(data=dict)。
- True：对列表中每个元素并发提取，返回 ConceptOutput(data=list, item_errors=[...])。
  提取失败的元素记录在 item_errors 中，不中断其余元素的提取。
"""

import json
from typing import Any

import anyio
from pydantic import BaseModel

from aicore.models.model_api import ModelAPI, UserMessage, SystemMessage
from aicore.utils._concepts.meta import Concept


_EXTRACT_INSTANCE_MAX_ATTEMPTS = 3


def _structured_output_failure_message(result: Any, fallback: str) -> str:
    metadata = getattr(result, "metadata", {})
    metadata_text = json.dumps(metadata, ensure_ascii=False, default=str)
    return f"{fallback}; metadata={metadata_text}"


class ConceptItemError(BaseModel):
    """list 模式下单个元素提取失败的记录。"""

    index: int
    reason: str


class ConceptOutput(BaseModel):
    """concept_tool_outputs 的结构化返回值。

    is_list=False：data 为 dict（提取失败时为 {}）。
    is_list=True： data 为 list[dict]（仅含成功元素），item_errors 记录失败元素。
    error 在顶层失败时设置（如 is_list=True 但输入不是列表）。
    """

    data: dict[str, Any] | list[dict[str, Any]]
    item_errors: list[ConceptItemError] = []
    error: str | None = None


def _normalize(raw: Any) -> Any:
    """将工具原始输出递归转为 JSON-serializable 结构（BaseModel → dict）。"""
    if isinstance(raw, BaseModel):
        return raw.model_dump()
    if isinstance(raw, list):
        return [_normalize(item) for item in raw]  # type: ignore[misc]
    if isinstance(raw, dict):
        return {k: _normalize(v) for k, v in raw.items()}  # type: ignore[union-attr]
    return raw


async def concept_tool_outputs(
    raw: Any,
    concept: Concept,
    is_list: bool,
    model_api: ModelAPI[Any] | None,
    tool_name: str = "",
) -> ConceptOutput:
    """将工具原始输出转换为 Concept 定义的概念实例。

    Args:
        raw:        工具原始返回值（任意类型，函数内部自动 normalize）。
        concept:    描述目标输出结构的 Concept 定义。
        is_list:    True 时 raw 须为列表，对每个元素并发提取；False 时整体提取一个实例。
        model_api:  用于 LLM 推导的模型 API；为 None 时所有字段填 None。
        tool_name:  工具名称，仅用于日志。
    """
    normalized = _normalize(raw)

    if not is_list:
        try:
            result = await _extract_instance(concept, normalized, model_api, tool_name)
        except Exception as exc:
            return ConceptOutput(data={}, error=str(exc))
        return ConceptOutput(data=result or {})

    if not isinstance(normalized, list):
        return ConceptOutput(
            data=[],
            error=f"is_list=True but output is not a list: {type(normalized).__name__!r}",
        )

    raw_list: list[Any] = normalized
    item_results: list[dict[str, Any] | None] = [None] * len(raw_list)
    item_errors: list[ConceptItemError] = []

    async def extract_at(idx: int, element: Any) -> None:
        try:
            item_results[idx] = await _extract_instance(concept, element, model_api, tool_name)
        except Exception as exc:
            item_errors.append(ConceptItemError(index=idx, reason=str(exc)))

    async with anyio.create_task_group() as tg:
        for idx, element in enumerate(raw_list):
            tg.start_soon(extract_at, idx, element)

    return ConceptOutput(
        data=[item for item in item_results if item is not None],
        item_errors=item_errors,
    )


async def _extract_instance(
    concept: Concept,
    raw: Any,
    model_api: ModelAPI[Any] | None,
    tool_name: str,
) -> dict[str, Any]:
    """调用 LLM 从 raw 中提取一个 Concept 实例，全部重试失败后抛出异常。"""
    if model_api is None:
        return {a.name: None for a in concept.attributes}

    ConceptModel = concept.to_pydantic_model(enforce_none_type=True)
    context_json = json.dumps(raw, ensure_ascii=False, indent=2, default=str)

    system_msg = SystemMessage(
        text=(
            "你是一个结构化数据提取助手。"
            "你会收到某个工具的原始输出和一个目标概念名称。"
            "请根据原始输出的语义，提取或推导出目标概念的各属性值。"
            "字段名与原始输出的 key 可能不完全一致，需要根据语义进行对应。"
             # TODO: 模型的发挥需要可追溯
            # "某些情况原始输入字段可能缺少某些必要信息, 你可以结合常识和背景补充，"
            # "只允许补充广泛的常识性知识，严禁补充任何不确定的内容，比如 id 等"
            # "只返回 JSON，不要附加任何说明文字。"
        )
    )
    user_msg = UserMessage(
        text=(
            f"工具名称：{tool_name}\n\n"
            f"原始输出：\n```json\n{context_json}\n```\n\n"
        )
    )

    failures: list[str] = []
    last_exc: Exception | None = None
    for attempt in range(1, _EXTRACT_INSTANCE_MAX_ATTEMPTS + 1):
        state = model_api.initial_state(system_prompt=system_msg.text)
        try:
            result: Any = await model_api.structured_output(  # type: ignore
                user_msg, output_type=ConceptModel, state=state
            )
            if result.parsed is not None:
                return result.parsed.model_dump()
            failures.append(
                f"attempt {attempt}: "
                + _structured_output_failure_message(result, "parsed output is None")
            )
        except Exception as exc:
            last_exc = exc
            failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")

    message = (
        "concept extraction failed after "
        f"{_EXTRACT_INSTANCE_MAX_ATTEMPTS} attempts: "
        + "; ".join(failures)
    )
    raise RuntimeError(message) from last_exc


__all__ = ["concept_tool_outputs", "ConceptOutput", "ConceptItemError"]
