from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from aicore.events.react import ReActStartEvent, ReActTextDeltaEvent, ReActTextDoneEvent
from aicore.session import SessionDumpPayload, SessionTurnStatus

from projects.nanoai.runtime import (
    SessionBusyError,
    V1AgentConfig,
    V1AgentFactory,
    SessionStateUpdateUnsupportedError,
    V1AgentSession,
)


class FakeAgent:
    async def astream(self, query: Any, /, **kwargs: Any) -> AsyncIterator[Any]:
        yield ReActStartEvent()
        yield ReActTextDeltaEvent(delta=f"{query}-")
        yield ReActTextDoneEvent(text=f"{query}-done")


class BlockingFakeAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def astream(self, query: Any, /, **kwargs: Any) -> AsyncIterator[Any]:
        self.started.set()
        await asyncio.Event().wait()
        yield ReActTextDoneEvent(text="unreachable")


async def _collect(outputs: AsyncIterator[Any]) -> list[Any]:
    return [output async for output in outputs]


def test_sync_session_records_a_complete_turn() -> None:
    session = V1AgentSession.new_session(agent_factory=lambda _, __: FakeAgent())
    submission, outputs = session.submit("hello")

    received = asyncio.run(_collect(outputs))

    assert submission.accepted is True
    assert len(received) == 2
    assert all(output.turn_id == submission.turn_id for output in received)
    assert session.state.values == {}
    assert len(session.state.history) == 1
    turn = session.state.history[0]
    assert turn.id == submission.turn_id
    assert turn.status is SessionTurnStatus.COMPLETED
    assert [trace.data["type"] for trace in turn.traces] == [
        "react.start",
        "react.text.delta",
        "react.text.done",
    ]


def test_dynamic_state_updates_are_rejected_without_mutating_the_session() -> None:
    session = V1AgentSession.new_session(agent_factory=lambda _, __: FakeAgent())

    with pytest.raises(SessionStateUpdateUnsupportedError):
        session.update_state({"car_info": {"battery_percent": 74}})
    with pytest.raises(SessionStateUpdateUnsupportedError):
        session.submit("hello", state_update={"car_info": {"battery_percent": 74}})

    assert session.state.values == {}
    assert session.state.history == []


def test_v1_agent_dump_survives_a_json_round_trip_and_restores() -> None:
    async def run() -> None:
        session = V1AgentSession.new_session(
            {"car_info": {"battery_percent": 18}},
            metadata={"source": "test"},
            agent_factory=V1AgentFactory(V1AgentConfig(model="fake-model")),
        )

        payload = await session.dump()
        persisted_payload = SessionDumpPayload.model_validate_json(
            payload.model_dump_json()
        )
        restored = V1AgentSession.restore(
            persisted_payload,
            agent_factory=V1AgentFactory.restore_agent,
        )

        assert restored.id == session.id
        assert restored.context == session.context
        assert restored.state == session.state
        assert restored.metadata == {"source": "test"}
        assert (await restored.dump()).session_id == session.id

    asyncio.run(run())


def test_cancel_stops_a_running_turn() -> None:
    async def run() -> None:
        agent = BlockingFakeAgent()
        session = V1AgentSession.new_session(agent_factory=lambda _, __: agent)
        submission, outputs = session.submit("hello")
        consumer = asyncio.create_task(_collect(outputs))
        await agent.started.wait()

        with pytest.raises(SessionBusyError):
            await session.dump()

        turn = await session.cancel(submission.turn_id)
        received = await consumer

        assert received == []
        assert turn.status is SessionTurnStatus.CANCELLED
        assert session.state.history[0].error == "cancelled"

    asyncio.run(run())
