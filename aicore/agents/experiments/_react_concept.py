from typing import Literal, TypeAlias, Union, AsyncGenerator, cast

from pydantic import Field

from aicore.core.event import EventBase

from aicore.tools.responses_helper import (
    FunctionCallOutput, 
    function_call_output,
    ResponseFunctionToolCall,
    base_tool_to_param, 
)
from aicore.tools.task import SafeResult, TaskTool

from aicore.core.task_runner import TaskAsyncRunner

from aicore.models.responses import AsyncArk, Response

__all__ = [
    "ReActStartEvent",
    "ToolCallStartEvent",
    "ReActTextStartEvent",
    "ReActTextDeltaEvent",
    "ReActTextDoneEvent",
    "TaskToolDoneEvent",
    "ToolCallsDoneEvent",
    "ReActErrorEvent",
    "ReActFinishEvent",
    "ReActEvent",
    "astream_react",
]

class ReActStartEvent(EventBase):
    """会话开始：Agent 开始推理，只发一次"""
    type: Literal["react.start"] = Field(default="react.start", init=False)

class ReActTextStartEvent(EventBase):
    """文本流式开始：模型即将开始输出文本"""
    type: Literal["react.text.start"] = Field(default="react.text.start", init=False)


class ReActTextDeltaEvent(EventBase):
    """文本流式增量：模型输出文本的一小段"""
    type: Literal["react.text.delta"] = Field(default="react.text.delta", init=False)
    delta: str

class ReActTextDoneEvent(EventBase):
    """文本流式结束：当前段文本输出完毕"""
    type: Literal["react.text.done"] = Field(default="react.text.done", init=False)
    text: str

class ToolCallStartEvent(EventBase):
    """工具调用开始：模型请求调用工具，外部需执行"""
    type: Literal["react.tool_call.start"] = Field(default="react.tool_call.start", init=False)
    tool_call: ResponseFunctionToolCall

class TaskToolDoneEvent[OT](EventBase):
    type: Literal["task_tool.done"] = Field(default="task_tool.done", init=False)
    output: SafeResult[OT]

class ToolCallsDoneEvent(EventBase):
    """工具调用结束：工具执行完成，结果返回给模型"""
    type: Literal["react.tool_results.done"] = Field(default="react.tool_results.done", init=False)
    tool_results: list[FunctionCallOutput]

# 完成：Agent 给出最终答案（成功）
class ReActFinishEvent(EventBase):
    """完成：Agent 给出最终答案（成功）"""
    type: Literal["react.finish"] = Field(default="react.finish", init=False)
    response: Response
    forced: bool = Field(default=False, description="是否强制完成对话。")
    reason: str | None = Field(default=None, description="完成原因")

class ReActErrorEvent(EventBase):
    """失败：未完成或超轮次等"""
    type: Literal["react.error"] = Field(default="react.error", init=False)
    reason: str | None = Field(default=None, description="失败原因")


# 总事件类型：不包括responses 事件，只有自定义事件
ReActEvent: TypeAlias = Union[
    ReActStartEvent,
    ReActTextStartEvent,
    ToolCallStartEvent,
    ReActTextDeltaEvent,
    ReActTextDoneEvent,
    TaskToolDoneEvent,
    ToolCallsDoneEvent,
    ReActErrorEvent,
    ReActFinishEvent,
]


async def astream_react(
    query: str,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: list[TaskTool] | None = None,
    max_turns: int = 5,
) -> AsyncGenerator[ReActEvent, None]:
    # 初始化
    input_data: str | list[FunctionCallOutput] = query
    # 创建工具映射，方便根据工具名称快速查找
    tool_map = {t.name: t for t in tools} if tools else {}

    # 开始一轮,标志开始
    yield ReActStartEvent()

    for turn_index in range(max_turns):        
        # 调用模型的流式接口，获取响应流
        stream_result = await llm_call_astream(   # type: ignore
            input_data,             # type: ignore
            client=client,
            model=model,
            tools=[base_tool_to_param(t) for t in tools] if tools else None,
        )

        # 创建任务运行器，用于管理和执行工具任务
        runner = TaskAsyncRunner()

        # 异步迭代处理流事件
        async for event in stream_result:
            # 转换原始事件为 ReAct 事件
            assert isinstance(event, ReActEvent)

            # 处理工具调用开始事件
            match event:
                case ToolCallStartEvent():
                    task = tool_map[event.tool_call.name].create_task(event.tool_call.arguments)
                    # 异步添加任务到运行器
                    await runner.add_task(task)
                
            # 转发事件
            yield event

        # 若没有 tool_calls → 表示模型已经给出最终答案
        if not stream_result.response.tool_calls:
            # TODO：真正结束，补充ReAct完成事件（只针对当前的filter，需要优化）
            yield ReActFinishEvent(response=stream_result.response)
            return
        
        # 按照执行结束的顺序返回结果，实时响应性更好
        # 注意：这里的顺序和tool_calls中的顺序可能不一致
        async for output in runner.run():
            yield TaskToolDoneEvent(output=output)

        # 拼装最终的tool_results，确保顺序与工具调用顺序一致
        tool_results: list[FunctionCallOutput] = []
        for output, tc in zip(runner.results, stream_result.response.tool_calls):
            tool_results.append(function_call_output(cast(str, tc.id), output.nl_repr()))

        # 检查是否达到最大轮次
        if turn_index == max_turns - 1:
            yield ReActErrorEvent(reason="最大轮次超过")
            break

        # 未达到最大轮次，更新下一轮的输入数据和上下文
        input_data = tool_results
