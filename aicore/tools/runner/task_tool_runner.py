from contextlib import aclosing

from anyio import fail_after

from typing import Any, override, AsyncGenerator

from pydantic import BaseModel

from aicore.core.types import SafeResult
from aicore.events.react import TaskToolDoneEvent
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.tools.task_worker import bind_task_tool_worker
from aicore.utils.misc import model_to_dict

from .base import ToolRunnerBase

from aicore.core.anyio.task_runner import TaskAsyncRunner

from aicore.core.anyio.stream_task_runner import (
    TaskEvent,
    StreamTaskRunner,
    TaskSuccessEvent,
)

__all__ = ["TaskToolRunner", "StreamTaskToolRunner"]


class TaskToolRunner(
    ToolRunnerBase[TaskToolProtocolGeneral, TaskToolDoneEvent[Any]], TaskAsyncRunner
):
    def __init__(self):
        TaskAsyncRunner.__init__(self)

    # 调用方需要确保 arguments 是符合对应 tool args_schema 要求的实例
    @override
    def add_tool(self, tool: TaskToolProtocolGeneral, arguments: BaseModel):
        worker = tool.simple_worker(**model_to_dict(arguments))

        async def run_task() -> Any:
            try:
                with fail_after(tool.timeout):
                    return await worker()
            except TimeoutError:
                raise TimeoutError(f"任务 {tool.name} 超时")
            except Exception as e:
                if tool.on_error:
                    raise RuntimeError(tool.on_error(e))
                raise

        self.add_task(run_task)

    @override
    async def run(self) -> AsyncGenerator[TaskToolDoneEvent[Any], None]:  # type: ignore
        async with aclosing(self.run_indexed()) as inner:
            async for _, event in inner:
                yield event

    async def run_indexed(
        self,
    ) -> AsyncGenerator[tuple[int, TaskToolDoneEvent[Any]], None]:
        # 显式 aclosing: 确保外层 aclose 时内层 gen 也及时关闭, 避免嵌套
        # async generator + task_group 跨 task 关闭引发的 "Attempted to exit cancel
        # scope in a different task" 错误.
        async with aclosing(TaskAsyncRunner.run_indexed(self)) as inner:
            async for idx, safe in inner:
                yield idx, TaskToolDoneEvent(output=safe)

    @property
    def tool_results(self) -> list[str]:
        return [r.nl_repr() for r in self.results]


class StreamTaskToolRunner(
    ToolRunnerBase[TaskToolProtocolGeneral, TaskEvent | TaskToolDoneEvent[Any]],
    StreamTaskRunner,
):
    def __init__(self):
        StreamTaskRunner.__init__(self)

    @override
    def add_tool(
        self,
        tool: TaskToolProtocolGeneral,
        arguments: BaseModel,
        *,
        task_id: str | None = None,
    ) -> None:

        worker = bind_task_tool_worker(tool, arguments)
        StreamTaskRunner.add_task(self, worker, task_id=task_id)

    @override
    async def run(self) -> AsyncGenerator[TaskEvent, None]:

        async for event in StreamTaskRunner.run(self):
            if isinstance(event, TaskSuccessEvent):
                # TODO: 下面的type error确实有逻辑问题。
                # StreamTaskRunner返回的TaskSuccessEvent的result类型是Any，但实际中的stream worker返回的确实是SafeResult。两者不匹配。
                yield TaskToolDoneEvent(output=SafeResult(data=event.result))
                # 这里并不需要continue，把event再yield一次没问题

            yield event

    @property
    def tool_results(self) -> list[str]:
        results = self.results

        return [r.nl_repr() for r in results]
