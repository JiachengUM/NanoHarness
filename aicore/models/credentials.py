from functools import cache

# 通过 pip install volcengine-python-sdk[ark] 安装方舟SDK
from volcenginesdkarkruntime import Ark, AsyncArk

from aicore.models.doubao_models import ModelName

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# ARK_API_KEY = "REDACTED"
ARK_API_KEY = "REDACTED"
ARK_API_KEY_FOR_1_8 = "REDACTED"


@cache
def create_client[T: Ark | AsyncArk](model_name: ModelName, client_class: type[T]) -> tuple[T, str]:
    """
    通用的客户端创建函数。
    
    Args:
        model_name: 模型名称
        client_class: 客户端类 (OpenAI 或 AsyncOpenAI 或 Ark 或 AsyncArk)    
    Returns:
        tuple[client, model_name]: 创建的客户端实例和模型名称
    """

    assert isinstance(model_name, ModelName), f"model_name must be ModelName, but got type {type(model_name)}"

    return client_class(base_url=ARK_BASE_URL, api_key=ARK_API_KEY,), model_name.value


# TODO: 用于取代 create_client 函数，但get_client这个名字有待商榷。
def get_client[T: Ark | AsyncArk](client_class: type[T]) -> T:
    return client_class(base_url=ARK_BASE_URL, api_key=ARK_API_KEY)