import os
from pathlib import Path
from typing import Any, Literal

from volcenginesdkarkruntime import Ark, AsyncArk

from pydantic_models.uitars_pydantic_model import (
    ModelErrorResponse,
    ModelResponse,
    ModelSuccessResponse,
    ResponseMetadata,
)
from utils.utils import encode_image

from .prompt import PHONE_USE_DOUBAO


def uitars_call(
    client: Ark,
    image: Any,
    query: str | None = None,
    image_type: str | None = None,
    custom_prompt: str | None = None,
    prompt_type: Literal["official", "custom_prompt"] = "official",
    language: str = "Chinese",
    model: str = "doubao-1-5-ui-tars-250428",
) -> ModelSuccessResponse | ModelErrorResponse:
    """
    模型调用函数

    Args:
        client: 火山引擎客户端实例
        image: 图片路径或Path对象
        query: 用户查询文本
        language: 回答语言
        model: 使用的模型名称

    Returns:
        ModelResponse对象, 包含分析结果
    """

    try:
        # 编码图片
        base64_image = encode_image(image)
        if isinstance(image, (str, Path)):
            image_path = Path(image)
            image_format = image_path.suffix[1:]  # 去掉点号
        else:
            image_format = image_type
        # 构建系统提示
        if prompt_type == "official":
            system_prompt = PHONE_USE_DOUBAO.format(instruction=query, language=language)
        elif prompt_type == "custom_prompt":
            if custom_prompt is None:
                raise ValueError(
                    "当 prompt_type 为 'custom_prompt' 时，custom_prompt 参数不能为 None"
                )
            system_prompt = custom_prompt
        else:
            raise ValueError("prompt_type 必须为 'official' 或 'custom_prompt'")
        messages = [
            {"role": "user", "content": f"{system_prompt}"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_format};base64,{base64_image}"
                        },
                    }
                ],
            },
        ]
        # 调用LLM
        response = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=messages,  # type: ignore
            stream=False,
        )
        return ModelResponse(
            success=True,
            content=response.choices[0].message.content,  # type: ignore
            error=None,
            metadata=ResponseMetadata(
                total_tokens=response.usage.total_tokens,  # type: ignore
                model=model,
                image_format=image_format,
            ),
        )

    except FileNotFoundError as e:
        # 图片文件不存在时直接抛出异常
        raise e
    except Exception as e:
        return ModelErrorResponse(
            content=None, error=str(e), success=False, model=model
        )


def create_client(api_key: str | None = None) -> Ark:
    """
    创建火山引擎客户端实例

    Args:
        api_key: 火山引擎API密钥，如果不提供则从环境变量ARK_API_KEY读取

    Returns:
        Ark客户端实例
    """
    if api_key is None:
        api_key = os.getenv("ARK_API_KEY", "REDACTED")

    return Ark(api_key=api_key)


def create_async_client(api_key: str | None = None) -> Ark:
    """
    创建火山引擎异步客户端实例

    Args:
        api_key: 火山引擎API密钥，如果不提供则从环境变量ARK_API_KEY读取

    Returns:
        Ark异步客户端实例
    """
    if api_key is None:
        api_key = os.getenv("ARK_API_KEY", "REDACTED")

    return AsyncArk(api_key=api_key)


async def a_uitars_call(
    client: AsyncArk,
    image: Any,
    query: str | None = None,
    image_type: str | None = None,
    custom_prompt: str | None = None,
    prompt_type: Literal["official", "custom_prompt"] = "official",
    language: str = "Chinese",
    model: str = "doubao-1-5-ui-tars-250428",
) -> ModelSuccessResponse | ModelErrorResponse:
    """
    模型调用函数

    Args:
        client: 火山引擎客户端实例
        image: 图片路径或Path对象
        query: 用户查询文本
        language: 回答语言
        model: 使用的模型名称

    Returns:
        ModelResponse对象, 包含分析结果
    """

    try:
        # 编码图片
        base64_image = encode_image(image)
        if isinstance(image, (str, Path)):
            image_path = Path(image)
            image_format = image_path.suffix[1:]  # 去掉点号
        else:
            image_format = image_type
        # 构建系统提示
        if prompt_type == "official":
            system_prompt = PHONE_USE_DOUBAO.format(instruction=query, language=language)
        elif prompt_type == "custom_prompt":
            if custom_prompt is None:
                raise ValueError(
                    "当 prompt_type 为 'custom_prompt' 时，custom_prompt 参数不能为 None"
                )
            system_prompt = custom_prompt
        else:
            raise ValueError("prompt_type 必须为 'official' 或 'custom_prompt'")
        messages = [
            {"role": "user", "content": f"{system_prompt}"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_format};base64,{base64_image}"
                        },
                    }
                ],
            },
        ]
        # 调用LLM
        response = await client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=messages,  # type: ignore
            stream=False,
        )
        return ModelResponse(
            success=True,
            content=response.choices[0].message.content,  # type: ignore
            error=None,
            metadata=ResponseMetadata(
                total_tokens=response.usage.total_tokens,  # type: ignore
                model=model,
                image_format=image_format,
            ),
        )

    except FileNotFoundError as e:
        # 图片文件不存在时直接抛出异常
        raise e
    except Exception as e:
        return ModelErrorResponse(
            content=None, error=str(e), success=False, model=model
        )


async def a_ark_llm_call(
    client: AsyncArk,
    messages: list[dict[str, str]],
    model: str = "doubao-1-5-ui-tars-250428",
) -> ModelSuccessResponse | ModelErrorResponse:
    """
    模型调用函数

    Args:
        client: 火山引擎异步客户端实例
        messages: 消息列表，每个消息是一个字典，包含 'role' 和 'content' 键
        model: 使用的模型名称

    Returns:
        ModelResponse对象, 包含分析结果
    """
    try:
        # 调用LLM
        response = await client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=messages,  # type: ignore
            stream=False,
        )
        return ModelResponse(
            success=True,
            content=response.choices[0].message.content,  # type: ignore
            error=None,
            metadata=ResponseMetadata(
                total_tokens=response.usage.total_tokens,  # type: ignore
                model=model,
            ),
        )
    except Exception as e:
        return ModelErrorResponse(
            content=None, error=str(e), success=False, model=model
        )
