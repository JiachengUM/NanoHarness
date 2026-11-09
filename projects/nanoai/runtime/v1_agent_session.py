from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, Protocol, Self
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from aicore.session import (
    SessionContext,
    SessionDumpPayload,
    SessionOutput,
    SessionState,
    SessionStateUpdate,
    SessionStatus,
    SessionSubmission,
    SessionTrace,
    SessionTurn,
    SessionTurnStatus,
    SyncSessionBase,
)
from aicore.v1.experiments.agent import AgentContext, AgentState

_V1_AGENT_SNAPSHOT_METADATA_KEY = "nanoai.v1_agent_snapshot"
_TEXT_EVENT_TYPES = {
    "react.text.delta",
    "react.text.done",
    "explicit.text.delta",
    "explicit.text.done",
}
_ACTIVE_TURN_STATUSES = {SessionTurnStatus.PENDING, SessionTurnStatus.RUNNING}


class AgentLike(Protocol):
    def astream(self, query: Any, /, **kwargs: Any) -> AsyncIterator[Any]: ...


class SessionBusyError(RuntimeError):
    """The Session already has a pending or running turn."""


class SessionClosedError(RuntimeError):
    """The Session has been closed."""


class SessionStateUpdateUnsupportedError(NotImplementedError):
    """The V1 Agent adapter cannot make dynamic state visible to the model."""


class SessionRestoreError(ValueError):
    """A Session dump cannot be restored by the V1 Agent adapter."""


class SessionTurnNotFoundError(LookupError):
    """The requested turn is not present in the Session history."""


class SessionTurnNotCancellableError(RuntimeError):
    """The requested turn is already terminal."""


class V1AgentSnapshot(BaseModel):
    """V1 Agent state captured as part of a Session dump."""

    context: AgentContext
    state: AgentState


type AgentFactory = Callable[[SessionContext, V1AgentSnapshot | None], AgentLike]


class V1AgentSession(SyncSessionBase):
    """Sync Session adapter around ``aicore.v1.experiments.agent.Agent``."""

    # TODO: 车载产品不应长期直接复用通用 V1 Agent；应显式建模车辆静态 context、
    # 动态 state 及其注入方式，再由车载领域运行时驱动 Agent。

    def __init__(
        self,
        *,
        session_id: str,
        context: SessionContext,
        state: SessionState,
        metadata: Mapping[str, Any],
        agent: AgentLike,
    ) -> None:
        self._id = session_id
        self._context = context
        self._state = state
        self._metadata = dict(metadata)
        self._agent = agent
        self._active_turn_tasks: dict[str, asyncio.Task[Any]] = {}

    @classmethod
    def new_session(
        cls,
        context: SessionContext | Mapping[str, Any] | None = None,
        /,
        *,
        metadata: Mapping[str, Any] | None = None,
        agent_factory: AgentFactory,
        **kwargs: Any,
    ) -> Self:
        if kwargs:
            raise TypeError(
                f"Unsupported V1 Agent session options: {', '.join(kwargs)}"
            )
        session_context = _coerce_context(context)
        return cls(
            session_id=f"sess-{uuid4()}",
            context=session_context,
            state=SessionState(),
            metadata=metadata or {},
            agent=agent_factory(session_context, None),
        )

    @classmethod
    def restore(
        cls,
        payload: SessionDumpPayload,
        /,
        *,
        agent_factory: AgentFactory,
        **kwargs: Any,
    ) -> Self:
        if kwargs:
            raise TypeError(
                f"Unsupported V1 Agent session restore options: {', '.join(kwargs)}"
            )

        snapshot_value = payload.metadata.get(_V1_AGENT_SNAPSHOT_METADATA_KEY)
        snapshot = _coerce_snapshot(snapshot_value)
        if snapshot is None:
            raise SessionRestoreError(
                "Session dump does not contain a V1 Agent snapshot"
            )
        metadata = dict(payload.metadata)
        metadata.pop(_V1_AGENT_SNAPSHOT_METADATA_KEY, None)
        return cls(
            session_id=payload.session_id,
            context=payload.context.model_copy(deep=True),
            state=payload.state.model_copy(deep=True),
            metadata=metadata,
            agent=agent_factory(payload.context, snapshot),
        )

    @property
    def id(self) -> str:
        return self._id

    @property
    def context(self) -> SessionContext:
        return self._context

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def metadata(self) -> Mapping[str, Any]:
        return self._metadata

    def update_state(
        self, state_update: SessionStateUpdate | Mapping[str, Any], /
    ) -> SessionState:
        raise SessionStateUpdateUnsupportedError(
            "V1 Agent Session does not support dynamic state updates because they are not visible to the model"
        )

    def submit(
        self,
        input: Any,
        /,
        *,
        state_update: SessionStateUpdate | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[SessionSubmission, AsyncIterator[SessionOutput]]:
        if kwargs:
            raise TypeError(f"Unsupported V1 Agent turn options: {', '.join(kwargs)}")
        if self._state.status is SessionStatus.CLOSED:
            raise SessionClosedError(f"Session {self.id} is closed")
        if self._active_turn_tasks or any(
            turn.status in _ACTIVE_TURN_STATUSES for turn in self._state.history
        ):
            raise SessionBusyError(f"Session {self.id} already has an active turn")
        if state_update is not None:
            self.update_state(state_update)

        turn = SessionTurn(id=f"turn-{uuid4()}", input=input)
        self._state.history.append(turn)
        self._state.status = SessionStatus.RUNNING
        submission = SessionSubmission(accepted=True, turn_id=turn.id)
        return submission, self._stream_turn(turn.id)

    async def cancel(self, turn_id: str, /) -> SessionTurn:
        turn = self._get_turn(turn_id)
        if turn.status not in _ACTIVE_TURN_STATUSES:
            raise SessionTurnNotCancellableError(
                f"Turn {turn_id} is already {turn.status}"
            )

        turn.status = SessionTurnStatus.CANCELLED
        turn.error = "cancelled"
        task = self._active_turn_tasks.get(turn_id)
        if task is not None and not task.done():
            task.cancel()
        self._refresh_session_status()
        return turn

    async def close(self) -> None:
        if self._state.status is SessionStatus.CLOSED:
            return
        for turn in self._state.history:
            if turn.status in _ACTIVE_TURN_STATUSES:
                await self.cancel(turn.id)
        self._state.status = SessionStatus.CLOSED

    async def dump(self) -> SessionDumpPayload:
        if self._active_turn_tasks or any(
            turn.status in _ACTIVE_TURN_STATUSES for turn in self._state.history
        ):
            raise SessionBusyError(
                f"Session {self.id} has an active turn and cannot be dumped"
            )

        metadata = dict(self._metadata)
        dump_method = getattr(self._agent, "dump", None)
        if callable(dump_method):
            agent_context, agent_state = await dump_method()
            metadata[_V1_AGENT_SNAPSHOT_METADATA_KEY] = V1AgentSnapshot(
                context=agent_context,
                state=agent_state,
            )
        return SessionDumpPayload(
            session_id=self.id,
            context=self.context.model_copy(deep=True),
            state=self.state.model_copy(deep=True),
            metadata=metadata,
        )

    async def _stream_turn(self, turn_id: str) -> AsyncIterator[SessionOutput]:
        turn = self._get_turn(turn_id)
        if turn.status is SessionTurnStatus.CANCELLED:
            self._refresh_session_status()
            return

        turn.status = SessionTurnStatus.RUNNING
        current_task = asyncio.current_task()
        if current_task is not None:
            self._active_turn_tasks[turn_id] = current_task

        try:
            async for event in self._agent.astream(turn.input):
                payload = _event_payload(event)
                trace = SessionTrace(turn_id=turn_id, data=payload)
                turn.traces.append(trace)
                if _event_type(payload) in _TEXT_EVENT_TYPES:
                    output = SessionOutput(turn_id=turn_id, data=payload)
                    turn.outputs.append(output)
                    yield output
            if turn.status is SessionTurnStatus.RUNNING:
                turn.status = SessionTurnStatus.COMPLETED
        except asyncio.CancelledError:
            if turn.status in _ACTIVE_TURN_STATUSES:
                turn.status = SessionTurnStatus.CANCELLED
                turn.error = "cancelled"
        except Exception as error:
            if turn.status in _ACTIVE_TURN_STATUSES:
                turn.status = SessionTurnStatus.FAILED
                turn.error = str(error)
                output = SessionOutput(
                    turn_id=turn_id,
                    data={"type": "session.error", "reason": turn.error},
                )
                turn.outputs.append(output)
                yield output
        finally:
            self._active_turn_tasks.pop(turn_id, None)
            self._refresh_session_status()

    def _get_turn(self, turn_id: str) -> SessionTurn:
        for turn in self._state.history:
            if turn.id == turn_id:
                return turn
        raise SessionTurnNotFoundError(
            f"Turn {turn_id} does not exist in Session {self.id}"
        )

    def _refresh_session_status(self) -> None:
        if self._state.status is SessionStatus.CLOSED:
            return
        self._state.status = (
            SessionStatus.RUNNING
            if self._active_turn_tasks
            or any(turn.status in _ACTIVE_TURN_STATUSES for turn in self._state.history)
            else SessionStatus.IDLE
        )


def _coerce_context(
    context: SessionContext | Mapping[str, Any] | None,
) -> SessionContext:
    if context is None:
        return SessionContext()
    if isinstance(context, SessionContext):
        return context.model_copy(deep=True)
    return SessionContext(values=dict(context))


def _coerce_snapshot(value: Any) -> V1AgentSnapshot | None:
    if value is None:
        return None
    if isinstance(value, V1AgentSnapshot):
        return value
    try:
        return V1AgentSnapshot.model_validate(value)
    except ValidationError as error:
        raise SessionRestoreError(
            "Session dump contains an invalid V1 Agent snapshot"
        ) from error


def _event_payload(event: Any) -> Any:
    if isinstance(event, BaseModel):
        try:
            return event.model_dump(mode="json")
        except (TypeError, ValueError):
            return event.model_dump()
    return event


def _event_type(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        value = payload.get("type")
        return value if isinstance(value, str) else None
    return None
