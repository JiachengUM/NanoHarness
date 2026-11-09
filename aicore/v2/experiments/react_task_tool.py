from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from aicore.runtime.task import TaskManager
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.experiments.react_agent_with_task_runner import (
    create_react_agent_with_task_runner,
)
from aicore.v2.tools.factory import create_tool

__all__ = [
    "DEFAULT_REACT_TASK_SYSTEM_PROMPT",
    "NAVIGATION_REACT_TASK_SYSTEM_PROMPT",
    "REACT_TASK_SELECTION_PROMPT",
    "ReactTaskInput",
    "ReactTaskOutput",
    "create_react_task_tool",
]


DEFAULT_REACT_TASK_SYSTEM_PROMPT = """
你是依赖型子任务执行器，只完成传入的子目标。
只能使用本次提供的工具；工具结果存在数据依赖时，必须等待真实结果后再构造下一步参数。
不要创建异步任务，不要执行子目标之外的独立需求。
完成全部步骤后，简短总结实际执行结果。
""".strip()

NAVIGATION_REACT_TASK_SYSTEM_PROMPT = f"""
{DEFAULT_REACT_TASK_SYSTEM_PROMPT}

如果导航路线包含途经地点和最终目的地，先获取全部地点信息，再通过一次 navigation 调用构造
“当前起点 → 全部途经点 → 最终目的地”的完整路线；不能省略当前起点到途经点这一段，
也不要先导航到途经地点、随后立刻用第二次导航覆盖前一条路线。
""".strip()

REACT_TASK_SELECTION_PROMPT = """
## 依赖型子目标

- 先按完整用户输入拆分目标。
- 如果工具结果决定后续工具的地点、对象、参数或顺序，将完整依赖链合并成一次 react_task；
  sub_goal 保留起点、途经点、最终目标和执行顺序，tools 只列实际需要的工具。
- 独立目标不得并入 react_task，应单独调用普通工具；独立搜索或检索默认 with_async=true，
  用户明确要求同步时除外。
- 调用 react_task 后，不要再由主 Agent 重复调用其内部工具。
""".strip()


class ReactTaskInput(BaseModel):
    sub_goal: str = Field(
        min_length=1,
        description=(
            "需要子 ReAct 完整执行的依赖型子目标；必须自包含并保留原请求中的"
            "起点、途经点、最终目标和执行顺序"
        ),
    )
    tools: list[str] = Field(
        min_length=1,
        description="允许子 ReAct 使用的工具名称，只能从工具描述给出的白名单中选择",
    )


class ReactTaskOutput(BaseModel):
    sub_goal: str
    result: str

    def __nl_repr__(self, **_: object) -> str:
        return f"依赖子目标已完成：{self.sub_goal}\n执行结果：{self.result}"


def create_react_task_tool(
    *,
    task_manager: TaskManager,
    model: str,
    tool_registry: Mapping[str, TaskToolProtocolGeneral],
    context_snapshot: str = "",
    system_prompt: str = DEFAULT_REACT_TASK_SYSTEM_PROMPT,
    max_turns: int = 4,
    name: str = "react_task",
) -> TaskToolProtocolGeneral:
    """创建固定异步的依赖型子目标工具。

    tool_registry 中必须放入未经过 AsyncableTaskTool 包装的 inline 工具。
    """
    # TODO(experiment): 当前取消 react_task 只会终止子 Agent 协程，不会补偿已经
    # 成功触发的导航等外部副作用；进入生产前需要明确父子任务和副作用取消语义。
    registry = dict(tool_registry)
    if not registry:
        raise ValueError("ReactTaskTool 至少需要一个可用工具")

    allowed_tool_names = "、".join(registry)
    schema_name = re.sub(r"\W+", "_", name).strip("_") or "ReactTask"
    allowed_tool_name_type: Any = Literal.__getitem__(tuple(registry))
    restricted_input_schema = create_model(
        f"{schema_name.title()}Input",
        __base__=ReactTaskInput,
        tools=(
            list[allowed_tool_name_type],
            Field(
                min_length=1,
                description=f"允许子 ReAct 使用的工具，只能选择：{allowed_tool_names}",
            ),
        ),
    )
    # TODO(experiment): 当前 demo 依赖主 Agent 将“附近”“公司”等指代完整展开到
    # sub_goal；进入生产前应由调用方注入结构化的运行时上下文。
    child_system_prompt = (
        f"{system_prompt}\n\n任务上下文：\n{context_snapshot.strip()}"
        if context_snapshot.strip()
        else system_prompt
    )

    async def react_task_worker(
        sub_goal: str,
        tools: list[str],
    ) -> ReactTaskOutput:
        selected_names = list(dict.fromkeys(tools))
        unknown_names = [tool_name for tool_name in selected_names if tool_name not in registry]
        if unknown_names:
            unknown = "、".join(unknown_names)
            raise ValueError(f"ReactTaskTool 收到未授权工具：{unknown}")

        child_agent = create_react_agent_with_task_runner(
            model=model,
            tools=[registry[tool_name] for tool_name in selected_names],
            system_prompt=child_system_prompt,
            max_turns=max_turns,
        )
        async for _ in child_agent.astream(sub_goal):
            pass

        history = child_agent.state.message_history
        if not history:
            raise RuntimeError("子 ReAct 未产生最终回复")

        return ReactTaskOutput(
            sub_goal=sub_goal,
            result=history[-1][1].content,
        )

    return create_tool(
        name=name,
        description=(
            "异步执行一个包含数据依赖的完整子目标。"
            "当某一步工具结果决定后续工具的地点、对象、参数或顺序时使用；"
            "独立目标不得合并进来。"
            f"tools 只能从以下白名单选择：{allowed_tool_names}。"
            "该工具固定异步执行，不提供 with_async 参数。"
        ),
        args_schema=restricted_input_schema,
        worker=react_task_worker,
        asyncable="async",
        task_manager=task_manager,
    )
