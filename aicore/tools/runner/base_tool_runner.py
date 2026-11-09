import asyncio

from typing import Any, override, AsyncGenerator

from pydantic import BaseModel

from aicore.events.react import TaskToolDoneEvent
from aicore.utils.misc import model_to_dict

from .base import ToolRunnerBase

from aicore.tools import BaseTool

from aicore.core.types import SafeResult

__all__ = [
    "BaseToolRunner",
]


class BaseToolRunner(ToolRunnerBase[BaseTool, TaskToolDoneEvent[Any]]):
    def __init__(self):
        self.tasks: list[asyncio.Task[SafeResult[Any]]] = []
        self._results: list[SafeResult[Any]] = []

    # 调用方需要确保 arguments 是符合对应 tool args_schema 要求的实例
    @override
    def add_tool(self, tool: BaseTool, arguments: BaseModel):

        async def run_tool() -> SafeResult[Any]:
            try:
                result = await tool.arun(model_to_dict(arguments))
                return SafeResult(data=result)
            except Exception as e:
                return SafeResult(error=f"工具执行错误: {e}")

        self.tasks.append(asyncio.create_task(run_tool()))

    @override
    async def run(self) -> AsyncGenerator[TaskToolDoneEvent[Any], None]:
        self._results = await asyncio.gather(*self.tasks)

        for result in self._results:
            yield TaskToolDoneEvent(output=result)

    @property
    def tool_results(self) -> list[str]:
        return [r.nl_repr() for r in self._results]
