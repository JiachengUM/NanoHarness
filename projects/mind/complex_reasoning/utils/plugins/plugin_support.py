"""火山插件调用支持：签名、请求头、SSE 拉流结果提取。"""
import base64
import hashlib
import hmac
import json
import logging
import uuid
import random
import asyncio
from typing import Any, Mapping

from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.complex_reasoning.configs.constants import VolcAPIEndpoint, VolcRequest, VolcSSEResponse
from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


def _gen_sign(sk: str, method: str, querystr: str, body: str | None) -> str:
    """按火山签名规则生成 base64(HMAC-SHA256)。"""
    strtosign = method + "\n" + querystr + "\n"
    if body:
        strtosign += hashlib.md5(body.encode("utf8")).hexdigest() + "\n"
    sig = hmac.new(sk.encode("utf8"), strtosign.encode("utf8"), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def _generate_signature(method: str, query_params: Mapping[str, Any], body: dict[str, Any] | None = None) -> str:
    """生成 X-Signature 头的值（AK:签名）。"""
    cfg = get_app_config()
    querystr = "&".join(f"{k}={v}" for k, v in sorted(query_params.items()))
    body_str = json.dumps(body) if body else None
    signature = _gen_sign(cfg.SK, method, querystr, body_str)
    return f"{cfg.AK}:{signature}"


def _prepare_headers(x_signature: str) -> dict[str, str]:
    """构造火山插件请求头。"""
    cfg = get_app_config()
    return {
        "Content-Type": "application/json",
        "X-Signature": x_signature,
        "X-Use-PPE": "1",
        "X-Tt-Env": cfg.PLUGIN_X_Tt_Env,
    }


async def _call_sse_api(
    api: VolcAPIEndpoint,
    body: dict[str, Any],
    volc_request: VolcRequest,
) -> str:
    """
    调用 SSE 接口并返回首个 observation。

    - SSE error event -> RuntimeError
    - 业务 error_code > 0 -> FcException
    - 无 observation -> ""
    """
    query_params = volc_request.to_dict()
    headers = _prepare_headers(_generate_signature(api.method, query_params, body))
    cfg = get_app_config()
    url = f"{cfg.VOLCANO_API_URL}{api.path}"
    try:
        client = await HttpClient.get_instance()
        async for event in client.fetch_sse(url, params=query_params, headers=headers, body=body):
            if not event.ok:
                detail = f": {event.detail}" if event.detail else ""
                raise RuntimeError(f"SSE错误 {event.error}{detail}")
            if not event.data:
                continue
            volc = VolcSSEResponse(**event.data)
            if volc.error_code > 0:
                raise FcException(volc.error_message or "unknown")
            if volc.observation:
                return volc.observation
        return ""
    except FcException:
        raise
    except Exception as e:
        logger.error("sse request failed: %s", e, exc_info=True)
        raise RuntimeError(f"API调用失败: {str(e)}") from e

async def get_question_id() -> str:
    """获取 question_id，用于火山插件调用."""
    cfg = get_app_config()
    # 构造请求体
    chat_id = uuid.uuid4().hex
    body = {
        "query": "打开车窗",
        "chat_id": chat_id,
        "plugin_name": "function_call",
        "channel": cfg.PLUGIN_CHANEL,
        "app_id": str(cfg.PLUGIN_APP_ID),
    }
    
    # 构建带签名参数的请求对象
    volc_request = VolcRequest.build(**body)
    
    # 准备请求头和签名
    query_params = volc_request.to_dict()
    signature = _generate_signature(
        VolcAPIEndpoint.CHAT_REJECTION.method, 
        query_params, 
        body
    )
    # 这是必要的！
    headers = _prepare_headers(signature)
    
    # 发送请求
    client = await HttpClient.get_instance()
    url = f"{cfg.VOLCANO_API_URL}{VolcAPIEndpoint.CHAT_REJECTION.path}"
    # 防止请求过于频繁
    num = random.randint(1, 5)
    await asyncio.sleep(0.1*num)
    response = await client.post(url, json_data=body, params=query_params, headers=headers)
    
    # 解析响应, 返回question_id
    result = response.json
    question_id = result.get("data").get("question_id")
    
    return question_id