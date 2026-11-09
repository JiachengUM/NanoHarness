from typing import Any, AsyncGenerator

from pydantic import BaseModel, ValidationError

from aicore.core.types import SafeResult
from aicore.events.react import (
    ReActStartEvent,
    ToolCallStartEvent,
    ReActTextStartEvent,
    ReActTextDeltaEvent,
    ReActTextDoneEvent,
    ReActFinishEvent,
    TaskToolDoneEvent,
    ToolCallsDoneEvent,
    ReActEvent,
)

from aicore.models.model_api import (
    ModelAPI,
    ModelCallParams,
    ModelEvent,
    ModelInput,
    ModelResponse,
    ModelState,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    ModelToolCallEvent,
    UserMessage,
    ToolResultsMessage,
)

from aicore.tools import ToolProtocol, ToolRunResult, validate_tool_arguments
from aicore.tools.runner import ToolRunnerBase

__all__ = [
    "_model_event_to_react_event",
    "_astream_react_terminate",
    "astream_react_base",
]


def _model_event_to_react_event(event: ModelEvent, round: int) -> ReActEvent | None:
    """将 ModelEvent 转换为 ReActEvent, round 用于标识当前轮次"""
    if isinstance(event, ModelToolCallEvent):
        # 工具调用是模型层事件，但对 ReAct 调用方需要补充 round 上下文。
        return ToolCallStartEvent(
            name=event.tool_call.tool_name,
            arguments=event.tool_call.arguments,
            round=round,
        )

    if isinstance(event, ModelTextStartEvent):
        return ReActTextStartEvent()

    if isinstance(event, ModelTextDeltaEvent):
        return ReActTextDeltaEvent(delta=event.delta)

    assert isinstance(event, ModelTextDoneEvent)
    return ReActTextDoneEvent(text=event.text)

    # 其它 ModelEvent 暂时不进入 ReAct 对外事件流。
    return None


async def _astream_react_terminate[StateT: ModelState](
    completed_response: ModelResponse[StateT],
    tool_results: list[ToolRunResult],
    model_api: ModelAPI[StateT],
    params: ModelCallParams | None,
    round: int,
) -> AsyncGenerator[ReActEvent, None]:
    """强制生成回复的流式处理（用于超过最大轮次的情况）

    这是一个异步生成器，会流式返回事件，最后返回 ReActFinishEvent。
    """

    # 强制提示
    query = (
        "受限于工具调用次数，当前无法继续执行任何工具，必须根据现有信息直接给出回答！"
    )
    # 流式调用模型（不传 tools，强制直接回答）
    final_stream_result = await model_api.stream(
        [
            ToolResultsMessage(results=tool_results),
            UserMessage(text=query),
        ],
        state=completed_response.state,
        tools=None,
        params=params,
    )

    # 流式返回事件
    async for event in final_stream_result:
        translated_event = _model_event_to_react_event(event, round)
        if translated_event is not None:
            yield translated_event

    # 获取最终响应
    final_response = final_stream_result.response
    assert final_response is not None, "没有完成响应"
    assert not final_response.tool_calls, "强制生成回复时，不应该有 tool call"

    # 标记为强制完成
    yield ReActFinishEvent(
        response=final_response,
        forced=True,
        reason="达到最大轮次，强制生成回复",
        round=round,
    )


async def astream_react_base[StateT: ModelState, TT: ToolProtocol[BaseModel], RE](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    runner_type: type[ToolRunnerBase[TT, RE]],
    state: StateT,
    tools: list[TT] | None = None,
    max_turns: int = 5,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ReActEvent | RE, None]:
    """流式执行：消费模型事件，并在关键节点插入 ReAct 自定义事件。

    该函数实现了一个异步的 ReAct 代理，具有以下特点：
    1. 支持流式处理模型响应。
    2. 工具执行在专门的 tool runner 中完成。
    3. 按照工具完成顺序返回结果。
    """
    # 初始化本轮输入和显式 state。
    input_data: ModelInput = UserMessage(text=query)
    current_state = state
    # 创建工具映射，方便根据工具名称快速查找。
    tool_map = {t.name: t for t in tools} if tools else {}

    # 开始一轮，标志开始。
    yield ReActStartEvent()

    for turn_index in range(max_turns):
        # 从 1 开始编号。
        react_round = turn_index + 1
        # 调用模型的流式接口，获取响应流。
        stream_result = await model_api.stream(
            input_data,
            state=current_state,
            tools=tools,
            params=params,
        )

        # 创建运行器，用于管理和执行工具任务。
        runner = runner_type()

        # 异步迭代处理流事件。
        async for raw_event in stream_result:
            # 转换模型事件为 ReAct 事件。
            event = _model_event_to_react_event(raw_event, react_round)

            # None 不是我们关注的事件，跳过。
            if event is None:
                continue

            # 转发事件。
            yield event

        # 流结束后获取完整响应。
        response = stream_result.response

        assert response is not None, "没有完成响应"

        # 若没有 tool_calls，表示模型已经给出最终答案。
        if not response.tool_calls:
            yield ReActFinishEvent(response=response, round=react_round)
            return

        # 用 response.tool_calls 的 idx 建立结果表：成功校验的调用交给 runner，
        # 校验失败或未知工具的调用直接写入对应位置，确保 run_id 一一配对。
        tool_outputs: list[str | None] = [None] * len(response.tool_calls)
        valid_tool_indices: list[int] = []
        for idx, tool_call in enumerate(response.tool_calls):
            tool = tool_map.get(tool_call.tool_name)
            try:
                if tool is not None:
                    validated_arguments = validate_tool_arguments(tool, tool_call.arguments)
                    runner.add_tool(tool, validated_arguments)
                    valid_tool_indices.append(idx)
                    continue
                else:
                    safe_result = SafeResult[Any](error=f"未知工具: {tool_call.tool_name}")
            except ValidationError as e:
                safe_result = SafeResult[Any](error = f"工具参数校验失败: {e.json()}")

            yield TaskToolDoneEvent(output=safe_result)
            tool_outputs[idx] = safe_result.nl_repr()


        # 按照执行结束的顺序返回有效工具的结果，实时响应性更好。
        # 最终传回模型时再按 valid_tool_indices 还原为 tool_calls 顺序。
        if valid_tool_indices:
            async for event in runner.run():
                yield event
            tool_results_raw = runner.tool_results
        else:
            tool_results_raw = []

        assert len(valid_tool_indices) == len(tool_results_raw), (
            f"有效工具调用数{len(valid_tool_indices)}和结果数{len(tool_results_raw)}不一致"
        )

        for idx, output in zip(valid_tool_indices, tool_results_raw):
            tool_outputs[idx] = output

        tool_results: list[ToolRunResult] = []
        for output, tc in zip(tool_outputs, response.tool_calls):
            assert output is not None
            tool_results.append(ToolRunResult(run_id=tc.run_id, output=output))

        # 返回工具调用结束事件。
        yield ToolCallsDoneEvent(
            tool_results=[tool_result.output for tool_result in tool_results],
            round=react_round,
        )

        # 检查是否达到最大轮次。
        if turn_index == max_turns - 1:
            # 使用显式 fork 后的强制对话逻辑（流式返回）。
            async for event in _astream_react_terminate(
                response,
                tool_results,
                model_api,
                params,
                react_round,
            ):
                yield event

            return

        # 未达到最大轮次，更新下一轮的输入数据和 state。
        input_data = ToolResultsMessage(results=tool_results)
        current_state = response.state
