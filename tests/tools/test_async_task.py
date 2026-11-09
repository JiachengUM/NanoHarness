import anyio
import pytest
from rich import print

from aicore.runtime.task import TaskSuccess
from aicore.tools import TaskTool
from aicore.utils.nl_repr import nl_repr_safe
from aicore.v2.tools.async_task import (
    Asyncable,
    AsyncableTaskTool,
    AsyncTaskReceipt,
    AsyncTaskResultBackfill,
)
from tests.tools.async_task_test_support import (
    FakeTaskManager,
    WeatherInput,
    WeatherOutput,
    weather_worker,
)


pytestmark = pytest.mark.asyncio


def create_weather_tool(
    task_manager: FakeTaskManager,
    *,
    asyncable: Asyncable = "async",
):
    base_tool = TaskTool[WeatherInput, WeatherOutput, str, ...](
        name="天气查询工具",
        description="查询指定城市天气",
        args_schema=WeatherInput,
        worker=weather_worker,
    )
    return AsyncableTaskTool(
        base_tool,
        asyncable=asyncable,
        task_id_factory=lambda: "task-001",
        task_manager=task_manager,  # type: ignore[arg-type]
    )


async def test_async_stream_submits_task_and_returns_receipt_only():
    print("\n***** test_async_stream_submits_task_and_returns_receipt_only *****")
    manager = FakeTaskManager()
    tool = create_weather_tool(manager)

    chunks = [chunk async for chunk in tool.stream_worker_factory(city="香港")()]
    print(chunks)

    assert len(chunks) == 1
    assert isinstance(chunks[0], TaskSuccess)
    assert isinstance(chunks[0].result, AsyncTaskReceipt)
    assert chunks[0].result.task_id == "task-001"

    assert len(manager.submitted) == 1
    submitted = manager.submitted[0]
    assert submitted.task_id == "task-001"
    assert submitted.name == "天气查询工具"
    assert submitted.arguments == {"city": "香港"}


async def test_async_receipt_nl_repr():
    print("\n***** test_async_receipt_nl_repr *****")
    manager = FakeTaskManager()
    tool = create_weather_tool(manager)
    receipt = await tool.simple_worker(city="香港")()
    text = nl_repr_safe(receipt)
    print(text)

    assert isinstance(receipt, AsyncTaskReceipt)
    assert "[占位回执]" in text
    assert "天气查询工具" in text
    assert "task-001" in text
    assert len(manager.submitted) == 1


async def test_async_backfill_nl_repr():
    print("\n***** test_async_backfill_nl_repr *****")
    manager = FakeTaskManager()
    tool = create_weather_tool(manager)
    chunks = [chunk async for chunk in tool.stream_worker_factory(city="香港")()]
    print(chunks)

    assert len(manager.submitted) == 1
    backfill_chunks = [chunk async for chunk in manager.submitted[0].factory()]
    print(backfill_chunks)

    assert len(backfill_chunks) == 1
    assert isinstance(backfill_chunks[0], TaskSuccess)
    assert isinstance(backfill_chunks[0].result, AsyncTaskResultBackfill)

    text = nl_repr_safe(backfill_chunks[0].result)
    print(text)
    assert "[工具结果回灌]" in text
    assert "task-001" in text
    assert "天气查询工具" in text
    assert "香港" in text
    assert "晴" in text


async def test_asyncable_tool_exposes_mode_and_selects_execution_path():
    manager = FakeTaskManager()
    tool = create_weather_tool(manager, asyncable="dynamic")
    second_tool = create_weather_tool(FakeTaskManager(), asyncable="dynamic")

    fields = tool.args_schema.model_fields
    assert tool.args_schema is second_tool.args_schema
    assert "with_async" in fields
    assert fields["with_async"].default is False
    assert fields["reason"].is_required()

    inline_chunks = [
        chunk
        async for chunk in tool.stream_worker_factory(
            city="上海",
            with_async=False,
            reason="当前回复需要天气结果",
        )()
    ]
    assert len(inline_chunks) == 1
    assert isinstance(inline_chunks[0], TaskSuccess)
    assert isinstance(inline_chunks[0].result, WeatherOutput)
    assert manager.submitted == []

    async_chunks = [
        chunk
        async for chunk in tool.stream_worker_factory(
            city="香港",
            with_async=True,
            reason="查询结果可稍后回灌",
        )()
    ]
    assert len(async_chunks) == 1
    assert isinstance(async_chunks[0], TaskSuccess)
    assert isinstance(async_chunks[0].result, AsyncTaskReceipt)
    assert manager.submitted[0].arguments == {"city": "香港"}


async def main():
    await test_async_stream_submits_task_and_returns_receipt_only()
    await test_async_receipt_nl_repr()
    await test_async_backfill_nl_repr()
    await test_asyncable_tool_exposes_mode_and_selects_execution_path()


if __name__ == "__main__":
    anyio.run(main)
