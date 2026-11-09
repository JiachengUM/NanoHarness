from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

import anyio

_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if sys.path[0] != _PROJECT_ROOT:
    sys.path.insert(0, _PROJECT_ROOT)

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
from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
from aicore.v2.tools.async_task import AsyncableTaskTool
from projects.mind.toolset.experiments.async_task_tools import (
    get_async_task_tools,
)


CHAT_ID = os.getenv("V2_REACT_TEST_CHAT_ID", "v2-react-dependency-test")
QUERY = "我车子有点脏了，找个近一点的地方我要洗个车，然后去公司，顺便你给我来段音乐"


class ProcessPrinter:
    def __init__(self, activity: ActivityState) -> None:
        self.delegate = AgentTaskEventPrinter()
        self.activity = activity

    def __call__(self, event: Any) -> None:
        self.activity.touch()
        self.delegate(event)


def build_full_backend_tools(
    task_manager: TaskManager,
    *,
    activity: ActivityState,
) -> list[TaskToolProtocolGeneral]:
    business_tools = get_async_task_tools(CHAT_ID, task_manager)
    for tool in business_tools:
        if not isinstance(tool, AsyncableTaskTool) or tool.asyncable != "async":
            raise TypeError(f"{tool.name} 不是固定异步工具")

    tools = [
        *business_tools,
        create_task_cancel_tool(task_manager=task_manager),
    ]
    return [
        PrintingTool(tool, activity)  # type: ignore[list-item]
        for tool in tools
    ]


async def run_case(
    *,
    max_seconds: float,
    quiet_seconds: float,
) -> None:
    task_manager = TaskManager()
    activity = ActivityState()
    tools = build_full_backend_tools(
        task_manager,
        activity=activity,
    )

    print(f"\n{'=' * 100}")
    print("MODE: baseline (所有业务工具固定异步)")
    print(f"QUERY: {QUERY}")
    print(f"TOOLS: {[tool.name for tool in tools]}")
    print(f"{'=' * 100}")

    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_2_0_PRO_260215,
        tools=tools,
        system_prompt=ASYNC_REACT_SYSTEM_PROMPT,
        max_turns=5,
        ambient_context_provider=lambda: render_active_task_context(task_manager),
    )
    printer = ProcessPrinter(activity)
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
            print(f"\n⏱ 达到最大观察时间 {max_seconds:.0f}s，停止本轮")
        else:
            print(f"\n✅ 连续 {quiet_seconds:.0f}s 无新事件且无活跃任务，本轮结束")
        task_group.cancel_scope.cancel()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=90,
        help="最大观察时间",
    )
    parser.add_argument(
        "--quiet-seconds",
        type=float,
        default=8,
        help="无活跃任务后连续无事件多久自动结束",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await run_case(
        max_seconds=args.max_seconds,
        quiet_seconds=args.quiet_seconds,
    )


if __name__ == "__main__":
    anyio.run(main)
