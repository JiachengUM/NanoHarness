from collections.abc import AsyncGenerator
from typing import Any

import anyio
import pytest

from aicore.events.agent import AgentOutTextDeltaEvent
from aicore.events.task import (
    TaskCreatedEvent,
    TaskEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.runtime.task import TaskManager
from aicore.simulation.user_env.data_source import UserDataSourceBase
from aicore.v2.agent_model import AgentBase, AgentInputEvent, AgentOutEvent
from aicore.v2.agent_runner import AgentRunner


pytestmark = pytest.mark.asyncio


class EmptyUserData(UserDataSourceBase):
    async def __call__(self) -> AsyncGenerator[str, None]:
        if False:
            yield ""


class RecordingAgent(AgentBase):
    def __init__(self) -> None:
        self.inputs: list[AgentInputEvent] = []

    async def astream(
        self,
        input: AgentInputEvent,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentOutEvent, None]:
        self.inputs.append(input)
        if isinstance(input, TaskSuccessEvent):
            yield AgentOutTextDeltaEvent(delta=f"task done: {input.result}")


class FakeTaskManager:
    def __init__(self, events: list[TaskEvent]) -> None:
        self.events = events

    async def run(self) -> None:
        return

    async def astream(self) -> AsyncGenerator[TaskEvent, None]:
        for event in self.events:
            yield event


def build_runner(
    *,
    manager: FakeTaskManager,
    client_events: list[AgentOutEvent | TaskEvent] | None = None,
) -> AgentRunner:
    client_events = client_events if client_events is not None else []
    return AgentRunner(
        user_data=EmptyUserData(),
        agent=RecordingAgent(),
        task_manager=manager,  # type: ignore[arg-type]
        client=client_events.append,
    )


async def receive_agent_input_if_any(runner: AgentRunner) -> AgentInputEvent | None:
    with anyio.move_on_after(0.05) as scope:
        event = await runner._agent_in_receive.receive()
    if scope.cancel_called:
        return None
    return event


async def test_manager_task_events_are_forwarded_to_client() -> None:
    created = TaskCreatedEvent(
        task_id="weather-1",
        name="weather_search",
        arguments={"city": "上海"},
    )
    started = TaskStartEvent(task_id="weather-1")
    client_events: list[AgentOutEvent | TaskEvent] = []
    runner = build_runner(
        manager=FakeTaskManager([created, started]),
        client_events=client_events,
    )

    await runner._listen_task()

    assert client_events == [created, started]
    assert await receive_agent_input_if_any(runner) is None


async def test_task_success_is_forwarded_to_client_and_sent_back_to_agent() -> None:
    success = TaskSuccessEvent(task_id="weather-1", result="sunny")
    client_events: list[AgentOutEvent | TaskEvent] = []
    runner = build_runner(
        manager=FakeTaskManager([success]),
        client_events=client_events,
    )

    await runner._listen_task()

    assert client_events == [success]
    assert await receive_agent_input_if_any(runner) == success


async def test_agent_runner_uses_manager_as_task_runtime() -> None:
    manager = TaskManager()
    runner = AgentRunner(
        user_data=EmptyUserData(),
        agent=RecordingAgent(),
        task_manager=manager,
        client=lambda _: None,
    )

    assert runner.task_manager is manager
    assert not hasattr(runner, "task_runner")
