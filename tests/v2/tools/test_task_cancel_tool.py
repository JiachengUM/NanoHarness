from __future__ import annotations

import inspect

import pytest

from aicore.runtime.task import TaskCancelOutcome
import aicore.v2.experiments.task_cancel_tool as task_cancel_module
from aicore.v2.experiments.task_cancel_tool import (
    TaskCancelCommand,
    TaskCancelWorker,
    create_raw_task_cancel_tool,
    create_task_cancel_tool,
)
from aicore.v2.tools.async_task import AsyncableTaskTool


class FakeTaskManager:
    def __init__(self, outcome: TaskCancelOutcome | None = None) -> None:
        self.outcome = outcome
        self.cancelled_ids: list[str] = []

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        self.cancelled_ids.append(task_id)
        return self.outcome or TaskCancelOutcome(
            status="accepted",
            task_id=task_id,
        )


def test_official_schema_only_accepts_receipt_task_id() -> None:
    schema = TaskCancelCommand.model_json_schema()

    assert set(schema["properties"]) == {"task_id"}
    assert schema["required"] == ["task_id"]
    description = schema["properties"]["task_id"]["description"]
    assert "task_id" in description
    assert "占位回执" not in description
    assert "call_id" not in description
    assert "target_hint" not in schema["properties"]


def test_official_factory_keeps_canonical_public_contract() -> None:
    assert task_cancel_module.__all__ == [
        "TaskCancelCommand",
        "TaskCancelWorker",
        "create_raw_task_cancel_tool",
        "create_task_cancel_tool",
    ]
    assert list(inspect.signature(create_task_cancel_tool).parameters) == [
        "task_manager"
    ]

    manager = FakeTaskManager()
    tool = create_task_cancel_tool(task_manager=manager)  # type: ignore[arg-type]

    assert tool.name == "cancel_task"
    assert tool.asyncable == "sync"
    assert tool.args_schema is TaskCancelCommand
    assert set(tool.args_schema.model_json_schema()["properties"]) == {"task_id"}
    assert "一次调用只取消一个任务" in tool.description
    assert "占位回执" not in tool.description


def test_raw_factory_keeps_the_same_contract_without_asyncable_wrapper() -> None:
    manager = FakeTaskManager()

    tool = create_raw_task_cancel_tool(task_manager=manager)  # type: ignore[arg-type]
    wrapped = create_task_cancel_tool(task_manager=manager)  # type: ignore[arg-type]

    assert tool.name == wrapped.name == "cancel_task"
    assert tool.description == wrapped.description
    assert tool.args_schema is wrapped.args_schema is TaskCancelCommand
    assert not isinstance(tool, AsyncableTaskTool)
    assert isinstance(wrapped, AsyncableTaskTool)
    assert wrapped.asyncable == "sync"


@pytest.mark.asyncio
async def test_official_worker_passes_exact_task_id_to_manager() -> None:
    manager = FakeTaskManager()
    worker = TaskCancelWorker(manager)  # type: ignore[arg-type]

    result = await worker(task_id="weather-1")

    assert result == "[已取消] task_id=weather-1"
    assert manager.cancelled_ids == ["weather-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            TaskCancelOutcome(status="already_terminal", task_id="task-1"),
            "[无需取消] task_id=task-1 已经结束",
        ),
        (
            TaskCancelOutcome(status="not_found", task_id="task-1"),
            "[取消失败] task_id=task-1: 不存在",
        ),
        (
            TaskCancelOutcome(
                status="failed",
                task_id="task-1",
                reason="manager refused cancellation",
            ),
            "[取消失败] task_id=task-1: manager refused cancellation",
        ),
    ],
)
async def test_official_worker_preserves_manager_outcome(
    outcome: TaskCancelOutcome,
    expected: str,
) -> None:
    manager = FakeTaskManager(outcome)

    result = await TaskCancelWorker(manager)(task_id=outcome.task_id)  # type: ignore[arg-type]

    assert result == expected
    assert manager.cancelled_ids == [outcome.task_id]
