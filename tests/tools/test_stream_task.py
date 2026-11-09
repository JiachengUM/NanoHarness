from typing import AsyncGenerator, Any

import anyio

from rich import print
from pydantic import BaseModel, Field

from aicore.core.types import SafeResult
from aicore.events.react import TaskToolDoneEvent
from aicore.events.task import (
    TaskEvent,
    TaskFailureEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.tools import TaskProgress, TaskSuccess, create_tool
from aicore.tools.runner import StreamTaskToolRunner


class DummyInput(BaseModel):
    input: str = Field(..., description="输入字符串")


def make_stream_worker(
    *,
    progress_list: list[str],
    delay: float = 0.01,
    raise_error: Exception | None = None,
    name: str | None = None,
) -> Any:
    async def worker(
        input: str,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[str], None]:
        for progress in progress_list:
            await anyio.sleep(delay)
            yield TaskProgress(progress=progress)

        if raise_error is not None:
            raise raise_error

        result = f"{name}: {input.upper()}" if name else input.upper()
        yield TaskSuccess(result=result)

    return worker


def dummy_tool(
    *,
    progress_list: list[str],
    timeout: float | None = None,
    raise_error: Exception | None = None,
    delay: float = 0.01,
    name: str | None = None,
):
    return create_tool(
        name=name or "字符串工具",
        description="将输入转换为大写",
        args_schema=DummyInput,
        worker=make_stream_worker(
            progress_list=progress_list,
            delay=delay,
            raise_error=raise_error,
            name=name,
        ),
        timeout=timeout,
    )


async def test_stream_worker_factory_basic() -> None:
    print("\n***** test_stream_worker_factory_basic *****")

    tool = dummy_tool(progress_list=["Step 1", "Step 2"])
    factory = tool.stream_worker_factory(input="hello")

    chunks: list[TaskProgress[str] | TaskSuccess[str]] = []
    async for chunk in factory():
        print(chunk)
        chunks.append(chunk)

    assert len(chunks) == 3
    assert isinstance(chunks[0], TaskProgress)
    assert chunks[0].progress == "Step 1"
    assert isinstance(chunks[1], TaskProgress)
    assert chunks[1].progress == "Step 2"
    assert isinstance(chunks[2], TaskSuccess)
    assert chunks[2].result == "HELLO"


async def test_stream_task_runner_success() -> None:
    print("\n***** test_stream_task_runner_success *****")

    runner = StreamTaskToolRunner()
    runner.add_tool(
        dummy_tool(progress_list=["A1", "A2"], name="A"),
        {"input": "alpha"},
    )
    runner.add_tool(
        dummy_tool(progress_list=["B1"], name="B"),
        {"input": "beta"},
    )

    events: list[TaskEvent | TaskToolDoneEvent[Any]] = []
    async for event in runner.run():
        print(event)
        events.append(event)

    assert sum(isinstance(event, TaskStartEvent) for event in events) == 2
    assert sum(isinstance(event, TaskProgressEvent) for event in events) == 3
    assert sum(isinstance(event, TaskSuccessEvent) for event in events) == 2
    assert sum(isinstance(event, TaskToolDoneEvent) for event in events) == 2

    final = runner.results
    assert final == [
        SafeResult(data="A: ALPHA"),
        SafeResult(data="B: BETA"),
    ]
    assert runner.tool_results == ["A: ALPHA", "B: BETA"]


async def test_stream_task_runner_failure() -> None:
    print("\n***** test_stream_task_runner_failure *****")

    runner = StreamTaskToolRunner()
    runner.add_tool(
        dummy_tool(
            progress_list=["before error"],
            raise_error=ValueError("boom"),
        ),
        {"input": "hello"},
    )

    events: list[TaskEvent | TaskToolDoneEvent[Any]] = []
    async for event in runner.run():
        print(event)
        events.append(event)

    assert any(isinstance(event, TaskStartEvent) for event in events)
    assert any(isinstance(event, TaskProgressEvent) for event in events)
    failure_events = [
        event for event in events if isinstance(event, TaskFailureEvent)
    ]
    assert len(failure_events) == 1
    assert "boom" in failure_events[0].error
    assert not any(isinstance(event, TaskToolDoneEvent) for event in events)

    final = runner.results
    assert len(final) == 1
    assert not final[0].is_success
    assert "boom" in (final[0].error or "")


async def test_stream_task_runner_timeout() -> None:
    print("\n***** test_stream_task_runner_timeout *****")

    runner = StreamTaskToolRunner()
    runner.add_tool(
        dummy_tool(
            progress_list=["slow step"],
            delay=0.2,
            timeout=0.05,
        ),
        {"input": "hello"},
    )

    events: list[TaskEvent | TaskToolDoneEvent[Any]] = []
    async for event in runner.run():
        print(event)
        events.append(event)

    failure_events = [
        event for event in events if isinstance(event, TaskFailureEvent)
    ]
    assert len(failure_events) == 1
    assert "超时" in failure_events[0].error

    final = runner.results
    assert len(final) == 1
    assert not final[0].is_success
    assert "超时" in (final[0].error or "")


async def main() -> None:
    await test_stream_worker_factory_basic()
    await test_stream_task_runner_success()
    await test_stream_task_runner_failure()
    await test_stream_task_runner_timeout()
    print("\n[bold green]stream task 测试全部通过[/bold green]")


if __name__ == "__main__":
    anyio.run(main)
