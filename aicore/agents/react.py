from typing import AsyncGenerator

from aicore.events.react import (
    ReActEvent,
    ReActFinishEvent,
    TaskToolDoneEvent,
    ToolCallStartEvent,
    ToolCallsDoneEvent,
)

from aicore.events.task import TaskEvent

from aicore.tools import BaseTool, TaskToolTypeGeneral
from aicore.tools.runner import BaseToolRunner, TaskToolRunner, StreamTaskToolRunner

from aicore.models.model_api import ModelAPI, ModelCallParams, ModelState

from aicore.agents._react_core import astream_react_base


__all__ = [
    "ReActEvent",
    "ReActFinishEvent",
    "TaskToolDoneEvent",
    "ToolCallStartEvent",
    "ToolCallsDoneEvent",
    "react_with_base_tools",
    "react_with_task_tools",
    "react_with_stream_tools",
]

# TODO: 写一个通用的react函数，有一个runner参数，能自由选择runner


async def react_with_base_tools[StateT: ModelState](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[BaseTool] | None = None,
    max_turns: int = 5,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ReActEvent, None]:

    async for event in astream_react_base(
        query,
        model_api=model_api,
        runner_type=BaseToolRunner,
        state=state,
        tools=tools,
        max_turns=max_turns,
        params=params,
    ):
        yield event


async def react_with_task_tools[StateT: ModelState](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[TaskToolTypeGeneral] | None = None,
    max_turns: int = 5,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ReActEvent, None]:

    async for event in astream_react_base(
        query,
        model_api=model_api,
        runner_type=TaskToolRunner,
        state=state,
        tools=tools,
        max_turns=max_turns,
        params=params,
    ):
        yield event


async def react_with_stream_tools[StateT: ModelState](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[TaskToolTypeGeneral] | None = None,
    max_turns: int = 5,
    params: ModelCallParams | None = None,
) -> AsyncGenerator[ReActEvent | TaskEvent, None]:

    async for event in astream_react_base(
        query,
        model_api=model_api,
        runner_type=StreamTaskToolRunner,
        state=state,
        tools=tools,
        max_turns=max_turns,
        params=params,
    ):
        yield event
