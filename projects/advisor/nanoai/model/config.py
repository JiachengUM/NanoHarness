from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from openai import AsyncOpenAI, OpenAI
# 通过 pip install volcengine-python-sdk[ark] 安装方舟SDK
from volcenginesdkarkruntime import Ark, AsyncArk

__all__ = [
    "ModelName",
    "create_client",
]

class ModelName(StrEnum):
    DOUBAO_SEED_1_6_251015 = "doubao-seed-1-6-251015"
    DOUBAO_SEED_1_6_250615 = "doubao-seed-1-6-250615"
    '''
    https://www.volcengine.com/docs/82379/1593702
    效果: 5, 速度: 4
    全新多模态深度思考模型，同时支持 thinking、non-thinking、auto三种思考模式。其中 non-thinking 模型对比 doubao-1.5-pro-32k-250115 模型大幅提升。
    支持结构化输出，function call, response API
    '''
    
    DOUBAO_SEED_1_6_FLASH_250828 = "doubao-seed-1-6-flash-250828"
    DOUBAO_SEED_1_6_FLASH_250715 = "doubao-seed-1-6-flash-250715"
    DOUBAO_SEED_1_6_FLASH_250615 = "doubao-seed-1-6-flash-250615"
    '''
    https://www.volcengine.com/docs/82379/1593704
    效果: 4, 速度: 5
    有极致推理速度的多模态深度思考模型；同时支持文本和视觉理解。文本理解能力超过上一代 Lite 系列模型，视觉理解比肩友商 Pro 系列模型。
    支持结构化输出，function call, response API
    '''
    
    DOUBAO_SEED_1_6_THINKING_250715 = "doubao-seed-1-6-thinking-250715"
    DOUBAO_SEED_1_6_THINKING_250615 = "doubao-seed-1-6-thinking-250615"
    '''
    https://www.volcengine.com/docs/82379/1593703
    效果: 5, 速度: 4
    在思考能力上进行了大幅强化， 对比 doubao 1.5 代深度理解模型，在编程、数学、逻辑推理等基础能力上进一步提升， 支持视觉理解。
    支持结构化输出，function call, response API
    '''

    DOUBAO_SEED_1_6_VISION_250815 = "doubao-seed-1-6-vision-250815"
    '''
    https://www.volcengine.com/docs/82379/1799865
    效果: 5, 速度: 4
    适用于视频理解、Grounding、GUI Agent等高复杂度的场景，与Doubao-1.5-thinking-vision-pro相比，在教育、图像审核、巡检与安防和AI搜索问答等场景下展现出更强的通用多模态理解和推理能力，支持 256k 上下文窗口，输出长度支持最大 64k tokens。
    支持结构化输出，function call, response API, GUI 任务处理
    '''

    DOUBAO_1_5_UI_TARS_250428 = "doubao-1-5-ui-tars-250428"
    '''
    https://www.volcengine.com/docs/82379/1536429
    效果: 5, 速度: 4
    一款原生面向图形界面交互（GUI）的Agent模型。通过感知、推理和动作执行等类人的能力，与 GUI 进行连续、流程的交互。
与传统模块化框架不同，模型将所有核心能力（感知、推理、基础理解能力），统一集成在视觉大模型（VLM）中，实现无需预定义工作流程或人工规则的端到端任务自动化。
    支持GUI 任务处理。不支持结构化输出，function call, response API。
    '''


ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
ARK_API_KEY = "REDACTED"

@dataclass(frozen=True)
class _OpenAIConfig:
    base_url: str
    api_key: str
    model: str


@cache
def _get_model_config(model_name: ModelName) -> _OpenAIConfig:
    return _OpenAIConfig(
                base_url=ARK_BASE_URL,
                api_key=ARK_API_KEY,
                model=model_name.value
            )


@cache
def create_client[T: OpenAI | AsyncOpenAI | Ark | AsyncArk](
    model_name: ModelName,
    client_class: type[T],
) -> tuple[T, str]:
    """
    通用的客户端创建函数。
    
    Args:
        model_name: 模型名称
        client_class: 客户端类 (OpenAI 或 AsyncOpenAI 或 Ark 或 AsyncArk)    
    Returns:
        tuple[client, model_name]: 创建的客户端实例和模型名称
    """
    config = _get_model_config(model_name)
    # 火山API调用时URL需要添加自定义headers，否则无法调用
    headers = {}
    if "volces.com" in config.base_url or "ark.cn-beijing" in config.base_url:
        headers = {"Accept-Encoding": "identity"}

    if client_class in (Ark, AsyncArk):
        return client_class(
            base_url=config.base_url,
            api_key=config.api_key,
        ), config.model  # type: ignore
    else:
        assert client_class in (OpenAI, AsyncOpenAI), f"client_class must be OpenAI or AsyncOpenAI, but got {client_class}"
        
        return client_class(
            base_url=config.base_url,
            api_key=config.api_key,
            default_headers=headers,
            timeout=30.0  # 设置30秒超时时间
        ), config.model  # type: ignore
    