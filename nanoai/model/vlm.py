from typing import Final, Sequence, Callable, Type
from pathlib import Path
import base64

from pydantic import BaseModel

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionContentPartImageParam,
)
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema


from nanoai.model.config import ModelName, create_client
from nanoai.model.llm import RunResultStreamAsync

__all__ = [
    "avlm",
    "avlm_stream",
    "avlm_output_by_schema",
]

def image_from_path(image_path: str) -> tuple[str, str]:
    """读入图片文件, 返回 (base64编码的图像数据base64_image, 图像格式image_format)"""

    path = Path(image_path)
    image_format = path.suffix[1:]  # 去掉点号
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    
    # 检查文件扩展名
    valid_extensions = {'png', 'jpg', 'jpeg'}
    if image_format.lower() not in valid_extensions:
        raise ValueError(f"不支持的图片格式: {image_format}")
    
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8'), image_format


def _compose_messages(input: str, base64_image: str, image_format: str) -> Sequence[ChatCompletionMessageParam]:
    image_param = ChatCompletionContentPartImageParam(type="image_url", 
                    image_url={"url": f"data:image/{image_format};base64,{base64_image}"})

    messages = [
        ChatCompletionUserMessageParam(role="user", content=input),
        ChatCompletionUserMessageParam(role="user", content=[image_param])
        ]

    return messages


DEFAULT_SYS_PROMPT: Final[str] = "你是一个有用的助手"

async def _avlm_core[T](
    input: str,
    base64_image: str,
    image_format: str,
    output_processor: Callable[[ChatCompletionMessage], T],
    messages: list[ChatCompletionMessageParam] | None = None,
    /,
    *,
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> T:
    if messages:
        the_input_messages = messages.extend(_compose_messages(input, base64_image, image_format))
    else:
        the_input_messages = _compose_messages(input, base64_image, image_format)
    
    response = await client.chat.completions.create(
        model=model,
        messages=the_input_messages, # type: ignore
        stream=False,
        **kwargs
    )

    response_msg: ChatCompletionMessage = response.choices[0].message
    
    output = output_processor(response_msg)
    
    # 更新消息历史
    # messages.append({"role": "assistant", "content": response_msg.content})
    
    return output

def _str_output_processor(response_msg: ChatCompletionMessage) -> str:
    """字符串输出处理器"""
    assert response_msg.content is not None
    return response_msg.content

async def avlm(
    input: str,
    base64_image: str,
    image_format: str,
    messages: list[ChatCompletionMessageParam] | None = None,
    /,
    *,
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> str:
    """基础VLM调用函数。"""
    return await _avlm_core(input, base64_image, image_format, _str_output_processor, messages, client=client, model=model, **kwargs)


def _create_schema_output_processor(output_type: Type[BaseModel]) -> Callable[[ChatCompletionMessage], BaseModel]:
    """创建基于 JSON Schema 的输出处理器"""
    def output_processor(response_msg: ChatCompletionMessage) -> BaseModel:
        assert response_msg.content is not None
        return output_type.model_validate_json(response_msg.content)

    return output_processor


async def avlm_output_by_schema[T](
    input: str,
    base64_image: str,
    image_format: str,
    messages: list[ChatCompletionMessageParam] | None = None,
    /,
    *,
    output_type: Type[T],
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> T:
    """基于JSON Schema的结构化输出。"""
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"
    
    if "json" not in input.lower():
        input = f"{input}\n请返回JSON格式的字符串。不要包括任何其它文字。"

    response_format = ResponseFormatJSONSchema(
        type="json_schema", 
        json_schema={"name": "response", "schema": output_type.model_json_schema(), "strict": True})
    
    return await _avlm_core(
        input,
        base64_image,
        image_format,
        _create_schema_output_processor(output_type),
        messages,
        client=client,
        model=model,
        response_format=response_format,
        **kwargs,
    ) # type: ignore


async def avlm_stream(
    input: str,
    base64_image: str,
    image_format: str,
    messages: list[ChatCompletionMessageParam] | None = None,
    /,
    *,
    delta: bool = True,
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> RunResultStreamAsync:
    """基础VLM调用函数（流式）。"""
    if messages:
        the_input_messages = messages.extend(_compose_messages(input, base64_image, image_format))
    else:
        the_input_messages = _compose_messages(input, base64_image, image_format)
    
    return RunResultStreamAsync(
        stream_response=await client.chat.completions.create(
            model=model, messages=the_input_messages, stream=True, **kwargs
            ),
            delta=delta,
            messages=the_input_messages,
        )