from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aicore.session import SessionContext, SessionState

from projects.nanoai.runtime import V1AgentConfig


class CreateSessionRequest(BaseModel):
    config: V1AgentConfig
    context: dict[str, Any] = Field(
        default_factory=dict, description="创建后不变的会话上下文"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="会话元数据")


class SessionCreatedResponse(BaseModel):
    session_id: str


class SessionRestoredResponse(BaseModel):
    session_id: str


class SessionView(BaseModel):
    session_id: str
    context: SessionContext
    state: SessionState
    metadata: dict[str, Any]


class SubmitTurnRequest(BaseModel):
    input: Any
    state_update: dict[str, Any] | None = None
