from __future__ import annotations

import anyio
import pytest
from pydantic import BaseModel

from aicore.events.react import TaskToolDoneEvent
from aicore.models.model_api import ModelParams
from aicore.runtime.task import (
    TaskCancelOutcome,
    TaskManager,
    TaskStatus,
    TaskSuccess,
)
from aicore.tools.protocol import TaskToolProtocol
from aicore.tools.run import ToolRunResult
from aicore.tools.runner import StreamTaskToolRunner
from aicore.utils.nl_repr import nl_repr
from aicore.v2.experiments.react_agent_with_task_runner import (
    ReactAgentWithTaskRunnerContext,
)
from aicore.v2.experiments.task_cancel_eval.cases import (
    CANCEL_TOOL_CASES,
    build_simulated_business_tools,
)
from aicore.v2.experiments.task_cancel_tool_v0 import (
    TaskCancelCommandV0,
    create_task_cancel_tool_v0,
)
from aicore.v2.experiments.task_cancel_eval.eval import (
    V0_SYSTEM_PROMPT,
    build_v0_agent,
    build_v0_tools,
)
from aicore.v2.tools.async_task import AsyncTaskReceipt
from aicore.v2.tools.factory import create_tool


class FakeTaskManager:
    def __init__(self, outcome: TaskCancelOutcome | None = None) -> None:
        self.outcome = outcome
        self.cancelled_ids: list[str] = []

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        self.cancelled_ids.append(task_id)
        return self.outcome or TaskCancelOutcome(status="accepted", task_id=task_id)


def build_tool(
    outcome: TaskCancelOutcome | None = None,
) -> tuple[TaskToolProtocol, FakeTaskManager]:
    manager = FakeTaskManager(outcome)
    return create_task_cancel_tool_v0(task_manager=manager), manager  # type: ignore[arg-type]


def test_v0_schema_only_requires_task_id() -> None:
    schema = TaskCancelCommandV0.model_json_schema()

    assert set(schema["properties"]) == {"task_id"}
    assert schema["required"] == ["task_id"]
    assert schema["properties"]["task_id"]["minLength"] == 1
    description = schema["properties"]["task_id"]["description"]
    assert "task_id" in description
    assert "占位回执" not in description
    assert "call_id" not in description


@pytest.mark.asyncio
async def test_v0_passes_task_id_directly_to_manager() -> None:
    tool, manager = build_tool()

    result = await tool.simple_worker(task_id="weather-1")()

    assert result == "[已取消] task_id=weather-1"
    assert manager.cancelled_ids == ["weather-1"]


@pytest.mark.asyncio
async def test_v0_uses_receipt_task_id_instead_of_function_call_id() -> None:
    receipt = AsyncTaskReceipt(
        task_id="task-weather-1",
        tool_name="weather_search",
    )
    function_call_result = ToolRunResult(
        run_id="call-provider-1",
        output=nl_repr(receipt),
    )
    tool, manager = build_tool()

    result = await tool.simple_worker(task_id=receipt.task_id)()

    assert function_call_result.run_id != receipt.task_id
    assert "task-weather-1" in function_call_result.output
    assert result == "[已取消] task_id=task-weather-1"
    assert manager.cancelled_ids == ["task-weather-1"]


@pytest.mark.asyncio
async def test_v0_closes_loop_from_async_receipt_without_active_context() -> None:
    class SearchCommand(BaseModel):
        city: str

    async def search_worker(city: str) -> str:
        return f"{city}查询完成"

    manager = TaskManager()
    search_tool = create_tool(
        name="search",
        description="查询",
        args_schema=SearchCommand,
        worker=search_worker,
        asyncable="async",
        task_manager=manager,
    )
    receipt_events = [
        event
        async for event in search_tool.stream_worker_factory(city="上海")()
    ]

    assert len(receipt_events) == 1
    assert isinstance(receipt_events[0], TaskSuccess)
    receipt = receipt_events[0].result
    assert isinstance(receipt, AsyncTaskReceipt)

    cancel_tool = create_task_cancel_tool_v0(task_manager=manager)
    result = await cancel_tool.simple_worker(task_id=receipt.task_id)()

    assert result == f"[已取消] task_id={receipt.task_id}"


def test_v0_evaluation_uses_shared_cases_without_ambient_task_state() -> None:
    manager = TaskManager()
    tools = build_v0_tools(manager)
    agent = build_v0_agent(
        manager,
        CANCEL_TOOL_CASES["running_task_cancel"],
    )

    assert {tool.name for tool in tools} == {
        "天气查询工具",
        "地点搜索工具",
        "car_control",
        "cancel_task",
    }
    assert agent.context.ambient_context_provider is None
    assert agent.context.system_prompt == V0_SYSTEM_PROMPT
    assert "占位回执" in V0_SYSTEM_PROMPT
    assert "根据历史业务工具调用和占位回执找到目标 task_id" in V0_SYSTEM_PROMPT
    assert "call_id" not in V0_SYSTEM_PROMPT
    assert "target_hint" not in V0_SYSTEM_PROMPT
    assert "取消范围必须由用户明确授权" in V0_SYSTEM_PROMPT
    assert "不能把未指明目标或数量的取消意图推断为取消多个任务" in V0_SYSTEM_PROMPT
    assert "明确逐一指出多个目标" in V0_SYSTEM_PROMPT
    assert "一次取消意图最多授权取消一个任务" in V0_SYSTEM_PROMPT
    assert "有多个可能目标且无法唯一识别时，直接询问" in V0_SYSTEM_PROMPT


async def _wait_for_status(
    manager: TaskManager,
    task_id: str,
    expected: TaskStatus,
) -> None:
    with anyio.fail_after(1):
        while True:
            projection = manager.get_projection(task_id)
            if projection is not None and projection.status == expected:
                return
            await anyio.sleep(0)


@pytest.mark.asyncio
async def test_simulated_running_business_task_is_cancelled_by_v0() -> None:
    manager = TaskManager()
    tools = build_simulated_business_tools(
        task_manager=manager,
        case=CANCEL_TOOL_CASES["running_task_cancel"],
    )
    poi_tool = next(tool for tool in tools if tool.name == "地点搜索工具")
    cancel_tool = create_task_cancel_tool_v0(task_manager=manager)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(manager.run)
        events = [
            event
            async for event in poi_tool.stream_worker_factory(
                query="酒店",
                city="上海",
                address="徐家汇",
                criteria=["人均100左右"],
                radius=3000,
            )()
        ]
        receipt = events[0].result
        assert isinstance(receipt, AsyncTaskReceipt)
        await _wait_for_status(manager, receipt.task_id, TaskStatus.RUNNING)

        result = await cancel_tool.simple_worker(task_id=receipt.task_id)()

        assert result == f"[已取消] task_id={receipt.task_id}"
        await _wait_for_status(manager, receipt.task_id, TaskStatus.CANCELLED)
        assert manager.get_active_tasks() == []

        second_result = await cancel_tool.simple_worker(task_id=receipt.task_id)()
        assert second_result == (
            f"[无需取消] task_id={receipt.task_id} 已经结束"
        )
        task_group.cancel_scope.cancel()


@pytest.mark.asyncio
async def test_simulated_multiple_tasks_cancel_only_receipt_target() -> None:
    manager = TaskManager()
    tools = build_simulated_business_tools(
        task_manager=manager,
        case=CANCEL_TOOL_CASES["targeted_cancel_one_of_many"],
    )
    weather_tool = next(tool for tool in tools if tool.name == "天气查询工具")
    poi_tool = next(tool for tool in tools if tool.name == "地点搜索工具")
    cancel_tool = create_task_cancel_tool_v0(task_manager=manager)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(manager.run)
        weather_events = [
            event
            async for event in weather_tool.stream_worker_factory(
                query="香港今天的天气",
                criteria=[],
            )()
        ]
        poi_events = [
            event
            async for event in poi_tool.stream_worker_factory(
                query="酒店",
                city="上海",
                address="徐家汇",
                criteria=["人均100左右"],
                radius=3000,
            )()
        ]
        weather_receipt = weather_events[0].result
        poi_receipt = poi_events[0].result
        assert isinstance(weather_receipt, AsyncTaskReceipt)
        assert isinstance(poi_receipt, AsyncTaskReceipt)
        await _wait_for_status(
            manager,
            weather_receipt.task_id,
            TaskStatus.RUNNING,
        )
        await _wait_for_status(manager, poi_receipt.task_id, TaskStatus.RUNNING)

        result = await cancel_tool.simple_worker(
            task_id=poi_receipt.task_id
        )()

        assert result == f"[已取消] task_id={poi_receipt.task_id}"
        await _wait_for_status(
            manager,
            poi_receipt.task_id,
            TaskStatus.CANCELLED,
        )
        weather_projection = manager.get_projection(weather_receipt.task_id)
        assert weather_projection is not None
        assert weather_projection.status == TaskStatus.RUNNING
        await cancel_tool.simple_worker(task_id=weather_receipt.task_id)()
        task_group.cancel_scope.cancel()


@pytest.mark.asyncio
async def test_simulated_terminal_case_returns_already_finished() -> None:
    manager = TaskManager()
    tools = build_simulated_business_tools(
        task_manager=manager,
        case=CANCEL_TOOL_CASES["cancel_already_terminal_task"],
    )
    weather_tool = next(tool for tool in tools if tool.name == "天气查询工具")
    cancel_tool = create_task_cancel_tool_v0(task_manager=manager)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(manager.run)
        events = [
            event
            async for event in weather_tool.stream_worker_factory(
                query="香港今天的天气",
                criteria=[],
            )()
        ]
        receipt = events[0].result
        assert isinstance(receipt, AsyncTaskReceipt)
        await _wait_for_status(manager, receipt.task_id, TaskStatus.SUCCESS)

        result = await cancel_tool.simple_worker(task_id=receipt.task_id)()

        assert result == f"[无需取消] task_id={receipt.task_id} 已经结束"
        task_group.cancel_scope.cancel()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            TaskCancelOutcome(
                status="already_terminal",
                task_id="weather-1",
                terminal_status=TaskStatus.SUCCESS,
            ),
            "[无需取消] task_id=weather-1 已经结束",
        ),
        (
            TaskCancelOutcome(status="not_found", task_id="missing"),
            "[取消失败] task_id=missing: 不存在",
        ),
        (
            TaskCancelOutcome(
                status="failed",
                task_id="weather-1",
                reason="runner unavailable",
            ),
            "[取消失败] task_id=weather-1: runner unavailable",
        ),
    ],
)
@pytest.mark.asyncio
async def test_v0_formats_non_accepted_outcomes(
    outcome: TaskCancelOutcome,
    expected: str,
) -> None:
    tool, manager = build_tool(outcome)

    result = await tool.simple_worker(task_id=outcome.task_id)()

    assert result == expected
    assert manager.cancelled_ids == [outcome.task_id]


def test_v0_has_no_clarify_wrapper_or_extra_schema_fields() -> None:
    tool, _ = build_tool()

    assert tool.name == "cancel_task"
    assert tool.asyncable == "sync"
    assert tool.args_schema is TaskCancelCommandV0
    assert set(tool.args_schema.model_json_schema()["properties"]) == {"task_id"}
    assert "占位回执" not in tool.description
    assert "占位回执" not in (
        tool.args_schema.model_json_schema()["properties"]["task_id"]["description"]
    )
    assert "当前活跃任务" not in tool.description


def test_v0_satisfies_react_tool_protocol() -> None:
    tool, _ = build_tool()

    assert isinstance(tool, TaskToolProtocol)

    context = ReactAgentWithTaskRunnerContext(
        system_prompt="system",
        model_params=ModelParams(model="fake-model"),
        tools=[tool],
    )

    assert context.tool_defs is not None
    assert context.tool_defs[0].name == "cancel_task"
    assert context.tools is not None
    assert set(context.tools[0].args_schema.model_json_schema()["properties"]) == {
        "task_id"
    }


@pytest.mark.asyncio
async def test_v0_runs_through_stream_tool_runner() -> None:
    tool, manager = build_tool()
    runner = StreamTaskToolRunner()

    runner.add_tool(tool, TaskCancelCommandV0(task_id="poi-1"))
    events = [event async for event in runner.run()]

    done_events = [
        event for event in events if isinstance(event, TaskToolDoneEvent)
    ]
    assert len(done_events) == 1
    assert done_events[0].output.data == "[已取消] task_id=poi-1"
    assert runner.tool_results == ["[已取消] task_id=poi-1"]
    assert manager.cancelled_ids == ["poi-1"]
