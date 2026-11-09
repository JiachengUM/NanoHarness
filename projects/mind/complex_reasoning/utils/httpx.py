from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Mapping, Optional
from weakref import WeakKeyDictionary

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from projects.mind.complex_reasoning.configs.config import get_app_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    json: Optional[Any] = None
    text: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SSEEvent:
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    detail: Optional[str] = None
    raw: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class SharedAsyncHttpxClientFactory:
    """
    提供给第三方 SDK（如 AsyncArk）复用的原生 httpx.AsyncClient。

    说明：
    - 按 event loop 维护一个共享 client，避免跨 loop 复用
    - 返回的是“原生 httpx.AsyncClient”，便于直接注入 SDK 的 `http_client=` 参数
    - 生命周期由本 factory 管理；调用方不应随意关闭返回的 client
    """

    _clients: "WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = WeakKeyDictionary()

    @classmethod
    def get_client_for_current_loop(cls) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        client = cls._clients.get(loop)
        if client is not None and not client.is_closed:
            return client

        cfg = get_app_config()
        limits = httpx.Limits(
            max_connections=cfg.MAX_CONCURRENT_REQUESTS,
            max_keepalive_connections=getattr(cfg, "MAX_KEEPALIVE_CONNECTIONS", None) or cfg.MAX_CONCURRENT_REQUESTS,
            keepalive_expiry=cfg.KEEP_ALIVE_TIMEOUT,
        )
        timeout = httpx.Timeout(
            timeout=cfg.RESPONSE_TIMEOUT,
            connect=getattr(cfg, "CONNECT_TIMEOUT", None),
            read=getattr(cfg, "READ_TIMEOUT", None),
            write=getattr(cfg, "WRITE_TIMEOUT", None),
            pool=getattr(cfg, "POOL_TIMEOUT", None),
        )
        client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            http2=getattr(cfg, "HTTP2", False),
            headers=getattr(cfg, "DEFAULT_HEADERS", None),
        )
        cls._clients[loop] = client
        return client

    @classmethod
    async def close_for_current_loop(cls) -> None:
        loop = asyncio.get_running_loop()
        client = cls._clients.pop(loop, None)
        if client is not None and not client.is_closed:
            await client.aclose()


class HttpClient:
    _instances: "WeakKeyDictionary[asyncio.AbstractEventLoop, HttpClient]" = WeakKeyDictionary()
    _init_locks: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = WeakKeyDictionary()

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sem: Optional[asyncio.Semaphore] = None

    async def initialize(self) -> None:
        cfg = get_app_config()
        self._loop = asyncio.get_running_loop()

        await self.close()

        # httpx 连接池/keepalive 上限：Limits（这和 aiohttp 的 connector limit 类似但不完全等价）
        limits = httpx.Limits(
            max_connections=cfg.MAX_CONCURRENT_REQUESTS,
            max_keepalive_connections=getattr(cfg, "MAX_KEEPALIVE_CONNECTIONS", None) or cfg.MAX_CONCURRENT_REQUESTS,
            keepalive_expiry=cfg.KEEP_ALIVE_TIMEOUT,
        )  # :contentReference[oaicite:5]{index=5}

        # 默认 timeout：普通请求可以 total；SSE 常用 timeout=None 或 sock_read 更长
        timeout = httpx.Timeout(
            timeout=cfg.RESPONSE_TIMEOUT,  # total
            connect=getattr(cfg, "CONNECT_TIMEOUT", None),
            read=getattr(cfg, "READ_TIMEOUT", None),
            write=getattr(cfg, "WRITE_TIMEOUT", None),
            pool=getattr(cfg, "POOL_TIMEOUT", None),
        )

        self._sem = asyncio.Semaphore(cfg.MAX_CONCURRENT_REQUESTS)

        self._client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            http2=getattr(cfg, "HTTP2", False),
            headers=getattr(cfg, "DEFAULT_HEADERS", None),
        )  # :contentReference[oaicite:6]{index=6}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None
        self._sem = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HttpClient is not initialized or already closed")
        return self._client

    @staticmethod
    def _parse_json_payload(payload: str) -> SSEEvent:
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                return SSEEvent(data=obj)
            return SSEEvent(error="invalid_payload_type", detail=f"expected dict, got {type(obj).__name__}", raw=payload)
        except Exception as e:
            return SSEEvent(error="invalid_json", detail=str(e), raw=payload)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        timeout: Optional[httpx.Timeout] = None,
        max_retries: int = 0,
    ) -> HttpResponse:
        client = self._ensure_client()
        if self._sem is None:
            raise RuntimeError("HttpClient semaphore not initialized")

        # httpx 自己在 transport 层支持“连接类错误”的重试（ConnectError/ConnectTimeout 等），
        # 但对 429/5xx 这类业务重试通常建议用 tenacity 来做更灵活的策略。:contentReference[oaicite:7]{index=7}
        async def do_once() -> httpx.Response:
            async with self._sem:
                return await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_data,
                    timeout=timeout,
                )

        # 只做最常见的“瞬态错误”重试：网络层异常、超时、以及你愿意的话加 429/5xx
        retryable_excs = (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout, httpx.TimeoutException)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential_jitter(initial=0.2, max=2.0),
            retry=retry_if_exception_type(retryable_excs),
            reraise=True,
        ):
            with attempt:
                resp = await do_once()

                # 业务级重试：按需启用（示例：429/5xx）
                if resp.status_code in {429, 500, 502, 503, 504} and attempt.retry_state.attempt_number <= max_retries:
                    # 读掉响应体，便于连接复用
                    _ = resp.content
                    raise httpx.HTTPStatusError(
                        message=f"retryable_status_{resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                resp.raise_for_status()

                # 更稳：先尝试 json，再回退 text
                try:
                    parsed = resp.json()
                    return HttpResponse(status=resp.status_code, headers=resp.headers, json=parsed)
                except Exception:
                    return HttpResponse(status=resp.status_code, headers=resp.headers, text=resp.text)

        raise AssertionError("unreachable")

    async def post(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        timeout: Optional[httpx.Timeout] = None,
        max_retries: int = 0,
    ) -> HttpResponse:
        return await self._request(
            "POST",
            url,
            params=params,
            headers=headers,
            json_data=json_data,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[httpx.Timeout] = None,
        max_retries: int = 0,
    ) -> HttpResponse:
        return await self._request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def fetch_sse(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        body: Optional[dict[str, Any]] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        client = self._ensure_client()
        if self._sem is None:
            raise RuntimeError("HttpClient semaphore not initialized")

        # SSE 常见：timeout=None（否则 read timeout 会把长连接干掉）
        # 你也可以只把 read 设很大：httpx.Timeout(None) 或 read=...
        try:
            try:
                from httpx_sse import aconnect_sse  # type: ignore
            except ImportError as e:
                yield SSEEvent(error="missing_dependency", detail=f"httpx_sse not installed: {e}")
                return

            async with self._sem:
                async with aconnect_sse(
                    client,
                    method="POST",
                    url=url,
                    params=params,
                    headers=headers,
                    json=body,
                    timeout=timeout,
                ) as event_source:
                    async for sse in event_source.aiter_sse():
                        # sse.data 是文本（SSE 标准就是文本），你要 json 就自己 loads
                        payload = (sse.data or "").strip()
                        if not payload:
                            continue
                        yield self._parse_json_payload(payload)

        except httpx.TimeoutException as e:
            logger.error("SSE %s timeout: %r", url, e)
            yield SSEEvent(error="timeout", detail=str(e))
        except httpx.HTTPError as e:
            logger.error("SSE %s http error: %r", url, e)
            yield SSEEvent(error="http_error", detail=repr(e))
        except Exception as e:
            logger.error("SSE %s unexpected error: %r", url, e, exc_info=True)
            yield SSEEvent(error="unexpected_error", detail=repr(e))

    @classmethod
    async def get_instance(cls) -> "HttpClient":
        loop = asyncio.get_running_loop()

        inst = cls._instances.get(loop)
        if inst is not None:
            return inst

        lock = cls._init_locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            cls._init_locks[loop] = lock

        async with lock:
            inst = cls._instances.get(loop)
            if inst is None:
                inst = cls()
                await inst.initialize()
                cls._instances[loop] = inst
            return inst

    @classmethod
    async def close_for_current_loop(cls) -> None:
        loop = asyncio.get_running_loop()
        inst = cls._instances.pop(loop, None)
        if inst is not None:
            await inst.close()
