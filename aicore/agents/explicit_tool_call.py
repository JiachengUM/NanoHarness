from typing import Any, AsyncGenerator

from aicore.agents._explicit_tool_call_core import astream_explicit_tool_call

from aicore.events.explicit_tool_call import ExplicitEvent
from aicore.events.react import TaskToolDoneEvent
from aicore.events.task import TaskEvent

from aicore.models.model_api import ModelAPI, ModelCallParams, ModelState

from aicore.tools import BaseTool, TaskToolTypeGeneral
from aicore.tools.runner import (
    BaseToolRunner,
    StreamTaskToolRunner,
    TaskToolRunner,
)


__all__ = [
    "explicit_tool_call_with_base_tools",
    "explicit_tool_call_with_task_tools",
    "explicit_tool_call_with_stream_tools",
]


async def explicit_tool_call_with_base_tools[StateT: ModelState](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[BaseTool] | None = None,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ExplicitEvent | TaskToolDoneEvent[Any], None]:
    async for event in astream_explicit_tool_call(
        query,
        model_api=model_api,
        runner_type=BaseToolRunner,
        state=state,
        tools=tools,
        params=params,
    ):
        yield event


async def explicit_tool_call_with_task_tools[StateT: ModelState](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[TaskToolTypeGeneral] | None = None,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ExplicitEvent | TaskToolDoneEvent[Any], None]:
    async for event in astream_explicit_tool_call(
        query,
        model_api=model_api,
        runner_type=TaskToolRunner,
        state=state,
        tools=tools,
        params=params,
    ):
        yield event


async def explicit_tool_call_with_stream_tools[StateT: ModelState](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[TaskToolTypeGeneral] | None = None,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ExplicitEvent | TaskEvent | TaskToolDoneEvent[Any], None]:
    async for event in astream_explicit_tool_call(
        query,
        model_api=model_api,
        runner_type=StreamTaskToolRunner,
        state=state,
        tools=tools,
        params=params,
    ):
        yield event
