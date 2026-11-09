"""基于火山方舟引擎chat api的封装
https://www.volcengine.com/docs/82379/1494384?lang=zh
"""
from __future__ import annotations

from typing import AsyncIterator, Iterator, Iterable, cast, override

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

from volcenginesdkarkruntime._streaming import AsyncStream, Stream

from volcenginesdkarkruntime.types.chat.chat_completion_chunk import ChatCompletionChunk

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
    "ChatResultStreamBase",
    "ChatResultStream",
    "ChatResultAsyncStream",
    "stream",
    "astream",
]


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


def stream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    show_reasoning: bool = False,
    client: Ark,
    model: str,
    tools: Iterable[ChatCompletionToolParam] | None = None,
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