"""核心数据结构和基础功能模块"""

from __future__ import annotations

from typing import TypeAlias, Annotated, Union

from pydantic import Field, model_validator

from volcenginesdkarkruntime import Ark, AsyncArk

from volcenginesdkarkruntime._utils import PropertyInfo

from volcenginesdkarkruntime.types.responses.response_input_param import (
    FunctionCallOutput,
    ResponseFunctionToolCallParam,
    ResponseInputItemParam,
)

from volcenginesdkarkruntime.types.responses import (
    # input
    EasyInputMessageParam,
    ResponseInputParam,

    # output
    Response as ResponseRaw,
    ResponseReasoningItem,
    ResponseFunctionToolCall,
    FunctionToolParam,
    ResponseItem,
)
from volcenginesdkarkruntime.types.responses.response_output_message import ResponseOutputMessage
from volcenginesdkarkruntime.types.responses.response_output_text import ResponseOutputText
from volcenginesdkarkruntime.types.responses.response_input_message_item import ResponseInputMessageItem
from volcenginesdkarkruntime.types.responses.response_function_tool_call_item import ResponseFunctionToolCallItem
from volcenginesdkarkruntime.types.responses.response_function_tool_call_output_item import ResponseFunctionToolCallOutputItem

from aicore.models.messages import BaseMessage, AIMessage, HumanMessage


# 火山sdk挪过来的，目前只处理了这四种类型，原始有七种
ResponseItemSimple: TypeAlias = Annotated[
    Union[
        ResponseInputMessageItem,
        ResponseOutputMessage,
        ResponseReasoningItem,
        ResponseFunctionToolCallItem,
        ResponseFunctionToolCallOutputItem,
    ],
    PropertyInfo(discriminator="type"),
]

# 消息辅助函数
def system_msg(content: str) -> EasyInputMessageParam:
    return {"role": "system", "content": content}

def user_msg(content: str) -> EasyInputMessageParam:
    return {"role": "user", "content": content}

def assistant_msg(content: str) -> EasyInputMessageParam:
    return {"role": "assistant", "content": content}

def function_call_output(call_id: str, output: str, /) -> FunctionCallOutput:
    return FunctionCallOutput(
        call_id=call_id,
        output=output,
        type="function_call_output"
    )


# 核心数据结构。将来可以解耦出和数据库打通。
class Response(ResponseRaw):
    """
    基于原始的Response, 增加了一些功能.
    """
    message_history: list[tuple[HumanMessage, AIMessage]] = Field(..., description="消息历史记录")
    """由用户输入和模型回复组成的消息历史记录。
    原理上并不是Response的一部分，因为Response是一次model call的输出，而message_history是一次会话中多次连续model call的输出。
    暂时放在这里。更加干净的写法是要解耦出去进入agent state。
    """
    
    message: ResponseOutputMessage | None = Field(default=None, description="输出的消息")

    think: ResponseReasoningItem | None = Field(default=None, description="推理过程")
    """thinking和reasoning这两个字段名在ResponseRaw均定义了，因此使用think字段名"""

    tool_calls: list[ResponseFunctionToolCall] | None = Field(default=None, description="输出的工具调用")

    # TODO: 增加 run_info 字段，包含模型参数、调用时间、tokens等信息
    latency: float = Field(..., description="LLM 调用耗时")
    
    history: list[ResponseItemSimple] | None = Field(default=None, init=False, description="dump时从id获取的历史对话")

    @property
    def raw_text(self) -> str:
        # TODO: caching为enable且prefix=true时，无内容。raw_text不可用。
        if self.caching and self.caching.type == "enabled" and self.caching.prefix:
            raise RuntimeError("raw_text 仅在存在模型回复时可用（prefix=true时无内容）")
                
        assert isinstance(self.message, ResponseOutputMessage)
        return self.message.content[0].text

    @model_validator(mode="after")
    def validate_all(self) -> Response:
        # TODO: prefix场景下，无message，不可用raw_text。临时处理。
        if self.caching and self.caching.type == "enabled" and self.caching.prefix:

            return self

        # message 和 tool_calls 有可能同时出现，这是合理的，目的是 “先给用户反馈，再触发工具执行”；
        # 但多轮场景下，不能说先告诉你执行完毕，然后才去执行工具；
        # 且当前轮次内容不可依赖工具结果，后续指令需待工具返回 message 后执行。
        # 官方文档：( https://www.volcengine.com/docs/82379/1262342?lang=zh#ff6e0fcb )

        # assert (
        #     (self.message is None) != (self.tool_calls is None)
        # ), f"message {self.message} and tool_calls {self.tool_calls} should have exactly one non-None value"
        
        return self

    @classmethod
    def from_raw(
        cls, 
        response: ResponseRaw, 
        /,
        *,
        message_history: list[tuple[HumanMessage, AIMessage]],
        latency: float) -> Response:
        # 这是ResponseRaw的bug。声明时不允许为None，但实际返回的可以是None。
        if response.output is None:
            response.output = []
        # 这是ResponseRaw的bug。声明时不允许为None，但实际返回的可以是None。这样就无法用ResponseRaw来构造Response。

        if response.tools is None:
            response.tools = []

        # TODO：ResponseRaw 把 parallel_tool_calls 和 tool_choice 定义为必填，但 API 会返回 None，导致dump失败。
        # 要改的话，需要改 ResponseRaw 的定义，或者改 API 的返回？不知道怎么处理好,临时处理。
        if response.parallel_tool_calls is None:
            response.parallel_tool_calls = False
        if response.tool_choice is None:
            response.tool_choice = "none"
        
        message: ResponseOutputMessage | None = None
        think: ResponseReasoningItem | None = None
        tool_calls: list[ResponseFunctionToolCall] | None = None

        dump = response.model_dump()

        for item in response.output:
            if isinstance(item, ResponseOutputMessage):
                # ResponseOutputMessage只能有一个？不确定，先这样约束。
                assert message is None, "message should be None before assigned for the first time"
                assert len(item.content) == 1, "content len must be 1"
                message = item                
            elif isinstance(item, ResponseReasoningItem):
                # 如果开启thinking，会有它
                # ResponseReasoningItem只能有一个？不确定，先这样约束。
                assert think is None, "think should be None before assigned for the first time"
                think = item
            elif isinstance(item, ResponseFunctionToolCall):
                # 如果传入tool，会有它
                if tool_calls is None:
                    tool_calls = []

                tool_calls.append(item)
            else:
                raise TypeError(f"wrong item type: {type(item)}")

        return cls(
            message_history=message_history,
            message=message,
            think=think,
            tool_calls=tool_calls,
            latency=latency,
            **dump
        )
    
    async def ahistory(self, /, *, client: AsyncArk) -> list[ResponseItemSimple]:
        """获取当前response id对应的消息历史，以及当前的output"""
        # 防止循环导入
        from aicore.models.responses.management import alist_all_items 
        # 根据当前id 获取之前的历史对话，不包含当前id的结果
        history_items_list = await alist_all_items(self.id, client=client)
         # TODO: 这里是api返回的一个bug，不得不这么处理。
        for i, item in enumerate(history_items_list):
            if isinstance(item, ResponseOutputMessage) and item.content and item.role == "assistant" and item.content[0].type == "input_text" :
                    history_items_list[i] = ResponseOutputMessage(
                        type="message",
                        role="assistant",
                        content=[ResponseOutputText(type="output_text", text=item.content[0].text)],
                        status="completed",
                        id=item.id,
                        partial=None
                    )
            # TODO: 不得不这么处理，火山sdk将thinking模式下的内容塞进了ResponseInputMessageItem中，type为'reasoning',按理说属于ResponseReasoningItem
            elif isinstance(item, ResponseInputMessageItem) and item.type == 'reasoning':
                history_items_list[i] = ResponseReasoningItem(
                    id=item.id,
                    type="reasoning",
                    summary=item.summary,
                    status="completed",
                )

        #TODO：将当前id的输出结果加上，隐患，后续需要处理，可能有多个output
        if self.output:  # 先判断 self.output 非空（避免空列表/None）
            for output_item in self.output:
                # TODO：目前只处理指定的两种类型，过滤其他类型
                if isinstance(output_item, (ResponseOutputMessage, ResponseReasoningItem, ResponseFunctionToolCall)):
                    if isinstance(output_item, ResponseFunctionToolCall):
                        # 工具调用，需要转换为 ResponseFunctionToolCallItem
                        assert output_item.id is not None, "function call id must be provided"
                        new_item = ResponseFunctionToolCallItem(
                            id=output_item.id,
                            type="function_call",
                            name=output_item.name,
                            arguments=output_item.arguments,
                            status="completed",
                            call_id=output_item.call_id,
                        )
                        history_items_list.append(new_item)
                        continue
                    
                    history_items_list.append(output_item)
        assert all(isinstance(item, (ResponseInputMessageItem, ResponseOutputMessage, ResponseFunctionToolCallItem, ResponseFunctionToolCallOutputItem, ResponseReasoningItem)) for item in history_items_list), "history_items_list 中包含了未知类型的item,暂时无法处理。"
        return history_items_list


"""转换工具，将ResponseItem转换为input_param"""

def _convert_output_message_and_ResponseInputMessageItem(
    msg: ResponseOutputMessage| ResponseInputMessageItem
) -> EasyInputMessageParam:
    """
    转换输入输出文本消息，简单处理。
    """
    return EasyInputMessageParam(
        type="message",
        role=msg.role,
        content=msg.content[0].text, # 只针对文本
    )

# 模型调用工具的输出
def _convert_tool_call_item(
    tool_call: ResponseFunctionToolCallItem,
) -> ResponseFunctionToolCallParam:
    """
    转换工具调用项（ResponseFunctionToolCallItem）为API标准输入消息项
    """
    return ResponseFunctionToolCallParam(
        arguments=tool_call.arguments,
        call_id=tool_call.call_id,
        name=tool_call.name,
        type="function_call"
    )

def _convert_tool_call_output_item(
    tool_output: ResponseFunctionToolCallOutputItem
) -> FunctionCallOutput:
    """
    转换工具调用输出项（ResponseFunctionToolCallOutputItem）为API标准输入消息项
    """
    return FunctionCallOutput(
        output=tool_output.output,
        call_id=tool_output.call_id,
        type="function_call_output"
    )

# 自动匹配到EasyInputMessageParam, ResponseFunctionToolCallParam, FunctionCallOutput
def convert_to_input_param(
    item: ResponseOutputMessage| ResponseInputMessageItem| ResponseFunctionToolCallItem| ResponseFunctionToolCallOutputItem| ResponseReasoningItem
) -> EasyInputMessageParam| ResponseFunctionToolCallParam| FunctionCallOutput| None:
    """
    自动匹配到EasyInputMessageParam, ResponseFunctionToolCallParam, FunctionCallOutput
    先简单处理，后续需要扩展。
    # TODO： 需要看下官方是否有convert_to_input_param这种转化的逻辑，按理说有，不需要开发者自己维护。convert只处理了已知的几类,未知的会返回None。只保留非None的结果
    """
    if isinstance(item, (ResponseOutputMessage, ResponseInputMessageItem)):
        return _convert_output_message_and_ResponseInputMessageItem(item)
    elif isinstance(item, ResponseFunctionToolCallItem):
        return _convert_tool_call_item(item)
    elif isinstance(item, ResponseFunctionToolCallOutputItem):
        return _convert_tool_call_output_item(item)
    else:
        # TODO：目前只处理以上4类已知的情况。但是item可能会有其他未知类型。
        return None

def convert_items_to_input_params(
    items: list[ResponseItemSimple],
) -> list[ResponseInputItemParam]:
    """
    批量转换为 API 标准输入格式，并过滤掉当前不支持的类型（None）。
    """
    return [
        converted_item
        for item in items
        if (converted_item := convert_to_input_param(item)) is not None
    ]

def _prepare_request(
    input: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
) -> tuple[str | None, list[tuple[HumanMessage, AIMessage]], str | ResponseInputParam]:
    """
    根据 input 和 previous 组装 previous_response_id、message_history 和请求用 input。
    供 invokation、streaming模块使用。
    """
    # 初始化
    previous_response_id = None
    message_history: list[tuple[HumanMessage, AIMessage]] = []

    if previous_response_or_system_prompt is None:
        # None,只处理为str 的情况，tool情况不处理。
        if isinstance(input, str):
            message_history.append((HumanMessage(content=input), AIMessage(content="")))

        # TODO: 还没想好要怎么处理，遇到再说。目前list只有通过此方式传入，按理说最后一条消息应该是user_msg，进入message_history？。
        # elif isinstance(input, list) and input[-1]["role"] == "user":
        #     message_history.append((HumanMessage(content=input[-1]["content"]), AIMessage(content="")))

    elif isinstance(previous_response_or_system_prompt, str):
        # 组装消息列表，如果是str 
        if isinstance(input, str):
            message_history.append((HumanMessage(content=input), AIMessage(content="")))
            # 组装系统提示词和用户query
            input = [system_msg(previous_response_or_system_prompt), user_msg(input)]

    else:
        # 传入的是Response对象
        resp = previous_response_or_system_prompt
        # 构造下一轮调用输入；有history则走history，无history则走response_id连续对话。如果是有history同时还要获取message_history
        if resp.history:
            # dump 恢复 与 ReAct 达最大轮次强制收尾（agents/_react_core._astream_react_terminate）共用：
            # previous 为带 history 的 Response；input 为 str 或 [*tool_results, user_msg(强制提示)]。
            # list 时强制提示只进 API input，不进 message_history（给人看的对话里不掺这条）。
            message_history = resp.message_history
            last_ai_empty = bool(message_history and message_history[-1][1].content == "")
            if isinstance(input, str) and not last_ai_empty:
                # 对应agent dump场景
                message_history.append((HumanMessage(content=input), AIMessage(content="")))
            # 将火山返回的history 转换为输入的格式
            prefix = convert_items_to_input_params(resp.history)
            input = (
                [*prefix, user_msg(input)]
                if isinstance(input, str)
                else [*prefix, *input]
            )
        else:
            previous_response_id = resp.id
            message_history = resp.message_history
            if isinstance(input, str):
                message_history.append((HumanMessage(content=input), AIMessage(content="")))
            # input 为 list（如仅工具输出）时直接交给 API，不追加 message_history 占位

    return previous_response_id, message_history, input

