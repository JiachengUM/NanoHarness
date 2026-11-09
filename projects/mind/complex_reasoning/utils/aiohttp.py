"""
异步 HTTP 客户端，供插件调用火山 API。

目标：
1) 同一事件循环(loop)内复用 aiohttp 的连接池（性能好）
2) 不同 loop 各用各的 ClientSession（避免跨 loop 复用导致 "Event loop is closed"）
3) 对外提供强类型返回：
   - 普通 POST：返回 HttpResponse（包含 JSON / text / status / headers）
   - SSE：返回 AsyncGenerator[SSEEvent]（每条事件都强类型，包含 data 或 error）
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Mapping, Optional
from weakref import WeakKeyDictionary

import aiohttp
from aiohttp import ClientError, ClientResponseError

from projects.mind.complex_reasoning.configs.config import get_app_config

logger = logging.getLogger(__name__)


# 1) 返回结构
@dataclass(frozen=True, slots=True)
class HttpResponse:
    """
    普通 HTTP 请求的强类型响应。
    JSON 响应：
    HttpResponse(status=200, headers={"Content-Type": "application/json"}, json={"code": 0, "msg": "ok"}, text=None)
    文本响应：
    HttpResponse(status=200, headers={"Content-Type": "text/plain"}, json=None, text="hello world")
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


# 2) HttpClient：按事件循环缓存的单例
class HttpClient:
    """
    按事件循环缓存的 HTTP 客户端单例。

    为什么要“按 loop 单例”？
    - aiohttp.ClientSession / TCPConnector 内部持有连接池与 socket
    - 这些底层资源绑定创建它们的 event loop
    - 如果把一个 session 拿到另一个 loop 里用，很容易报错：
        RuntimeError: Event loop is closed
        RuntimeError: attached to a different loop

    因此我们用：loop -> HttpClient 的映射。
    """

    # 用 WeakKeyDictionary 更“自然”：loop 销毁时，这里的 key 会自动消失，避免测试/多 loop 场景的隐性泄漏。
    _instances: "WeakKeyDictionary[asyncio.AbstractEventLoop, HttpClient]" = WeakKeyDictionary()

    def __init__(self) -> None:
        # aiohttp 会话（里面有连接池）
        self._session: Optional[aiohttp.ClientSession] = None
        # 连接池配置
        self._connector: Optional[aiohttp.TCPConnector] = None
        # 默认超时配置
        self._timeout: Optional[aiohttp.ClientTimeout] = None
        # 记录创建时绑定的 loop（主要用于调试/排错）
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def initialize(self) -> None:
        """
        初始化（或重新初始化）底层 session / connector。

        注意：
        - 必须在 async 上下文里运行，因为要获取 running loop
        - 会先 close()，因此 initialize 可重复调用（幂等-ish）
        """
        cfg = get_app_config()
        self._loop = asyncio.get_running_loop()

        # 若之前已初始化过，先干净地关闭一次，防止资源泄漏
        await self.close()

        # 连接池：限制并发与 keepalive，避免端口/FD耗尽，同时尽量复用连接
        self._connector = aiohttp.TCPConnector(
            limit=cfg.MAX_CONCURRENT_REQUESTS,     # 连接池并发上限
            keepalive_timeout=cfg.KEEP_ALIVE_TIMEOUT,  # 空闲连接保活时间（复用连接很重要）
            force_close=False,                     # 不强制关闭连接，尽量复用
            enable_cleanup_closed=True,            # 清理已关闭连接，降低泄漏风险
        )

        # 默认总超时：普通 POST 适合用 total；SSE 常常会单独传 timeout 覆盖
        self._timeout = aiohttp.ClientTimeout(total=cfg.RESPONSE_TIMEOUT)

        # 创建 session：后续所有请求都走同一个连接池
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            timeout=self._timeout,
            json_serialize=json.dumps,
        )

    async def close(self) -> None:
        """
        关闭 session 与 connector
        """
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

        if self._connector:
            await self._connector.close()
        self._connector = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        """
        确保 session 可用

        这里不做“自动 initialize”，是为了让生命周期更明确：
        - 由 get_instance() 负责创建/初始化
        - 请求路径上不隐式创建资源（更好排错）
        """
        if not self._session or self._session.closed:
            raise RuntimeError("HttpClient is not initialized or already closed")
        return self._session

    @staticmethod
    def _parse_sse_payload(payload: str) -> SSEEvent:
        """把单个 SSE payload 解析成 SSEEvent。"""
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

    async def post(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> HttpResponse:
        """
        发 POST 请求，强类型返回 HttpResponse。

        语义：
        - 成功：返回 HttpResponse（其中 json 或 text 至少有一个）
        - 失败：
            - HTTP 4xx/5xx：resp.raise_for_status() -> ClientResponseError
            - 网络错误：ClientError
            - 超时：asyncio.TimeoutError
          这些都抛异常（fail-fast），由上层决定如何处理/重试。
        """
        session = self._ensure_session()

        try:
            # async with 的核心价值：
            # - 响应对象 resp 退出时会把连接“归还”到连接池（或关闭）
            # - 不用它非常容易连接泄漏，最终连接池耗尽
            async with session.post(
                url,
                params=params,
                headers=headers,
                json=json_data,
                timeout=timeout,
            ) as resp: # aiohttp.ClientResponse 可以是json，也可以是stream，取决于url/body/query
                # 对普通请求：非 2xx/3xx 直接当作错误抛异常
                resp.raise_for_status()

                ct = resp.headers.get("Content-Type", "")

                # 优先按 JSON 解析
                if "application/json" in ct:
                    parsed = await resp.json()
                    return HttpResponse(status=resp.status, headers=resp.headers, json=parsed)

                # 不是 JSON 时，返回文本
                text = await resp.text()
                return HttpResponse(status=resp.status, headers=resp.headers, text=text)

        except ClientResponseError as e:
            logger.error("POST %s failed: status=%s msg=%s", url, e.status, e.message)
            raise
        except ClientError as e:
            logger.error("POST %s client error: %r", url, e)
            raise
        except asyncio.TimeoutError:
            logger.error("POST %s timeout", url)
            raise

    async def get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> HttpResponse:
        """发 GET 请求，强类型返回 HttpResponse。"""
        session = self._ensure_session()

        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()

                ct = resp.headers.get("Content-Type", "")
                if "application/json" in ct:
                    parsed = await resp.json()
                    return HttpResponse(status=resp.status, headers=resp.headers, json=parsed)

                text = await resp.text()
                return HttpResponse(status=resp.status, headers=resp.headers, text=text)

        except ClientResponseError as e:
            logger.error("GET %s failed: status=%s msg=%s", url, e.status, e.message)
            raise
        except ClientError as e:
            logger.error("GET %s client error: %r", url, e)
            raise
        except asyncio.TimeoutError:
            logger.error("GET %s timeout", url)
            raise


    # SSE：持续 yield SSEEvent，sse这个协议很原始，需要手动parse
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
        按 SSE 协议拉流（Server-Sent Events）并逐条 yield SSEEvent。

        SSE 典型格式（服务端不断输出文本行）：
            data: {...}
            data: {...}

            data: {...}

        约定：
        - 空行表示一个 event 结束
        - 我们只关心 data: 行，忽略 event/id/retry 等字段
        - 每个 event 的 data 可能分成多行，需要拼接后再 json.loads

        错误策略：
        - 错误作为 SSEEvent 输出，流不中断调用方
        """
        session = self._ensure_session()

        try:
            async with session.post(
                url,
                params=params,
                headers=headers,
                json=body,
                timeout=timeout, 
            ) as resp: # aiohttp.ClientResponse 可以是json，也可以是stream，取决于url/body/query

                # 如果一上来就不是 200，说明流根本没建立成功；这里没有 raise_for_status()，因为我们希望把错误作为事件 yield
                if resp.status != 200:
                    yield SSEEvent(error=f"http_status_{resp.status}", detail=f"status={resp.status}")
                    return

                # 收集一个 event 中所有 data 行
                data_lines: list[str] = []

                while True:
                    raw = await resp.content.readline()
                    if not raw:
                        # EOF：服务端关闭连接/流结束。若最后一条事件未以空行结尾，这里补一次 flush。
                        if data_lines:
                            payload = "\n".join(data_lines).strip()
                            if payload:
                                event = self._parse_sse_payload(payload)
                                yield event
                        return

                    # 将 bytes 解码成 str，并去掉换行
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

                    if line == "":
                        # 空行：表示一个 event 结束，开始处理 data_lines
                        if data_lines:
                            payload = "\n".join(data_lines).strip()
                            data_lines.clear()

                            if payload:
                                event = self._parse_sse_payload(payload)
                                yield event
                        continue

                    if line.startswith("data:"):
                        # 只取 data: 后面的内容，去掉开头空格
                        data_lines.append(line[5:].lstrip())

        except asyncio.TimeoutError as e:
            # 对 SSE，我们倾向于把网络类错误也作为事件返回（避免 async for 被异常打断）
            logger.error("SSE %s timeout: %r", url, e)
            yield SSEEvent(error="timeout", detail=str(e))
            return
        except ClientError as e:
            logger.error("SSE %s client error: %r", url, e)
            yield SSEEvent(error="client_error", detail=repr(e))
            return
        except Exception as e:
            # 最后兜底：避免意外异常导致消费端崩掉
            logger.error("SSE %s unexpected error: %r", url, e, exc_info=True)
            yield SSEEvent(error="unexpected_error", detail=repr(e))
            return

    # 获取/清理：按当前 loop 单例
    @classmethod
    async def get_instance(cls) -> "HttpClient":
        """
        获取当前事件循环下的 HttpClient 单例。

        - 同一 loop：复用同一个 client（共享连接池）
        - 不同 loop：各自创建自己的 client（避免跨 loop 复用）
        """
        loop = asyncio.get_running_loop()

        inst = cls._instances.get(loop)
        if inst is None:
            inst = cls()
            await inst.initialize()
            cls._instances[loop] = inst

        return inst

    @classmethod
    async def close_for_current_loop(cls) -> None:
        """
        关闭当前 loop 对应的 client，并从缓存移除。
        """
        loop = asyncio.get_running_loop()
        inst = cls._instances.pop(loop, None)
        if inst is not None:
            await inst.close()