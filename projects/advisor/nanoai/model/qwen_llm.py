"""
Qwen LLM (Large Language Model) 模块 - Qwen API 的高级封装

这个模块提供了对 Qwen API 的完整封装，支持多种使用场景和输出格式。

主要功能:
1. 基础对话功能
   - 同步和异步接口 (qwen/qwen_async)
   - 支持自定义客户端和模型
   - 消息历史管理

2. 流式输出
   - 同步流式输出 (qwen_stream)
   - 异步流式输出 (qwen_async_stream)
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
    result = qwen("你好，介绍一下Python")
    print(result.output)
    
    # 流式输出
    stream = qwen_stream("写一首诗")
    for chunk in stream:
        print(chunk, end="")
    
    # 结构化输出
    from pydantic import BaseModel
    class Person(BaseModel):
        name: str
        age: int
    
    result = qwen_output("生成一个用户信息", output_type=Person)
    print(result.output.name)

注意:
- 暂时只支持文本输入，不支持多模态输入
- 默认使用 Qwen3-0.6B 模型
- 所有函数都支持自定义客户端和模型参数
"""

from typing import AsyncIterator, Iterator, Type, Literal, Final, Callable, Optional, Dict, Any

import torch
from openai import APIConnectionError, APIError, RateLimitError, Timeout
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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from transformers import AutoModelForCausalLM, AutoTokenizer

from nanoai.model._type_tool import create_type_tool, _BaseTypeTool
from nanoai.model.messages import QAList

__all__ = [
    "QwenRunResult",
    "QwenRunResultStream",
    "QwenRunResultStreamAsync",
    "qwen",
    "qwen_async",
    "qwen_stream",
    "qwen_async_stream",
    "qwen_output",
    "qwen_async_output",
    "qwen_output_by_schema",
    "qwen_async_output_by_schema",
    "qwen_output_by_tool",
    "qwen_async_output_by_tool",
]


# 默认模型：使用config.py中定义的有效模型名称
from nanoai.model.config import ModelName
_default_model: Final[str] = ModelName.DOUBAO_SEED_1_8_251228.value

DEFAULT_SYS_PROMPT: Final[str] = "你是一个有用的助手"

# 本地模型管理单例类
class LocalModelManager:
    """本地Qwen模型管理器，负责模型的加载和缓存"""
    _instance = None
    _models: Dict[str, Any] = {}
    _tokenizers: Dict[str, Any] = {}
    _device: str = "cuda" if torch.cuda.is_available() else "cpu"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocalModelManager, cls).__new__(cls)
        return cls._instance
    
    def get_model(self, model_id: str, hf_token: Optional[str] = None) -> Any:
        """获取或加载本地模型
        
        Args:
            model_id: 模型ID，如"Qwen/Qwen3-0.6B"
            hf_token: Hugging Face访问令牌
        
        Returns:
            加载好的模型
        """
        # 检查模型是否已经加载，避免重复加载
        if model_id not in self._models:
            self._models[model_id] = AutoModelForCausalLM.from_pretrained(
                model_id,
                dtype=torch.bfloat16,
                token=hf_token,
                local_files_only=True
            ).to(self._device)
        return self._models[model_id]
    
    def get_tokenizer(self, model_id: str, hf_token: Optional[str] = None) -> Any:
        """获取或加载本地分词器
        
        Args:
            model_id: 模型ID，如"Qwen/Qwen3-0.6B"
            hf_token: Hugging Face访问令牌
        
        Returns:
            加载好的分词器
        """
        # 检查分词器是否已经加载，避免重复加载
        if model_id not in self._tokenizers:
            self._tokenizers[model_id] = AutoTokenizer.from_pretrained(
                model_id,
                token=hf_token,
                local_files_only=True
            )
        return self._tokenizers[model_id]
    
    def generate_text(self, model_id: str, messages: list, hf_token: Optional[str] = None, enable_thinking: bool = False, **kwargs) -> str:
        """使用本地模型生成文本
        
        Args:
            model_id: 模型ID
            messages: 消息列表
            hf_token: Hugging Face访问令牌
            enable_thinking: 是否启用思考模式
            **kwargs: 其他生成参数，支持以下参数：
                - max_new_tokens: 生成的最大token数
                - do_sample: 是否使用采样生成
                - temperature: 采样温度
                - top_p: 核采样概率
                - top_k: 采样的top-k值
                - repetition_penalty: 重复惩罚系数
                - 其他transformers库支持的generate方法参数
        
        Returns:
            生成的文本
        """
        # 获取模型和分词器
        model = self.get_model(model_id, hf_token)
        tokenizer = self.get_tokenizer(model_id, hf_token)

        # 使用消息列表构建Chat模式输入
        input_ids = tokenizer.apply_chat_template(
            messages,
            return_tensors="pt",
            add_generation_prompt=True,
            enable_thinking=enable_thinking
        )
        
        # 将输入移动到模型设备
        input_ids = input_ids.to(self._device)
        attention_mask = torch.ones_like(input_ids)

        # 生成文本
        outputs = model.generate(
            input_ids,
            attention_mask=attention_mask,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            **kwargs
        )
        
        # 解码生成的文本（跳过输入部分）
        generated_text = tokenizer.decode(
            outputs[0][input_ids.shape[1]:],
            skip_special_tokens=True
        )
        
        return generated_text

# 创建本地模型管理器实例
local_model_manager = LocalModelManager()


def _parse_client_model[T: OpenAI | AsyncOpenAI](
    client: T | None,
    model: str | None,
    client_class: type[T],
    /,
) -> tuple[T, str]:
    """
    通用的客户端和模型参数解析函数。
    当 model 为 None 时，使用默认模型 Qwen3-0.6B；
    
    Args:
        client: 客户端实例，可以为 None
        model: 模型名称，可以是字符串
        client_class: 客户端类 (OpenAI 或 AsyncOpenAI)
    
    Returns:
        tuple[client, model_name]: 解析后的客户端和模型名称
        
    Raises:
        AssertionError: 当参数组合不合法时
    """
    # 如果没有提供客户端，使用create_client函数创建客户端，并使用其返回的模型名称
    if client is None:
        from nanoai.model.config import create_client, ModelName
        client, model = create_client(ModelName.DOUBAO_SEED_1_8_251228, client_class)
        return client, model
    
    # 如果提供了客户端，使用用户指定的模型名称
    if model is None:
        model = _default_model
    
    assert isinstance(model, str), f"model must be str, but got {type(model)}"
    
    # 不再强制验证模型名称，允许用户使用自定义模型名称
    # 只在调试模式下显示警告
    from nanoai.model.config import ModelName
    valid_models = [m.value for m in ModelName]
    if model not in valid_models:
        print(f"Debug: Using custom model '{model}'. Valid models are: {valid_models}")
    
    return client, model


def _compose_messages(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
) -> list[ChatCompletionMessageParam]:
    """将输入和消息历史合并为Qwen API的messages参数。"""

    assert isinstance(input, str), f"input must be str, but got {type(input)}"
    assert isinstance(messages_or_sys_prompt, (str, list)), f"messages_or_sys_prompt must be str or list, but got {type(messages_or_sys_prompt)}"

    if isinstance(messages_or_sys_prompt, str):
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam({"role": "system", "content": messages_or_sys_prompt})
        ]
    else:
        messages = messages_or_sys_prompt.copy()

    # 只有当输入不为空时，才添加用户消息
    if input:
        messages.append(ChatCompletionUserMessageParam(role="user", content=input))
    
    return messages


class QwenRunResult[T](BaseModel):
    """Qwen LLM运行结果, 包含输出内容、原始响应和消息历史。"""

    output: T = Field(..., description="LLM 的输出结果")
    response: ChatCompletionMessage = Field(..., description="Qwen API 的原始响应")
    messages: list[ChatCompletionMessageParam] = Field(default_factory=list, description="完整的对话消息历史")

    def details(self) -> list[str]:
        """返回详细的调试信息"""
        res = []
        res.append(f"output: {self.output}")
        res.append(f"response: {self.response}")
        res.append(QAList.from_messages(self.messages).format())
        return res


# 定义流式结果的基础类
class QwenBaseRunResultStream(BaseModel):
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
        '''返回详细的调试信息'''
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


class QwenRunResultStream(QwenBaseRunResultStream):
    """同步流式输出。
    
    使用示例:
        # 基本用法
        stream = qwen_stream("你好，请介绍一下Python")
        for chunk in stream:
            print(chunk, end="")  # 实时输出增量内容
        
        # 获取完整输出
        print(f"完整输出: {stream.output}")
        
        # 增量模式 vs 累积模式
        stream_delta = qwen_stream("写一首诗", delta=True)    # 只返回新增内容
        stream_cumulative = qwen_stream("写一首诗", delta=False)  # 返回累积内容
        
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
            raise RuntimeError("此 QwenRunResultStream 已经被使用过了, 请使用 .output 获取最终结果")

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


class QwenRunResultStreamAsync(QwenBaseRunResultStream):
    """异步流式输出。
    
    使用示例:
        # 基本用法
        stream = await qwen_async_stream("你好，请介绍一下Python")
        async for chunk in stream:
            print(chunk, end="")  # 实时输出增量内容
        
        # 获取完整输出
        print(f"完整输出: {stream.output}")
        
        # 增量模式 vs 累积模式
        stream_delta = await qwen_async_stream("写一首诗", delta=True)    # 只返回新增内容
        stream_cumulative = await qwen_async_stream("写一首诗", delta=False)  # 返回累积内容
        
        # 流式输出只能消费一次
        async for chunk in stream:
            print(chunk)
        # stream.output  # 可以获取最终结果
        # async for chunk in stream:  # 错误！流已被耗尽
        
        # 在异步函数中使用
        async def process_stream():
            stream = await qwen_async_stream("生成代码")
            async for chunk in stream:
                await process_chunk(chunk)
            return stream.output
    """

    stream_response: AsyncStream[ChatCompletionChunk] | None = Field(..., description="流式响应")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def __aiter__(self) -> AsyncIterator[str]:
        if self.is_complete:
            raise RuntimeError("此 QwenRunResultStreamAsync 已经被使用过了, 请使用 .output 获取最终结果")

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


# 字符串输出处理器
def _str_output_processor(response_msg: ChatCompletionMessage) -> str:
    """字符串输出处理器"""
    assert response_msg.content is not None
    return response_msg.content


def _qwen_core[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    output_processor: Callable[[ChatCompletionMessage], T],
    /,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[T]:
    """
    核心Qwen调用函数，处理通用的API调用逻辑，支持本地模型和远程API。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        client: OpenAI客户端（兼容Qwen API）
        model: 模型名称
        output_processor: 输出处理函数，将ChatCompletionMessage转换为目标类型T
        **kwargs: 传递给API的其他参数
    
    Returns:
        QwenRunResult[T]: 包含处理后的输出结果
    """
    # 判断是否使用本地模型
    # 本地模型判断条件：
    # 1. 没有提供客户端
    # 2. 模型名称以"/"或"Qwen"开头（Hugging Face模型ID）
    # 3. 模型名称是本地文件路径
    if model:
        # 使用本地模型
        messages = _compose_messages(input, messages_or_sys_prompt)
        # 生成文本
        try:
            generated_text = local_model_manager.generate_text(
                model_id=model,
                messages=messages,
                **kwargs
            )
        except Exception as e:
            # 记录详细错误信息
            print(f"Error in local model generation: {str(e)}")
            print(f"Model: {model}")
            print(f"Messages: {messages}")
            raise
        
        # 构造模拟的ChatCompletionMessage
        response_msg = ChatCompletionMessage(
            role="assistant",
            content=generated_text
        )
        
        output = output_processor(response_msg)
        
        # 更新消息历史
        messages.append({"role": "assistant", "content": generated_text})
        
        return QwenRunResult(output=output, response=response_msg, messages=messages)
    else:
        # 使用远程API
        client, model = _parse_client_model(client, model, OpenAI)

        messages = _compose_messages(input, messages_or_sys_prompt)
        
        # 过滤掉不被OpenAI SDK支持的自定义参数
        api_kwargs = {}
        for key, value in kwargs.items():
            # 跳过自定义参数
            if key not in ["apply_chat_template", "enable_thinking"]:
                api_kwargs[key] = value
        
        response = client.chat.completions.create(model=model, messages=messages, **api_kwargs)

        response_msg: ChatCompletionMessage = response.choices[0].message
        
        output = output_processor(response_msg)
        
        # 更新消息历史
        messages.append({"role": "assistant", "content": response_msg.content})
        
        return QwenRunResult(output=output, response=response_msg, messages=messages)


@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避，等待时间1秒开始，最多10秒
    retry=retry_if_exception_type((
        APIConnectionError,  # 连接错误
        APIError,  # API错误
        RateLimitError,  # 速率限制错误
        Timeout,  # 超时错误
    ))
)
async def _qwen_async_core[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
    output_processor: Callable[[ChatCompletionMessage], T],
    /,
    *, 
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[T]:
    """异步版本的核心Qwen调用函数。"""
    client, model = _parse_client_model(client, model, AsyncOpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)
    
    # 过滤掉不被OpenAI SDK支持的自定义参数
    api_kwargs = {}
    for key, value in kwargs.items():
        # 跳过自定义参数
        if key not in ["apply_chat_template", "enable_thinking"]:
            api_kwargs[key] = value
    
    response = await client.chat.completions.create(model=model, messages=messages, **api_kwargs)

    response_msg: ChatCompletionMessage = response.choices[0].message
    
    output = output_processor(response_msg)
    
    # 更新消息历史
    messages.append({"role": "assistant", "content": response_msg.content})
    
    return QwenRunResult(output=output, response=response_msg, messages=messages)


def qwen(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[str]:
    """基础Qwen调用函数。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        client: OpenAI客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        hf_token: Hugging Face访问令牌，用于访问私有模型
        **kwargs: 传递给API或本地模型的其他参数。
            对于本地模型，支持以下生成参数：
            - max_new_tokens: 生成的最大token数
            - do_sample: 是否使用采样生成
            - temperature: 采样温度
            - top_p: 核采样概率
            - top_k: 采样的top-k值
            - repetition_penalty: 重复惩罚系数
    
    Returns:
        QwenRunResult[str]: 包含输出结果的运行结果
    """
    # 模型为空时：doubao-seed-1-8-251228
    if model:
        return _qwen_core(input, messages_or_sys_prompt, _str_output_processor, client=client, model=model, **kwargs)
    else:
        return _qwen_core(input, messages_or_sys_prompt, _str_output_processor, client=client, model=model)



async def qwen_async(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[str]:
    """异步版本的基础Qwen调用函数。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        client: AsyncOpenAI客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 传递给API的其他参数
    
    Returns:
        QwenRunResult[str]: 包含输出结果的运行结果
    """
    return await _qwen_async_core(input, messages_or_sys_prompt, _str_output_processor, client=client, model=model, **kwargs)


@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避，等待时间1秒开始，最多10秒
    retry=retry_if_exception_type((
        APIConnectionError,  # 连接错误
        APIError,  # API错误
        RateLimitError,  # 速率限制错误
        Timeout,  # 超时错误
    ))
)
def qwen_stream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    delta: bool = True,
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResultStream:
    """
    流式输出。
    Args:
        input: 用户输入。
        messages_or_sys_prompt: 初次调用时为系统提示词(sys_prompt)，后续调用时为消息历史(message_history)。可以为字符串或消息列表。
        delta: 是否返回增量内容，默认为True。
        **kwargs: 其他参数将传递给Qwen API。

    Returns:
        QwenRunResultStream: 流式输出结果对象。
    """

    client, model = _parse_client_model(client, model, OpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)

    # 过滤掉不被OpenAI SDK支持的自定义参数
    api_kwargs = {}
    for key, value in kwargs.items():
        # 跳过自定义参数
        if key not in ["apply_chat_template", "enable_thinking"]:
            api_kwargs[key] = value

    return QwenRunResultStream(
        stream_response=client.chat.completions.create(
            model=model, messages=messages, stream=True, **api_kwargs
        ),
        delta=delta,
        messages=messages,
    )


@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避，等待时间1秒开始，最多10秒
    retry=retry_if_exception_type((
        APIConnectionError,  # 连接错误
        APIError,  # API错误
        RateLimitError,  # 速率限制错误
        Timeout,  # 超时错误
    ))
)
async def qwen_async_stream(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    delta: bool = True,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResultStreamAsync:
    """异步流式输出。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        delta: 是否返回增量内容，默认为True
        client: AsyncOpenAI客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 传递给API的其他参数
    
    Returns:
        QwenRunResultStreamAsync: 异步流式输出结果对象
    """

    client, model = _parse_client_model(client, model, AsyncOpenAI)

    messages = _compose_messages(input, messages_or_sys_prompt)

    # 过滤掉不被OpenAI SDK支持的自定义参数
    api_kwargs = {}
    for key, value in kwargs.items():
        # 跳过自定义参数
        if key not in ["apply_chat_template", "enable_thinking"]:
            api_kwargs[key] = value

    return QwenRunResultStreamAsync(
        stream_response=await client.chat.completions.create(
            model=model, messages=messages, stream=True, **api_kwargs
            ),
            delta=delta,
            messages=messages,
        )


def _create_schema_output_processor(output_type: Type[BaseModel]) -> Callable[[ChatCompletionMessage], BaseModel]:
    """创建基于 JSON Schema 的输出处理器"""
    def output_processor(response_msg: ChatCompletionMessage) -> BaseModel:
        assert response_msg.content is not None
        return output_type.model_validate_json(response_msg.content)
    return output_processor


def qwen_output[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    output_type: Type[T],
    strategy: Literal["auto", "schema", "tool_call"] = "auto",
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[T]:
    """
    结构化输出函数，支持 auto、schema 和 tool_call 三种策略。
    
    策略说明：
    - 'auto': 自动选择策略（默认）。当前实现选择 tool_call，未来可能基于模型能力、输出类型复杂度等智能选择
    - 'schema': 使用 JSON schema 方式，要求 output_type 必须是 BaseModel。优点：简单直接，兼容性好；缺点：依赖模型JSON生成能力
    - 'tool_call': 使用工具调用方式，支持任意类型 T。优点：更可靠的结构化输出，类型安全；缺点：需要模型支持工具调用
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: 输出类型
        strategy: 输出策略
            - 'auto': 自动选择（默认使用 tool_call）
            - 'schema': 使用 JSON schema，要求 output_type 必须是 BaseModel
            - 'tool_call': 使用工具调用，支持任意类型
        client: OpenAI 客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 其他参数
    
    Returns:
        QwenRunResult[T]: 包含输出结果的运行结果
    
    Raises:
        ValueError: 当 strategy='schema' 但 output_type 不是 BaseModel 时
        ValueError: 当 strategy 不是有效值时
    """
    assert output_type is not str, "output_type cannot be str in qwen_output"

    if strategy == "auto":
        # 最简单的实现：auto 时选择 tool_call
        strategy = "tool_call"
    
    if strategy == "schema":
        # 对于 schema 策略，output_type 必须是 BaseModel
        if not issubclass(output_type, BaseModel):
            raise ValueError(f"strategy='schema' requires output_type to be BaseModel, got {output_type}")
        return qwen_output_by_schema(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    elif strategy == "tool_call":
        # tool_call 策略支持任意类型 T，包括 BaseModel、基本类型、复杂类型等
        return qwen_output_by_tool(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}. Must be 'auto', 'schema' or 'tool_call'")


async def qwen_async_output[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    output_type: Type[T],
    strategy: Literal["auto", "schema", "tool_call"] = "auto",
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[T]:
    """
    异步版本的结构化输出函数，支持 auto、schema 和 tool_call 三种策略。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: 输出类型
        strategy: 输出策略
        client: AsyncOpenAI 客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 其他参数
    
    Returns:
        QwenRunResult[T]: 包含输出结果的运行结果
    """
    assert output_type is not str, "output_type cannot be str in qwen_async_output"

    if strategy == "auto":
        # 最简单的实现：auto 时选择 tool_call
        strategy = "tool_call"
    
    if strategy == "schema":
        # 对于 schema 策略，output_type 必须是 BaseModel
        if not issubclass(output_type, BaseModel):
            raise ValueError(f"strategy='schema' requires output_type to be BaseModel, got {output_type}")
        return await qwen_async_output_by_schema(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    elif strategy == "tool_call":
        return await qwen_async_output_by_tool(  # type: ignore
            input, messages_or_sys_prompt, output_type=output_type, client=client, model=model, **kwargs
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}. Must be 'auto', 'schema' or 'tool_call'")


def qwen_output_by_schema(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    output_type: Type[BaseModel],
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[BaseModel]:
    """基于JSON Schema的结构化输出。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: BaseModel类型
        client: OpenAI 客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 其他参数
    
    Returns:
        QwenRunResult[BaseModel]: 包含输出结果的运行结果
    """
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"
    
    if "json" not in input.lower():
        input = f"{input}\n请返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return _qwen_core(
        input,
        messages_or_sys_prompt,
        _create_schema_output_processor(output_type),
        client=client,
        model=model,
        response_format=response_format,
        **kwargs,
    )


async def qwen_async_output_by_schema(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    output_type: Type[BaseModel],
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[BaseModel]:
    """异步版本的基于JSON Schema的结构化输出。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: BaseModel类型
        client: AsyncOpenAI 客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 其他参数
    
    Returns:
        QwenRunResult[BaseModel]: 包含输出结果的运行结果
    """
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"
    
    if "json" not in input.lower():
        input = f"{input}\n请返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return await _qwen_async_core(
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
        raise e

    return output, messages


@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避，等待时间1秒开始，最多10秒
    retry=retry_if_exception_type((
        APIConnectionError,  # 连接错误
        APIError,  # API错误
        RateLimitError,  # 速率限制错误
        Timeout,  # 超时错误
    ))
)
def qwen_output_by_tool[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    output_type: Type[T],
    client: OpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[T]:
    '''
    使用tool call的方式实现结构化输出，支持本地模型和远程API。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: 输出类型
        client: OpenAI 客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 其他参数
    
    Returns:
        QwenRunResult[T]: 包含输出结果的运行结果
    '''
    # 判断是否使用本地模型
    # 本地模型判断条件：
    # 1. 没有提供客户端
    # 2. 模型名称以"/"或"Qwen/"开头（Hugging Face模型ID）
    # 3. 模型名称是本地文件路径
    
    if model:
        # 本地模型暂不支持tool call，降级为普通调用
        print("Warning: Local model does not support tool call, using regular output instead")
        return _qwen_core(
            input, messages_or_sys_prompt, _str_output_processor, 
            client=client, model=model, **kwargs
        )
    else:
        # 使用远程API
        client, model = _parse_client_model(client, model, OpenAI)

        # kwargs中不可以有tools和tool_choice。
        assert "tools" not in kwargs, "tools in kwargs is not allowed"
        assert "tool_choice" not in kwargs, "tool_choice in kwargs is not allowed"
        
        messages = _compose_messages(input, messages_or_sys_prompt)
        tool = create_type_tool(output_type)
        
        # 过滤掉不被OpenAI SDK支持的自定义参数
        api_kwargs = {}
        for key, value in kwargs.items():
            # 跳过自定义参数
            if key not in ["apply_chat_template", "enable_thinking"]:
                api_kwargs[key] = value
        
        response = client.chat.completions.create(
            model=model, 
            messages=messages, 
            tools = [tool.tool_param],
            tool_choice = {"type": "function", "function": {"name": tool.tool_param["function"]["name"]}}, # 强制要求调用tool。
            **api_kwargs)
        response_msg: ChatCompletionMessage = response.choices[0].message

        output, messages = _process_tool_response(response_msg, tool, messages, output_type)  # type: ignore

        return QwenRunResult(output=output, response=response_msg, messages=messages)  # type: ignore


@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避，等待时间1秒开始，最多10秒
    retry=retry_if_exception_type((
        APIConnectionError,  # 连接错误
        APIError,  # API错误
        RateLimitError,  # 速率限制错误
        Timeout,  # 超时错误
    ))
)
async def qwen_async_output_by_tool[T](
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    /,
    *, 
    output_type: Type[T],
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> QwenRunResult[T]:
    '''
    异步版本的使用tool call的方式实现结构化输出。
    
    Args:
        input: 用户输入
        messages_or_sys_prompt: 消息历史或系统提示词
        output_type: 输出类型
        client: AsyncOpenAI 客户端（兼容Qwen API）
        model: 模型名称，默认使用Qwen3-0.6B
        **kwargs: 其他参数
    
    Returns:
        QwenRunResult[T]: 包含输出结果的运行结果
    '''

    client, model = _parse_client_model(client, model, AsyncOpenAI)

    # kwargs中不可以有tools和tool_choice。
    assert "tools" not in kwargs, "tools in kwargs is not allowed"
    assert "tool_choice" not in kwargs, "tool_choice in kwargs is not allowed"
    
    messages = _compose_messages(input, messages_or_sys_prompt)
    tool = create_type_tool(output_type)

    # 过滤掉不被OpenAI SDK支持的自定义参数
    api_kwargs = {}
    for key, value in kwargs.items():
        # 跳过自定义参数
        if key not in ["apply_chat_template", "enable_thinking"]:
            api_kwargs[key] = value

    response = await client.chat.completions.create(
        model=model, 
        messages=messages, 
        tools=[tool.tool_param],
        tool_choice={"type": "function", "function": {"name": tool.tool_param["function"]["name"]}}, # 强制要求调用tool。
        **api_kwargs
    )
    response_msg: ChatCompletionMessage = response.choices[0].message

    output, messages = _process_tool_response(response_msg, tool, messages, output_type)  # type: ignore

    return QwenRunResult(output=output, response=response_msg, messages=messages)  # type: ignore
