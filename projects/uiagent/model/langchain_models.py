from typing import Any
from langchain_openai import ChatOpenAI

from pydantic_models.uitars_pydantic_model import ModelSuccessResponse, ModelErrorResponse, ModelResponse, ResponseMetadata

def create_langchain_client(
    api_key: str = "REDACTED",
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    model: str = "doubao-1-5-ui-tars-250428",
    temperature: float = 0.0
) -> ChatOpenAI:
    """
    使用 langchain-openai 创建兼容火山引擎方舟的 ChatOpenAI 客户端
    
    Args:
        api_key: 方舟 API_KEY
        base_url: 方舟 API 地址
        model: 模型名称
        temperature: 温度参数
        
    Returns:
        ChatOpenAI 实例
    """
    return ChatOpenAI(
        openai_api_key=api_key,
        openai_api_base=base_url,
        model_name=model,
        temperature=temperature,
    )

def call_llm_langchain(client: ChatOpenAI,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    model: str = "doubao-1-5-ui-tars-250428") -> ModelSuccessResponse | ModelErrorResponse:
    """
    通过 langchain ChatOpenAI 调用大语言模型进行推理
    
    Args:
        client: langchain ChatOpenAI 实例
        model: 模型名称
        messages: 消息列表（兼容原格式）
        temperature: 温度参数，控制输出随机性
        
    Returns:
        ModelSuccessResponse对象或ModelErrorResponse对象
    """
    try:
        # 调用模型
        response = client.invoke(messages, temperature=temperature)
        # 提取 usage 信息（langchain 返回的 AIMessage 中可能包含 token_usage）
        usage = response.response_metadata.get("token_usage", {})
        total_tokens = usage.get("total_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return ModelSuccessResponse(
            content=response.content,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
            success=True
        )

    except Exception as e:
        return ModelErrorResponse(
            content=None,
            error=str(e),
            success=False,
            model=model
        )

async def acall_llm_langchain(
    client: ChatOpenAI,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    model: str = "doubao-1-5-ui-tars-250428"
) -> ModelSuccessResponse | ModelErrorResponse:
    """
    通过 langchain ChatOpenAI 调用大语言模型进行推理
    
    Args:
        client: langchain ChatOpenAI 实例
        model: 模型名称
        messages: 消息列表（兼容原格式）
        temperature: 温度参数，控制输出随机性
        
    Returns:
        ModelSuccessResponse对象或ModelErrorResponse对象
    """
    try:
        # 调用模型
        response = await client.ainvoke(messages, temperature=temperature)
        # 提取 usage 信息（langchain 返回的 AIMessage 中可能包含 token_usage）
        usage = response.response_metadata.get("token_usage", {})
        total_tokens = usage.get("total_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return ModelSuccessResponse(
            content=response.content,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
            success=True
        )

    except Exception as e:
        return ModelErrorResponse(
            content=None,
            error=str(e),
            success=False,
            model=model
        )