from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time
from typing import Any

import anyio

_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if sys.path[0] != _PROJECT_ROOT:
    sys.path.insert(0, _PROJECT_ROOT)

from aicore.events.agent import AgentOutTextStartEvent
from aicore.events.task import TaskSuccessEvent
from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskManager
from aicore.simulation.user_env.data_source import UserDataMocked
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.agent_runner import AgentRunner
from tests.v2.experiments.async_task_dependency_observer import (
    ActivityState,
    PrintingTool,
    wait_until_quiet,
)
from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT
from aicore.v2.experiments.react_agent_with_task_runner import (
    AgentTaskEventPrinter,
    create_react_agent_with_task_runner,
    render_active_task_context,
)
from aicore.v2.experiments.react_task_tool import (
    NAVIGATION_REACT_TASK_SYSTEM_PROMPT,
    REACT_TASK_SELECTION_PROMPT,
    create_react_task_tool,
)
from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
from aicore.v2.tools.async_task import (
    AsyncableTaskTool,
    AsyncTaskResultBackfill,
)
from projects.mind.toolset.experiments.async_task_tools import (
    get_async_task_tools,
)


CHAT_ID = os.getenv("V2_REACT_TEST_CHAT_ID", "v2-react-sub-goal-test")
QUERY = "我车子有点脏了，找个近一点的地方我要洗个车，然后去公司，顺便你给我来段音乐"

CONTEXT_SNAPSHOT = """
用户当前位于上海市徐汇滨江城开中心 T2 楼。
“公司”指上海市徐汇滨江城开中心 T2 楼。
今天是 2026 年 7 月 27 日。
""".strip()


class TimelinePrinter:
    def __init__(self, activity: ActivityState) -> None:
        self.started_at = time.monotonic()
        self.activity = activity
        self.delegate = AgentTaskEventPrinter()
        self.completed_tasks: list[tuple[float, str]] = []

    def __call__(self, event: Any) -> None:
        elapsed = time.monotonic() - self.started_at
        self.activity.touch()

        if isinstance(event, TaskSuccessEvent):
            result = event.result
            tool_name = (
                result.tool_name
                if isinstance(result, AsyncTaskResultBackfill)
                else type(result).__name__
            )
            self.completed_tasks.append((elapsed, tool_name))
            print(f"\n⏱ [{elapsed:6.2f}s] BACKFILL READY: {tool_name}")
        elif isinstance(event, AgentOutTextStartEvent):
            print(f"\n⏱ [{elapsed:6.2f}s] AGENT REPLY START")

        self.delegate(event)


def build_tools(
    task_manager: TaskManager,
    activity: ActivityState,
) -> list[TaskToolProtocolGeneral]:
    business_tools = get_async_task_tools(
        CHAT_ID,
        task_manager,
        asyncable="dynamic",
    )
    business_tools_by_name = {tool.name: tool for tool in business_tools}

    raw_tool_registry: dict[str, TaskToolProtocolGeneral] = {}
    for tool_name in ("地点搜索工具", "navigation"):
        wrapped_tool = business_tools_by_name[tool_name]
        if not isinstance(wrapped_tool, AsyncableTaskTool):
            raise TypeError(f"{tool_name} 不是 AsyncableTaskTool")
        raw_tool_registry[tool_name] = PrintingTool(
            wrapped_tool.inner_tool,  # type: ignore[arg-type]
            activity,
            lane="SUB-REACT",
        )

    react_task_tool = create_react_task_tool(
        task_manager=task_manager,
        model=ModelName.SEED_2_0_PRO_260215,
        tool_registry=raw_tool_registry,
        context_snapshot=CONTEXT_SNAPSHOT,
        system_prompt=NAVIGATION_REACT_TASK_SYSTEM_PROMPT,
        max_turns=4,
    )
    if not isinstance(react_task_tool, AsyncableTaskTool):
        raise TypeError("react_task 必须复用 AsyncableTaskTool")
    assert react_task_tool.asyncable == "async"
    assert set(react_task_tool.args_schema.model_fields) == {"sub_goal", "tools"}

    root_tools = [
        react_task_tool,
        *business_tools,
        create_task_cancel_tool(task_manager=task_manager),
    ]
    return [
        PrintingTool(tool, activity, lane="ROOT")  # type: ignore[list-item]
        for tool in root_tools
    ]


async def run_case(
    *,
    max_seconds: float,
    quiet_seconds: float,
) -> None:
    task_manager = TaskManager()
    activity = ActivityState()
    tools = build_tools(task_manager, activity)
    prompt = f"{ASYNC_REACT_SYSTEM_PROMPT}\n\n{REACT_TASK_SELECTION_PROMPT}"

    react_task = next(tool for tool in tools if tool.name == "react_task")
    print(f"\n{'=' * 100}")
    print(f"QUERY: {QUERY}")
    print(f"ROOT TOOLS: {[tool.name for tool in tools]}")
    print(f"react_task schema: {list(react_task.args_schema.model_fields)}")
    print("EXPECTED ROOT CALLS: react_task + one music search tool(with_async=True)")
    print("EXPECTED SUB-REACT CALLS: 地点搜索工具 -> navigation")
    print(f"{'=' * 100}")

    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_2_0_PRO_260215,
        tools=tools,
        system_prompt=prompt,
        max_turns=5,
        ambient_context_provider=lambda: render_active_task_context(task_manager),
    )
    printer = TimelinePrinter(activity)
    runner = AgentRunner(
        user_data=UserDataMocked([QUERY]),
        agent=agent,
        task_manager=task_manager,
        client=printer,
    )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(runner.run)
        with anyio.move_on_after(max_seconds) as cancel_scope:
            await wait_until_quiet(
                task_manager,
                activity,
                quiet_seconds=quiet_seconds,
            )

        if cancel_scope.cancel_called:
            print(f"\n⏱ 达到最大观察时间 {max_seconds:.0f}s，停止")
        else:
            print(f"\n✅ 连续 {quiet_seconds:.0f}s 无新事件且无活跃任务，停止")

        print("\nBACKFILL COMPLETION ORDER:")
        for elapsed, tool_name in printer.completed_tasks:
            print(f"- {elapsed:6.2f}s {tool_name}")
        task_group.cancel_scope.cancel()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument("--quiet-seconds", type=float, default=8)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await run_case(
        max_seconds=args.max_seconds,
        quiet_seconds=args.quiet_seconds,
    )


if __name__ == "__main__":
    anyio.run(main)
