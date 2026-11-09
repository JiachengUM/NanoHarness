import anyio
import pytest

from aicore.events.task import (
    TaskCancelledEvent,
    TaskFailureEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.runtime.task import TaskSuccess
from aicore.v2.stream_task_runner import DynamicStreamTaskRunner

pytestmark = pytest.mark.asyncio


def slow_success_worker():
    async def _run():
        await anyio.sleep(10)
        yield TaskSuccess(result="done")

    return _run


def immediate_success_worker():
    async def _run():
        yield TaskSuccess(result="done")
        yield TaskSuccess(result="late")

    return _run


async def collect_events(runner: DynamicStreamTaskRunner, events: list[object]):
    async for event in runner.astream():
        events.append(event)


async def wait_for_event(events: list[object], event_type: type):
    with anyio.fail_after(1):
        while True:
            for event in events:
                if isinstance(event, event_type):
                    return event

            await anyio.sleep(0)


async def wait_for_task_event(events: list[object], event_type: type, task_id: str):
    with anyio.fail_after(1):
        while True:
            for event in events:
                if isinstance(event, event_type) and event.task_id == task_id:
                    return event

            await anyio.sleep(0)


async def test_cancel_active_slow_task_emits_cancelled():
    runner = DynamicStreamTaskRunner()
    events: list[object] = []

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(collect_events, runner, events)

        task_id = runner.add_task(slow_success_worker(), task_id="slow")
        await wait_for_task_event(events, TaskStartEvent, task_id)

        assert runner.cancel_task(task_id) is True
        cancelled_event = await wait_for_event(events, TaskCancelledEvent)

        assert cancelled_event.task_id == task_id

        tg.cancel_scope.cancel()


async def test_cancel_active_task_does_not_emit_cancel_request_event():
    runner = DynamicStreamTaskRunner()
    events: list[object] = []

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(collect_events, runner, events)

        task_id = runner.add_task(slow_success_worker(), task_id="slow")
        await wait_for_task_event(events, TaskStartEvent, task_id)

        runner.cancel_task(task_id)
        cancelled_event = await wait_for_task_event(events, TaskCancelledEvent, task_id)

        assert cancelled_event.task_id == task_id
        assert [
            event
            for event in events
            if event.__class__.__name__ == "TaskCancelRequest"
        ] == []

        tg.cancel_scope.cancel()


async def test_cancel_active_worker_that_suppresses_cancel_does_not_emit_success():
    runner = DynamicStreamTaskRunner()
    events: list[object] = []
    worker_started = anyio.Event()
    worker_finalized = anyio.Event()

    def suppressing_worker():
        async def _run():
            worker_started.set()
            try:
                await anyio.sleep(10)
            except anyio.get_cancelled_exc_class():
                yield TaskSuccess(result="late-success")
            finally:
                worker_finalized.set()

        return _run

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(collect_events, runner, events)

        task_id = runner.add_task(suppressing_worker(), task_id="suppressed")
        await wait_for_task_event(events, TaskStartEvent, task_id)
        with anyio.fail_after(1):
            await worker_started.wait()

        runner.cancel_task(task_id)
        cancelled_event = await wait_for_task_event(events, TaskCancelledEvent, task_id)

        success_events = [
            event
            for event in events
            if isinstance(event, TaskSuccessEvent) and event.task_id == task_id
        ]

        assert worker_finalized.is_set()
        assert cancelled_event.task_id == task_id
        assert success_events == []
        assert [
            event
            for event in events
            if isinstance(event, TaskCancelledEvent) and event.task_id == task_id
        ] == [cancelled_event]

        tg.cancel_scope.cancel()


async def test_cancel_wins_when_worker_replaces_cancellation_with_error():
    runner = DynamicStreamTaskRunner()
    events: list[object] = []

    def failing_after_cancel_worker():
        async def _run():
            try:
                await anyio.sleep(10)
            except anyio.get_cancelled_exc_class():
                raise RuntimeError("late worker error")
            yield TaskSuccess(result="unreachable")

        return _run

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(collect_events, runner, events)

        task_id = runner.add_task(
            failing_after_cancel_worker(),
            task_id="cancel-before-error",
        )
        await wait_for_task_event(events, TaskStartEvent, task_id)
        runner.cancel_task(task_id)
        await wait_for_task_event(events, TaskCancelledEvent, task_id)

        terminals = [
            event
            for event in events
            if event.task_id == task_id
            and isinstance(event, (TaskSuccessEvent, TaskCancelledEvent))
        ]
        assert len(terminals) == 1
        assert isinstance(terminals[0], TaskCancelledEvent)
        assert not any(
            isinstance(event, TaskFailureEvent) and event.task_id == task_id
            for event in events
        )
        tg.cancel_scope.cancel()


async def test_cancel_unknown_task_is_no_op():
    runner = DynamicStreamTaskRunner()

    assert runner.cancel_task("missing") is False


async def test_cancel_after_success_is_no_op():
    """任务成功并完成清理后，cancel 明确报告终态已固定。"""
    runner = DynamicStreamTaskRunner()
    events: list[object] = []

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(collect_events, runner, events)

        task_id = runner.add_task(immediate_success_worker(), task_id="success")

        success_event = await wait_for_event(events, TaskSuccessEvent)
        await anyio.sleep(0.01)

        assert runner.cancel_task(task_id) is False

        assert success_event.task_id == task_id
        assert success_event.result == "done"

        tg.cancel_scope.cancel()


async def test_cancel_pending_task_before_run_emits_cancelled_without_starting_worker():
    runner = DynamicStreamTaskRunner()
    events: list[object] = []

    task_id = runner.add_task(slow_success_worker(), task_id="pending")
    assert runner.cancel_task(task_id) is True

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(collect_events, runner, events)

        cancelled_event = await wait_for_task_event(events, TaskCancelledEvent, task_id)
        await anyio.sleep(0)

        assert cancelled_event.task_id == task_id
        assert [
            event
            for event in events
            if isinstance(event, TaskStartEvent) and event.task_id == task_id
        ] == []
        assert task_id not in runner._entries

        tg.cancel_scope.cancel()
