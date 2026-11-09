"""流式输出相关功能模块"""

from __future__ import annotations

import time

from typing import Generator, AsyncGenerator, Iterable, cast, override, Protocol, assert_never, Any

from enum import StrEnum

from collections import Counter

from pydantic import BaseModel, Field, ConfigDict

import rich

# 下述symbol是stream的实现细节。只要无需对外暴露，就不需要进入.core。
from volcenginesdkarkruntime.types.responses import (
    ResponseStreamEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
    ResponseCompletedEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseOutputItemAddedEvent,
    ResponseInProgressEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseCreatedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDoneEvent,
    ResponseReasoningSummaryTextDoneEvent,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryPartDoneEvent,
    ResponseOutputMessage,
)

from volcenginesdkarkruntime._streaming import AsyncStream, Stream

from aicore.utils.misc import safe_update

from .core import (
    Ark, 
    AsyncArk, 
    Response,
    HumanMessage,
    AIMessage,
    ResponseInputParam,
    FunctionToolParam,
    _prepare_request
)

from .params import ResponseParams

class StreamVerbosity(StrEnum):
    """流式输出的详细程度。"""

    MINIMAL = "minimal"
    """仅输出外部能消费的实质性结果: tool call, reasoning, final answer。"""
    
    MAXIMAL = "maximal"
    """输出所有中间event。"""

# 确定无用的event
EVENTS_IGNORE: tuple[type[ResponseStreamEvent], ...] = (
    ResponseInProgressEvent, # 进度事件
    ResponseContentPartAddedEvent, # 内容部分增加
    ResponseContentPartDoneEvent, # 内容部分完成
    ResponseFunctionCallArgumentsDeltaEvent, # tool参数增量
    ResponseReasoningSummaryPartDoneEvent, # 推理部分完成
    ResponseReasoningSummaryPartAddedEvent, # 推理部分增加
)

# 对应于StreamVerbosity.MINIMAL
EVENTS_MINIMAL: tuple[type[ResponseStreamEvent], ...] = (
    # 文本相关
    ResponseTextDeltaEvent, # 文本增量
    ResponseTextDoneEvent, # 文本完成
    # 推理相关
    ResponseReasoningSummaryTextDeltaEvent,  # 推理增量
    ResponseReasoningSummaryTextDoneEvent,   # 推理完成
    # 全局状态
    ResponseCreatedEvent,  # 响应创建
    ResponseCompletedEvent, # 响应完成
    # FC工具调用
    ResponseFunctionCallArgumentsDoneEvent,  # FC参数完整
    ResponseOutputItemDoneEvent, # FC输出项完成
    # 输出项增加,可用来判断即将开始的行为，如text、reasoning等
    ResponseOutputItemAddedEvent, # 输出项增加

)


class ResponseResultStreamBase(BaseModel):
    """流式输出结果的基类。"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    message_history: list[tuple[HumanMessage, AIMessage]] = Field(..., description="消息历史记录")
    """为了初始化 Response 对象，需要记录消息历史。放在这里其实非常不合适。参见 Response中的说明。 暂时先这样。"""

    response: Response | None = Field(default=None, description="完整的 Response 对象")
    """完整的 Response 对象，仅在完成时填充。"""

    latency: float | None = Field(default=None, description="LLM 调用耗时")  

    # 下述字段是流式输出的实现细节，无需暴露给外部。
    verbosity: StreamVerbosity = Field(default=StreamVerbosity.MINIMAL, description="流式输出的详细程度", repr=False, exclude=True)

    start: float | None = Field(default=None, description="流式输出开始时间", repr=False, exclude=True)
    
    is_complete: bool = Field(default=False, description="是否完成了输出", repr=False, exclude=True)

    def _finish(self, event: ResponseCompletedEvent) -> None:
        self.is_complete = True
        assert self.start is not None
        self.latency = time.perf_counter() - self.start
        
        self.response = Response.from_raw(event.response, latency=self.latency, message_history=self.message_history)
        # 获取text，只有当没有tool时进行处理。
        if not self.response.tool_calls:
            # 如果self.meesage_history最后一条AIMessage为空，则生成，非常脏，
            # 确保 message_history 非空
            if self.response.message_history and self.response.message_history[-1][1].content == "":
                self.response.message_history[-1][1].content = self.response.raw_text
    

class ResponseResultStream(ResponseResultStreamBase):
    """同步流式输出。"""
    stream_response: Stream[ResponseStreamEvent] = Field(..., repr=False, exclude=True)

    @override
    def __iter__(self) -> Generator[ResponseStreamEvent, None]: # type: ignore

        if self.is_complete:
            raise RuntimeError("此流已被消费，请使用 .output 获取最终结果")

        if self.stream_response is None:
            raise RuntimeError("流未初始化")
            
        if self.start is None:
            self.start = time.perf_counter()

        for event in self.stream_response:
            assert not self.is_complete

            if isinstance(event, EVENTS_IGNORE):
                continue

            if isinstance(event, ResponseCompletedEvent):
                self._finish(event)

            match self.verbosity:
                case StreamVerbosity.MINIMAL:
                    if isinstance(event, EVENTS_MINIMAL):
                        yield event

                case StreamVerbosity.MAXIMAL:
                    yield event

                case _:
                    assert_never(self.verbosity)
                
        assert self.is_complete
        assert isinstance(self.response, Response)

        self.stream_response.close()

class ResponseResultAsyncStream(ResponseResultStreamBase):
    """异步流式输出。"""
    stream_response: AsyncStream[ResponseStreamEvent] = Field(..., repr=False, exclude=True)

    async def __aiter__(self) -> AsyncGenerator[ResponseStreamEvent, None]:
        if self.is_complete:
            raise RuntimeError("此流已被消费，请使用 .output 获取最终结果")

        if self.stream_response is None:
            raise RuntimeError("流未初始化")

        if self.start is None:
            self.start = time.perf_counter()

        async for event in self.stream_response:
            assert not self.is_complete

            if isinstance(event, EVENTS_IGNORE):
                continue

            if isinstance(event, ResponseCompletedEvent):
                self._finish(event)

            match self.verbosity:
                case StreamVerbosity.MINIMAL:
                    if isinstance(event, EVENTS_MINIMAL):
                        yield event

                case StreamVerbosity.MAXIMAL:
                    yield event

                case _:
                    assert_never(self.verbosity)

        assert self.is_complete
        assert isinstance(self.response, Response)

        await self.stream_response.close()


def stream(
    input: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: Ark,
    model: str,
    tools: Iterable[FunctionToolParam] | None = None,
    params: ResponseParams | None = None,
    **kwargs,
) -> ResponseResultStream:
    """
    流式调用。参数与 invoke 一致，stream=True，逐条 yield ResponseStreamEvent。
    调用方可根据 event 的 type 处理文本增量（如 response.output_item.delta）、完成、错误等。
    """
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))
    assert "format" not in kwargs, "format must not be specified in kwargs in invoke_stream."
    assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"
    kwargs.pop("stream", None)  # 由本函数固定为 True

    previous_response_id, message_history, input = _prepare_request(input, previous_response_or_system_prompt)

    response = cast(
        Stream[ResponseStreamEvent], 
        client.responses.create(
            model=model,
            input=input,
            tools=tools,
            previous_response_id=previous_response_id,
            stream=True,
            **kwargs,
        )
    )

    return ResponseResultStream(
        message_history=message_history,
        stream_response=response,
    )


async def astream(
    input: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: Iterable[FunctionToolParam] | None = None,
    params: ResponseParams | None = None,
    **kwargs: dict[str, Any],
) -> ResponseResultAsyncStream:
    """
    异步流式调用。参数与 ainvoke 一致，stream=True，逐条 yield ResponseStreamEvent。
    """
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))
    assert "format" not in kwargs, "format must not be specified in kwargs in ainvoke_stream."
    assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"
    kwargs.pop("stream", None)  # 由本函数固定为 True

    previous_response_id, message_history, input = _prepare_request(input, previous_response_or_system_prompt)

    response = cast(
        AsyncStream[ResponseStreamEvent], 
        await client.responses.create(
            model=model,
            input=input,
            tools=tools,
            previous_response_id=previous_response_id,
            stream=True,
            **kwargs,
        )
    )

    return ResponseResultAsyncStream(
        message_history=message_history,
        stream_response=response,
    )


class StreamEventHandler(Protocol):
    def __call__(self, event: ResponseStreamEvent) -> None:
        ...


class DefaultStreamEventHandler:
    """缺省事件处理器： 打印和统计，方便基本的测试使用。可以逐步增加基础功能。"""

    def __init__(self, *, print_fn=print, do_print: bool=True, do_stats : bool=False) -> None:
        self.print = print_fn
        self.captured_events: list[ResponseStreamEvent] = []
        self.do_stats = do_stats
        self.do_print = do_print

    def __call__(self, event: ResponseStreamEvent) -> None:
        if self.do_stats:
            self.captured_events.append(event)

        if not self.do_print:
            return

        match event:
            case ResponseTextDeltaEvent():
                self.print(event.delta, end="", flush=True)
            
            case ResponseFunctionCallArgumentsDeltaEvent():
                self.print(event.delta, end="", flush=True)
            
            case ResponseReasoningSummaryTextDeltaEvent():
                self.print(event.delta, end="", flush=True)
            
            case _:
                self.print(event)

    def stats(self) -> None:
        """打印统计信息"""
        if not self.captured_events:
            self.print("没有捕获事件，请检查event_handler的do_stats参数是否为True。")
            return
            
        self.event_types = Counter([type(event) for event in self.captured_events])
        self.print(f"Captured {len(self.captured_events)} events with {len(self.event_types)} types.")
        self.print(self.event_types)


def stream_run(
    input_data: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: Ark,
    model: str,
    tools: Iterable[FunctionToolParam] | None = None,
    params: ResponseParams | None = None,
    verbosity: StreamVerbosity = StreamVerbosity.MINIMAL,
    event_handler: StreamEventHandler = DefaultStreamEventHandler(print_fn=rich.print),
    **kwargs,
) -> Response:
    """
    执行单个 stream run，返回 Response 对象。
    """
    stream_result = stream(
        input_data,
        previous_response_or_system_prompt,
        client=client,
        model=model,
        tools=tools,
        params=params,
        **kwargs,
    )
    stream_result.verbosity = verbosity
    for event in stream_result:
        event_handler(event)

    assert isinstance(stream_result.response, Response)
    return stream_result.response


async def astream_run(
    input_data: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: Iterable[FunctionToolParam] | None = None,
    params: ResponseParams | None = None,
    verbosity: StreamVerbosity = StreamVerbosity.MINIMAL,
    event_handler: StreamEventHandler = DefaultStreamEventHandler(print_fn=rich.print),
    **kwargs,
) -> Response:
    """
    执行单个 stream run，返回 Response 对象。
    """
    stream_result = await astream(
        input_data,
        previous_response_or_system_prompt,
        client=client,
        model=model,
        tools=tools,
        params=params,
        **kwargs,
    )
    stream_result.verbosity = verbosity
    async for event in stream_result:
        event_handler(event)

    assert isinstance(stream_result.response, Response)
    return stream_result.response
