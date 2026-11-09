"""Jev（TypeSafe AI System One）客户端：异步调用 + 答案归一化。

为什么需要这一层
----------------
1. **归一化**：把 SDK 的 ``ChoiceAnswer / ScoreAnswer / NoulAnswer`` 统一成
   :class:`JevAnswer`（纯数据、可 JSON 序列化、字段语义显式），判定方程只依赖它。
   额外补两个工程上必需的量：Score 的 ``level``（档位要对 probabilities 取 argmax，
   不能用四舍五入——偏斜分布下四舍五入会指错档位）。
2. **超时**：SDK 默认 10s 对热路径太长，统一收紧到 :data:`DEFAULT_JEV_TIMEOUT`。
   超时用 SDK 自己的 per-call ``timeout``（它直接成为这次 HTTP 请求的 timeout），
   超时异常是 ``TypeSafeAPITimeoutError``（``TimeoutError`` 子类）→ 归一成
   :class:`JevTimeoutError`。
3. **不吞错**：按项目约定，Jev 失败**不回退**、不静默降级，直接抛 :class:`JevError`，
   由调用方决定怎么处理。静默回退会让"A/B 对比"失去意义（分不清是判得好还是没判）。

异步
----
SDK 自带 ``AsyncTypeSafeClient``（httpx 异步客户端），所以**不需要**任何线程包装：
``await client.system_one(state, questions, timeout=...)`` 就是原生异步调用，超时、取消、
连接复用都由 SDK/httpx 负责。此前那版用 ``anyio.to_thread.run_sync`` 把同步 SDK 包成异步，
既多一层线程池，又要靠 ``abandon_on_cancel=True`` 绕开"取消会等线程跑完"的坑——那层现在
整个删掉了。
"""

from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from typesafe_sdk import (
    AsyncTypeSafeClient,
    RetryPolicy,
    TypeSafeAPITimeoutError,
    TypeSafeError,
)

__all__ = [
    "JevError",
    "JevTimeoutError",
    "JevAnswer",
    "JevResponse",
    "JevClient",
    "AsyncJevClient",
    "DEFAULT_JEV_TIMEOUT",
    "load_typesafe_api_key",
]

# 默认单次判定超时。SDK 自身 DEFAULT_TIMEOUT=10s 对热路径太长（一次判定拖 10s 会毁掉体验），
# 这里收紧；慢一点也比不可用强，且超时直接报错、不静默降级。
DEFAULT_JEV_TIMEOUT = 6.0

# 项目里 .env 的候选位置（按顺序尝试，不覆盖已存在的进程环境变量）。
_ENV_CANDIDATES: tuple[Path, ...] = (
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parents[3] / "v2" / "experiments" / "jev_lab" / ".env",
    Path.cwd() / ".env",
)


class JevError(RuntimeError):
    """Jev 判定调用失败（网络 / 鉴权 / 服务端 / 反序列化）。调用方不应吞掉它。"""


class JevTimeoutError(JevError):
    """Jev 判定超时。单独成类是因为它通常是"这次状态太复杂"的信号，而非服务不可用。"""


# ────────────────────────────── 归一化答案 ──────────────────────────────


class JevAnswer(BaseModel):
    """一个问题的归一化答案。三个原语共用此结构，按 ``kind`` 取对应字段。

    - Choice：``choice``（选中项）+ ``probabilities``（完整分布）+ ``confidence``（尖锐度）
    - Score：``score``（概率加权均值，可落两档之间）+ ``level``（argmax 档位）+ 分布 + confidence
    - Noul：``noul``（0-1 校准概率，本身即答案，没有 confidence 字段）
    """

    id: str
    kind: Literal["choice", "score", "noul"]
    choice: str | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = None
    score: float | None = None
    level: str | None = None
    noul: float | None = None
    legend: list[str] | None = None

    def as_json(self) -> dict[str, Any]:
        """判定事件里落盘用的紧凑表示（保留分布，便于事后校准统计）。"""
        return self.model_dump(mode="json", exclude_none=True)


class JevResponse(BaseModel):
    """一次 ``system_one`` 的归一化结果。"""

    answers: dict[str, JevAnswer]
    model: str | None = None
    latency_ms: float = 0.0

    def as_json(self) -> dict[str, Any]:
        return {k: v.as_json() for k, v in self.answers.items()}


# ────────────────────────────── 客户端协议 ──────────────────────────────


@runtime_checkable
class JevClient(Protocol):
    """异步 Jev 客户端协议。实现方（真实 / 假）都必须保证：失败即抛错，不回退。"""

    async def system_one(
        self,
        *,
        state: Any,
        questions: Mapping[str, Any],
        timeout: float | None = None,
    ) -> JevResponse: ...


def load_typesafe_api_key() -> str | None:
    """从环境变量或项目内 .env 读取 TYPESAFE_API_KEY（不覆盖已存在的环境变量）。"""
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv 是项目依赖，缺失时直接跳过
        return None
    for path in _ENV_CANDIDATES:
        if path.is_file():
            load_dotenv(path, override=False)
            if os.environ.get("TYPESAFE_API_KEY"):
                return os.environ["TYPESAFE_API_KEY"]
    return None


class AsyncJevClient:
    """基于 SDK ``AsyncTypeSafeClient`` 的 Jev 客户端。

    - 客户端懒建、复用（httpx 连接池跟着生命周期走），用完 ``await aclose()`` 或直接用
      ``async with``；
    - 每次调用用 SDK 的 per-call ``timeout``（``self._timeout`` 是默认值），超时即
      :class:`JevTimeoutError`；
    - 其余 SDK 异常统一归 :class:`JevError`，绝不静默降级。
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_JEV_TIMEOUT,
        max_retries: int = 0,
    ) -> None:
        self._api_key = api_key or load_typesafe_api_key()
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        # 默认关掉 SDK 内部重试：判定在 plan 热路径上，重试会把延迟乘上倍数；
        # 需要重试时由调用方显式打开（并相应放宽 timeout）。
        self._max_retries = max_retries
        self._client: AsyncTypeSafeClient | None = None

    @property
    def client(self) -> AsyncTypeSafeClient:
        """懒建的底层 SDK 客户端（缺 key 时在这里报错，而不是构造时）。"""
        if self._client is None:
            if not self._api_key:
                raise JevError(
                    "缺少 TYPESAFE_API_KEY：请设置环境变量或在 jev_lab/.env 中提供"
                )
            kwargs: dict[str, Any] = {
                "api_key": self._api_key,
                "retry": RetryPolicy(max_retries=self._max_retries),
                "timeout": self._timeout,
            }
            if self._model:
                kwargs["model"] = self._model
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncTypeSafeClient(**kwargs)
        return self._client

    async def aclose(self) -> None:
        """释放连接资源（幂等）。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> AsyncJevClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def system_one(
        self,
        *,
        state: Any,
        questions: Mapping[str, Any],
        timeout: float | None = None,
    ) -> JevResponse:
        limit = self._timeout if timeout is None else timeout
        started = perf_counter()
        try:
            response = await self.client.system_one(state, questions, timeout=limit)
        except TypeSafeAPITimeoutError as e:
            raise JevTimeoutError(
                f"Jev system_one 超时（>{limit}s，questions={sorted(questions)}）"
            ) from e
        except TypeSafeError as e:
            raise JevError(f"Jev system_one 调用失败：{type(e).__name__}: {e}") from e
        except Exception as e:  # 兜底：不把 SDK 之外的异常形态漏给调用方
            raise JevError(f"Jev system_one 调用失败：{type(e).__name__}: {e}") from e
        latency_ms = (perf_counter() - started) * 1000
        return _normalize_response(response, latency_ms=latency_ms)


def _normalize_response(response: Any, *, latency_ms: float) -> JevResponse:
    """SDK 响应 → :class:`JevResponse`（含 Score 档位 argmax）。"""
    answers: dict[str, JevAnswer] = {}
    for qid, ans in (response.answers or {}).items():
        answers[qid] = _normalize_answer(qid, ans)
    return JevResponse(
        answers=answers,
        model=getattr(response, "model", None),
        latency_ms=latency_ms,
    )


def _normalize_answer(qid: str, ans: Any) -> JevAnswer:
    """单个答案归一化。按 ``type`` 字段分派，不依赖具体 SDK 类。"""
    kind = getattr(ans, "type", None)
    if kind == "choice":
        return JevAnswer(
            id=qid,
            kind="choice",
            choice=ans.choice,
            probabilities=dict(ans.probabilities or {}),
            confidence=getattr(ans, "confidence", None),
        )
    if kind == "score":
        # 实测：ScoreAnswer.probabilities 以**档位下标（int）**为 key，标签在 legend 里
        # （{0: '低风险', 1: '中等', 2: '高风险'}）。这里把下标换成标签，使分布可直接被人读、
        # 也能稳定地跨请求比较（下标顺序其实依赖 criteria 顺序，标签不会）。
        legend = {int(k): str(v) for k, v in (getattr(ans, "legend", None) or {}).items()}
        raw_probs = {int(k): float(v) for k, v in (ans.probabilities or {}).items()}
        probs = {legend.get(k, str(k)): v for k, v in raw_probs.items()}
        labels = [legend[k] for k in sorted(legend)]
        return JevAnswer(
            id=qid,
            kind="score",
            score=ans.score,
            # 档位取 argmax 而非四舍五入：偏斜分布下四舍五入会指错档位。
            level=_argmax_key(probs),
            probabilities=probs,
            confidence=getattr(ans, "confidence", None),
            legend=labels or None,
        )
    if kind == "noul":
        return JevAnswer(id=qid, kind="noul", noul=ans.noul)
    raise JevError(f"Jev 返回了未知答案类型：question={qid!r} type={kind!r} answer={ans!r}")


def _argmax_key(probs: Mapping[str, float]) -> str | None:
    """概率分布的 argmax（同概率时按 key 名排序取第一个，保证确定性）。"""
    if not probs:
        return None
    return max(sorted(probs), key=lambda k: probs[k])
