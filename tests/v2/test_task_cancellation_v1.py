"""保留 target_hint v1 实验实现的低层回归测试。"""

from datetime import datetime
import inspect

import pytest

from aicore.events.task import TaskCreatedEvent, TaskStartEvent
from aicore.runtime.task import (
    TaskCancelOutcome,
    TaskManager,
    TaskProjection,
    TaskStatus,
)
import aicore.v2.experiments.task_cancel_tool_v1 as task_cancel_module
from aicore.v2.experiments.task_cancel_tool_v1 import (
    CancelTaskCommand,
    TaskCancelWorker,
    create_task_cancel_tool,
)


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


def default_projections() -> list[TaskProjection]:
    return [
        projection("w1", "weather_search", {"city": "香港"}),
        projection("p1", "poi_search", {"city": "上海", "type": "酒店"}),
    ]


class FakeTaskManager:
    def __init__(
        self,
        *,
        projections: list[TaskProjection] | None = None,
        statuses: dict[str, str] | None = None,
        reasons: dict[str, str] | None = None,
    ) -> None:
        self.projections = (
            default_projections() if projections is None else projections
        )
        self.statuses = statuses or {}
        self.reasons = reasons or {}
        self.cancelled_ids: list[str] = []

    def get_active_task_projections(self) -> list[TaskProjection]:
        return self.projections

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        self.cancelled_ids.append(task_id)
        return TaskCancelOutcome(
            status=self.statuses.get(task_id, "accepted"),  # type: ignore[arg-type]
            task_id=task_id,
            reason=self.reasons.get(task_id),
        )


class FakeRunner:
    def __init__(self) -> None:
        self.cancelled_ids: list[str] = []

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        self.cancelled_ids.append(task_id)
        return TaskCancelOutcome(status="accepted", task_id=task_id)


def running_task_manager(runner: FakeRunner) -> TaskManager:
    manager = TaskManager(runner=runner)
    for task in default_projections():
        manager.apply_created(
            TaskCreatedEvent(
                task_id=task.task_id,
                name=task.tool_name,
                arguments=task.arguments,
            )
        )
        manager.apply_event(TaskStartEvent(task_id=task.task_id))
    return manager


def test_cancel_tool_public_surface_has_no_decision_engine_abstractions():
    assert task_cancel_module.__all__ == [
        "CancelTaskCommand",
        "TaskCancelWorker",
        "create_task_cancel_tool",
    ]
    for removed_name in [
        "CancelDecision",
        "CancelExecutionOutcome",
        "CancelMatchEngine",
        "RuleBasedCancelMatchEngine",
        "TaskCancellationService",
        "format_cancel_observation",
    ]:
        assert not hasattr(task_cancel_module, removed_name)


def test_create_task_cancel_tool_names_task_manager_dependency():
    signature = inspect.signature(create_task_cancel_tool)

    assert list(signature.parameters) == ["task_manager"]


def test_target_hint_schema_requires_raw_context_excerpt():
    schema = CancelTaskCommand.model_json_schema()
    assert set(schema["properties"]) == {"target_hint"}
    description = schema["properties"]["target_hint"]["description"]

    for phrase in [
        "当前活跃任务",
        "原样摘取",
        "连续片段",
        "tool_name",
        "已展示的字符串参数值",
        "不要拼接多个字段",
        "不要填写完整任务摘要",
        "不要翻译、改写",
        "task_id",
        "单个片段",
    ]:
        assert phrase in description
    assert "用户原话中" not in description


@pytest.mark.asyncio
async def test_create_task_cancel_tool_uses_standard_tool_factory(monkeypatch):
    manager = FakeTaskManager()
    created_tool = object()
    factory_calls: list[dict[str, object]] = []

    def fake_create_tool(**kwargs):
        factory_calls.append(kwargs)
        return created_tool

    monkeypatch.setattr(task_cancel_module, "create_tool", fake_create_tool)

    tool = create_task_cancel_tool(task_manager=manager)

    assert tool is created_tool
    assert len(factory_calls) == 1

    call = factory_calls[0]
    assert call["name"] == "cancel_task"
    assert call["args_schema"] is CancelTaskCommand
    assert call["timeout"] is None
    assert call["asyncable"] == "sync"
    assert call["with_clarify"] is False
    assert call["task_manager"] is manager
    assert "修改同一个 pending 任务" in call["description"]
    assert "用户不必明确说出取消" in call["description"]
    assert "不能把 cancel_task 和替代它的新工具调用放在同一次模型响应中" in call[
        "description"
    ]
    assert "当前活跃任务为空时绝不能调用" in call["description"]

    observation = await call["worker"](target_hint="酒店")

    assert observation == "[已取消] poi_search(city=上海, type=酒店)"
    assert manager.cancelled_ids == ["p1"]


@pytest.mark.asyncio
async def test_task_cancel_worker_prints_model_arguments(monkeypatch):
    manager = FakeTaskManager()
    worker = TaskCancelWorker(manager)
    printed: list[str] = []

    monkeypatch.setattr(
        task_cancel_module,
        "print",
        lambda *args, **kwargs: printed.append(" ".join(str(arg) for arg in args)),
        raising=False,
    )

    observation = await worker(target_hint="酒店")

    assert observation == "[已取消] poi_search(city=上海, type=酒店)"
    assert "cancel_task 入参" in printed[0]
    assert "target_hint=酒店" in printed[0]


@pytest.mark.asyncio
async def test_no_active_task_returns_no_op():
    manager = FakeTaskManager(projections=[])

    observation = await TaskCancelWorker(manager)(target_hint=None)

    assert observation == (
        "[无需取消] 当前没有正在执行的任务。"
        "若相关结果已经返回，请说明信息已经查到，不要回复“已取消”。"
    )
    assert manager.cancelled_ids == []


@pytest.mark.asyncio
async def test_single_active_task_without_matching_asks_for_clarification():
    manager = FakeTaskManager(projections=[default_projections()[0]])

    observation = await TaskCancelWorker(manager)(target_hint=None)

    assert observation == (
        "[需要澄清] 未能唯一匹配取消目标。"
        "候选任务: weather_search(city=香港)。"
        "请询问用户要取消哪个。"
    )
    assert manager.cancelled_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target_hint", ["weather", "香港"])
async def test_single_active_task_is_cancelled_only_after_matching(
    target_hint: str,
):
    manager = FakeTaskManager(projections=[default_projections()[0]])

    observation = await TaskCancelWorker(manager)(target_hint=target_hint)

    assert observation == "[已取消] weather_search(city=香港)"
    assert manager.cancelled_ids == ["w1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_hint", "expected_task_id"),
    [
        ("weather", "w1"),
        ("  WEATHER  ", "w1"),
        ("酒店", "p1"),
    ],
)
async def test_unique_string_match_selects_task(
    target_hint: str,
    expected_task_id: str,
):
    manager = FakeTaskManager()

    await TaskCancelWorker(manager)(target_hint=target_hint)

    assert manager.cancelled_ids == [expected_task_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_hint",
    [None, "", "上", "香", "search", "别找上海的酒店了", "没有这个参数"],
)
async def test_ambiguous_string_match_asks_for_clarification(
    target_hint: str | None,
):
    manager = FakeTaskManager()

    observation = await TaskCancelWorker(manager)(target_hint=target_hint)

    assert observation == (
        "[需要澄清] 未能唯一匹配取消目标。候选任务: "
        "weather_search(city=香港), poi_search(city=上海, type=酒店)。"
        "请询问用户要取消哪个。"
    )
    assert manager.cancelled_ids == []


@pytest.mark.asyncio
async def test_ambiguous_hint_only_lists_matched_tasks():
    manager = FakeTaskManager(
        projections=[
            *default_projections(),
            projection("w2", "weather_forecast", {"city": "北京"}),
        ]
    )

    observation = await TaskCancelWorker(manager)(target_hint="weather")

    assert observation == (
        "[需要澄清] 未能唯一匹配取消目标。候选任务: "
        "weather_search(city=香港), weather_forecast(city=北京)。"
        "请询问用户要取消哪个。"
    )
    assert manager.cancelled_ids == []


@pytest.mark.asyncio
async def test_already_finished_race_is_not_reported_as_cancelled():
    manager = FakeTaskManager(statuses={"p1": "already_terminal"})

    observation = await TaskCancelWorker(manager)(target_hint="酒店")

    assert observation == (
        "[无需取消] 相关任务已经完成，结果已经返回或正在回复中。"
        "请说明信息已经查到，不要回复“已取消”。"
    )
    assert manager.cancelled_ids == ["p1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        ("not_found", None, "[取消失败] poi_search(city=上海, type=酒店): 未找到"),
        (
            "failed",
            "manager refused cancellation",
            "[取消失败] poi_search(city=上海, type=酒店): manager refused cancellation",
        ),
        ("failed", None, "[取消失败] poi_search(city=上海, type=酒店): 未知错误"),
    ],
)
async def test_cancel_failure_is_reported(
    status: str,
    reason: str | None,
    expected: str,
):
    manager = FakeTaskManager(
        statuses={"p1": status},
        reasons={"p1": reason} if reason else None,
    )

    observation = await TaskCancelWorker(manager)(target_hint="酒店")

    assert observation == expected
    assert manager.cancelled_ids == ["p1"]


@pytest.mark.asyncio
async def test_real_manager_cancel_keeps_state_event_driven():
    runner = FakeRunner()
    manager = running_task_manager(runner)

    observation = await TaskCancelWorker(manager)(target_hint="酒店")

    task = manager.get_task("p1")
    assert observation == "[已取消] poi_search(city=上海, type=酒店)"
    assert manager.get_projection("p1") is not None
    assert task is not None
    assert task.status == TaskStatus.RUNNING
    assert runner.cancelled_ids == ["p1"]
