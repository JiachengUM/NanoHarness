import anyio
import time
import random
import pytest

from aicore.v2.stream_task_runner import (
    DynamicStreamTaskRunner,
    TaskAStreamWorkerGeneral,
    TaskStartEvent, 
    TaskProgressEvent, 
    TaskSuccessEvent, 
    TaskFailureEvent, 
    TaskCancelledEvent,
    TaskProgress, 
    TaskSuccess,
)

from aicore.events.task import TaskEventPrinter

pytestmark = pytest.mark.asyncio


def mock_success_worker(value: int) -> TaskAStreamWorkerGeneral:
    """模拟一个成功的任务"""
    async def _run():
        await anyio.sleep(random.uniform(0.1, 0.5)) # 模拟随机耗时
        yield TaskProgress(progress=f"processing {value}")
        await anyio.sleep(random.uniform(0.1, 0.5)) # 模拟随机耗时
        yield TaskSuccess(result=value * 2)

    return _run


def mock_fail_worker() -> TaskAStreamWorkerGeneral:
    """模拟一个失败的任务"""
    async def _run():
        raise ValueError("Something went wrong!")
        yield TaskSuccess(result="Something went wrong!")

    return _run


async def test_basic_success_flow():
    runner = DynamicStreamTaskRunner(max_concurrency=2)

    printer = TaskEventPrinter()

    N = 10
    tasks = [mock_success_worker(i) for i in range(0, N)]

    results: list[None | int] = [None for i in range(0, N)]
    taskid_to_idx: dict[str, int] = {}

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)

        for i, task in enumerate(tasks):
            runner.add_task(task, task_id=f"task_{i}")
            taskid_to_idx[f"task_{i}"] = i

        async for event in runner.astream():
            printer(event)

            # 注意：runner.run() 是无限循环，必须手动 break，否则程序不会停            
            if isinstance(event, TaskSuccessEvent):
                results[taskid_to_idx[event.task_id]] = event.result

                # 如果所有任务都完成了，就取消任务组
                if all([r is not None for r in results]):
                    tg.cancel_scope.cancel()


def slow_worker(name: str):
    
    async def _run():
        try:
            for i in range(5):
                yield TaskProgress(progress=f"{name}: working {i}...")
                await anyio.sleep(1)
        except anyio.get_cancelled_exc_class():
            # 不做任何具体事情
            raise

    return _run


async def test_cancel():
    runner = DynamicStreamTaskRunner(max_concurrency=2)

    printer = TaskEventPrinter()

    async def _listen_output():
        async for event in runner.astream():
            printer(event)

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(_listen_output)

        runner.add_task(slow_worker("Task A"), "A")
        runner.add_task(slow_worker("Task B"), "B")
        # 如果此时结束，会打印出worker的全部过程

        await anyio.sleep(2)
        runner.cancel_task("A")
        # 如果此时结束，2秒钟之后的worker A的过程会缺失

        await anyio.sleep(1)
        runner.cancel_task("B")
        # 如果此时结束，3秒钟之后的worker B的过程会缺失

        tg.cancel_scope.cancel()
        


async def test_concurrency_limit():
    """测试 3: 并发限制 (CapacityLimiter)"""
    runner = DynamicStreamTaskRunner(max_concurrency=2)
    start_times = {}
    end_times = {}
    
    def make_tracking_worker(task_id):
        async def _run():
            start_times[task_id] = time.time()
            await anyio.sleep(0.2)
            end_times[task_id] = time.time()
            yield TaskSuccess(result="done")
        return _run

    events = []
    
    async def consumer():
        async for event in runner.astream():
            events.append(event)
            # 收集完所有 Success 就退出
            if sum(isinstance(e, TaskSuccessEvent) for e in events) == 3:
                break

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(consumer)
        
        # 几乎同时添加 3 个任务
        runner.add_task(make_tracking_worker("A"), task_id="A")
        runner.add_task(make_tracking_worker("B"), task_id="B")
        runner.add_task(make_tracking_worker("C"), task_id="C")
        
        # 等待完成
        await anyio.sleep(1)
        tg.cancel_scope.cancel()

    # 验证：A 和 B 应该几乎同时开始，C 应该晚 0.2秒左右开始
    assert abs(start_times["A"] - start_times["B"]) < 0.05
    assert start_times["C"] >= start_times["A"] + 0.15 # C 必须等待 A 或 B 完成


async def test_error_handling():
    """测试 4: 错误处理"""
    runner = DynamicStreamTaskRunner(max_concurrency=1)
    events = []

    async def consumer():
        async for event in runner.astream():
            events.append(event)
            if isinstance(event, TaskFailureEvent):
                break

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)
        tg.start_soon(consumer)
        
        runner.add_task(mock_fail_worker(), task_id="fail_task")
        await anyio.sleep(0.5)
        tg.cancel_scope.cancel()

    assert any(isinstance(e, TaskStartEvent) for e in events)
    assert any(isinstance(e, TaskFailureEvent) for e in events)
    failure_event = [e for e in events if isinstance(e, TaskFailureEvent)][0]
    assert "Something went wrong!" in failure_event.error


async def test_eof_without_success_emits_one_failure():
    runner = DynamicStreamTaskRunner(max_concurrency=1)
    events: list[object] = []

    async def worker():
        yield TaskProgress(progress="almost done")

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)

        async def consume():
            async for event in runner.astream():
                events.append(event)
                if isinstance(event, TaskFailureEvent):
                    return

        tg.start_soon(consume)
        runner.add_task(worker, task_id="missing-success")

        with anyio.fail_after(1):
            while not any(isinstance(event, TaskFailureEvent) for event in events):
                await anyio.sleep(0)
        tg.cancel_scope.cancel()

    terminals = [
        event
        for event in events
        if isinstance(event, (TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent))
    ]
    assert len(terminals) == 1
    assert isinstance(terminals[0], TaskFailureEvent)
    assert terminals[0].error == "Task completed without TaskSuccess"


async def test_success_drains_to_eof_holds_slot_and_ignores_late_events(caplog):
    runner = DynamicStreamTaskRunner(max_concurrency=1)
    events: list[object] = []
    drain_started = anyio.Event()
    release_drain = anyio.Event()
    worker_drained = anyio.Event()
    second_started = anyio.Event()

    async def draining_worker():
        try:
            yield TaskSuccess(result="first")
            drain_started.set()
            await release_drain.wait()
            yield TaskProgress(progress="late-progress")
            yield TaskSuccess(result="late-success")
        finally:
            worker_drained.set()

    async def second_worker():
        second_started.set()
        yield TaskSuccess(result="second")

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)

        async def consume():
            async for event in runner.astream():
                events.append(event)

        tg.start_soon(consume)
        runner.add_task(draining_worker, task_id="draining")
        runner.add_task(second_worker, task_id="second")

        with anyio.fail_after(1):
            await drain_started.wait()
        assert runner._entries["draining"].state == "draining"
        assert not second_started.is_set()

        # Success is already the business terminal, so a late cancel is a no-op.
        assert runner.cancel_task("draining") is False
        release_drain.set()

        with anyio.fail_after(1):
            await worker_drained.wait()
            await second_started.wait()
            while "draining" in runner._entries:
                await anyio.sleep(0)
        tg.cancel_scope.cancel()

    draining_events = [
        event for event in events if getattr(event, "task_id", None) == "draining"
    ]
    terminals = [
        event
        for event in draining_events
        if isinstance(event, (TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent))
    ]
    assert len(terminals) == 1
    assert isinstance(terminals[0], TaskSuccessEvent)
    assert terminals[0].result == "first"
    assert not any(isinstance(event, TaskProgressEvent) for event in draining_events)
    assert "Ignoring TaskProgress after TaskSuccess" in caplog.text
    assert "Ignoring duplicate TaskSuccess" in caplog.text


async def test_exception_after_success_is_cleanup_warning_not_failure(caplog):
    runner = DynamicStreamTaskRunner(max_concurrency=1)
    events: list[object] = []

    async def worker():
        yield TaskSuccess(result="done")
        raise RuntimeError("cleanup exploded")

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.run)

        async def consume():
            async for event in runner.astream():
                events.append(event)

        tg.start_soon(consume)
        runner.add_task(worker, task_id="cleanup-error")

        with anyio.fail_after(1):
            while (
                "cleanup-error" in runner._entries
                or not any(isinstance(event, TaskSuccessEvent) for event in events)
            ):
                await anyio.sleep(0)
        tg.cancel_scope.cancel()

    terminals = [
        event
        for event in events
        if isinstance(event, (TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent))
    ]
    assert len(terminals) == 1
    assert isinstance(terminals[0], TaskSuccessEvent)
    assert "Task cleanup failed after TaskSuccess" in caplog.text
    assert "cleanup exploded" in caplog.text


async def main():
    #await test_basic_success_flow()
    await test_cancel()
    #await test_full_lifecycle()
    #await test_concurrency_limit()
    #await test_error_handling()

if __name__ == "__main__":
    anyio.run(main)
