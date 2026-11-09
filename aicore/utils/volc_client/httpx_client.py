"""
异步 HTTP 客户端（httpx 版本）。

分层约定：
1) `HttpxTransport`：最薄的一层，只做“发请求/读流”，不承载业务语义
2) `HttpClient`：对外 API 层，定义 GET/POST/SSE 的返回契约与错误语义

说明：
- FastAPI 的 startup/shutdown 中创建/关闭一个 AsyncClient(asynccontextmanager), 然后注入到 HttpxTransport 
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

Method = Literal["GET", "POST"]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """
    普通 HTTP 请求的强类型响应。
    JSON 响应：HttpResponse(status=200, headers={"Content-Type": "application/json"}, json={"code": 0}, text=None)
    文本响应：HttpResponse(status=200, headers={"Content-Type": "text/plain"}, json=None, text="hello")
    """
    status: int
    headers: Mapping[str, str]
    json: Optional[Any] = None
    text: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """
    SSE 每条事件的强类型表示。
    正常事件：SSEEvent(data={"error_code": 0, "observation": "..."})
    错误事件：SSEEvent(error="http_status_403", detail="status=403")
    """
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    detail: Optional[str] = None
    raw: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class HttpxTransport:
    """
    Transport 层：只负责 I/O。

    设计目标：
    - 保持无状态、低复杂度，便于替换
    - 不做业务判断（例如 SSE payload 是否合法、是否要抛业务异常）
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        content_data: Optional[str | bytes] = None,
        timeout: Optional[httpx.Timeout] = None,
        raise_for_status: bool = True,
    ) -> HttpResponse:
        """
        发一个普通 HTTP 请求并把响应解析成 HttpResponse。
        统一只暴露 json/text 两种响应体形态，避免业务层重复写 Content-Type 判断。
        """
        # V4 签名场景下必须保证“签名体 == 实际发送体”，因此支持显式 content 透传。
        # 本来我就这么写的，会报错
        # resp = await self._client.request(
        #     method,
        #     url,
        #     params=params,
        #     headers=headers,
        #     json=json_data,
        #     timeout=timeout,
        # )
        # TODO: 这里需要修改，让content_data能够正常传递。
        req_kwargs: dict[str, Any] = {
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }
        if content_data is not None:
            req_kwargs["content"] = content_data
        else:
            req_kwargs["json"] = json_data

        resp = await self._client.request(method, url, **req_kwargs)

        if raise_for_status:
            resp.raise_for_status()

        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct:
            return HttpResponse(status=resp.status_code, headers=resp.headers, json=resp.json())
        return HttpResponse(status=resp.status_code, headers=resp.headers, text=resp.text)

    async def stream_lines(
        self,
        method: Method,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        content_data: Optional[str | bytes] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> AsyncGenerator[tuple[int, Mapping[str, str], str], None]:
        """
        以“逐行”的方式读取响应体，适用于 SSE 流式协议。

        返回：
        - status: HTTP 状态码
        - resp_headers: 响应 headers
        - line: 解码后的文本行（httpx 已处理换行）
        """
        req_kwargs: dict[str, Any] = {
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }
        if content_data is not None:
            req_kwargs["content"] = content_data
        else:
            req_kwargs["json"] = json_data

        async with self._client.stream(method, url, **req_kwargs) as resp:
            status = resp.status_code
            resp_headers = resp.headers

            async for line in resp.aiter_lines():
                yield status, resp_headers, line


class HttpClient:
    """
    Client 层：定义对上游调用方可见的语义。

    约定：
    - `get/post` 失败直接抛异常（fail-fast）
    - `fetch_sse` 失败以 `SSEEvent(error=...)` 的形式返回（不中断 `async for`）
    """

    def __init__(self, transport: HttpxTransport) -> None:
        self._transport = transport

    async def get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> HttpResponse:
        try:
            return await self._transport.request(
                "GET",
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPStatusError as e:
            logger.error("GET %s failed: status=%s", url, e.response.status_code)
            raise
        except httpx.TimeoutException as e:
            logger.error("GET %s timeout: %r", url, e)
            raise
        except httpx.HTTPError as e:
            logger.error("GET %s http error: %r", url, e)
            raise

    async def post(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        content_data: Optional[str | bytes] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> HttpResponse:
        try:
            return await self._transport.request(
                "POST",
                url,
                params=params,
                headers=headers,
                json_data=json_data,
                content_data=content_data,
                timeout=timeout,
            )
        except httpx.HTTPStatusError as e:
            logger.error("POST %s failed: status=%s", url, e.response.status_code)
            raise
        except httpx.TimeoutException as e:
            logger.error("POST %s timeout: %r", url, e)
            raise
        except httpx.HTTPError as e:
            logger.error("POST %s http error: %r", url, e)
            raise

    async def fetch_sse(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: dict[str, str],
        body: Optional[dict[str, Any]] = None,
        content_data: Optional[str | bytes] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        按 SSE 协议读取并解析事件。

        简化版协议处理规则：
        - 仅消费 `data:` 行
        - 空行视为一个 event 边界
        - 多个 `data:` 行会拼接后统一做 JSON 解析
        - 首次收到行时检查 HTTP status，非 200 直接返回错误事件
        """
        data_lines: list[str] = []
        saw_first = False

        try:
            async for status, _, line in self._transport.stream_lines(
                "POST",
                url,
                params=params,
                headers=headers,
                json_data=body,
                content_data=content_data,
                timeout=timeout,
            ):
                if not saw_first:
                    saw_first = True
                    if status != 200:
                        yield SSEEvent(error=f"http_status_{status}", detail=f"status={status}")
                        return

                if line == "":
                    if data_lines:
                        payload = "\n".join(data_lines).strip()
                        data_lines.clear()
                        if payload:
                            yield self._parse_sse_payload(payload)
                    continue

                # SSE 注释行，忽略
                if line.startswith(":"):
                    continue

                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())

            # 流结束时，如果最后一个 event 没有以空行结尾，这里补一次 flush
            if data_lines:
                payload = "\n".join(data_lines).strip()
                if payload:
                    yield self._parse_sse_payload(payload)

        except httpx.TimeoutException as e:
            logger.error("SSE %s timeout: %r", url, e)
            yield SSEEvent(error="timeout", detail=str(e))
        except httpx.HTTPError as e:
            logger.error("SSE %s http error: %r", url, e)
            yield SSEEvent(error="client_error", detail=repr(e))
        except Exception as e:
            logger.error("SSE %s unexpected error: %r", url, e, exc_info=True)
            yield SSEEvent(error="unexpected_error", detail=repr(e))

    @staticmethod
    def _parse_sse_payload(payload: str) -> SSEEvent:
        """
        单条 payload 解析失败不抛异常，转换为 error event 交给上层决定策略。
        """
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                return SSEEvent(data=obj)
            return SSEEvent(
                error="invalid_payload_type",
                detail=f"expected dict, got {type(obj).__name__}",
                raw=payload,
            )
        except (json.JSONDecodeError, ValueError) as e:
            return SSEEvent(error="invalid_json", detail=str(e), raw=payload)
