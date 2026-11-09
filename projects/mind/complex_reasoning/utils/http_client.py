"""
异步 HTTP 客户端（aiohttp 版本）。

分层约定：
1) `AiohttpTransport`：最薄的一层，只做“发请求/读流”，不承载业务语义
2) `HttpClient`：对外 API 层，定义 GET/POST/SSE 的返回契约与错误语义
3) `HttpClientFactory`：生命周期层，按 event loop 缓存 client/session，避免跨 loop 复用

为什么要按 loop 缓存：
- aiohttp.ClientSession/TCPConnector 绑定创建它们的事件循环
- 跨 loop 复用会触发 `attached to a different loop` / `Event loop is closed`
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Mapping, Optional
from weakref import WeakKeyDictionary

import aiohttp
from aiohttp import ClientError, ClientResponseError

from projects.mind.complex_reasoning.configs.config import get_app_config

logger = logging.getLogger(__name__)

Method = Literal["GET", "POST"]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """
    普通 HTTP 请求的强类型响应。
    JSON 响应：HttpResponse(status=200, headers={"Content-Type": "application/json"}, json={"code": 0, "msg": "ok"}, text=None)
    文本响应：HttpResponse(status=200, headers={"Content-Type": "text/plain"}, json=None, text="hello world")
    """
    status: int
    headers: Mapping[str, str]
    json: Optional[Any] = None
    text: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """
    SSE 每条事件的强类型表示。
    正常事件：SSEEvent(data={"error_code": 0, "observation": "{\"action\":\"play\"}"}) # ok == True
    错误事件：SSEEvent(error="http_status_403", detail="status=403") # ok == False
    """
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    detail: Optional[str] = None
    raw: Optional[str] = None

    @property
    def ok(self) -> bool:
        """调用方可以用 event.ok 快速判断这条事件是不是成功数据。"""
        return self.error is None


class AiohttpTransport:
    """
    Transport 层：只负责 I/O。

    设计目标：
    - 保持无状态、低复杂度，便于被替换（例如未来换成 httpx transport）
    - 不做业务判断（例如 SSE payload 是否合法、是否要抛业务异常）
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        raise_for_status: bool = True,
    ) -> HttpResponse:
        """发一个普通 HTTP 请求并把响应解析成 HttpResponse.这里统一把“HTTP 响应体解析”做成 Json/Text 两种，业务层无需重复写 Content-Type 分支。"""
        async with self._session.request(method, url, params=params, headers=headers, json=json_data, timeout=timeout) as resp:
            if raise_for_status: # 是否对非 2xx/3xx 调用 resp.raise_for_status()
                resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                return HttpResponse(status=resp.status, headers=resp.headers, json=await resp.json())
            else:
                return HttpResponse(status=resp.status, headers=resp.headers, text=await resp.text())

    async def stream_lines(
        self,
        method: Method,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> AsyncGenerator[tuple[int, Mapping[str, str], str], None]:
        """以“逐行”的方式读取响应体，适用于 SSE 流式协议。没有 raise_for_status，因为SSE/流式通常希望自己处理非200的情况。
        status: HTTP 状态码
        resp_headers: 响应 headers
        line: 解码后的文本行（去掉 \r\n）
        """
        async with self._session.request(method, url, params=params, headers=headers, json=json_data, timeout=timeout) as resp:
            status = resp.status
            resp_headers = resp.headers
            while True:
                raw = await resp.content.readline()
                if not raw:
                    return
                yield status, resp_headers, raw.decode("utf-8", errors="replace").rstrip("\r\n")


class HttpClient:
    """
    Client 层：定义对上游调用方可见的语义。

    约定：
    - `get/post` 失败直接抛异常（fail-fast）
    - `fetch_sse` 失败以 `SSEEvent(error=...)` 的形式返回（不中断 `async for`）
    """

    def __init__(self, transport: AiohttpTransport) -> None:
        self._transport = transport

    async def get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> HttpResponse:
        try:
            return await self._transport.request("GET", url, params=params, headers=headers, timeout=timeout)
        except ClientResponseError as e:
            logger.error("GET %s failed: status=%s msg=%s", url, e.status, e.message)
            raise
        except ClientError as e:
            logger.error("GET %s client error: %r", url, e)
            raise
        except asyncio.TimeoutError:
            logger.error("GET %s timeout", url)
            raise

    async def post(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> HttpResponse:
        try:
            return await self._transport.request("POST", url, params=params, headers=headers, json_data=json_data, timeout=timeout)
        except ClientResponseError as e:
            logger.error("POST %s failed: status=%s msg=%s", url, e.status, e.message)
            raise
        except ClientError as e:
            logger.error("POST %s client error: %r", url, e)
            raise
        except asyncio.TimeoutError:
            logger.error("POST %s timeout", url)
            raise

    async def fetch_sse(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        body: Optional[dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
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
            async for status, _, line in self._transport.stream_lines("POST", url, params=params, headers=headers, json_data=body, timeout=timeout):
                if not saw_first:
                    saw_first = True
                    if status != 200: #先看 status 再继续, SSE 建链失败不会让上游 async for 直接异常中断，而是“收到一条错误事件”
                        yield SSEEvent(error=f"http_status_{status}", detail=f"status={status}")
                        return

                if line == "": 
                    if data_lines:
                        payload = "\n".join(data_lines).strip()
                        data_lines.clear()
                        if payload:
                            yield self._parse_sse_payload(payload)
                    continue

                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())

            if data_lines:
                payload = "\n".join(data_lines).strip()
                if payload:
                    yield self._parse_sse_payload(payload)

        except asyncio.TimeoutError as e:
            logger.error("SSE %s timeout: %r", url, e)
            yield SSEEvent(error="timeout", detail=str(e))
        except ClientError as e:
            logger.error("SSE %s client error: %r", url, e)
            yield SSEEvent(error="client_error", detail=repr(e))
        except Exception as e:
            logger.error("SSE %s unexpected error: %r", url, e, exc_info=True)
            yield SSEEvent(error="unexpected_error", detail=repr(e))

    @staticmethod
    def _parse_sse_payload(payload: str) -> SSEEvent:
        # 单条 payload 解析失败不抛异常，转换为 error event 交给上层决定策略。
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

    @classmethod
    async def get_instance(cls) -> "HttpClient":
        return await HttpClientFactory.get_client()

    @classmethod
    async def close_for_current_loop(cls) -> None:
        await HttpClientFactory.close_for_current_loop()


class HttpClientFactory:
    """
    Factory 层：按事件循环维护 HttpClient 单例生命周期。

    细节：
    - `_instances`: loop -> HttpClient
    - `_sessions`:  loop -> ClientSession（便于显式 close）
    - `_init_locks`: loop 级初始化锁，避免并发首次调用重复创建 session
    """
    # 仿照aiohttp/resolver.py都用 WeakKeyDictionary：当 loop 被销毁时，key 自动消失，减少测试/多 loop 场景内存泄漏风险。
    _instances: "WeakKeyDictionary[asyncio.AbstractEventLoop, HttpClient]" = WeakKeyDictionary()
    _init_locks: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = WeakKeyDictionary()
    _sessions: "WeakKeyDictionary[asyncio.AbstractEventLoop, aiohttp.ClientSession]" = WeakKeyDictionary()

    @classmethod
    async def get_client(cls) -> HttpClient:
        """获取“当前 running event loop”下的 HttpClient 单例。"""
        # 1) 定位当前协程正在运行的事件循环（注意：不是 get_event_loop；必须在 async 上下文中）
        loop = asyncio.get_running_loop()

        # 2) 快路径：这个 loop 已经创建过 client，直接复用（避免每次都走锁/创建连接池）
        existing = cls._instances.get(loop)
        if existing is not None:
            return existing

        # 3) 为每个 loop 准备一把初始化锁：多个协程可能同时第一次调用 get_client()，需要串行化“创建 session/connector”这段临界区。
        lock = cls._init_locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            cls._init_locks[loop] = lock

        # 4) 进入临界区：同一 loop 内，只有一个协程负责真正初始化
        async with lock:
            # 5) 双检：当我们等待锁时，可能别的协程已经完成初始化并写入缓存；
            #    这里再检查一次，避免重复创建 session/connector 造成资源泄漏/连接池浪费。
            existing = cls._instances.get(loop)
            if existing is not None:
                return existing

            # 6) 读取配置并创建底层资源：TCPConnector(连接池) + ClientSession(复用连接、管理 cookie/timeout 等)
            cfg = get_app_config()
            connector = aiohttp.TCPConnector(
                limit=cfg.MAX_CONCURRENT_REQUESTS,          # 连接池上限（并不等同于请求并发，但能避免 FD/端口耗尽）
                keepalive_timeout=cfg.KEEP_ALIVE_TIMEOUT,   # 空闲连接保活时间（提高复用率）
                force_close=False,                          # 允许 keep-alive 复用连接
                enable_cleanup_closed=True,                 # 清理已关闭连接，降低泄漏风险
            )
            timeout = aiohttp.ClientTimeout(total=cfg.RESPONSE_TIMEOUT)  # 默认总超时；SSE 可在调用时覆盖

            session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                json_serialize=json.dumps,                  # 统一 JSON 序列化函数
            )

            # 7) 组装 HttpClient（业务语义层）与 Transport（纯 I/O 层）
            client = HttpClient(AiohttpTransport(session))

            # 8) 写入缓存：同一 loop 后续所有调用都复用该 client/session
            cls._sessions[loop] = session
            cls._instances[loop] = client
            return client


    @classmethod
    async def close_for_current_loop(cls) -> None:
        """关闭并清理“当前 running event loop”下的 HttpClient/ClientSession"""
        loop = asyncio.get_running_loop()

        # 1) 先从缓存移除 client（client 自身不持有资源关闭逻辑，资源在 session 里）
        cls._instances.pop(loop, None)

        # 2) 取出并关闭 session：session.close() 会连带关闭 connector/连接池中的底层连接
        session = cls._sessions.pop(loop, None)
        if session is not None and not session.closed:
            await session.close()
            