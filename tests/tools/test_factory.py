import anyio
import pytest
from rich import print

from aicore.runtime.task import TaskSuccess
from aicore.tools.decorators.clarify import clarify_response
from aicore.utils.nl_repr import nl_repr_safe
from aicore.v2.tools.async_task import (
    AsyncableTaskTool,
    AsyncTaskReceipt,
    AsyncTaskResultBackfill,
)
from aicore.v2.tools.factory import create_tool
from tests.tools.async_task_test_support import (
    FakeTaskManager,
    WeatherInput,
    WeatherOutput,
    weather_worker,
)


pytestmark = pytest.mark.asyncio


def create_factory_weather_tool(task_manager: FakeTaskManager):
    return create_tool(
        name="天气查询工具",
        description="查询指定城市天气。缺少关键信息时返回澄清问题。",
        args_schema=WeatherInput,
        worker=weather_worker,
        asyncable="async",
        with_clarify=True,
        task_manager=task_manager,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("asyncable", ["async", "dynamic"])
async def test_factory_asyncable_requires_task_manager(asyncable):
    with pytest.raises(ValueError, match="task_manager"):
        create_tool(
            name="天气查询工具",
            description="查询指定城市天气。",
            args_schema=WeatherInput,
            worker=weather_worker,
            asyncable=asyncable,
        )


async def test_factory_fixed_async_and_clarify_schema():
    print("\n***** test_factory_fixed_async_and_clarify_schema *****")
    manager = FakeTaskManager()
    tool = create_factory_weather_tool(manager)
    fields = tool.args_schema.model_fields
    print(fields)

    assert "city" in fields
    assert "with_async" not in fields
    assert "reason" not in fields
    assert "description" in fields
    assert "clarify" in fields


async def test_factory_clarify_short_circuit():
    print("\n***** test_factory_clarify_short_circuit *****")
    manager = FakeTaskManager()
    tool = create_factory_weather_tool(manager)

    chunks = [
        chunk
        async for chunk in tool.stream_worker_factory(
            description="用户想查天气但缺少城市",
            clarify="请问要查询哪个城市？",
        )()
    ]
    print(chunks)

    assert len(chunks) == 1
    assert isinstance(chunks[0], TaskSuccess)
    assert chunks[0].result == clarify_response("请问要查询哪个城市？")
    assert manager.submitted == []


async def test_factory_async_receipt_and_backfill():
    print("\n***** test_factory_async_receipt_and_backfill *****")
    manager = FakeTaskManager()
    tool = create_factory_weather_tool(manager)

    chunks = [
        chunk
        async for chunk in tool.stream_worker_factory(
            city="香港",
            description="查询香港今日天气",
        )()
    ]
    print(chunks)

    assert len(chunks) == 1
    assert isinstance(chunks[0], TaskSuccess)
    assert isinstance(chunks[0].result, AsyncTaskReceipt)

    assert len(manager.submitted) == 1
    submitted = manager.submitted[0]
    assert submitted.name == "天气查询工具"
    assert submitted.arguments == {"city": "香港"}

    backfill_chunks = [chunk async for chunk in submitted.factory()]
    print(backfill_chunks)

    assert len(backfill_chunks) == 1
    assert isinstance(backfill_chunks[0], TaskSuccess)
    assert isinstance(backfill_chunks[0].result, AsyncTaskResultBackfill)

    backfill_text = nl_repr_safe(backfill_chunks[0].result)
    print(backfill_text)
    assert "[工具结果回灌]" in backfill_text
    assert submitted.task_id in backfill_text
    assert "香港" in backfill_text
    assert "晴" in backfill_text


async def test_factory_configures_sync_and_dynamic_modes():
    sync_tool = create_tool(
        name="同步天气查询工具",
        description="同步等待结果",
        args_schema=WeatherInput,
        worker=weather_worker,
        asyncable="sync",
    )
    assert isinstance(sync_tool, AsyncableTaskTool)
    assert sync_tool.asyncable == "sync"
    assert "with_async" not in sync_tool.args_schema.model_fields
    sync_result = await sync_tool.simple_worker(city="上海")()
    assert isinstance(sync_result, WeatherOutput)

    manager = FakeTaskManager()
    dynamic_tool = create_tool(
        name="动态天气查询工具",
        description="由模型选择同步或异步",
        args_schema=WeatherInput,
        worker=weather_worker,
        asyncable="dynamic",
        task_manager=manager,  # type: ignore[arg-type]
    )
    assert isinstance(dynamic_tool, AsyncableTaskTool)
    assert dynamic_tool.asyncable == "dynamic"
    fields = dynamic_tool.args_schema.model_fields
    assert {"with_async", "reason"}.issubset(fields)


async def main():
    for asyncable in ("async", "dynamic"):
        await test_factory_asyncable_requires_task_manager(asyncable)
    await test_factory_fixed_async_and_clarify_schema()
    await test_factory_clarify_short_circuit()
    await test_factory_async_receipt_and_backfill()
    await test_factory_configures_sync_and_dynamic_modes()


if __name__ == "__main__":
    anyio.run(main)
