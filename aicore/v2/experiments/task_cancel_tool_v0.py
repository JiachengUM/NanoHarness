"""v0 评测兼容入口；实现已提升为正式 ``task_cancel_tool``。"""

from __future__ import annotations

from aicore.runtime.task import TaskManager
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.experiments.task_cancel_tool import (
    TaskCancelCommand,
    create_task_cancel_tool,
)

__all__ = [
    "TaskCancelCommandV0",
    "create_task_cancel_tool_v0",
]


TaskCancelCommandV0 = TaskCancelCommand


def create_task_cancel_tool_v0(
    *,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    return create_task_cancel_tool(task_manager=task_manager)
