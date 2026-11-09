from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport, SSEEvent

__all__ = ["IntentType", "call_fc"]

HOST = "http://101.126.11.190/sgm-volc-llm-agent-dev"
AK = "biekefd2ac80148034f53f7a46133330ca"
SK = "ssassasUpNAgVQyiGvqPaCfcpHmgWezppUvFOxdiQOCs"
TIMEOUT = 60.0
STREAM_PATH = "/dpfm/v1/agent/do/stream"


class IntentType(StrEnum):
    VEHICLE_CONTROL = "vehicle_control"
    MEDIA_CONTROL = "media"
    NAVIGATION = "navigation"


@dataclass(frozen=True, slots=True)
class FunctionCallRequest:
    """函数调用请求，包含查询内容、会话ID和意图类型"""
    query: str
    chat_id: str
    intent_type: IntentType

    def to_body(self) -> str:
        """序列化为紧凑JSON字符串，用于签名和发送"""
        payload = {
            "query": self.query,
            "chat_id": self.chat_id,
            "intent_type": self.intent_type.value,
            "role_id": "default",
            "intent_log_id": uuid.uuid4().hex,
            "history": [],
            "car_info": {},
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class SignedStreamRequest:
    """已签名的SSE流请求，包含URL、请求头和请求体"""
    url: str
    headers: dict[str, str]
    body: str


def _generate_signature(method: str, raw_query: str, body: str) -> str:
    """生成HMAC-SHA256签名：method + sorted_query + body_md5"""
    sorted_query = "&".join(sorted(raw_query.split("&"))) if raw_query else ""
    to_sign = f"{method}\n{sorted_query}\n"
    if body:
        body_md5 = hashlib.md5(body.encode("utf-8")).hexdigest()
        to_sign += f"{body_md5}\n"
    digest = hmac.new(SK.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _build_signed_stream_request(request: FunctionCallRequest) -> SignedStreamRequest:
    """构建带签名的SSE请求，包含timestamp/nonce防重放"""
    body = request.to_body()
    raw_query = f"_timestamp={int(time.time())}&_nonce={random.randint(0, 65535)}"
    signature = _generate_signature("POST", raw_query, body)
    return SignedStreamRequest(
        url=f"{HOST}{STREAM_PATH}?{raw_query}",
        headers={
            "Content-Type": "application/json",
            "X-Signature": f"{AK}:{signature}",
        },
        body=body,
    )


def _extract_observation(event: SSEEvent) -> str | None:
    """从SSE事件中提取observation字段，错误时抛异常，非attractions阶段返回None"""
    if not event.ok:
        raise RuntimeError(f"sse_error={event.error}: {event.detail or ''}")

    data = event.data or {}
    if error_code := int(data.get("error_code") or 0):
        raise RuntimeError(data.get("error_message") or f"error_code={error_code}")

    if data.get("stage") != "attractions":
        return None

    observation = data.get("observation")
    return observation if isinstance(observation, str) else json.dumps(observation, ensure_ascii=False) if observation else None


async def call_fc(query: str, chat_id: str, intent_type: IntentType) -> str:
    """调用SSE接口，返回observation结果或空字符串"""
    signed_request = _build_signed_stream_request(FunctionCallRequest(query=query, chat_id=chat_id, intent_type=intent_type))
    timeout = httpx.Timeout(TIMEOUT)

    async with httpx.AsyncClient(timeout=timeout) as raw_client:
        client = HttpClient(HttpxTransport(raw_client))
        async for event in client.fetch_sse(
            signed_request.url,
            headers=signed_request.headers,
            content_data=signed_request.body,
            timeout=timeout,
        ):
            observation = _extract_observation(event)
            if observation is not None:
                return observation

    return "" 
