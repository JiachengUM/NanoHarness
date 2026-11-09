"""使用精确 ``task_id`` 取消异步任务的正式工具。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager
from aicore.tools.factory import create_tool as create_raw_tool
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.tools.async_task import AsyncableTaskTool

__all__ = [
    "TaskCancelCommand",
    "TaskCancelWorker",
    "create_raw_task_cancel_tool",
    "create_task_cancel_tool",
]


class TaskCancelCommand(BaseModel):
    task_id: str = Field(
        min_length=1,
        description="要取消任务的 task_id。",
    )


class TaskCancelWorker:
    def __init__(self, task_manager: TaskManager) -> None:
        self._task_manager = task_manager

    async def __call__(self, task_id: str) -> str:
        print(f"🛠 cancel_task 入参 | task_id={task_id}")
        outcome = self._task_manager.cancel_task(task_id)
        if outcome.status == "accepted":
            return f"[已取消] task_id={task_id}"
        if outcome.status == "already_terminal":
            return f"[无需取消] task_id={task_id} 已经结束"

        reason = "不存在" if outcome.status == "not_found" else outcome.reason
        return f"[取消失败] task_id={task_id}: {reason or '未知错误'}"


def create_raw_task_cancel_tool(
    *,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="cancel_task",
        description=(
            "取消一个已提交且真实结果尚未返回的异步任务。"
            "一次调用只取消一个任务；目标不明确时不要调用。"
        ),
        args_schema=TaskCancelCommand,
        worker=TaskCancelWorker(task_manager),
        timeout=None,
        with_clarify=False,
    )


def create_task_cancel_tool(
    *,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    """保留 v2 入口：cancel_task 始终同步执行，不进入任务队列。"""

    return AsyncableTaskTool(
        create_raw_task_cancel_tool(task_manager=task_manager),
        asyncable="sync",
        task_manager=task_manager,
    )
