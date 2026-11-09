"""基于 ``target_hint`` 子串匹配的取消工具实验（v1）。

实验表明，``target_hint`` 会把一次目标选择拆成“模型生成自由文本”和
“后台 matcher 二次解析”，引入不必要的信息损失。单一字符串还无法稳定表达
多字段联合条件、非字符串参数或完整任务摘要，因此该版本只保留用于对比评测；
正式取消工具改为让模型从异步任务占位回执中复制精确 ``task_id``。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager, TaskProjection
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.tools.factory import create_tool

__all__ = [
    "CancelTaskCommand",
    "TaskCancelWorker",
    "create_task_cancel_tool",
]


class CancelTaskCommand(BaseModel):
    target_hint: str | None = Field(
        default=None,
        description=(
            "从“当前活跃任务”状态块中原样摘取一个能唯一标识目标任务的连续片段："
            "只能是 tool_name 片段或状态块中已展示的字符串参数值片段。"
            "只填写这个片段，不要拼接多个字段，不要填写完整任务摘要或 task_id，"
            "也不要翻译、改写。找不到这样的单个片段时填 null，让工具返回澄清问题。"
        ),
    )


class TaskCancelWorker:
    def __init__(self, task_manager: TaskManager) -> None:
        self._task_manager = task_manager

    async def __call__(
        self,
        target_hint: str | None = None,
    ) -> str:
        print(f"🛠 cancel_task 入参 | target_hint={target_hint}")

        active_tasks = self._task_manager.get_active_task_projections()
        if not active_tasks:
            return (
                "[无需取消] 当前没有正在执行的任务。"
                "若相关结果已经返回，请说明信息已经查到，不要回复“已取消”。"
            )

        candidates = _matching_tasks(active_tasks, target_hint)
        if len(candidates) != 1:
            options = ", ".join(
                _task_summary(task) for task in (candidates or active_tasks)
            )
            return (
                f"[需要澄清] 未能唯一匹配取消目标。候选任务: {options}。"
                "请询问用户要取消哪个。"
            )

        task = candidates[0]
        summary = _task_summary(task)
        outcome = self._task_manager.cancel_task(task.task_id)
        if outcome.status == "accepted":
            return f"[已取消] {summary}"
        if outcome.status == "already_terminal":
            return (
                "[无需取消] 相关任务已经完成，结果已经返回或正在回复中。"
                "请说明信息已经查到，不要回复“已取消”。"
            )

        reason = "未找到" if outcome.status == "not_found" else outcome.reason
        return f"[取消失败] {summary}: {reason or '未知错误'}"


def _matching_tasks(
    tasks: list[TaskProjection],
    target_hint: str | None,
) -> list[TaskProjection]:
    """按照 v1 的唯一规则返回 target_hint 子串命中的活跃任务。"""

    query = (target_hint or "").strip().casefold()
    if len(query) < 2:
        return []

    matches: list[TaskProjection] = []
    for task in tasks:
        tool_name_matches = query in task.tool_name.strip().casefold()
        argument_matches = any(
            query in value.strip().casefold()
            for value in task.arguments.values()
            if isinstance(value, str)
        )
        if tool_name_matches or argument_matches:
            matches.append(task)
    return matches


def _task_summary(task: TaskProjection) -> str:
    arguments = [
        f"{key}={value}"
        for key, value in task.arguments.items()
        if isinstance(value, str)
    ]
    if not arguments:
        return task.tool_name
    return f"{task.tool_name}({', '.join(arguments)})"


def create_task_cancel_tool(
    *,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    return create_tool(
        name="cancel_task",
        description=(
            "用于取消活跃异步任务，也用于在用户修改同一个 pending 任务时先取消旧任务。"
            "修改包括补充、删除、更正或替换查询目标、筛选条件和参数；用户不必明确说出取消。"
            "修改任务时必须先单独调用本工具，等待取消结果后再调用业务工具提交合并了新旧要求的新任务，"
            "绝不能把 cancel_task 和替代它的新工具调用放在同一次模型响应中。绝不能填写 task_id。"
            "请从活跃任务上下文中提取 target_hint，优先使用工具名或参数值；"
            "如果存在模糊的取消指令（例如：取消任务、那个不用了、先不用了、别查了），"
            "或用户没有明确指向某一个任务，target_hint 填 null，让工具返回需要澄清。"
            "当前活跃任务为空时绝不能调用；此时应直接说明任务已经完成或当前没有任务，无需取消。"
            "既没有明确取消意图、也不是修改活跃任务时不要调用。"
        ),
        args_schema=CancelTaskCommand,
        worker=TaskCancelWorker(task_manager),
        timeout=None,
        asyncable="sync",  # 一定不能异步，否则会进入排队
        with_clarify=False,
        task_manager=task_manager,
    )
