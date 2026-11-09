from collections.abc import AsyncGenerator

import pytest

from aicore.events.task import (
    TaskCancelledEvent,
    TaskCreatedEvent,
    TaskEvent,
    TaskFailureEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.runtime.task import (
    TaskManager,
    TaskStatus,
    TaskSuccess,
)


class FakeEngine:
    def __init__(self) -> None:
        self.added: dict[str, object] = {}
        self.cancelled: list[str] = []
        self.events: list[TaskEvent] = []

    def add_task(self, factory: object, task_id: str) -> None:
        self.added[task_id] = factory

    def cancel_task(self, task_id: str) -> None:
        self.cancelled.append(task_id)

    async def run(self) -> None:
        return

    async def astream(self) -> AsyncGenerator[TaskEvent, None]:
        for event in self.events:
            yield event


def success_worker():
    async def _run():
        yield TaskSuccess(result="done")

    return _run


def test_submit_task_creates_pending_task_and_registers_engine_entry() -> None:
    engine = FakeEngine()
    manager = TaskManager(runner=engine)

    task_id = manager.submit_task(
        success_worker(),
        task_id="weather-1",
        name="weather_search",
        arguments={"city": "上海"},
    )

    projection = manager.get_projection(task_id)
    assert task_id == "weather-1"
    assert projection is not None
    assert projection.tool_name == "weather_search"
    assert projection.arguments == {"city": "上海"}
    assert projection.status == TaskStatus.PENDING
    assert "weather-1" in engine.added


def test_submission_context_merges_metadata_and_explicit_values_win() -> None:
    manager = TaskManager(runner=FakeEngine())

    with manager.submission_context(
        {"origin_message_id": "agent-1", "source": "context"}
    ):
        manager.submit_task(
            success_worker(),
            task_id="weather-context",
            name="weather_search",
            metadata={"source": "explicit"},
        )

    task = manager.get_task("weather-context")
    assert task is not None
    assert task.metadata == {
        "origin_message_id": "agent-1",
        "source": "explicit",
    }


@pytest.mark.asyncio
async def test_submit_task_publishes_created_event() -> None:
    manager = TaskManager(runner=FakeEngine())

    manager.submit_task(
        success_worker(),
        task_id="weather-1",
        name="weather_search",
        arguments={"city": "上海"},
    )

    event = await manager._event_output_recv.receive()
    assert isinstance(event, TaskCreatedEvent)
    assert event.task_id == "weather-1"
    assert event.name == "weather_search"
    assert event.arguments == {"city": "上海"}


def test_cancel_task_delegates_active_task_to_engine() -> None:
    engine = FakeEngine()
    manager = TaskManager(runner=engine)
    manager.submit_task(success_worker(), task_id="weather-1", name="weather_search")

    outcome = manager.cancel_task("weather-1")

    assert outcome.status == "accepted"
    assert outcome.task_id == "weather-1"
    assert engine.cancelled == ["weather-1"]


def test_cancel_task_does_not_rewrite_runner_terminal_awaiting_projection() -> None:
    class TerminalFixedEngine(FakeEngine):
        def cancel_task(self, task_id: str) -> bool:
            self.cancelled.append(task_id)
            return False

    engine = TerminalFixedEngine()
    manager = TaskManager(runner=engine)
    manager.submit_task(success_worker(), task_id="weather-1", name="weather_search")

    outcome = manager.cancel_task("weather-1")

    assert outcome.status == "already_terminal"
    assert engine.cancelled == ["weather-1"]
    assert "weather-1" not in manager._cancel_requested_task_ids


def test_cancel_task_returns_not_found_without_calling_engine() -> None:
    engine = FakeEngine()
    manager = TaskManager(runner=engine)

    outcome = manager.cancel_task("missing")

    assert outcome.status == "not_found"
    assert engine.cancelled == []


def test_cancel_task_returns_already_terminal_without_calling_engine() -> None:
    engine = FakeEngine()
    manager = TaskManager(runner=engine)
    manager.apply_created(TaskCreatedEvent(task_id="weather-1", name="weather_search"))
    manager.apply_event(TaskStartEvent(task_id="weather-1"))
    manager.apply_event(TaskSuccessEvent(task_id="weather-1", result="done"))

    outcome = manager.cancel_task("weather-1")

    assert outcome.status == "already_terminal"
    assert outcome.terminal_status == TaskStatus.SUCCESS
    assert engine.cancelled == []


@pytest.mark.asyncio
async def test_manager_run_projects_and_publishes_accepted_runner_events() -> None:
    engine = FakeEngine()
    engine.events = [
        TaskStartEvent(task_id="weather-1"),
        TaskSuccessEvent(task_id="weather-1", result="sunny"),
        TaskSuccessEvent(task_id="weather-1", result="late"),
    ]
    manager = TaskManager(runner=engine)
    manager.apply_created(TaskCreatedEvent(task_id="weather-1", name="weather_search"))

    await manager._consume_runner_events()

    first_event = await manager._event_output_recv.receive()
    second_event = await manager._event_output_recv.receive()
    task = manager.get_task("weather-1")

    assert isinstance(first_event, TaskStartEvent)
    assert isinstance(second_event, TaskSuccessEvent)
    assert second_event.result == "sunny"
    assert task is not None
    assert task.status == TaskStatus.SUCCESS
    assert task.result == "sunny"


@pytest.mark.asyncio
async def test_cancelled_event_from_engine_updates_manager_state() -> None:
    engine = FakeEngine()
    engine.events = [TaskCancelledEvent(task_id="weather-1", reason="user")]
    manager = TaskManager(runner=engine)
    manager.apply_created(TaskCreatedEvent(task_id="weather-1", name="weather_search"))

    await manager._consume_runner_events()

    task = manager.get_task("weather-1")
    assert task is not None
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_intent_rewrites_unseen_success_to_cancelled() -> None:
    engine = FakeEngine()
    engine.events = [TaskSuccessEvent(task_id="weather-1", result="sunny")]
    manager = TaskManager(runner=engine)
    manager.apply_created(TaskCreatedEvent(task_id="weather-1", name="weather_search"))
    manager.apply_event(TaskStartEvent(task_id="weather-1"))

    outcome = manager.cancel_task("weather-1")
    await manager._consume_runner_events()

    event = await manager._event_output_recv.receive()
    task = manager.get_task("weather-1")
    assert outcome.status == "accepted"
    assert engine.cancelled == ["weather-1"]
    assert isinstance(event, TaskCancelledEvent)
    assert event.task_id == "weather-1"
    assert task is not None
    assert task.status == TaskStatus.CANCELLED
    assert task.result is None
    assert "weather-1" not in manager._cancel_requested_task_ids


@pytest.mark.asyncio
async def test_cancel_intent_rewrites_unseen_failure_to_cancelled() -> None:
    engine = FakeEngine()
    engine.events = [TaskFailureEvent(task_id="weather-1", error="boom")]
    manager = TaskManager(runner=engine)
    manager.apply_created(TaskCreatedEvent(task_id="weather-1", name="weather_search"))
    manager.apply_event(TaskStartEvent(task_id="weather-1"))

    manager.cancel_task("weather-1")
    await manager._consume_runner_events()

    event = await manager._event_output_recv.receive()
    task = manager.get_task("weather-1")
    assert isinstance(event, TaskCancelledEvent)
    assert task is not None
    assert task.status == TaskStatus.CANCELLED
    assert task.error is None


@pytest.mark.asyncio
async def test_cancel_intent_still_publishes_start_and_progress_before_cancelled() -> None:
    engine = FakeEngine()
    engine.events = [
        TaskStartEvent(task_id="weather-1"),
        TaskProgressEvent(task_id="weather-1", progress="halfway"),
        TaskSuccessEvent(task_id="weather-1", result="sunny"),
    ]
    manager = TaskManager(runner=engine)
    manager.apply_created(TaskCreatedEvent(task_id="weather-1", name="weather_search"))

    manager.cancel_task("weather-1")
    await manager._consume_runner_events()

    first_event = await manager._event_output_recv.receive()
    second_event = await manager._event_output_recv.receive()
    third_event = await manager._event_output_recv.receive()
    task = manager.get_task("weather-1")

    assert isinstance(first_event, TaskStartEvent)
    assert isinstance(second_event, TaskProgressEvent)
    assert isinstance(third_event, TaskCancelledEvent)
    assert task is not None
    assert task.status == TaskStatus.CANCELLED
    assert task.trace == ["halfway"]
