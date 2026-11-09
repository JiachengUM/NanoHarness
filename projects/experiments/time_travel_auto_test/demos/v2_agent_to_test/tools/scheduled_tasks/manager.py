"""定时任务管理器：存储 + 到期检查 + 触发 + 时间锚点注入。

时间快进时，aupdate_context 调用 get_due_tasks 获取到期任务，
然后将任务描述作为系统消息注入 Agent 对话，Agent 自然响应即为主动话语。

时间锚点（WorldTick）注入：
- 每次 add_task 时，自动记录 trigger_time - WORLD_TICK_BUFFER 作为注入时间锚点
- get_pending_world_ticks() 返回待注入的时间锚点，由 aupdate_context 放入 ContextUpdateResult
- 时间锚点确保 Runner 在定时任务触发前 5s 停靠，配合多步快进双重保障不跳过

时间模型（自然时间流逝）：
- set_reminder 工具通过 Runner 注入的实时虚拟时间源取当前时刻，
  助手回复期间时间照常流逝 → trigger_time 天然包含回复耗时，无需偏移修正
"""

from __future__ import annotations

from datetime import datetime, timedelta

# 时间锚点注入缓冲：在定时任务触发时间前 N 秒注入 WorldTick
WORLD_TICK_BUFFER: timedelta = timedelta(seconds=5)


class ScheduledTask:
    """一个定时任务。"""

    def __init__(self, task_id: str, trigger_time: datetime, description: str) -> None:
        self.task_id = task_id
        self.trigger_time = trigger_time
        self.description = description
        self.triggered = False

    def is_due(self, current_time: datetime) -> bool:
        return not self.triggered and current_time >= self.trigger_time


class ScheduledTaskManager:
    """管理所有 pending 定时任务。

    用法：
        mgr = ScheduledTaskManager()
        mgr.add_task("remind-water", trigger_time, "提醒喝水")
        ...
        # 快进时
        due = mgr.get_due_tasks(from_time, to_time)
        for task in due:
            agent_chat(f"[系统通知] {task.description}")
    """

    _counter = 0

    def __init__(self) -> None:
        self._tasks: list[ScheduledTask] = []
        # 待注入的时间锚点（WorldTick）：(注入绝对时间, 任务描述)
        self._pending_world_ticks: list[tuple[datetime, str]] = []

    def add_task(self, trigger_time: datetime, description: str) -> str:
        """添加定时任务，返回 task_id。

        同时自动记录时间锚点注入时间 = trigger_time - WORLD_TICK_BUFFER。

        Args:
            trigger_time: 任务触发绝对时间（来自实时虚拟时间源，天然包含回复耗时）
            description: 任务描述
        """
        self._counter += 1
        task_id = f"scheduled_{self._counter}"
        task = ScheduledTask(task_id, trigger_time, description)
        self._tasks.append(task)

        # 记录时间锚点注入时间（trigger_time - 5s）
        wt_time = trigger_time - WORLD_TICK_BUFFER
        self._pending_world_ticks.append((wt_time, description))

        return task_id

    def get_due_tasks(self, from_time: datetime, to_time: datetime) -> list[ScheduledTask]:
        """返回在 [from_time, to_time] 区间内到期且未触发的任务，标记为已触发。"""
        due = [t for t in self._tasks if not t.triggered and from_time <= t.trigger_time <= to_time]
        for t in due:
            t.triggered = True
        return due

    def get_pending(self) -> list[ScheduledTask]:
        """返回所有未触发的任务。"""
        return [t for t in self._tasks if not t.triggered]

    def get_pending_triggers(self) -> list[tuple[datetime, str]]:
        """返回所有未触发任务的 (trigger_time, description)，供 Runner 判断中间停靠点。"""
        return [(t.trigger_time, t.description) for t in self._tasks if not t.triggered]

    def get_pending_world_ticks(self) -> list[tuple[datetime, str]]:
        """返回并清空待注入的时间锚点 (注入绝对时间, 任务描述)。

        每次调用后清空，确保同一批时间锚点只注入一次。
        """
        result = list(self._pending_world_ticks)
        self._pending_world_ticks.clear()
        return result

    def clear(self) -> None:
        self._tasks.clear()
        self._pending_world_ticks.clear()