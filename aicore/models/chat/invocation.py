"""基于火山方舟引擎chat api的封装
https://www.volcengine.com/docs/82379/1494384?lang=zh
"""
from __future__ import annotations

from typing import AsyncIterator, Iterator, Type, Final, Callable, cast, override, Iterable

import time

from pydantic import BaseModel, Field, ConfigDict

from volcenginesdkarkruntime.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionToolParam
)

from volcenginesdkarkruntime.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

from volcenginesdkarkruntime.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall

from aicore.utils.misc import safe_update

from .core import (
    Ark, 
    AsyncArk,
    system_msg, 
    user_msg,
    assistant_msg,
    DEFAULT_SYS_PROMPT,
    _compose_messages,
)
from .params import ChatParams

__all__ = [
    "ChatResult",
    "invoke",
    "ainvoke",
    "invoke_output_by_schema",
    "ainvoke_output_by_schema",
]

# 核心数据结构。将来可以解耦出和数据库打通。
class ChatResult[T](BaseModel):
    """LLM运行结果, 包含输出内容、原始响应和消息历史。"""

    output: T = Field(..., description="LLM 的输出结果")

    response: ChatCompletionMessage = Field(..., description="OpenAI API 的原始响应")
    
    messages: list[ChatCompletionMessageParam] = Field(default_factory=list, description="完整的对话消息历史")
    """被维护的消息历史。可以用于连续对话。参见test_chat.py::test_conversation"""

    # tool_calls: list[ChatCompletionMessageToolCall] | None = Field(default=None, description="输出的工具调用")

    # TODO: 增加 run_info 字段，包含模型参数、调用时间、tokens等信息
    latency: float = Field(..., description="LLM 调用耗时")


def _invoke[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    convert_output: Callable[[str], T],
    /,
    *,
    client: Ark,
    model: str,
    tools: Iterable[ChatCompletionToolParam] | None = None,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[T]:
    """
    核心LLM调用函数。在底层的chat api上增加如下功能：
    1. 维护消息历史：自动将输入和消息历史合并，将输入添加到消息历史中。从而可以直接作为外部agent的状态。
    2. 输出处理：将输出的str转换为目标类型T。缺省为identity函数。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        client: 火山方舟引擎客户端
        model: 模型名称
        tools: 工具列表
        output_processor: 输出处理函数，将ChatCompletionMessage转换为目标类型T
        params: 运行时参数
        **kwargs: 传递给API的其他参数，作为对于params的补充
    
    Returns:
        ChatResult[T]: 包含处理后的输出结果
    """

    start = time.perf_counter()

    # 合并两组参数。确保不会重复
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    messages = _compose_messages(input, messages_or_sys_prompt)
    
    response = cast(ChatCompletion, client.chat.completions.create(model=model, messages=messages, tools=tools, **kwargs))
    
    response_msg: ChatCompletionMessage = response.choices[0].message

    # 响应内容不为空，output_processor需要处理
    assert response_msg.content is not None
    output = convert_output(response_msg.content)
    
    # 更新消息历史
    messages.append(assistant_msg(response_msg.content))

    return ChatResult(
        output=output, 
        response=response_msg, 
        latency=time.perf_counter() - start,
        messages=messages)

async def _ainvoke[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    convert_output: Callable[[str], T],
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: Iterable[ChatCompletionToolParam] | None = None,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[T]:
    """异步版本"""

    start = time.perf_counter()

    # 合并两组参数。确保不会重复
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    messages = _compose_messages(input, messages_or_sys_prompt)
    
    response = cast(ChatCompletion, await client.chat.completions.create(model=model, messages=messages, tools=tools, **kwargs))
    
    response_msg: ChatCompletionMessage = response.choices[0].message

    # 响应内容不为空，output_processor需要处理
    assert response_msg.content is not None
    output = convert_output(response_msg.content)
    
    # 更新消息历史
    messages.append(assistant_msg(response_msg.content))

    return ChatResult(
        output=output, 
        response=response_msg, 
        latency=time.perf_counter() - start,
        messages=messages)


def invoke(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: Ark,
    model: str,
    tools: Iterable[ChatCompletionToolParam] | None = None,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[str]:
    """基础LLM调用函数。"""

    assert "response_format" not in kwargs, "response_format must not be specified in kwargs in invoke, use invoke_output_by_schema instead."

    return _invoke(
        input, 
        messages_or_sys_prompt,
        lambda x: x,
        client=client, 
        model=model, 
        tools=tools,
        params=params, 
        **kwargs
        )

async def ainvoke(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: Iterable[ChatCompletionToolParam] | None = None,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[str]:
    """基础LLM调用函数。"""

    assert "response_format" not in kwargs, "response_format must not be specified in kwargs in invoke, use invoke_output_by_schema instead."

    return await _ainvoke(
        input, 
        messages_or_sys_prompt,
        lambda x: x,
        client=client, 
        model=model, 
        tools=tools,
        params=params, 
        **kwargs
        )

def invoke_output_by_schema[T: Type[BaseModel]](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: T,
    client: Ark,
    model: str,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[T]:
    """基于JSON Schema的结构化输出。"""
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"

    if "json" not in input.lower():
        # 有些时候，模型会要求用户在输入中包含"json"。这是为了保险起见。可能是多余的。
        input = f"{input}\n请根据要求返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return _invoke(
        input,
        messages_or_sys_prompt,
        lambda x: output_type.model_validate_json(x),
        client=client,
        model=model,
        response_format=response_format,
        params=params,
        **kwargs,
    )


async def ainvoke_output_by_schema[T: Type[BaseModel]](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: T,
    client: AsyncArk,
    model: str,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[T]:
    """基于JSON Schema的结构化输出。"""
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"

    if "json" not in input.lower():
        # 有些时候，模型会要求用户在输入中包含"json"。这是为了保险起见。可能是多余的。
        input = f"{input}\n请根据要求返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return await _ainvoke(
        input,
        messages_or_sys_prompt,
        lambda x: output_type.model_validate_json(x),
        client=client,
        model=model,
        response_format=response_format,
        params=params,
        **kwargs,
    )