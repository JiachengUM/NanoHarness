"""定时提醒工具 —— 供 v2 Agent 通过 function calling 调用。

Agent 调用 set_reminder(delay_seconds, description) 设置提醒，
时间快进时 ScheduledTaskManager 检查到期任务并注入 Agent 对话。
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager
from aicore.v2.tools.factory import create_tool

if TYPE_CHECKING:
    from .manager import ScheduledTaskManager


class SetReminderInput(BaseModel):
    """设置提醒参数"""

    delay_seconds: int = Field(
        description="提醒延迟时长，单位秒。如 1800 表示 30 分钟后提醒。",
    )
    description: str = Field(
        description="提醒内容描述，如 '提醒喝水'、'提醒开会'",
    )


class SetReminderOutput(BaseModel):
    """设置提醒结果"""

    status: str = Field(description="success / error")
    task_id: str = Field(description="任务 ID")
    message: str = Field(description="执行结果描述")


def create_reminder_tool(
    manager: ScheduledTaskManager,
    get_current_time,
    task_manager: TaskManager | None = None,
):
    """创建提醒工具。

    Args:
        manager: 定时任务管理器
        get_current_time: 可调用对象，返回当前模拟时间 datetime
        task_manager: 传入时走异步任务化执行（产生 TaskCreatedEvent 工具事件，
                      落到工具泳道/对话流）；不传时同步执行（兼容单测直接调用）。
    """
    async def worker(delay_seconds: int, description: str) -> SetReminderOutput:
        if delay_seconds <= 0:
            return SetReminderOutput(
                status="error",
                task_id="",
                message="提醒延迟时间必须大于 0 秒",
            )
        current = get_current_time()
        trigger_time = current + timedelta(seconds=delay_seconds)
        task_id = manager.add_task(trigger_time, description)
        return SetReminderOutput(
            status="success",
            task_id=task_id,
            message=f"已设置提醒：{description}，将在 {delay_seconds} 秒后提醒您",
        )

    return create_tool(
        name="set_reminder",
        description="设置一个定时提醒。例如：提醒我30分钟后喝水、提醒我1小时后开会。"
                    "参数 delay_seconds 为延迟秒数，description 为提醒内容。",
        args_schema=SetReminderInput,
        worker=worker,
        timeout=5.0,
        asyncable="async" if task_manager is not None else "sync",
        task_manager=task_manager,
    )