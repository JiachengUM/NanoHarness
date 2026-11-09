from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from aicore.events.task import (
    TaskCancelledEvent,
    TaskEvent,
)
from aicore.models.stream_model_api import (
    AudioChunkInput,
    AudioCommitInput,
    StreamToolCallEvent,
    StreamTranscriptionDoneEvent,
    ToolResultBatchInput,
)
from aicore.models.stream_model_api.duplex.async_backfill import (
    DuplexAsyncCompatConfig,
)
from aicore.models.stream_model_api.duplex.config import DuplexConfig
from aicore.models.stream_model_api.duplex.duplex_agent_session import (
    DuplexAgentSession,
)
from aicore.models.stream_model_api.inputs import StreamModelInput
from aicore.runtime.task import TaskManager, TaskProgress, TaskSuccess
from aicore.tools.factory import create_tool
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.tools.run import ToolRunRequest
from aicore.v2.experiments.task_cancel_tool import create_raw_task_cancel_tool


class AddInput(BaseModel):
    left: int
    right: int


async def add_worker(left: int, right: int) -> int:
    return left + right


def make_add_tool() -> TaskToolProtocolGeneral:
    return create_tool(
        name="add",
        description="add two integers",
        args_schema=AddInput,
        worker=add_worker,
    )


def make_tool(
    name: str,
    worker: Callable[..., Awaitable[Any]],
) -> TaskToolProtocolGeneral:
    return create_tool(
        name=name,
        description=f"test tool {name}",
        args_schema=AddInput,
        worker=worker,
    )


def make_call(
    call_id: str,
    *,
    tool_name: str = "add",
    left: int = 1,
    right: int = 2,
    group_id: str = "response-1",
    group_size: int = 1,
    item_id: str | None = None,
    input_error: str | None = None,
    arguments: dict[str, object] | None = None,
) -> StreamToolCallEvent:
    return StreamToolCallEvent(
        session_id="stream-session",
        response_id=group_id,
        group_id=group_id,
        group_size=group_size,
        item_id=item_id,
        input_error=input_error,
        tool_call=ToolRunRequest(
            run_id=call_id,
            tool_name=tool_name,
            arguments=arguments or {"left": left, "right": right},
        ),
    )


class RecordingModelAPI:
    def __init__(self) -> None:
        self.submissions: list[StreamModelInput] = []
        self._blocked_groups: dict[frozenset[str], tuple[asyncio.Event, asyncio.Event]] = {}

    def block_tool_group(
        self,
        *call_ids: str,
    ) -> tuple[asyncio.Event, asyncio.Event]:
        started = asyncio.Event()
        release = asyncio.Event()
        self._blocked_groups[frozenset(call_ids)] = (started, release)
        return started, release

    async def submit(self, input: StreamModelInput) -> str | None:
        if isinstance(input, ToolResultBatchInput):
            key = frozenset(result.call_id for result in input.results)
            barrier = self._blocked_groups.get(key)
            if barrier is not None:
                started, release = barrier
                started.set()
                await release.wait()
        self.submissions.append(input)
        return None

    async def events(self):
        await asyncio.Event().wait()
        if False:
            yield


class RecordingBackfillScheduler:
    def __init__(self) -> None:
        self.published: list[dict[str, object]] = []

    @property
    def task(self) -> None:
        return None

    def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def note_transcription_done(self) -> bool:
        return False

    async def publish_backfill(
        self,
        *,
        question_id: str,
        task_id: str,
        tool_name: str,
        text: str,
    ) -> None:
        self.published.append(
            {
                "question_id": question_id,
                "task_id": task_id,
                "tool_name": tool_name,
                "text": text,
            }
        )


def make_agent_session(
    model_api: RecordingModelAPI,
    *,
    tools: Sequence[TaskToolProtocolGeneral],
    task_manager: TaskManager | None = None,
    tool_call_mode: str = "sync",
    task_events: list[TaskEvent] | None = None,
) -> tuple[DuplexAgentSession, RecordingBackfillScheduler | None]:
    manager = task_manager or TaskManager()
    async_compat = (
        DuplexAsyncCompatConfig(tool_trigger_audio_paths={})
        if tool_call_mode == "async"
        else None
    )
    session = DuplexAgentSession(
        model_api=model_api,  # type: ignore[arg-type]
        tools=tools,
        task_manager=manager,
        tool_call_mode=tool_call_mode,  # type: ignore[arg-type]
        config=DuplexConfig(),
        async_compat=async_compat,
        context_diagnostics=False,
        task_event_observer=(task_events if task_events is not None else []).append,
    )
    if tool_call_mode == "sync":
        return session, None

    scheduler = RecordingBackfillScheduler()
    session._backfill_scheduler = scheduler  # type: ignore[assignment]
    return session, scheduler


def tool_batches(model_api: RecordingModelAPI) -> list[ToolResultBatchInput]:
    return [
        item
        for item in model_api.submissions
        if isinstance(item, ToolResultBatchInput)
    ]


async def wait_until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def stop_session(session: DuplexAgentSession) -> None:
    session._closing = True
    await session._stop_tool_groups()
    await session._stop_task_manager()


@pytest.mark.asyncio
async def test_submit_audio_path_streams_pcm_then_commits(tmp_path: Path) -> None:
    model_api = RecordingModelAPI()
    session, _ = make_agent_session(model_api, tools=[])
    pcm = tmp_path / "trigger.pcm"
    pcm.write_bytes(b"\x01\x00\x02\x00")

    await session.submit_audio_path(pcm)

    assert [type(item) for item in model_api.submissions] == [
        AudioChunkInput,
        AudioCommitInput,
    ]


@pytest.mark.asyncio
async def test_sync_group_waits_for_all_tools_then_submits_once_in_call_order() -> None:
    model_api = RecordingModelAPI()
    started = {"slow": asyncio.Event(), "fast": asyncio.Event()}
    release = {"slow": asyncio.Event(), "fast": asyncio.Event()}

    def controlled_worker(name: str, result: str):
        async def worker(left: int, right: int) -> str:
            started[name].set()
            await release[name].wait()
            return result

        return worker

    session, _ = make_agent_session(
        model_api,
        tools=[
            make_tool("slow", controlled_worker("slow", "slow-result")),
            make_tool("fast", controlled_worker("fast", "fast-result")),
        ],
    )
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call("call-slow", tool_name="slow", group_size=2)
        )
        session._handle_tool_event(
            make_call("call-fast", tool_name="fast", group_size=2)
        )
        await wait_until(lambda: all(event.is_set() for event in started.values()))

        release["fast"].set()
        await wait_until(
            lambda: any(
                invocation.terminal_event is not None
                for invocation in session._active_tool_groups["response-1"].invocations
                if invocation.call_id == "call-fast"
            )
        )
        assert tool_batches(model_api) == []

        release["slow"].set()
        await wait_until(lambda: len(tool_batches(model_api)) == 1)

        batch = tool_batches(model_api)[0]
        assert [result.call_id for result in batch.results] == [
            "call-slow",
            "call-fast",
        ]
        assert [result.output for result in batch.results] == [
            "slow-result",
            "fast-result",
        ]
    finally:
        for event in release.values():
            event.set()
        await stop_session(session)


@pytest.mark.asyncio
async def test_sync_groups_have_independent_completion_barriers() -> None:
    model_api = RecordingModelAPI()
    release_a = asyncio.Event()
    release_b = asyncio.Event()

    async def worker_a(left: int, right: int) -> str:
        await release_a.wait()
        return "result-a"

    async def worker_b(left: int, right: int) -> str:
        await release_b.wait()
        return "result-b"

    session, _ = make_agent_session(
        model_api,
        tools=[make_tool("tool-a", worker_a), make_tool("tool-b", worker_b)],
    )
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call("call-a", tool_name="tool-a", group_id="group-a")
        )
        session._handle_tool_event(
            make_call("call-b", tool_name="tool-b", group_id="group-b")
        )
        await wait_until(lambda: len(session._active_tool_groups) == 2)

        release_b.set()
        await wait_until(lambda: len(tool_batches(model_api)) == 1)
        assert [result.call_id for result in tool_batches(model_api)[0].results] == [
            "call-b"
        ]

        release_a.set()
        await wait_until(lambda: len(tool_batches(model_api)) == 2)
        assert [
            batch.results[0].call_id for batch in tool_batches(model_api)
        ] == ["call-b", "call-a"]
    finally:
        release_a.set()
        release_b.set()
        await stop_session(session)


@pytest.mark.asyncio
async def test_sync_group_returns_failure_and_cancellation_as_tool_outputs() -> None:
    model_api = RecordingModelAPI()
    cancel_started = asyncio.Event()

    async def fails(left: int, right: int) -> str:
        raise RuntimeError("broken worker")

    async def waits(left: int, right: int) -> str:
        cancel_started.set()
        await asyncio.Event().wait()
        return "unreachable"

    session, _ = make_agent_session(
        model_api,
        tools=[make_tool("fails", fails), make_tool("waits", waits)],
    )
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call("call-fail", tool_name="fails", group_size=2)
        )
        session._handle_tool_event(
            make_call("call-cancel", tool_name="waits", group_size=2)
        )
        await asyncio.wait_for(cancel_started.wait(), timeout=1)
        group = session._active_tool_groups["response-1"]
        task_id = next(
            invocation.task_id
            for invocation in group.invocations
            if invocation.call_id == "call-cancel"
        )
        session.task_manager.cancel_task(task_id)

        await wait_until(lambda: len(tool_batches(model_api)) == 1)
        results = tool_batches(model_api)[0].results
        assert [result.call_id for result in results] == [
            "call-fail",
            "call-cancel",
        ]
        assert "工具调用失败：broken worker" == results[0].output
        assert "工具调用被取消" in results[1].output
        assert all(result.success is False for result in results)
    finally:
        await stop_session(session)


@pytest.mark.asyncio
async def test_async_receipt_uses_runtime_task_id_not_provider_call_id() -> None:
    model_api = RecordingModelAPI()
    release = asyncio.Event()

    async def worker(left: int, right: int) -> int:
        await release.wait()
        return left + right

    session, _ = make_agent_session(
        model_api,
        tools=[make_tool("delayed", worker)],
        tool_call_mode="async",
    )
    session._question_contexts["question-1"] = "calculate"
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call(
                "provider-call-id",
                tool_name="delayed",
                item_id="question-1",
            )
        )
        await wait_until(lambda: len(tool_batches(model_api)) == 1)

        group = session._active_tool_groups["response-1"]
        assert len(group.invocations) == 1
        task_id = group.invocations[0].task_id
        receipt = tool_batches(model_api)[0].results[0]
        assert task_id != "provider-call-id"
        assert receipt.call_id == "provider-call-id"
        assert task_id in receipt.output
    finally:
        release.set()
        await stop_session(session)


@pytest.mark.parametrize(
    ("fc_item_id", "expected_question_id"),
    [("origin-question", "origin-question"), (None, "latest-question")],
)
@pytest.mark.asyncio
async def test_tool_call_origin_prefers_item_id_then_latest_transcription(
    fc_item_id: str | None,
    expected_question_id: str,
) -> None:
    model_api = RecordingModelAPI()
    release = asyncio.Event()

    async def worker(left: int, right: int) -> int:
        await release.wait()
        return left + right

    session, _ = make_agent_session(
        model_api,
        tools=[make_tool("add", worker)],
        tool_call_mode="async",
    )
    session._handle_audio_event(
        StreamTranscriptionDoneEvent(
            session_id="stream-session",
            item_id="latest-question",
            transcript="latest query",
        )
    )
    session._question_contexts["origin-question"] = "origin query"
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call("call-1", item_id=fc_item_id)
        )
        await wait_until(lambda: "response-1" in session._active_tool_groups)
        invocation = session._active_tool_groups[
            "response-1"
        ].invocations[0]
        assert invocation.question_id == expected_question_id
    finally:
        release.set()
        await stop_session(session)


@pytest.mark.asyncio
async def test_fast_async_success_waits_until_its_receipt_is_accepted() -> None:
    model_api = RecordingModelAPI()
    receipt_started, accept_receipt = model_api.block_tool_group("call-fast")

    async def worker(left: int, right: int) -> str:
        return "finished-immediately"

    session, scheduler = make_agent_session(
        model_api,
        tools=[make_tool("fast", worker)],
        tool_call_mode="async",
    )
    assert scheduler is not None
    session._question_contexts["question-1"] = "run fast"
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call("call-fast", tool_name="fast", item_id="question-1")
        )
        await asyncio.wait_for(receipt_started.wait(), timeout=1)
        await wait_until(
            lambda: session._active_tool_groups["response-1"]
            .invocations[0]
            .terminal_event
            is not None
        )

        assert scheduler.published == []
        assert tool_batches(model_api) == []

        accept_receipt.set()
        await wait_until(lambda: len(scheduler.published) == 1)
        assert len(tool_batches(model_api)) == 1
        assert scheduler.published[0]["text"] == "finished-immediately"
    finally:
        accept_receipt.set()
        await stop_session(session)


@pytest.mark.asyncio
async def test_async_receipt_barrier_is_scoped_to_each_group() -> None:
    model_api = RecordingModelAPI()
    group_a_started, accept_group_a = model_api.block_tool_group("call-a")

    async def worker_a(left: int, right: int) -> str:
        return "result-a"

    async def worker_b(left: int, right: int) -> str:
        return "result-b"

    session, scheduler = make_agent_session(
        model_api,
        tools=[make_tool("tool-a", worker_a), make_tool("tool-b", worker_b)],
        tool_call_mode="async",
    )
    assert scheduler is not None
    session._question_contexts.update(
        {"question-a": "query a", "question-b": "query b"}
    )
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call(
                "call-a",
                tool_name="tool-a",
                group_id="group-a",
                item_id="question-a",
            )
        )
        await asyncio.wait_for(group_a_started.wait(), timeout=1)
        session._handle_tool_event(
            make_call(
                "call-b",
                tool_name="tool-b",
                group_id="group-b",
                item_id="question-b",
            )
        )

        await wait_until(lambda: len(scheduler.published) == 1)
        assert scheduler.published[0]["question_id"] == "question-b"
        assert [
            batch.results[0].call_id for batch in tool_batches(model_api)
        ] == ["call-b"]

        accept_group_a.set()
        await wait_until(lambda: len(scheduler.published) == 2)
        assert [item["question_id"] for item in scheduler.published] == [
            "question-b",
            "question-a",
        ]
    finally:
        accept_group_a.set()
        await stop_session(session)


@pytest.mark.asyncio
async def test_async_mode_backfills_only_successful_terminal_events() -> None:
    model_api = RecordingModelAPI()
    cancel_started = asyncio.Event()
    cancel_finalized = asyncio.Event()

    async def succeeds(left: int, right: int) -> str:
        return "success-fact"

    async def fails(left: int, right: int) -> str:
        raise RuntimeError("failed-fact")

    async def waits_for_cancel(left: int, right: int) -> str:
        cancel_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancel_finalized.set()
        return "unreachable"

    task_events: list[TaskEvent] = []
    session, scheduler = make_agent_session(
        model_api,
        tools=[
            make_tool("succeeds", succeeds),
            make_tool("fails", fails),
            make_tool("cancels", waits_for_cancel),
        ],
        tool_call_mode="async",
        task_events=task_events,
    )
    assert scheduler is not None
    session._question_contexts["question-1"] = "run all"
    session._start_task_manager()
    try:
        for call_id, tool_name in (
            ("call-success", "succeeds"),
            ("call-failure", "fails"),
            ("call-cancel", "cancels"),
        ):
            session._handle_tool_event(
                make_call(
                    call_id,
                    tool_name=tool_name,
                    group_size=3,
                    item_id="question-1",
                )
            )
        await wait_until(lambda: len(tool_batches(model_api)) == 1)
        await asyncio.wait_for(cancel_started.wait(), timeout=1)

        group = session._active_tool_groups["response-1"]
        cancel_task_id = next(
            invocation.task_id
            for invocation in group.invocations
            if invocation.call_id == "call-cancel"
        )
        session.task_manager.cancel_task(cancel_task_id)
        await asyncio.wait_for(cancel_finalized.wait(), timeout=1)
        await wait_until(
            lambda: any(
                isinstance(event, TaskCancelledEvent)
                and event.task_id == cancel_task_id
                for event in task_events
            )
        )
        await wait_until(lambda: "response-1" not in session._active_tool_groups)

        assert len(scheduler.published) == 1
        assert scheduler.published[0]["tool_name"] == "succeeds"
        assert scheduler.published[0]["text"] == "success-fact"
    finally:
        await stop_session(session)


@pytest.mark.parametrize("tool_call_mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_closing_session_cancels_active_task_manager_work(
    tool_call_mode: str,
) -> None:
    model_api = RecordingModelAPI()
    started = asyncio.Event()
    finalized = asyncio.Event()
    task_events: list[TaskEvent] = []

    async def worker(left: int, right: int) -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finalized.set()
        return "unreachable"

    session, _ = make_agent_session(
        model_api,
        tools=[make_tool("long-running", worker)],
        tool_call_mode=tool_call_mode,
        task_events=task_events,
    )
    session._start_task_manager()
    session._handle_tool_event(
        make_call("call-active", tool_name="long-running")
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task_id = session._active_tool_groups["response-1"].invocations[0].task_id
    if tool_call_mode == "async":
        await wait_until(lambda: len(tool_batches(model_api)) == 1)
    batches_before_close = list(tool_batches(model_api))

    session._closing = True
    await session._stop_tool_groups()
    try:
        await asyncio.wait_for(finalized.wait(), timeout=1)
        await wait_until(
            lambda: any(
                isinstance(event, TaskCancelledEvent) and event.task_id == task_id
                for event in task_events
            )
        )
        assert tool_batches(model_api) == batches_before_close
    finally:
        await session._stop_task_manager()


@pytest.mark.asyncio
async def test_cancel_control_bypasses_full_task_manager_capacity() -> None:
    model_api = RecordingModelAPI()
    manager = TaskManager(max_concurrency=1)
    started = asyncio.Event()
    finalized = asyncio.Event()

    async def long_running(left: int, right: int) -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finalized.set()
        return "unreachable"

    session, _ = make_agent_session(
        model_api,
        tools=[
            make_tool("long-running", long_running),
            create_raw_task_cancel_tool(task_manager=manager),
        ],
        task_manager=manager,
        tool_call_mode="async",
    )
    session._question_contexts["question-1"] = "start then cancel"
    session._start_task_manager()
    try:
        session._handle_tool_event(
            make_call(
                "call-business",
                tool_name="long-running",
                item_id="question-1",
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        await wait_until(lambda: len(tool_batches(model_api)) == 1)
        business_task_id = session._active_tool_groups[
            "response-1"
        ].invocations[0].task_id

        session._handle_tool_event(
            make_call(
                "call-cancel",
                tool_name="cancel_task",
                group_id="cancel-group",
                item_id="question-1",
                arguments={"task_id": business_task_id},
            )
        )

        await asyncio.wait_for(finalized.wait(), timeout=1)
        await wait_until(lambda: len(tool_batches(model_api)) == 2)
        cancel_result = tool_batches(model_api)[1].results[0]
        assert cancel_result.call_id == "call-cancel"
        assert cancel_result.output == f"[已取消] task_id={business_task_id}"
        assert "[占位回执]" not in cancel_result.output
        assert manager.get_task("call-cancel") is None
    finally:
        await stop_session(session)


@pytest.mark.asyncio
async def test_immediate_tool_errors_close_one_group_in_original_order() -> None:
    class RejectingTaskManager(TaskManager):
        def submit_task(self, *args: Any, **kwargs: Any) -> str:
            raise RuntimeError("submission rejected")

    model_api = RecordingModelAPI()
    session, _ = make_agent_session(
        model_api,
        tools=[make_add_tool()],
        task_manager=RejectingTaskManager(),
    )
    try:
        session._handle_tool_event(
            make_call(
                "call-missing",
                tool_name="missing",
                group_size=3,
            )
        )
        session._handle_tool_event(
            make_call(
                "call-invalid",
                group_size=3,
                input_error="invalid provider arguments",
            )
        )
        session._handle_tool_event(
            make_call("call-submit", group_size=3)
        )
        await wait_until(lambda: len(tool_batches(model_api)) == 1)

        results = tool_batches(model_api)[0].results
        assert [result.call_id for result in results] == [
            "call-missing",
            "call-invalid",
            "call-submit",
        ]
        assert all(result.success is False for result in results)
        assert results[0].output == "missing工具未注册"
        assert "invalid provider arguments" in results[1].output
        assert "submission rejected" in results[2].output
        assert session._active_tool_groups == {}
    finally:
        await stop_session(session)


@pytest.mark.parametrize("tool_call_mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_tool_result_submit_failure_is_supervised(
    tool_call_mode: str,
) -> None:
    class RejectingModelAPI(RecordingModelAPI):
        async def submit(self, input: StreamModelInput) -> str | None:
            if isinstance(input, ToolResultBatchInput):
                raise RuntimeError("tool result write failed")
            return await super().submit(input)

    session, _ = make_agent_session(
        RejectingModelAPI(),
        tools=[make_add_tool()],
        tool_call_mode=tool_call_mode,
    )
    session._question_contexts["question-1"] = "calculate"
    session._start_task_manager()
    session._handle_tool_event(
        make_call("call-1", item_id="question-1")
    )
    try:
        with pytest.raises(RuntimeError, match="Duplex background task failed"):
            await asyncio.wait_for(
                session._consume_events_with_background_errors(
                    stop_after_audio=False
                ),
                timeout=1,
            )
    finally:
        await stop_session(session)


@pytest.mark.asyncio
async def test_async_backfill_failure_is_supervised() -> None:
    class RejectingBackfillScheduler(RecordingBackfillScheduler):
        async def publish_backfill(self, **kwargs: object) -> None:
            raise RuntimeError("context update failed")

    model_api = RecordingModelAPI()
    session, _ = make_agent_session(
        model_api,
        tools=[make_add_tool()],
        tool_call_mode="async",
    )
    session._backfill_scheduler = RejectingBackfillScheduler()  # type: ignore[assignment]
    session._question_contexts["question-1"] = "calculate"
    session._start_task_manager()
    session._handle_tool_event(
        make_call("call-1", item_id="question-1")
    )
    try:
        with pytest.raises(RuntimeError, match="Duplex async backfill failed"):
            await asyncio.wait_for(
                session._consume_events_with_background_errors(
                    stop_after_audio=False
                ),
                timeout=1,
            )
    finally:
        await stop_session(session)
