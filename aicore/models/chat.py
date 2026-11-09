"""基于火山方舟引擎chat api的封装
https://www.volcengine.com/docs/82379/1494384?lang=zh
"""

from typing import AsyncIterator, Iterator, Type, Final, Callable, cast, override

import time

from pydantic import BaseModel, Field, ConfigDict

from volcenginesdkarkruntime import Ark, AsyncArk

from volcenginesdkarkruntime.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)

from volcenginesdkarkruntime.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

from volcenginesdkarkruntime._streaming import AsyncStream, Stream

from volcenginesdkarkruntime.types.chat.chat_completion_chunk import ChatCompletionChunk

from aicore.models.chat_params import ChatParams
from aicore.utils.misc import safe_update

__all__ = [
    "system_msg",
    "user_msg",
    "assistant_msg",
    "ChatResult",
    "ChatResultStream",
    "ChatResultAsyncStream",
    "invoke",
    "ainvoke",
    "invoke_output_by_schema",
    "ainvoke_output_by_schema",
    "stream",
    "astream",
]

# message helpers
def system_msg(content: str) -> ChatCompletionSystemMessageParam:
    return {"role": "system", "content": content}

def user_msg(content: str) -> ChatCompletionUserMessageParam:
    return {"role": "user", "content": content}

def assistant_msg(content: str) -> ChatCompletionAssistantMessageParam:
    return {"role": "assistant", "content": content}


# 核心数据结构。将来可以解耦出和数据库打通。
class ChatResult[T](BaseModel):
    """LLM运行结果, 包含输出内容、原始响应和消息历史。"""

    output: T = Field(..., description="LLM 的输出结果")

    response: ChatCompletionMessage = Field(..., description="OpenAI API 的原始响应")
    
    messages: list[ChatCompletionMessageParam] = Field(default_factory=list, description="完整的对话消息历史")
    """被维护的消息历史。可以用于连续对话。参见test_chat.py::test_conversation"""

    # TODO: 增加 run_info 字段，包含模型参数、调用时间、tokens等信息
    latency: float = Field(..., description="LLM 调用耗时")


class ChatResultStreamBase(BaseModel):
    """流式输出结果的基类。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 和ChatResult相同的字段
    output: str = Field(default="", description="输出的内容")
    '''仅支持输出str。不支持结构化输出。'''
    messages: list[ChatCompletionMessageParam] = Field(..., description="消息历史")
    latency: float | None = Field(default=None, description="LLM 调用耗时")

    # 不同的字段
    show_reasoning: bool = Field(default=False, description="是否显示推理过程")

    reasoning: str = Field(default="", description="模型的推理过程")
    """仅在thinking开启时有效。
    # TODO: reasoning按说应该进入上下文，对于后面有用。但怎么做不清楚。
    """

    output_part: str = Field(default="", description="增量输出", repr=False, exclude=True)
    reasoning_part: str = Field(default="", description="增量推理", repr=False, exclude=True)

    start: float | None = Field(default=None, description="流式输出开始时间", repr=False, exclude=True)

    is_complete: bool = Field(default=False, description="是否完成了输出", repr=False, exclude=True)

    def _process_chunk(self, chunk: ChatCompletionChunk) -> tuple[str | None, str | None]:
        """处理单个chunk，返回更新后的part_output和是否完成"""
        response = chunk.choices[0].delta
        assert not response.tool_calls, "ChatResultStreamBase不支持工具调用"

        output_delta = response.content
        if output_delta:  # 非None且不是""
            self.output_part += output_delta

        reasoning_delta = response.reasoning_content
        if reasoning_delta:  # 非None且不是""
            self.reasoning_part += reasoning_delta

        if chunk.choices[0].finish_reason is not None:
            # 收到了最后一条消息，完成输出
            # self.choice_delta = chunk.choices[0].delta  # 没什么用
            self.is_complete = True
            self.output = self.output_part
            self.reasoning = self.reasoning_part
            self.messages.append(assistant_msg(content=self.output))

            # 计算结束的时间
            assert isinstance(self.start, float)
            self.latency = time.perf_counter() - self.start

        return output_delta, reasoning_delta

class ChatResultStream(ChatResultStreamBase):
    """同步流式输出。
    
    使用示例:
        # 基本用法
        res = stream("你好，请介绍一下Python")
        for chunk in res:
            print(chunk, end="")  # 实时输出增量内容
        
        # 获取完整输出
        print(f"完整输出: {res.output}")
        
        # 增量模式 vs 累积模式
        res_delta = stream("写一首诗", delta=True)    # 只返回新增内容
        res_cumulative = stream("写一首诗", delta=False)  # 返回累积内容
        
        # 流式输出只能消费一次
        for chunk in res:
            print(chunk)
        # res.output  # 可以获取最终结果
        # for chunk in res:  # 错误！流已被耗尽
    """

    stream_response: Stream[ChatCompletionChunk] = Field(..., repr=False, exclude=True)

    @override
    def __iter__(self) -> Iterator[str]:  # type: ignore
        """流式响应只能被消费一次，因此实现为简单的可迭代对象。
        一旦开始迭代，底层的HTTP流就会被耗尽，不能重新读取。
        我们通过is_complete标志来防止重复消费已耗尽的流。"""
        if self.is_complete:
            raise RuntimeError("此 RunResultStream 已经被使用过了, 请使用 .output 获取最终结果")

        if self.stream_response is None:
            raise RuntimeError("流式输出未初始化，不能迭代")

        if self.start is None:
            self.start = time.perf_counter()

        for chunk in self.stream_response:
            output_delta, reasoning_delta = self._process_chunk(chunk)

            assert not (output_delta and reasoning_delta), "output_delta和reasoning_delta不能同时非空"

            if self.is_complete:
                break

            if output_delta:
                yield output_delta

            if self.show_reasoning and reasoning_delta:
                yield reasoning_delta
            
        self.stream_response.close()


class ChatResultAsyncStream(ChatResultStreamBase):
    """异步版本"""

    stream_response: AsyncStream[ChatCompletionChunk] = Field(..., repr=False, exclude=True)

    async def __aiter__(self) -> AsyncIterator[str]:
        """流式响应只能被消费一次，因此实现为简单的可迭代对象。
        一旦开始迭代，底层的HTTP流就会被耗尽，不能重新读取。
        我们通过is_complete标志来防止重复消费已耗尽的流。"""
        if self.is_complete:
            raise RuntimeError("此 RunResultStream 已经被使用过了, 请使用 .output 获取最终结果")

        if self.stream_response is None:
            raise RuntimeError("流式输出未初始化，不能迭代")

        if self.start is None:
            self.start = time.perf_counter()

        async for chunk in self.stream_response:
            output_delta, reasoning_delta = self._process_chunk(chunk)

            assert not (output_delta and reasoning_delta), "output_delta和reasoning_delta不能同时非空"

            if self.is_complete:
                break

            if output_delta:
                yield output_delta

            if self.show_reasoning and reasoning_delta:
                yield reasoning_delta
            
        await self.stream_response.close()


DEFAULT_SYS_PROMPT: Final[str] = "你是一个有用的助手"

def _compose_messages(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
) -> list[ChatCompletionMessageParam]:
    """将输入和消息历史合并为OpenAI API的messages参数。"""

    assert isinstance(input, str), f"input must be str, but got {type(input)}"
    assert isinstance(messages_or_sys_prompt, (str, list)), f"messages_or_sys_prompt must be str or list, but got {type(messages_or_sys_prompt)}"

    messages: list[ChatCompletionMessageParam]

    if isinstance(messages_or_sys_prompt, str):
        messages = [system_msg(messages_or_sys_prompt)]
    else:
        messages = messages_or_sys_prompt

    # 创建用户消息
    messages.append(ChatCompletionUserMessageParam(role="user", content=input))
    
    return messages

def _invoke[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    convert_output: Callable[[str], T],
    /,
    *,
    client: Ark,
    model: str,
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
    
    response = cast(ChatCompletion, client.chat.completions.create(model=model, messages=messages, **kwargs))
    
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
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResult[T]:
    """异步版本"""

    start = time.perf_counter()

    # 合并两组参数。确保不会重复
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    messages = _compose_messages(input, messages_or_sys_prompt)
    
    response = cast(ChatCompletion, await client.chat.completions.create(model=model, messages=messages, **kwargs))
    
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


def stream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    show_reasoning: bool = False,
    client: Ark,
    model: str,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResultStream:
    """
    流式输出。
    Args:
        input: 用户输入。
        messages_or_sys_prompt: 初次调用时为系统提示词(sys_prompt)，后续调用时为消息历史(message_history)。可以为字符串或消息列表。
        delta: 是否返回增量内容，默认为True。
        **kwargs: 其他参数将传递给OpenAI API。

    Returns:
        RunResultStream: 流式输出结果对象。
    """

    # 合并两组参数。确保不会重复
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    messages = _compose_messages(input, messages_or_sys_prompt)

    response = cast(
        Stream[ChatCompletionChunk],
        client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
        )
    )

    return ChatResultStream(
        stream_response=response,
        messages=messages,
        show_reasoning=show_reasoning,
    )


async def astream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    show_reasoning: bool = False,
    client: AsyncArk,
    model: str,
    params: ChatParams | None = None,
    **kwargs,
) -> ChatResultAsyncStream:
    """异步版本"""

    # 合并两组参数。确保不会重复
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    messages = _compose_messages(input, messages_or_sys_prompt)

    response = cast(
        AsyncStream[ChatCompletionChunk],
        await client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
        )
    )

    return ChatResultAsyncStream(
        stream_response=response,
        messages=messages,
        show_reasoning=show_reasoning,
    )