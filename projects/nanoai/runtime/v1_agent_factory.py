from __future__ import annotations

from collections.abc import Callable
import json
from typing import Literal

from pydantic import BaseModel, Field

from aicore.models.model_api import ModelCallParams
from aicore.session import SessionContext
from aicore.v1.experiments.agent import (
    Agent,
    AgentContext,
    AgentState,
    create_agent,
)

from .v1_agent_session import (
    AgentLike,
    SessionRestoreError,
    V1AgentSnapshot,
)


class V1AgentConfig(BaseModel):
    """Static configuration used to create one V1 Agent-backed Session."""

    model: str = Field(..., min_length=1, description="模型名称")
    system_prompt: str = Field(
        default="你是友好的用户智能助手", description="系统提示词"
    )
    params: ModelCallParams = Field(
        default_factory=ModelCallParams, description="模型调用参数"
    )
    max_turns: int = Field(default=5, ge=1, description="单个 turn 的最大 ReAct 回合数")
    model_api_backend: Literal["chat", "responses"] = Field(
        default="chat", description="模型 API 后端"
    )


class V1AgentFactory:
    """Builds new or restored V1 Agents from one session configuration."""

    def __init__(self, config: V1AgentConfig) -> None:
        self._config = config

    def __call__(
        self, session_context: SessionContext, snapshot: V1AgentSnapshot | None = None
    ) -> AgentLike:
        if snapshot is not None:
            if not isinstance(snapshot.context, AgentContext) or not isinstance(
                snapshot.state, AgentState
            ):
                raise TypeError(
                    "V1 Agent snapshot does not contain AgentContext and AgentState"
                )
            return Agent(snapshot.context, state=snapshot.state)

        return create_agent(
            model=self._config.model,
            tools=[],
            system_prompt=_system_prompt_with_session_context(
                self._config.system_prompt, session_context
            ),
            model_call_params=self._config.params,
            model_api_backend=self._config.model_api_backend,
            react_max_turns=self._config.max_turns,
        )

    @staticmethod
    def restore_agent(
        session_context: SessionContext,
        snapshot: V1AgentSnapshot | None,
    ) -> AgentLike:
        """Rebuild a V1 Agent exclusively from a serialized Agent snapshot."""

        del session_context
        if snapshot is None:
            raise SessionRestoreError(
                "Session dump does not contain a V1 Agent snapshot"
            )
        return Agent(snapshot.context, state=snapshot.state)


type V1AgentFactoryBuilder = Callable[
    [V1AgentConfig],
    Callable[[SessionContext, V1AgentSnapshot | None], AgentLike],
]


def _system_prompt_with_session_context(
    system_prompt: str, session_context: SessionContext
) -> str:
    if not session_context.values:
        return system_prompt
    context_json = json.dumps(session_context.values, ensure_ascii=False, default=str)
    return (
        f"{system_prompt.rstrip()}\n\n"
        "以下是本次会话已确认的静态上下文。回答涉及其中事实时必须以这些数据为准，"
        "不得编造或覆盖其中的信息：\n"
        f"{context_json}"
    )
