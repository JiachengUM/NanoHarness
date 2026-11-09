from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Mapping
from typing import Any

from .base import (
    SessionBase,
    SessionOutput,
    SessionStateUpdate,
    SessionSubmission,
    SessionTrace,
)


class AsyncSessionBase(SessionBase):
    """异步输出 Session 抽象。

    异步输出 Session 的 submit 只负责提交输入，并返回提交结果。
    实际响应和运行轨迹通过 out 与 traces 接口异步消费。
    """

    @abstractmethod
    async def submit(
        self,
        input: Any,
        /,
        *,
        state_update: SessionStateUpdate | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionSubmission:
        """提交一轮输入。

        返回值只表达消息是否被 Session 接收，不携带实际响应。Session 在接受
        输入时创建 turn 并分配 turn_id。state_update 表示本轮输入附带的动态
        事实，具体实现应最终将其合入 SessionState.values。
        """
        ...

    @abstractmethod
    def out(self) -> AsyncIterator[SessionOutput]:
        """消费 Session 对外输出流。

        out 面向产品交互。调用方应从该接口异步读取 Session 已产生的响应输出。
        """
        ...

    @abstractmethod
    def traces(self) -> AsyncIterator[SessionTrace]:
        """消费 Session 运行轨迹流。

        traces 面向诊断、审计和回放。它不应替代 out 成为产品响应通道。
        """
        ...
