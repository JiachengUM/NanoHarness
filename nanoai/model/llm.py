"""
LLM (Large Language Model) 模块 - OpenAI API 的高级封装

这个模块提供了对 OpenAI API 的完整封装，支持多种使用场景和输出格式。

主要功能:
1. 基础对话功能
   - 同步和异步接口 (llm/allm)
   - 支持自定义客户端和模型
   - 消息历史管理

2. 流式输出
   - 同步流式输出 (llm_stream)
   - 异步流式输出 (allm_stream)
   - 支持增量模式和累积模式
   - 实时内容生成

3. 结构化输出
   - 类型安全的结构化输出
   - 支持多种策略: auto/schema/tool_call
   - 基于 Pydantic 的 JSON Schema 验证
   - 基于工具调用的可靠结构化输出

4. 高级特性
   - 自动消息组合和格式化
   - 工具调用处理
   - 错误处理和验证
   - 完整的调试信息

使用示例:
    # 基础对话
    result = llm("你好，介绍一下Python")
    print(result.output)
    
    # 流式输出
    stream = llm_stream("写一首诗")
    for chunk in stream:
        print(chunk, end="")
    
    # 结构化输出
    from pydantic import BaseModel
    class Person(BaseModel):
        name: str
        age: int
    
    result = llm_output("生成一个用户信息", output_type=Person)
    print(result.output.name)

注意:
- 暂时只支持文本输入，不支持多模态输入
- 默认使用 DOUBAO_SEED_1_6_251015 模型
- 所有函数都支持自定义客户端和模型参数
"""

from typing import AsyncIterator, Iterator, Type, Literal, Final, Callable

from openai import AsyncOpenAI, OpenAI
from openai._streaming import AsyncStream, Stream
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema
from pydantic import BaseModel, ConfigDict, Field

from nanoai.model.config import (
    ModelName,
    create_client,
)
from nanoai.model._type_tool import create_type_tool, _BaseTypeTool
from nanoai.model.messages import QAList

__all__ = [
    "RunResult",
    "RunResultStream",
    "RunResultStreamAsync",
    "llm",
    "allm",
    "llm_stream",
    "allm_stream",
    "llm_output",
    "allm_output",
    "llm_output_by_schema",
    "allm_output_by_schema",
    "llm_output_by_tool",
    "allm_output_by_tool",
]


# 默认模型：这不是好的做法，仅仅是为了方便。实际项目中必须由上层调用者指定模型，不应该允许默认值。
_default_model: Final[ModelName] = ModelName.DOUBAO_SEED_1_6_FLASH_250828  # 最快的模型

def _parse_client_model[T: OpenAI | AsyncOpenAI](
    client: T | None,
    model: ModelName | str | None,
    client_class: type[T],
    /,
) -> tuple[T, str]:
    """
    通用的客户端和模型参数解析函数。
    当 model 为 ModelName 枚举时，会自动创建对应的客户端，client 参数必须为 None；
    当 model 为字符串时，必须提供对应的 client 参数 (OpenAI 或 AsyncOpenAI)；
    当 model 为 None 时，使用默认模型 DOUBAO_SEED_1_6_251015；
    这种设计确保了类型安全和参数一致性。
    
    Args:
        client: 客户端实例，可以为 None
        model: 模型名称，可以是 ModelName 枚举或字符串
        client_class: 客户端类 (OpenAI 或 AsyncOpenAI)
    
    Returns:
        tuple[client, model_name]: 解析后的客户端和模型名称
        
    Raises:
        AssertionError: 当参数组合不合法时
    """
    if model is None:
        model = _default_model

    if isinstance(model, ModelName):
        assert client is None, "client must be None when model is ModelName"
        client, model = create_client(model, client_class)
    else:
        assert isinstance(model, str), f"model must be str, but got {type(model)}"

    assert isinstance(client, client_class), f"client must be {client_class.__name__}, but got {type(client)}"

    return client, model


def _compose_messages(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
) -> list[ChatCompletionMessageParam]:
    """将输入和消息历史合并为OpenAI API的messages参数。"""

    assert isinstance(input, str), f"input must be str, but got {type(input)}"
    assert isinstance(messages_or_sys_prompt, (str, list)), f"messages_or_sys_prompt must be str or list, but got {type(messages_or_sys_prompt)}"

    if isinstance(messages_or_sys_prompt, str):
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam({"role": "system", "content": messages_or_sys_prompt})
        ]
    else:
        messages = messages_or_sys_prompt

    # 创建用户消息内容
    messages.append(ChatCompletionUserMessageParam(role="user", content=input))
    
    return messages


class RunResult[T](BaseModel):
    """LLM运行结果, 包含输出内容、原始响应和消息历史。"""

    output: T = Field(..., description="LLM 的输出结果")
    response: ChatCompletionMessage = Field(..., description="OpenAI API 的原始响应")
    messages: list[ChatCompletionMessageParam] = Field(default_factory=list, description="完整的对话消息历史")

    def details(self) -> list[str]:
        """返回详细的调试信息
        TODO: details这个名字不太好。实现也不太好。改为nl_repr?
        """
        res = []
        res.append(f"output: {self.output}")
        res.append(f"response: {self.response}")
        res.append(QAList.from_messages(self.messages).format())
        return res


# 定义流式结果的基础类
class BaseRunResultStream(BaseModel):
    """流式输出的基类。"""

    delta: bool = Field(..., description="是否返回增量内容")

    messages: list[ChatCompletionMessageParam] = Field(..., description="消息历史")

    output: str = Field(default="", description="输出的内容")
    '''仅支持输出str。不支持结构化输出。'''

    is_complete: bool = Field(default=False, description="是否完成了输出")

    def model_dump(self, *args, **kwargs) -> dict:
        # 在派生类中包括stream_response成员，其本质是HTTP链接，不能持久化，因此需要确保流式输出完成后再dump
        if not self.is_complete:
            raise RuntimeError("流式输出未完成，不能dump。请使用.output获取最终结果")
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args, **kwargs) -> str:
        if not self.is_complete:
            raise RuntimeError("流式输出未完成，不能dump。请使用.output获取最终结果")
        return super().model_dump_json(*args, **kwargs)

    def details(self) -> list[str]:
        '''TODO: 这个函数不太好。'''
        res = []
        res.append(f"delta: {self.delta}")
        res.append(f"is_complete: {self.is_complete}")
        res.append(f"output: {self.output}")
        res.append(QAList.from_messages(self.messages).format())
        return res

    def _process_chunk(self, chunk: ChatCompletionChunk, part_output: str) -> str:
        """处理单个chunk，返回更新后的part_output和是否完成"""
        response = chunk.choices[0].delta

        assert not response.tool_calls

        if response.content is not None:  # stream最后会返回None，然后再结束
            part_output += response.content

        if chunk.choices[0].finish_reason is not None:
            # 说明收到了最后一条消息
            self.is_complete = True
            self.output = part_output
            self.messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=self.output))

        return part_output


class RunResultStream(BaseRunResultStream):
    """同步流式输出。
    
    使用示例:
        # 基本用法
        stream = llm_stream("你好，请介绍一下Python")
        for chunk in stream:
            print(chunk, end="")  # 实时输出增量内容
        
        # 获取完整输出
        print(f"完整输出: {stream.output}")
        
        # 增量模式 vs 累积模式
        stream_delta = llm_stream("写一首诗", delta=True)    # 只返回新增内容
        stream_cumulative = llm_stream("写一首诗", delta=False)  # 返回累积内容
        
        # 流式输出只能消费一次
        for chunk in stream:
            print(chunk)
        # stream.output  # 可以获取最终结果
        # for chunk in stream:  # 错误！流已被耗尽
    """

    stream_response: Stream[ChatCompletionChunk] | None = Field(..., description="流式响应")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __iter__(self) -> Iterator[str]:
        """流式响应只能被消费一次，因此实现为简单的可迭代对象。
        
        一旦开始迭代，底层的HTTP流就会被耗尽，不能重新读取。
        我们通过is_complete标志来防止重复消费已耗尽的流。"""
        if self.is_complete:
            raise RuntimeError("此 RunResultStream 已经被使用过了, 请使用 .output 获取最终结果")

        if self.stream_response is None:
            raise RuntimeError("流式输出未初始化，不能迭代")

        part_output: str = ""
        for chunk in self.stream_response:
            part_output = self._process_chunk(chunk, part_output)

            if self.is_complete:
                break

            if self.delta:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            else:
                yield part_output
        self.stream_response.close()
        self.stream_response = None


class RunResultStreamAsync(BaseRunResultStream):
    """异步流式输出。
    
    使用示例:
        # 基本用法
        stream = await allm_stream("你好，请介绍一下Python")
        async for chunk in stream:
            print(chunk, end="")  # 实时输出增量内容
        
        # 获取完整输出
        print(f"完整输出: {stream.output}")
        
        # 增量模式 vs 累积模式
        stream_delta = await allm_stream("写一首诗", delta=True)    # 只返回新增内容
        stream_cumulative = await allm_stream("写一首诗", delta=False)  # 返回累积内容
        
        # 流式输出只能消费一次
        async for chunk in stream:
            print(chunk)
        # stream.output  # 可以获取最终结果
        # async for chunk in stream:  # 错误！流已被耗尽
        
        # 在异步函数中使用
        async def process_stream():
            stream = await allm_stream("生成代码")
            async for chunk in stream:
                await process_chunk(chunk)
            return stream.output
    """

    stream_response: AsyncStream[ChatCompletionChunk] | None = Field(..., description="流式响应")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def __aiter__(self) -> AsyncIterator[str]:
        if self.is_complete:
            raise RuntimeError("此 RunResultStreamAsync 已经被使用过了, 请使用 .output 获取最终结果")

        if self.stream_response is None:
            raise RuntimeError("流式输出未初始化，不能迭代")

        part_output: str = ""
        async for chunk in self.stream_response:
            part_output = self._process_chunk(chunk, part_output)

            if self.is_complete:
                break

            if self.delta:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            else:
                yield part_output

        await self.stream_response.close()
        self.stream_response = None


def _llm_core[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    output_processor: Callable[[ChatCompletionMessage], T],
    /,
    *,
    client: OpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[T]:
    """
    核心LLM调用函数，处理通用的API调用逻辑。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        client: OpenAI客户端
        model: 模型名称
        output_processor: 输出处理函数，将ChatCompletionMessage转换为目标类型T
        **kwargs: 传递给API的其他参数
    
    Returns:
        RunResult[T]: 包含处理后的输出结果
    """
    client, model = _parse_client_model(client, model, OpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)
    
    response = client.chat.completions.create(model=model, messages=messages, **kwargs)

    response_msg: ChatCompletionMessage = response.choices[0].message
    
    output = output_processor(response_msg)
    
    # 更新消息历史
    messages.append({"role": "assistant", "content": response_msg.content})
    
    return RunResult(output=output, response=response_msg, messages=messages)


async def _allm_core[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    output_processor: Callable[[ChatCompletionMessage], T],
    /,
    *,
    client: AsyncOpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[T]:
    """异步版本的核心LLM调用函数。"""
    client, model = _parse_client_model(client, model, AsyncOpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)
    
    response = await client.chat.completions.create(model=model, messages=messages, **kwargs)

    response_msg: ChatCompletionMessage = response.choices[0].message
    
    output = output_processor(response_msg)
    
    messages.append({"role": "assistant","content": response_msg.content})
    
    return RunResult(output=output, response=response_msg, messages=messages)


DEFAULT_SYS_PROMPT: Final[str] = "你是一个有用的助手"

def _str_output_processor(response_msg: ChatCompletionMessage) -> str:
    """字符串输出处理器"""
    assert response_msg.content is not None
    return response_msg.content

def llm(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: OpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[str]:
    """基础LLM调用函数。"""
    return _llm_core(input, messages_or_sys_prompt, _str_output_processor, client=client, model=model, **kwargs)


async def allm(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: AsyncOpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[str]:
    """异步版本的基础LLM调用函数。"""
    return await _allm_core(input, messages_or_sys_prompt, _str_output_processor, client=client, model=model, **kwargs)


def llm_stream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    delta: bool = True,
    client: OpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResultStream:
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

    client, model = _parse_client_model(client, model, OpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)

    return RunResultStream(
        stream_response=client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
        ),
        delta=delta,
        messages=messages,
    )


async def allm_stream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    delta: bool = True,
    client: AsyncOpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResultStreamAsync:
    """异步流式输出。"""

    client, model = _parse_client_model(client, model, AsyncOpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)

    return RunResultStreamAsync(
        stream_response=await client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
            ),
            delta=delta,
            messages=messages,
        )


def llm_output[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: Type[T],
    strategy: Literal["auto", "schema", "tool_call"] = "auto",
    client: OpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[T]:
    """
    结构化输出函数，支持 auto、schema 和 tool_call 三种策略。
    
    策略说明：
    - 'auto': 自动选择策略（默认）。当前实现选择 tool_call，未来可能基于模型能力、输出类型复杂度等智能选择
    - 'schema': 使用 JSON schema 方式，要求 output_type 必须是 BaseModel。优点：简单直接，兼容性好；缺点：依赖模型JSON生成能力
    - 'tool_call': 使用工具调用方式，支持任意类型 T。优点：更可靠的结构化输出，类型安全；缺点：需要模型支持工具调用
    
    设计考虑：
    1. 默认使用 'auto' 策略，降低用户认知负担，用户不需要了解底层实现细节
    2. 提供明确的策略选择，满足高级用户的需求
    3. 为未来扩展留下空间，auto 策略可以逐步完善智能选择逻辑
    4. 保持向后兼容性，原有的 llm_output_by_schema 和 llm_output_by_tool 函数仍然可用
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: 输出类型
        strategy: 输出策略
            - 'auto': 自动选择（默认使用 tool_call）
            - 'schema': 使用 JSON schema，要求 output_type 必须是 BaseModel
            - 'tool_call': 使用工具调用，支持任意类型
        client: OpenAI 客户端
        model: 模型名称
        **kwargs: 其他参数
    
    Returns:
        RunResult[T]: 包含输出结果的运行结果
    
    Raises:
        ValueError: 当 strategy='schema' 但 output_type 不是 BaseModel 时
        ValueError: 当 strategy 不是有效值时
    """
    assert output_type is not str, "output_type cannot be str in llm_output"

    if strategy == "auto":
        # 最简单的实现：auto 时选择 tool_call
        # 未来可以在这里添加更智能的策略选择逻辑，比如：
        # - 基于模型能力检测（是否支持工具调用）
        # - 基于输出类型复杂度（简单类型用 schema，复杂类型用 tool_call）
        # - 基于历史成功率数据
        # - 基于用户偏好设置
        strategy = "tool_call"
    
    if strategy == "schema":
        # 对于 schema 策略，output_type 必须是 BaseModel
        # 这是因为 JSON schema 方式需要从 BaseModel 生成 schema 定义
        if not issubclass(output_type, BaseModel):
            raise ValueError(f"strategy='schema' requires output_type to be BaseModel, got {output_type}")
        return llm_output_by_schema(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    elif strategy == "tool_call":
        # tool_call 策略支持任意类型 T，包括 BaseModel、基本类型、复杂类型等
        # 这是通过创建类型工具（type tool）来实现的
        return llm_output_by_tool(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    else:
        # 提供清晰的错误信息，帮助用户理解可用的策略选项
        raise ValueError(f"Unknown strategy: {strategy}. Must be 'auto', 'schema' or 'tool_call'")


async def allm_output[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: Type[T],
    strategy: Literal["auto", "schema", "tool_call"] = "auto",
    client: AsyncOpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[T]:
    """异步版本的结构化输出函数，支持 auto、schema 和 tool_call 三种策略。"""
    assert output_type is not str, "output_type cannot be str in allm_output"

    if strategy == "auto":
        # 最简单的实现：auto 时选择 schema
        strategy = "schema"
    
    if strategy == "schema":
        # 对于 schema 策略，output_type 必须是 BaseModel
        if not issubclass(output_type, BaseModel):
            raise ValueError(f"strategy='schema' requires output_type to be BaseModel, got {output_type}")
        return await allm_output_by_schema(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    elif strategy == "tool_call":
        return await allm_output_by_tool(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}. Must be 'auto', 'schema' or 'tool_call'")


def _create_schema_output_processor(output_type: Type[BaseModel]) -> Callable[[ChatCompletionMessage], BaseModel]:
    """创建基于 JSON Schema 的输出处理器"""
    def output_processor(response_msg: ChatCompletionMessage) -> BaseModel:
        assert response_msg.content is not None
        return output_type.model_validate_json(response_msg.content)
    return output_processor


def llm_output_by_schema(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: Type[BaseModel],
    client: OpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[BaseModel]:
    """基于JSON Schema的结构化输出。"""
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"
    
    if "json" not in input.lower():
        input = f"{input}\n请返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return _llm_core(
        input,
        messages_or_sys_prompt,
        _create_schema_output_processor(output_type),
        client=client,
        model=model,
        response_format=response_format,
        **kwargs,
    )

async def allm_output_by_schema(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: Type[BaseModel],
    client: AsyncOpenAI | None = None,
    model: ModelName | str | None = None,
    **kwargs,
) -> RunResult[BaseModel]:
    """异步版本。唯一区别是调用_allm_core"""
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"
    
    if "json" not in input.lower():
        input = f"{input}\n请返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return await _allm_core(
        input,
        messages_or_sys_prompt,
        _create_schema_output_processor(output_type),
        client=client,
        model=model,
        response_format=response_format,
        **kwargs,
    )


def _process_tool_response[T](
    response_msg: ChatCompletionMessage,
    tool: _BaseTypeTool[T],
    messages: list[ChatCompletionMessageParam],
    output_type: Type[T]
) -> tuple[T, list[ChatCompletionMessageParam]]:
    """处理工具响应"""
    if response_msg.tool_calls is None:
        raise RuntimeError(
            "无法生成正确的tool call: response.tool_calls is None "
            f"for output_type {output_type}, with response: {response_msg.content}"
        )

    if len(response_msg.tool_calls) != 1:
        raise RuntimeError(
            f"tool call数量{len(response_msg.tool_calls)}，错误, 应该为1, with response: {response_msg.content}"
        )

    # 处理tool calls
    # 把ChatCompletionMessage转成ChatCompletionAssistantMessageParam并放回到message_history中
    assistant_msg: ChatCompletionAssistantMessageParam = {
        "role": "assistant",
        "content": response_msg.content,
        "tool_calls": [tool_call.model_dump() for tool_call in response_msg.tool_calls],  # type: ignore
    }

    # 必须先append assistant_msg，再append tool_message
    messages.append(assistant_msg)

    # 自动生成占位tool消息
    for tool_call in response_msg.tool_calls:
        tool_message: ChatCompletionToolMessageParam = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": "工具调用被略过",  # 占位内容
        }
        messages.append(tool_message)

    # 确保assistant_msg会被append。因此，需要放到最后。
    try:
        tool_call = response_msg.tool_calls[0]
        assert tool_call.type == "function", f"Expected function tool call, got {tool_call.type}"
        output = tool.execute(tool_call)
    except Exception as e:
        # 不能print，只能log
        # print(f"tool validation error with tool call {response_msg.tool_calls[0]}\n error message: \n {e}")
        raise e

    return output, messages

def llm_output_by_tool[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: Type[T],
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> RunResult[T]:
    '''
    使用tool call的方式实现结构化输出。
    '''

    client, model = _parse_client_model(client, model, OpenAI)

    # kwargs中不可以有tools和tool_choice。
    assert "tools" not in kwargs, "tools in kwargs is not allowed"
    assert "tool_choice" not in kwargs, "tool_choice in kwargs is not allowed"
    
    messages = _compose_messages(input, messages_or_sys_prompt)
    tool = create_type_tool(output_type)
    
    response = client.chat.completions.create(
        model=model, 
        messages=messages, 
        tools = [tool.tool_param],
        tool_choice = {"type": "function", "function": {"name": tool.tool_param["function"]["name"]}}, # 强制要求调用tool。
        **kwargs)
    response_msg: ChatCompletionMessage = response.choices[0].message

    output, messages = _process_tool_response(response_msg, tool, messages, output_type)  # type: ignore

    return RunResult(output=output, response=response_msg, messages=messages)  # type: ignore
    # 类型推断问题：create_type_tool[T] 返回 _BaseTypeTool[T]，但 execute() 方法返回 T
    # 类型检查器无法正确推断 output 的类型为 T@tool_output_function，而是推断为 T@create_type_tool
    # 这两个 T 在类型系统中被视为不同的类型参数，导致不兼容错误。
    # 这个错误似乎是因为create_type_tool被lru_cache装饰，导致类型推断器无法正确推断类型参数。如果去掉lru_cache，则类型检查没有问题。
    # 因此，这个函数并没有类型不安全的问题。


async def allm_output_by_tool[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    output_type: Type[T],
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> RunResult[T]:
    '''异步版本。'''

    client, model = _parse_client_model(client, model, AsyncOpenAI)

    # kwargs中不可以有tools和tool_choice。
    assert "tools" not in kwargs, "tools in kwargs is not allowed"
    assert "tool_choice" not in kwargs, "tool_choice in kwargs is not allowed"
    
    messages = _compose_messages(input, messages_or_sys_prompt)
    tool = create_type_tool(output_type)

    response = await client.chat.completions.create(
        model=model, 
        messages=messages, 
        tools=[tool.tool_param],
        tool_choice={"type": "function", "function": {"name": tool.tool_param["function"]["name"]}}, # 强制要求调用tool。
        **kwargs
    )
    response_msg: ChatCompletionMessage = response.choices[0].message

    output, messages = _process_tool_response(response_msg, tool, messages, output_type)  # type: ignore

    return RunResult(output=output, response=response_msg, messages=messages)  # type: ignore
