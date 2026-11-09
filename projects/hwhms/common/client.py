import logging

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
_client: AsyncOpenAI | None = None

def get_openai_client(model_type: str = "doubao"):
    global _client
    if _client is None:
        if model_type == "doubao":
            _client = AsyncOpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                                    api_key="REDACTED",
                                    http_client=httpx.AsyncClient()
                                )
        elif model_type == "qianfan":
            _client = AsyncOpenAI(base_url="https://qianfan.baidubce.com/v2",
                                    api_key="REDACTED",
                                    http_client=httpx.AsyncClient()
                                )

    return _client
