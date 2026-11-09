
from typing import AsyncGenerator, Sequence, Any, assert_never

import asyncio

from pydantic import BaseModel, Field, ConfigDict

import json

from aicore.events.react import (
    ReActStartEvent,
    ToolCallsDoneEvent,
    ReActFinishEvent,
    ReActEvent,
    ReActEventListener,
    ReActEventPrinter,
)
 
from aicore.tools import (
    FunctionCallOutput, 
    function_call_output,
    ResponseFunctionToolCall,
    base_tool_to_param, 
    BaseTool,
    TaskTool, 
)


from aicore.models.responses import AsyncArk, ResponseParams, Response, ainvoke, astream

from aicore.agents._react_core import _response_to_react_event, _astream_react_terminate

from aicore.utils.nl_repr import nl_repr_safe

async def execute_tools(tool_calls: list[ResponseFunctionToolCall], tool_map: dict[str, BaseTool]) -> list[FunctionCallOutput]:
    """执行工具调用并收集结果
    Args:
        tool_calls: 工具调用列表
        tool_map: 工具映射字典
    Returns:
        工具结果列表
    """
    async def base_tool_acall(tool: BaseTool, tc: ResponseFunctionToolCall) -> FunctionCallOutput:
        """just a wrapper"""
        assert tc.id is not None 
        try:
            args_dict = json.loads(tc.arguments)
            match tool:
                # 必须先于BaseTool，否则会被其捕获
                case TaskTool():
                    result = await tool.arun(args_dict)
                    output = result.nl_repr()
                    
                case BaseTool():
                    #实现非常粗糙。尽量避免使用。请尽量使用TaskTool。
                    try:
                        # 注意：LangChain 的 run 接收展开的 kwargs
                        result = await tool.arun(args_dict)
                        output = nl_repr_safe(result)
                    except Exception as e:
                        output = f"工具执行错误: {e}"
                
                case _:
                    assert_never(f"未知工具类型: {type(tool)}")
        except (json.JSONDecodeError, KeyError) as e:
            output = f"参数解析失败: : {e}"

        
        return function_call_output(tc.id, output)
        
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(base_tool_acall(tool_map[tc.name], tc)) for tc in tool_calls]

    return [task.result() for task in tasks]



# 过期了，还能正确运行，但不建议使用，将来会废弃。请使用astream_react。
async def _astream_react_naive(
    query: str,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: list[BaseTool],
    max_turns: int,
    params: ResponseParams | None = None,
    **kwargs: Any,
) -> AsyncGenerator[ReActEvent, None]:
    """流式执行：传 SDK 流事件，并在关键节点插入 React 自定义事件。
    """
    # 初始化
    input_data: str | list[FunctionCallOutput] = query
    tool_map = {t.name: t for t in tools}

    # 开始一轮,标志开始
    yield ReActStartEvent()

    for turn_index in range(max_turns):
        react_round = turn_index + 1
        completed_response: Response | None = None
        
        stream_result = await astream(
            input_data,             # type: ignore
            previous_response_or_system_prompt,
            client=client,
            model=model,
            tools=[base_tool_to_param(t) for t in tools],
            params=params,
            **kwargs,
        )

        async for event in stream_result:
            translated_event = _response_to_react_event(event, react_round)
            if translated_event is not None:
                yield translated_event

        # 流结束后直接取结果        
        completed_response = stream_result.response
        
        assert completed_response is not None, "没有完成响应"

        tool_calls = completed_response.tool_calls
        #若没有 tool_calls → return（表示模型已经给出最终答案，这时“结束”主要靠 SDK 自己的 completed事件）
        if not tool_calls:
            # TODO：真正结束，补充ReAct完成事件（只针对当前的filter，需要优化）
            yield ReActFinishEvent(response=completed_response, round=react_round)
            return

        tool_results = await execute_tools(tool_calls, tool_map)
        yield ToolCallsDoneEvent(tool_results=[tool_result["output"] for tool_result in tool_results], round=react_round)

        # 检查是否达到最大轮次
        if turn_index == max_turns - 1:
            # 使用提取的强制对话逻辑（流式返回）
            async for event in _astream_react_terminate(
                completed_response,
                tool_results,
                client,
                model,
                params,
                react_round,
                **kwargs,
            ):
                yield event
            return

        # 未达最大轮次，继续循环
        input_data = tool_results
        previous_response_or_system_prompt = completed_response


async def ainvoke_react(
    query: str, 
    previous_response: Response | None = None,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: list[BaseTool],
    max_turns: int,
    params: ResponseParams | None = None,
    **kwargs: Any,
    ) -> str | None:
    """
    执行 react 推理过程。实现非常简单，用于实验，不进入生产。
    Args:
        query: 用户查询
        **kwargs: 其他参数
    Returns:
        最终响应文本
    """
    response = await ainvoke(
        query,
        previous_response,
        client=client,
        model=model,
        tools=[base_tool_to_param(t) for t in tools],
        params=params,
        **kwargs,
    )
    tool_calls: list[ResponseFunctionToolCall] | None = response.tool_calls
    # 无工具调用 → 成功，返回内容
    if not tool_calls:
        return response.raw_text

    tool_map = {t.name: t for t in tools}
    
    for _ in range(max_turns):
        tool_results = await execute_tools(tool_calls, tool_map)
        response = await ainvoke(
            tool_results, # type: ignore
            previous_response=response,
            client=client,
            model=model,
            tools=[base_tool_to_param(t) for t in tools],
            params=params,
            **kwargs,
        )         
        tool_calls = response.tool_calls       
        # 无工具调用 → 成功，返回内容
        if not tool_calls:
            return response.raw_text

    # 失败
    return None

class ReActAgentBase(BaseModel):
    """简单通用的ReAct智能体。本质上就是astream_react的wrapper。
    无状态。response在外部维护。仅作为实验用，不进入生产。
    生产中的ReAct智能体要复杂地多，见base.py
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tools: list[BaseTool] = Field(..., description="工具列表")
    model: str = Field(..., description="模型名称")
    client: AsyncArk = Field(..., description="AsyncArk 客户端", repr=False, exclude=True)
    params: ResponseParams | None = Field(default=None, description="模型参数")
    max_turns: int = Field(default=5, description="最大轮数")

    async def ainvoke(self, query: str, previous_response: Response | None = None, **kwargs: Any) -> str | None:
        """
        执行 Agent 推理过程
        Args:
            query: 用户查询
            response_id: 上轮响应ID
            **kwargs: 其他参数
        Returns:
            最终响应文本
        """
        return await ainvoke_react(
            query,
            previous_response,
            client=self.client,
            model=self.model,
            tools=self.tools,
            max_turns=self.max_turns,
            params=self.params,
            **kwargs,
        )

    async def astream(
        self, 
        query: str, 
        previous_response_or_system_prompt: Response | str | None = None,
        *,
        event_listeners: Sequence[ReActEventListener],
        **kwargs: Any,
    ) -> AsyncGenerator[ReActEvent, None]:
        """流式执行。仅仅是astream_react的wrapper"""
        
        async for event in _astream_react_naive(
            query,
            previous_response_or_system_prompt,
            client=self.client,
            model=self.model,
            tools=self.tools,
            max_turns=self.max_turns,
            params=self.params,
            **kwargs,
        ):
            # 调用事件监听器
            for event_listener in event_listeners:
                event_listener(event)

            yield event


    async def astream_run(
        self, 
        query: str, 
        previous_response_or_system_prompt: Response | str | None = None,
        event_listeners: Sequence[ReActEventListener] = [ReActEventPrinter()],
        **kwargs: dict[str, Any],
    ) -> Response:
        """
        流式执行，使用 event_handler 处理事件，返回最终 Response。
        """
        final_response: Response | None = None
        
        async for event in self.astream(
            query,
            previous_response_or_system_prompt,
            event_listeners=event_listeners,
            **kwargs,
        ):
            # TODO：捕获最终响应，只能在这里通过事件处理器捕获，astream返回generator，不能直接返回Response。
            if isinstance(event, ReActFinishEvent):
                final_response = event.response  # type: ignore

        if final_response is None:
            # 正常不会出现此情况
            raise RuntimeError("ReAct 执行未完成，未收到 ReActCompletedEvent")

        return final_response