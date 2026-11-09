from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Mapping
from typing import Any

from .base import SessionBase, SessionOutput, SessionStateUpdate, SessionSubmission


class SyncSessionBase(SessionBase):
    """同步输出 Session 抽象。

    同步输出 Session 的 submit 与输出流一一对应：调用方提交一轮输入后，
    直接消费该调用返回的输出流。本轮响应不通过独立的 out 接口异步分发。
    """

    @abstractmethod
    def submit(
        self,
        input: Any,
        /,
        *,
        state_update: SessionStateUpdate | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[SessionSubmission, AsyncIterator[SessionOutput]]:
        """提交一轮输入并返回本轮输出流。

        Session 在接受输入时创建 turn 并分配 turn_id。返回的提交结果可用于
        在消费输出前关联该 turn。state_update 表示本轮输入附带的动态事实。
        具体实现应在运行前或运行中将其合入 SessionState.values。
        """
        ...
