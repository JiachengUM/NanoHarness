"""Explicit tool call 引擎: select → run → finalize.

行为:
- 唯一 EXACT 命中: 跑工具 → 不带 tools 调模型基于 tool 结果生成最终回答 →
  以 ExplicitFinishEvent 收尾.
- 未命中 (NoToolMatch / ClarifyNeeded / Ambiguous): yield SelectionMissedEvent, return.

单轮语义: 不接受 previous_response；模型配置由 ModelAPI adapter 持有。
explicit 是一次性的 select-run-finalize, 没有跨轮上下文继承的概念.
"""

from typing import Any, AsyncGenerator

from pydantic import ValidationError

from aicore.events.explicit_tool_call import (
    ExplicitEvent,
    ExplicitFinishEvent,
    ExplicitStartEvent,
    ExplicitTextDeltaEvent,
    ExplicitTextDoneEvent,
    ExplicitTextStartEvent,
    SelectionMissedEvent,
)
from aicore.events.react import TaskToolDoneEvent
from aicore.events.task import TaskSuccessEvent

from aicore.models.model_api import (
    ModelAPI,
    ModelCallParams,
    ModelEvent,
    ModelState,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    UserMessage,
)

from aicore.tools import ToolProtocol, validate_tool_arguments
from aicore.tools.experiments.planning import (
    NoToolMatch,
    ToolSelection,
    select_tool,
)
from aicore.tools.runner import ToolRunnerBase

from aicore.utils.nl_repr import nl_repr


__all__ = ["astream_explicit_tool_call"]


def _model_event_to_text_event(
    event: ModelEvent,
) -> ExplicitTextStartEvent | ExplicitTextDeltaEvent | ExplicitTextDoneEvent | None:
    """将模型 ModelAPI 流事件翻译为 explicit text 事件."""
    if isinstance(event, ModelTextStartEvent):
        return ExplicitTextStartEvent()

    if isinstance(event, ModelTextDeltaEvent):
        return ExplicitTextDeltaEvent(delta=event.delta)

    if isinstance(event, ModelTextDoneEvent):
        return ExplicitTextDoneEvent(text=event.text)

    # Explicit finalize 只关心最终回答文本，忽略其它模型事件。
    return None


async def astream_explicit_tool_call[StateT: ModelState, TT: ToolProtocol[Any], RE](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    runner_type: type[ToolRunnerBase[TT, RE]],
    state: StateT,
    tools: list[TT] | None = None,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ExplicitEvent | RE, None]:
    """Explicit tool call: 选择 + 执行 + 流式返回.

    - 命中且 finalize 完成: 流出工具事件 + finalize 文本事件, 以 ExplicitFinishEvent 收尾
    - 未命中: yield 一个 SelectionMissedEvent (含 outcome), return.

    返回事件流由两类组成:
    - ExplicitEvent: 本 primitive 的所有 framing/text 事件
    - RE: runner 在工具执行阶段产的事件 (TaskEvent 等, 由 runner_type 决定)
    """
    yield ExplicitStartEvent()

    if not tools:
        yield SelectionMissedEvent(outcome=NoToolMatch())
        return

    outcome = await select_tool(
        query,
        tools,
        model_api=model_api,
        state=state,
        params=params,
    )

    if not isinstance(outcome, ToolSelection):
        yield SelectionMissedEvent(outcome=outcome)
        return


    runner = runner_type()
    try:
        validated_arguments = validate_tool_arguments(outcome.tool, outcome.arguments)
        runner.add_tool(outcome.tool, validated_arguments)
    except ValidationError:
        # 工具 arguments validate 失败, 直接退出 TODO: 反馈给模型并修复
        return

    # TaskToolRunner/BaseToolRunner 用 TaskToolDoneEvent 表达完成；
    # StreamTaskToolRunner 还会透出 TaskSuccessEvent。两者都可作为成功终态。
    tool_succeeded = False
    tool_res: Any = None
    async for event in runner.run():
        yield event
        if isinstance(event, TaskToolDoneEvent) and event.output.is_success:  # pyright: ignore[reportUnknownMemberType]
            tool_succeeded = True
            tool_res = event.output.data # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        elif isinstance(event, TaskSuccessEvent):
            tool_succeeded = True
            tool_res = event.result # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    if not tool_succeeded:
        # 工具调用失败，不进入 finalize，不 yield ExplicitFinishEvent。
        return

    finalize_input = (
        f"用户原始问题: {query}\n\n"
        f"工具执行结果:\n{nl_repr(tool_res) if tool_res is not None else '<未获得结果>'}\n\n"
        f"请基于以上工具结果, 直接给出对用户问题的最终回答. 不要再调用任何工具."
    )

    # 不绑定 tools。Explicit finalize 只允许模型基于工具结果生成最终回答。
    final_stream = await model_api.stream(
        UserMessage(text=finalize_input),
        state=state,
        tools=None,
        params=params,
    )

    async for raw_event in final_stream:
        translated = _model_event_to_text_event(raw_event)
        if translated is not None:
            yield translated

    final_response = final_stream.response
    assert final_response is not None, "explicit finalize 未返回完成响应"
    yield ExplicitFinishEvent(
        response=final_response,
        tool_name=outcome.tool.name,
    )
