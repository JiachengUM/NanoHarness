from collections.abc import AsyncGenerator

import anyio
import pytest
from pydantic import BaseModel

from aicore.runtime.task import TaskProgress, TaskSuccess
from aicore.tools.task import TaskTool
from aicore.tools.task_worker import bind_task_tool_worker


pytestmark = pytest.mark.asyncio


class _Input(BaseModel):
    value: str


def _make_tool(
    worker,
    *,
    timeout: float | None = None,
    on_error=None,
) -> TaskTool:
    return TaskTool(
        name="test_tool",
        description="test",
        args_schema=_Input,
        stream_worker=worker,
        timeout=timeout,
        on_error=on_error,
    )


async def test_bind_task_tool_worker_applies_timeout_to_real_worker():
    async def worker(value: str) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[str], None]:
        await anyio.sleep(1)
        yield TaskSuccess(result=value)

    bound = bind_task_tool_worker(
        _make_tool(worker, timeout=0.01),
        _Input(value="result"),
    )

    with pytest.raises(TimeoutError, match="任务 test_tool 超时"):
        async for _ in bound():
            pass


async def test_bind_task_tool_worker_applies_on_error_to_real_worker():
    async def worker(value: str) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[str], None]:
        raise ValueError(f"bad {value}")
        yield TaskSuccess(result=value)

    bound = bind_task_tool_worker(
        _make_tool(worker, on_error=lambda exc: f"mapped: {exc}"),
        _Input(value="input"),
    )

    with pytest.raises(RuntimeError, match="mapped: bad input"):
        async for _ in bound():
            pass


async def test_bind_task_tool_worker_does_not_map_cancellation_to_tool_error():
    on_error_calls: list[Exception] = []
    cancelled_exc = anyio.get_cancelled_exc_class()

    async def worker(value: str) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[str], None]:
        raise cancelled_exc()
        yield TaskSuccess(result=value)

    bound = bind_task_tool_worker(
        _make_tool(worker, on_error=lambda exc: on_error_calls.append(exc) or "mapped"),
        _Input(value="input"),
    )

    with pytest.raises(cancelled_exc):
        async for _ in bound():
            pass
    assert on_error_calls == []
