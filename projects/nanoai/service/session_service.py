from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from aicore.session import (
    SessionContext,
    SessionDumpPayload,
    SessionOutput,
    SessionStateUpdate,
    SessionSubmission,
    SessionTurn,
)

from projects.nanoai.runtime import V1AgentConfig, V1AgentFactory, V1AgentSession
from projects.nanoai.runtime.v1_agent_factory import V1AgentFactoryBuilder


class SessionNotFoundError(LookupError):
    """The requested Session is not present in this service instance."""


class SessionAlreadyExistsError(RuntimeError):
    """A Session with the requested stable ID is already active in this service."""


class SessionService:
    """In-memory application service for V1 Agent-backed Sessions."""

    def __init__(
        self, *, agent_factory_builder: V1AgentFactoryBuilder = V1AgentFactory
    ) -> None:
        self._agent_factory_builder = agent_factory_builder
        self._sessions: dict[str, V1AgentSession] = {}

    def create(
        self,
        config: V1AgentConfig,
        /,
        *,
        context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> V1AgentSession:
        session = V1AgentSession.new_session(
            SessionContext(values=dict(context or {})),
            metadata=metadata,
            agent_factory=self._agent_factory_builder(config),
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str, /) -> V1AgentSession:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise SessionNotFoundError(
                f"Session {session_id} does not exist"
            ) from error

    def restore(self, payload: SessionDumpPayload, /) -> V1AgentSession:
        if payload.session_id in self._sessions:
            raise SessionAlreadyExistsError(
                f"Session {payload.session_id} already exists"
            )
        session = V1AgentSession.restore(
            payload,
            agent_factory=V1AgentFactory.restore_agent,
        )
        self._sessions[session.id] = session
        return session

    def submit(
        self,
        session_id: str,
        input: Any,
        /,
        *,
        state_update: Mapping[str, Any] | None = None,
    ) -> tuple[V1AgentSession, SessionSubmission, AsyncIterator[SessionOutput]]:
        session = self.get(session_id)
        update = (
            SessionStateUpdate(values=dict(state_update))
            if state_update is not None
            else None
        )
        submission, outputs = session.submit(input, state_update=update)
        return session, submission, outputs

    async def cancel(self, session_id: str, turn_id: str, /) -> SessionTurn:
        return await self.get(session_id).cancel(turn_id)

    async def dump(self, session_id: str, /) -> SessionDumpPayload:
        return await self.get(session_id).dump()

    async def close(self, session_id: str, /) -> None:
        session = self.get(session_id)
        await session.close()
        del self._sessions[session_id]
