"""Protocols for the provider-neutral Model API."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, Sequence

from pydantic import BaseModel

# Import from the protocol module directly instead of aicore.tools to avoid
# pulling tool implementations/helpers into this boundary and to reduce
# circular-import risk.
from aicore.tools.protocol import ToolProtocol

from .events import ModelEvent
from .types import (
    ModelCallParams,
    ModelMessage,
    ModelInput,
    ModelResponse,
    ModelState,
    ModelStateDump,
    StructuredModelResponse,
)


class ModelStream[StateT: ModelState](Protocol):
    """Provider-neutral asynchronous model stream."""

    @property
    def response(self) -> ModelResponse[StateT] | None:
        raise NotImplementedError

    def __aiter__(self) -> AsyncIterator[ModelEvent]:
        raise NotImplementedError


class ModelAPI[StateT: ModelState](Protocol):
    """Adapter boundary between agent flows and model providers."""

    @classmethod
    def initial_state(
        cls,
        *,
        system_prompt: str | None = None,
    ) -> StateT:
        raise NotImplementedError

    async def invoke(
        self,
        input: ModelInput,
        *,
        state: StateT,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> ModelResponse[StateT]:
        raise NotImplementedError

    async def structured_output[T](
        self,
        input: ModelInput,
        *,
        output_type: type[T],
        state: StateT,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> StructuredModelResponse[T, StateT]:
        raise NotImplementedError

    async def stream(
        self,
        input: ModelInput,
        *,
        state: StateT,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> ModelStream[StateT]:
        raise NotImplementedError

    async def dump_state(
        self,
        state: StateT,
    ) -> ModelStateDump:
        raise NotImplementedError

    async def history(
        self,
        state: StateT,
    ) -> list[ModelMessage]:
        raise NotImplementedError

    def state_from_history(
        self,
        history: Sequence[ModelMessage],
    ) -> StateT:
        raise NotImplementedError

    def restore_state(
        self,
        dump: ModelStateDump,
    ) -> StateT:
        """从持久化 dump 还原模型状态。

        实现约束：必须是纯内存操作（JSON 反序列化），不得做任何 I/O 或网络请求。
        之所以设计为同步方法，是因为调用方在同步 ``@property`` 内调用此方法；
        若未来某个 adapter 需要在 restore 时做 I/O，应重新审视整体设计，
        而不是在此方法里做阻塞调用。
        """
        raise NotImplementedError
