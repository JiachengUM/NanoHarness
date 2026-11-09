import base64
from pathlib import Path
from typing import Final, Sequence, Callable, Type

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionContentPartImageParam,
)
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema
from pydantic import BaseModel

from nanoai.model.config import ModelName
from nanoai.model.llm import RunResultStreamAsync

__all__ = [
    "avlm",
    "avlm_stream",
    "avlm_output_by_schema",
]

def image_from_path(image_path: str) -> tuple[str, str]:
    """将图片文件编码为Base64字符串，并返回图片格式"""

    path = Path(image_path)
    image_format = path.suffix[1:]  # 去掉点号
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    
    # 检查文件扩展名
    valid_extensions = {'png', 'jpg', 'jpeg'}
    if image_format.lower() not in valid_extensions:
        raise ValueError(f"不支持的图片格式: {image_format}")
    # print(f"图片路径格式: {image_format}")
    # from PIL import Image
    # with Image.open(path) as img:
    #     print(f"真实格式: {img.format}")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8'), image_format


def _compose_messages(input: str, image_path: str) -> Sequence[ChatCompletionMessageParam]:
    base64_image, image_format = image_from_path(image_path)

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
    image_path: str,
    output_processor: Callable[[ChatCompletionMessage], T],
    messages_or_sys_prompt: str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> T:

    messages = _compose_messages(input, image_path)
    
    response = await client.chat.completions.create(
        model=model,
        messages=messages, # type: ignore
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
    image_path: str,
    messages_or_sys_prompt: str = DEFAULT_SYS_PROMPT,
    /,
    *,
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> str:
    """基础VLM调用函数。"""
    return await _avlm_core(input, image_path, _str_output_processor, messages_or_sys_prompt, client=client, model=model, **kwargs)


def _create_schema_output_processor(output_type: Type[BaseModel]) -> Callable[[ChatCompletionMessage], BaseModel]:
    """创建基于 JSON Schema 的输出处理器"""
    def output_processor(response_msg: ChatCompletionMessage) -> BaseModel:
        assert response_msg.content is not None
        return output_type.model_validate_json(response_msg.content)

    return output_processor


async def avlm_output_by_schema[T](
    input: str,
    image_path: str,
    messages_or_sys_prompt: str = DEFAULT_SYS_PROMPT,
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
        image_path,
        _create_schema_output_processor(output_type),
        messages_or_sys_prompt,
        client=client,
        model=model,
        response_format=response_format,
        **kwargs,
    ) # type: ignore


async def avlm_stream(
    input: str,
    image_path: str,
    messages_or_sys_prompt: str = DEFAULT_SYS_PROMPT,
    /,
    *,
    delta: bool = True,
    client: AsyncOpenAI,
    model: ModelName | str,
    **kwargs,
) -> RunResultStreamAsync:

    messages = _compose_messages(input, image_path)
    
    return RunResultStreamAsync(
        stream_response=await client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
            ),
            delta=delta,
            messages=messages,
        )