from __future__ import annotations

import time
from typing import Any

import anyio
from pydantic import BaseModel

from aicore.runtime.task import TaskManager
from aicore.tools.protocol import TaskToolProtocolGeneral


class ActivityState:
    def __init__(self) -> None:
        self.active_tool_calls = 0
        self.last_activity_at = time.monotonic()
        self.seen_activity = False

    def touch(self) -> None:
        self.seen_activity = True
        self.last_activity_at = time.monotonic()


class PrintingTool:
    """打印模型工具调用并记录活动时间，不改变工具行为。"""

    def __init__(
        self,
        inner_tool: TaskToolProtocolGeneral,
        activity: ActivityState,
        *,
        lane: str | None = None,
    ) -> None:
        self.inner_tool = inner_tool
        self.activity = activity
        self.lane = lane

    @property
    def name(self) -> str:
        return self.inner_tool.name

    @property
    def description(self) -> str:
        return self.inner_tool.description

    @property
    def args_schema(self) -> type[BaseModel]:
        return self.inner_tool.args_schema

    @property
    def timeout(self) -> float | None:
        return self.inner_tool.timeout

    @property
    def on_error(self):
        return self.inner_tool.on_error

    def simple_worker(self, *args: Any, **kwargs: Any):
        self._print_call(args, kwargs)
        inner_worker = self.inner_tool.simple_worker(*args, **kwargs)

        async def observed_worker():
            self.activity.active_tool_calls += 1
            try:
                return await inner_worker()
            finally:
                self.activity.active_tool_calls -= 1
                self.activity.touch()

        return observed_worker

    def stream_worker_factory(self, *args: Any, **kwargs: Any):
        self._print_call(args, kwargs)
        inner_factory = self.inner_tool.stream_worker_factory(*args, **kwargs)

        async def observed_factory():
            self.activity.active_tool_calls += 1
            try:
                async for event in inner_factory():
                    yield event
            finally:
                self.activity.active_tool_calls -= 1
                self.activity.touch()

        return observed_factory

    def _print_call(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        if args:
            raise TypeError("PrintingTool 只支持 keyword arguments")
        self.activity.touch()
        call_source = f"{self.lane} TOOL CALL" if self.lane else "MODEL TOOL CALL"
        print(f"\n🔧 [{call_source}] {self.name}: {kwargs}")


async def wait_until_quiet(
    task_manager: TaskManager,
    activity: ActivityState,
    *,
    quiet_seconds: float,
) -> None:
    while True:
        await anyio.sleep(0.5)
        idle_for = time.monotonic() - activity.last_activity_at
        if (
            activity.seen_activity
            and activity.active_tool_calls == 0
            and not task_manager.get_active_task_projections()
            and idle_for >= quiet_seconds
        ):
            return
