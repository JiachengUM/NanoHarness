from datetime import datetime

import anyio
import pytest

import aicore.v2.experiments.task_cancel_tool_v1 as task_cancel_v1_module
from aicore.events.react import TaskToolDoneEvent
from aicore.models.model_api import ModelParams
from aicore.runtime.task import (
    TaskCancelOutcome,
    TaskManager,
    TaskProjection,
    TaskStatus,
    TaskSuccess,
)
from aicore.tools.protocol import TaskToolProtocol
from aicore.tools.runner import StreamTaskToolRunner
from aicore.v2.experiments.react_agent_with_task_runner import (
    ReactAgentWithTaskRunnerContext,
)
from aicore.v2.experiments.task_cancel_tool_v1 import (
    CancelTaskCommand,
    create_task_cancel_tool,
)
from aicore.v2.experiments.task_cancel_eval.cases import (
    CANCEL_TOOL_CASES,
)
from aicore.v2.experiments.task_cancel_eval.eval import (
    build_v1_agent,
    build_v1_tools,
)
from aicore.v2.tools.async_task import AsyncTaskReceipt

pytestmark = pytest.mark.asyncio


async def test_v1_documents_why_target_hint_is_only_an_evaluation_variant() -> None:
    module_doc = task_cancel_v1_module.__doc__ or ""

    assert "后台 matcher 二次解析" in module_doc
    assert "信息损失" in module_doc
    assert "只保留用于对比评测" in module_doc
    assert "精确 ``task_id``" in module_doc


def projection(
    task_id: str,
    tool_name: str,
    arguments: dict[str, object],
) -> TaskProjection:
    now = datetime.now()
    return TaskProjection(
        task_id=task_id,
        tool_name=tool_name,
        arguments=arguments,
        status=TaskStatus.RUNNING,
        created_at=now,
        updated_at=now,
    )


class FakeTaskManager:
    def __init__(self) -> None:
        self.projections = {
            "w1": projection("w1", "weather_search", {"city": "香港"}),
            "p1": projection("p1", "poi_search", {"city": "上海", "type": "酒店"}),
        }
        self.cancelled_ids: list[str] = []

    def get_active_task_projections(self) -> list[TaskProjection]:
        return list(self.projections.values())

    def get_projection(self, task_id: str) -> TaskProjection | None:
        return self.projections.get(task_id)

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        self.cancelled_ids.append(task_id)
        return TaskCancelOutcome(status="accepted", task_id=task_id)


def build_cancel_tool() -> tuple[TaskToolProtocol, FakeTaskManager]:
    manager = FakeTaskManager()
    return create_task_cancel_tool(task_manager=manager), manager


async def test_task_cancel_tool_returns_observation_text():
    tool, manager = build_cancel_tool()

    worker = tool.simple_worker(target_hint="weather_search")
    result = await worker()

    assert result == "[已取消] weather_search(city=香港)"
    assert manager.cancelled_ids == ["w1"]


async def test_task_cancel_tool_schema_does_not_include_task_id():
    tool, _ = build_cancel_tool()

    schema = tool.args_schema.model_json_schema()

    assert "target_hint" in schema["properties"]
    assert "user_utterance" not in schema["properties"]
    assert "task_id" not in schema["properties"]
    assert "scope" not in schema["properties"]


async def test_task_cancel_tool_model_dump_excludes_worker_dependency():
    tool, _ = build_cancel_tool()
    inner_tool = getattr(tool, "inner_tool", tool)

    dump = inner_tool.model_dump()

    assert not hasattr(tool, "_service")
    assert not hasattr(inner_tool, "_service")
    assert "worker" not in dump
    assert "stream_worker" not in dump


async def test_task_cancel_tool_satisfies_task_tool_protocol_for_react_context():
    tool, _ = build_cancel_tool()

    assert isinstance(tool, TaskToolProtocol)

    context = ReactAgentWithTaskRunnerContext(
        system_prompt="system",
        model_params=ModelParams(model="fake-model"),
        tools=[tool],
    )

    assert context.tools == [tool]
    assert context.tool_defs is not None
    assert context.tool_defs[0].name == "cancel_task"


async def test_task_cancel_tool_runs_through_stream_tool_runner():
    tool, manager = build_cancel_tool()
    stream_runner = StreamTaskToolRunner()

    stream_runner.add_tool(
        tool,
        CancelTaskCommand(target_hint="weather_search"),
    )
    events = [event async for event in stream_runner.run()]

    done_events = [event for event in events if isinstance(event, TaskToolDoneEvent)]
    assert len(done_events) == 1
    assert done_events[0].output.data == "[已取消] weather_search(city=香港)"
    assert stream_runner.tool_results == ["[已取消] weather_search(city=香港)"]
    assert manager.cancelled_ids == ["w1"]


async def test_target_hint_tool_has_shared_evaluation_adapter():
    manager = TaskManager()
    case = CANCEL_TOOL_CASES["running_task_cancel"]

    tools = build_v1_tools(manager, case)
    agent = build_v1_agent(manager, case)

    assert {tool.name for tool in tools} == {
        "天气查询工具",
        "地点搜索工具",
        "car_control",
        "cancel_task",
    }
    assert agent.context.ambient_context_provider is not None
    assert agent.context.system_prompt


async def test_target_hint_tool_cancels_shared_simulated_task():
    manager = TaskManager()
    tools = build_v1_tools(
        manager,
        CANCEL_TOOL_CASES["running_task_cancel"],
    )
    poi_tool = next(tool for tool in tools if tool.name == "地点搜索工具")
    cancel_tool = next(tool for tool in tools if tool.name == "cancel_task")

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

        assert len(events) == 1
        assert isinstance(events[0], TaskSuccess)
        receipt = events[0].result
        assert isinstance(receipt, AsyncTaskReceipt)
        with anyio.fail_after(1):
            while (
                projection := manager.get_projection(receipt.task_id)
            ) is None or projection.status != TaskStatus.RUNNING:
                await anyio.sleep(0)

        result = await cancel_tool.simple_worker(target_hint="酒店")()

        assert result.startswith("[已取消] 地点搜索工具(")
        with anyio.fail_after(1):
            while (
                projection := manager.get_projection(receipt.task_id)
            ) is None or projection.status != TaskStatus.CANCELLED:
                await anyio.sleep(0)
        assert manager.get_active_tasks() == []
        task_group.cancel_scope.cancel()
