import asyncio
import time

from dataclasses import dataclass

from rich import print

from pydantic import BaseModel, Field

from aicore.agents.react import ToolCallStartEvent, TaskToolDoneEvent, react_with_task_tools
from aicore.models.model_api import (
    ModelResponse,
    ModelState,
    ModelToolCallEvent,
)
from aicore.tools import TaskTool, ToolRunRequest


class DummyInput(BaseModel):
    input: str = Field(..., description="测试输入")


class FakeModelState(ModelState):
    pass


@dataclass(frozen=True)
class FakeModelAPI:
    stream_result: "FakeStreamResult"

    def initial_state(self, *, system_prompt: str | None = None) -> FakeModelState:
        return FakeModelState()

    async def stream(self, *args, **kwargs):
        return self.stream_result

    async def invoke(self, *args, **kwargs):
        raise NotImplementedError

    async def dump_state(self, *args, **kwargs):
        raise NotImplementedError

    def restore_state(self, *args, **kwargs):
        raise NotImplementedError

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError


class FakeStreamResult:
    def __init__(
        self,
        raw_events: list[ModelToolCallEvent],
        response: object,
        *,
        tail_delay: float = 0.0,
        stream_done: asyncio.Event,
        timeline: dict[str, float],
    ) -> None:
        self.raw_events = raw_events
        self.response = response
        self.tail_delay = tail_delay
        self.stream_done = stream_done
        self.timeline = timeline

    async def __aiter__(self):
        for raw_event in self.raw_events:
            yield raw_event

        if self.tail_delay > 0:
            await asyncio.sleep(self.tail_delay)

        self.timeline["stream_done_at"] = time.perf_counter()
        self.stream_done.set()


def dummy_task_tool(worker) -> TaskTool[DummyInput, str, None, ...]:
    return TaskTool[DummyInput, str, None, ...](
        name="dummy_task_tool",
        description="并发测试工具",
        args_schema=DummyInput,
        worker=worker,
    )


async def test_task_starts_before_stream_finishes():
    print("\n测试 astream_react: stream 未结束前 task 已启动")

    timeline: dict[str, float] = {}
    task_started = asyncio.Event()
    stream_done = asyncio.Event()

    async def worker(input: str) -> str:
        timeline["task_started_at"] = time.perf_counter()
        task_started.set()
        await asyncio.sleep(0.01)
        timeline["task_finished_at"] = time.perf_counter()
        return f"done:{input}"

    tool = dummy_task_tool(worker)
    tool_call = ToolRunRequest(
        run_id="call_1",
        tool_name=tool.name,
        arguments={"input": "alpha"},
        raw_arguments='{"input": "alpha"}',
    )

    fake_stream = FakeStreamResult(
        raw_events=[ModelToolCallEvent(tool_call=tool_call)],
        response=ModelResponse(
            tool_calls=[tool_call],
            state=FakeModelState(),
        ),
        tail_delay=0.20,
        stream_done=stream_done,
        timeline=timeline,
    )
    model_api = FakeModelAPI(stream_result=fake_stream)

    event_stream = react_with_task_tools(
        "test query",
        model_api=model_api,
        state=model_api.initial_state(),
        tools=[tool],
        max_turns=2,
        params=None,
    )

    first_event = await event_stream.__anext__()
    assert first_event.type == "react.start"

    second_event = await event_stream.__anext__()
    assert isinstance(second_event, ToolCallStartEvent)

    await asyncio.wait_for(task_started.wait(), timeout=0.1)
    assert not stream_done.is_set(), "task 应在 stream 完成前启动"

    third_event = await event_stream.__anext__()
    assert isinstance(third_event, TaskToolDoneEvent)

    await event_stream.aclose()

    print("astream_react 启动时机测试通过")


async def test_task_done_event_is_not_realtime_yet():
    print("\n测试 astream_react: TaskToolDoneEvent 当前不是实时发出")

    timeline: dict[str, float] = {}
    task_finished = asyncio.Event()
    stream_done = asyncio.Event()

    async def worker(input: str) -> str:
        timeline["task_started_at"] = time.perf_counter()
        await asyncio.sleep(0.02)
        timeline["task_finished_at"] = time.perf_counter()
        task_finished.set()
        return f"done:{input}"

    tool = dummy_task_tool(worker)
    tool_call = ToolRunRequest(
        run_id="call_2",
        tool_name=tool.name,
        arguments={"input": "beta"},
        raw_arguments='{"input": "beta"}',
    )

    fake_stream = FakeStreamResult(
        raw_events=[ModelToolCallEvent(tool_call=tool_call)],
        response=ModelResponse(
            tool_calls=[tool_call],
            state=FakeModelState(),
        ),
        tail_delay=0.20,
        stream_done=stream_done,
        timeline=timeline,
    )
    model_api = FakeModelAPI(stream_result=fake_stream)

    event_stream = react_with_task_tools(
        "test query",
        model_api=model_api,
        state=model_api.initial_state(),
        tools=[tool],
        max_turns=2,
        params=None,
    )

    await event_stream.__anext__()  # ReActStartEvent
    await event_stream.__anext__()  # ToolCallStartEvent

    await asyncio.wait_for(task_finished.wait(), timeout=0.1)
    assert not stream_done.is_set(), "task 应在 stream 完成前就已执行结束"

    done_event = await event_stream.__anext__()
    emitted_at = time.perf_counter()

    assert isinstance(done_event, TaskToolDoneEvent)
    assert timeline["task_finished_at"] < timeline["stream_done_at"], "task 应早于 stream 完成"
    assert timeline["stream_done_at"] < emitted_at, "TaskToolDoneEvent 应在 stream 完成后才被发出"

    await event_stream.aclose()

    print("astream_react 非实时事件测试通过")


async def main():
    await test_task_starts_before_stream_finishes()
    await test_task_done_event_is_not_realtime_yet()


if __name__ == "__main__":
    asyncio.run(main())
