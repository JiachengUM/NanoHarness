"""
这个模块的定位暂时还不清楚。叫做planning是想包括一些规划相关的功能。
"""

from dataclasses import dataclass
from typing import Any

from enum import StrEnum

from pydantic import BaseModel, Field

from aicore.core.task_runner import TaskAsyncRunner
from aicore.core.types import SafeResult
from aicore.models.model_api import (
    ModelAPI,
    ModelCallParams,
    ModelState,
    UserMessage,
)
from aicore.tools import ToolProtocol

__all__ = [
    "ToolRelevanceType",
    "ToolRelevanceResult",
    "is_tool_relevant",
    "ToolSelection",
    "NoToolMatch",
    "ClarifyNeeded",
    "Ambiguous",
    "ToolSelectionOutcome",
    "select_tool",
]


class ToolRelevanceType(StrEnum):
    """工具与用户输入相关性类型"""

    EXACT = "exact"
    PARTIAL = "partial"
    IRRELEVANT = "irrelevant"


class ToolRelevanceResult(BaseModel):
    """工具与用户输入相关性描述"""

    relevance_type: ToolRelevanceType = Field(
        ..., description="工具与用户输入相关性的类型"
    )

    reason: str = Field(..., description="相关性类型判断结果的原因")

    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="如果relevance_type为EXACT，为从用户输入中提取的工具调用的参数。否则为None。",
    )

    clarify: str | None = Field(
        default=None,
        title="需要向用户澄清的问题",
        description="如果relevance_type为PARTIAL, clarify字段是为了清晰理解用户意图而需要向用户反问或澄清的问题。否则为None。",
    )


async def is_tool_relevant[StateT: ModelState](
    user_query: str,
    tool: ToolProtocol[Any],
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    params: ModelCallParams | None = None,
) -> ToolRelevanceResult:
    """判断工具是否与当前用户输入相关; 若 EXACT, 同时按 args_schema 提取参数."""

    input = f"""
你需要负责判断用户输入是否与工具相关; 如果判定为 EXACT 相关, 还需要从用户输入中提取工具调用所需的参数。

用户输入: {user_query}

工具描述:
{tool.description}

工具参数 schema (JSON Schema):
{tool.args_schema.model_json_schema()}
"""

    response = await model_api.structured_output(
        UserMessage(text=input),
        output_type=ToolRelevanceResult,
        state=state,
        params=params,
    )

    if response.parsed is None:
        raise RuntimeError("模型结构化输出解析失败: ToolRelevanceResult")

    return response.parsed


@dataclass(frozen=True)
class ToolSelection[TT: ToolProtocol[Any]]:
    """选中唯一一个 EXACT 匹配的工具, arguments 已通过 tool.args_schema 校验"""

    tool: TT
    arguments: dict[str, Any]


@dataclass(frozen=True)
class NoToolMatch:
    """所有 tool 都不相关, 或者 tools 列表为空"""

    pass


@dataclass(frozen=True)
class ClarifyNeeded:
    """有 PARTIAL 匹配但没有 EXACT, 收集到的待澄清问题"""

    questions: list[str]


@dataclass(frozen=True)
class Ambiguous[TT: ToolProtocol[Any]]:
    """有多个 EXACT 匹配, 无法决定"""

    candidates: list[TT]


type ToolSelectionOutcome[TT: ToolProtocol[Any]] = (
    ToolSelection[TT] | NoToolMatch | ClarifyNeeded | Ambiguous[TT]
)


async def select_tool[StateT: ModelState, TT: ToolProtocol[Any]](
    query: str,
    tools: list[TT],
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    params: ModelCallParams | None = None,
) -> ToolSelectionOutcome[TT]:
    """对每个 tool 并发判断与 query 的相关性, 聚合为结构化 outcome.

    - 唯一 EXACT → ToolSelection, arguments 已通过 tool.args_schema 校验后 dump 为 dict
    - 多个 EXACT → Ambiguous
    - 有 PARTIAL 但无 EXACT → ClarifyNeeded
    - 全部 IRRELEVANT 或 tools 为空 → NoToolMatch
    """
    if not tools:
        return NoToolMatch()

    task_runner = TaskAsyncRunner()

    for tool in tools:

        async def check(t: TT = tool) -> SafeResult[ToolRelevanceResult]:
            res = await is_tool_relevant(
                query,
                t,
                model_api=model_api,
                state=state,
                params=params,
            )
            return SafeResult(data=res)

        task_runner.add_task(check())

    async for _ in task_runner.run():
        pass  # 只关心最终结果, 不需要中间结果

    results: list[SafeResult[ToolRelevanceResult]] = task_runner.results

    exact_idxs = [
        i
        for i, sr in enumerate(results)
        if sr.data is not None and sr.data.relevance_type == ToolRelevanceType.EXACT
    ]

    if len(exact_idxs) == 1:
        i = exact_idxs[0]
        the_tool = tools[i]
        the_result = results[i].data
        assert the_result is not None  # narrowing
        return ToolSelection(tool=the_tool, arguments=the_result.arguments)

    if len(exact_idxs) > 1:
        return Ambiguous(candidates=[tools[i] for i in exact_idxs])

    clarifies = [
        sr.data.clarify
        for sr in results
        if sr.data is not None
        and sr.data.relevance_type == ToolRelevanceType.PARTIAL
        and sr.data.clarify
    ]
    if clarifies:
        return ClarifyNeeded(questions=clarifies)

    return NoToolMatch()
