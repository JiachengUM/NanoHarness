from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import time
from typing import Any

import anyio
from pydantic import BaseModel

_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if sys.path[0] != _PROJECT_ROOT:
    sys.path.insert(0, _PROJECT_ROOT)

from aicore.events.agent import (
    AgentOutEvent,
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.events.task import (
    TaskCancelledEvent,
    TaskCreatedEvent,
    TaskEvent,
    TaskFailureEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskManager, TaskSuccess
from aicore.simulation.user_env.data_source import UserDataMocked
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.agent_runner import AgentRunner
from aicore.v2.experiments.poi_search_v2 import poi_search_v2_tool
from aicore.v2.experiments.react_agent_with_task_runner import (
    create_react_agent_with_task_runner,
    render_active_task_context,
)
from aicore.v2.tools.async_task import (
    AsyncableTaskTool,
    AsyncTaskReceipt,
    AsyncTaskResultBackfill,
)
from projects.mind.toolset.car_control import CarControlTool


CHAT_ID = os.getenv("V2_REACT_TEST_CHAT_ID", "v2-react-real-tool-test")
CASE_TIMEOUT_SECONDS = 45.0

SYSTEM_PROMPT = """你是车载助手。需要工具时，一次性调用完成请求所需的全部工具。
基本信息：我在上海市徐汇滨江城开中心 T2 楼，今天是 2026 年 7 月 27 日。
每个工具独立选择 with_async：遵循用户明确要求；否则仅当工具预计耗时较长且当前处理不依赖其即时结果时设为 true，其余保持 false。
- 例如搜索类任务：地点和POI搜索、音乐搜索、和联网搜索都属于耗时较长任务，将with_async设置为true
"""


@dataclass(frozen=True)
class ExperimentCase:
    name: str
    query: str
    expected_post_tool_responses: int
    expected_async_modes: dict[str, bool]


CASES = [
    ExperimentCase(
        name="default_sync",
        query="打开空调",
        expected_post_tool_responses=1,
        expected_async_modes={"car_control": False},
    ),
    ExperimentCase(
        name="explicit_async",
        query="异步方式打开空调",
        expected_post_tool_responses=2,
        expected_async_modes={"car_control": True},
    ),
    ExperimentCase(
        name="mixed_modes",
        query="打开空调，并且搜索附近的人均100左右的咖啡店",
        expected_post_tool_responses=2,
        expected_async_modes={
            "car_control": False,
            "地点搜索工具": True,
        },
    ),
    ExperimentCase(
        name="sync_poi_search",
        query="同步搜索人均100的咖啡店",
        expected_post_tool_responses=1,
        expected_async_modes={"地点搜索工具": False},
    ),
]


@dataclass(frozen=True)
class TraceEntry:
    elapsed: float
    kind: str
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    text: str | None = None
    task_id: str | None = None


class Timeline:
    def __init__(self, case_name: str) -> None:
        self.case_name = case_name
        self.started_at = time.monotonic()
        self.entries: list[TraceEntry] = []

    def record(
        self,
        kind: str,
        *,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
        text: str | None = None,
        task_id: str | None = None,
    ) -> TraceEntry:
        entry = TraceEntry(
            elapsed=time.monotonic() - self.started_at,
            kind=kind,
            tool_name=tool_name,
            arguments=arguments,
            text=text,
            task_id=task_id,
        )
        self.entries.append(entry)

        details = f" tool={tool_name}" if tool_name is not None else ""
        if arguments is not None:
            details += f" arguments={arguments}"
        if task_id is not None:
            details += f" task_id={task_id}"
        if text:
            details += f" text={text!r}"
        print(f"[{entry.elapsed:7.3f}s] {kind}{details}")
        return entry

    def find(
        self,
        kind: str,
        *,
        tool_name: str | None = None,
    ) -> list[TraceEntry]:
        return [
            entry
            for entry in self.entries
            if entry.kind == kind
            and (tool_name is None or entry.tool_name == tool_name)
        ]


class ObservedTool:
    def __init__(
        self,
        inner_tool: TaskToolProtocolGeneral,
        timeline: Timeline,
    ) -> None:
        self.inner_tool = inner_tool
        self.timeline = timeline

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
        self._record_call(args, kwargs)
        inner_worker = self.inner_tool.simple_worker(*args, **kwargs)

        async def observed_worker():
            self.timeline.record(
                "worker.start",
                tool_name=self.name,
                arguments=dict(kwargs),
            )
            result = await inner_worker()
            if not isinstance(result, AsyncTaskReceipt):
                self.timeline.record("worker.done", tool_name=self.name)
            return result

        return observed_worker

    def stream_worker_factory(self, *args: Any, **kwargs: Any):
        self._record_call(args, kwargs)
        inner_factory = self.inner_tool.stream_worker_factory(*args, **kwargs)

        async def observed_factory():
            self.timeline.record(
                "worker.start",
                tool_name=self.name,
                arguments=dict(kwargs),
            )
            async for event in inner_factory():
                if (
                    isinstance(event, TaskSuccess)
                    and not isinstance(event.result, AsyncTaskReceipt)
                ):
                    self.timeline.record("worker.done", tool_name=self.name)
                yield event

        return observed_factory

    def _record_call(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        if args:
            raise TypeError("ObservedTool 只支持 keyword arguments")
        self.timeline.record(
            "tool.call.effective",
            tool_name=self.name,
            arguments=dict(kwargs),
        )


def create_experiment_tools(
    task_manager: TaskManager,
    timeline: Timeline,
) -> list[TaskToolProtocolGeneral]:
    car_control_tool = AsyncableTaskTool(
        CarControlTool(chat_id=CHAT_ID),
        asyncable="dynamic",
        task_manager=task_manager,
    )
    poi_tool = poi_search_v2_tool(
        task_manager=task_manager,
        asyncable="dynamic",
    )
    return [
        ObservedTool(car_control_tool, timeline),  # type: ignore[list-item]
        ObservedTool(poi_tool, timeline),  # type: ignore[list-item]
    ]


class TimelineCollector:
    def __init__(
        self,
        timeline: Timeline,
        *,
        expected_post_tool_responses: int,
        expected_async_modes: dict[str, bool],
    ) -> None:
        self.timeline = timeline
        self.expected_post_tool_responses = expected_post_tool_responses
        self.expected_async_modes = expected_async_modes
        self.done = anyio.Event()
        self._text_parts: list[str] = []

    def __call__(self, event: AgentOutEvent | TaskEvent) -> None:
        match event:
            case AgentOutTextStartEvent():
                self._text_parts = []
            case AgentOutTextDeltaEvent(delta=delta):
                self._text_parts.append(delta)
            case AgentOutTextDoneEvent():
                text = "".join(self._text_parts).strip()
                kind = (
                    "agent.reply.after_tool"
                    if self.timeline.find("tool.call.effective")
                    else "agent.reply.before_tool"
                )
                self.timeline.record(kind, text=text)
                if (
                    kind == "agent.reply.after_tool"
                    and (
                        len(self.timeline.find(kind))
                        >= self.expected_post_tool_responses
                        or self._has_mode_mismatch()
                    )
                ):
                    self.done.set()
            case TaskCreatedEvent(
                task_id=task_id,
                name=name,
                arguments=arguments,
            ):
                self.timeline.record(
                    "task.created",
                    tool_name=name,
                    arguments=arguments,
                    task_id=task_id,
                )
            case TaskStartEvent(task_id=task_id):
                self.timeline.record("task.started", task_id=task_id)
            case TaskProgressEvent(task_id=task_id):
                self.timeline.record("task.progress", task_id=task_id)
            case TaskSuccessEvent(task_id=task_id, result=result):
                if isinstance(result, AsyncTaskResultBackfill):
                    self.timeline.record(
                        "task.backfill",
                        tool_name=result.tool_name,
                        task_id=task_id,
                    )
                else:
                    self.timeline.record("task.succeeded", task_id=task_id)
            case TaskFailureEvent(task_id=task_id, error=error):
                self.timeline.record(
                    "task.failed",
                    text=str(error),
                    task_id=task_id,
                )
            case TaskCancelledEvent(task_id=task_id, reason=reason):
                self.timeline.record(
                    "task.cancelled",
                    text=reason,
                    task_id=task_id,
                )

    def _has_mode_mismatch(self) -> bool:
        for entry in self.timeline.find("tool.call.effective"):
            if entry.tool_name not in self.expected_async_modes:
                continue
            if entry.arguments is None:
                return True
            if entry.arguments.get("clarify"):
                return True
            reason = entry.arguments.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                return True
            expected = self.expected_async_modes[entry.tool_name]
            if entry.arguments.get("with_async") is not expected:
                return True
        return False


class DirectObservedAgentRunner(AgentRunner):
    """实验专用：按 agent yield 顺序同步记录事件，避免 client 队列改变时间顺序。"""

    async def _process_agent_out_event(self, event: AgentOutEvent) -> None:
        self._client(event)


async def _run_agent_safely(
    runner: AgentRunner,
    collector: TimelineCollector,
    timeline: Timeline,
) -> None:
    try:
        await runner.run()
    except Exception as exc:
        timeline.record("runner.error", text=repr(exc))
        collector.done.set()


async def _wait_for_completion(
    done: anyio.Event,
    *,
    timeout_seconds: float,
) -> bool:
    with anyio.move_on_after(timeout_seconds) as cancel_scope:
        await done.wait()
    return not cancel_scope.cancel_called


async def run_experiment_case(case: ExperimentCase) -> Timeline:
    print(f"\n{'=' * 80}")
    print(f"CASE {case.name}: {case.query}")
    print(f"{'=' * 80}")

    timeline = Timeline(case.name)
    timeline.record("user.query", text=case.query)
    task_manager = TaskManager()
    tools = create_experiment_tools(task_manager, timeline)
    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_2_0_PRO_260215,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        max_turns=5,
        ambient_context_provider=lambda: render_active_task_context(task_manager),
    )
    collector = TimelineCollector(
        timeline,
        expected_post_tool_responses=case.expected_post_tool_responses,
        expected_async_modes=case.expected_async_modes,
    )
    runner = DirectObservedAgentRunner(
        user_data=UserDataMocked([case.query]),
        agent=agent,
        task_manager=task_manager,
        client=collector,
    )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(
            _run_agent_safely,
            runner,
            collector,
            timeline,
        )
        completed = await _wait_for_completion(
            collector.done,
            timeout_seconds=CASE_TIMEOUT_SECONDS,
        )
        task_group.cancel_scope.cancel()

    if not completed:
        timeline.record(
            "case.timeout",
            text=f"超过 {CASE_TIMEOUT_SECONDS:.0f}s",
        )

    return timeline


def _effective_call(
    timeline: Timeline,
    tool_name: str,
) -> TraceEntry | None:
    calls = timeline.find("tool.call.effective", tool_name=tool_name)
    return calls[0] if len(calls) == 1 else None


def _first_elapsed(
    timeline: Timeline,
    kind: str,
    *,
    tool_name: str | None = None,
) -> float | None:
    entries = timeline.find(kind, tool_name=tool_name)
    return entries[0].elapsed if entries else None


def evaluate_case(
    case: ExperimentCase,
    timeline: Timeline,
) -> bool:
    checks: list[tuple[str, bool]] = []

    def add(label: str, passed: bool) -> None:
        checks.append((label, passed))

    air_call = _effective_call(timeline, "car_control")
    poi_call = _effective_call(timeline, "地点搜索工具")
    calls_by_tool = {
        "car_control": air_call,
        "地点搜索工具": poi_call,
    }
    for tool_name in case.expected_async_modes:
        call = calls_by_tool[tool_name]
        reason = call.arguments.get("reason") if call and call.arguments else None
        add(
            f"{tool_name} 输出非空 reason",
            isinstance(reason, str) and bool(reason.strip()),
        )

    air_created = bool(timeline.find("task.created", tool_name="car_control"))
    poi_created = bool(timeline.find("task.created", tool_name="地点搜索工具"))
    air_done = _first_elapsed(timeline, "worker.done", tool_name="car_control")
    if air_done is None:
        air_done = _first_elapsed(timeline, "task.backfill", tool_name="car_control")
    poi_done = _first_elapsed(timeline, "worker.done", tool_name="地点搜索工具")
    if poi_done is None:
        poi_done = _first_elapsed(
            timeline,
            "task.backfill",
            tool_name="地点搜索工具",
        )
    first_reply = _first_elapsed(timeline, "agent.reply.after_tool")
    replies = timeline.find("agent.reply.after_tool")

    if case.name == "default_sync":
        add(
            "空调调用 with_async=False",
            air_call is not None
            and air_call.arguments is not None
            and air_call.arguments.get("with_async") is False,
        )
        add("空调不创建后台任务", not air_created)
        add(
            "首次工具后回复不早于 worker 完成",
            first_reply is not None
            and air_done is not None
            and first_reply >= air_done,
        )
    elif case.name == "explicit_async":
        add(
            "空调调用 with_async=True",
            air_call is not None
            and air_call.arguments is not None
            and air_call.arguments.get("with_async") is True,
        )
        add("空调创建后台任务", air_created)
        add(
            "首次工具后回复早于 worker 完成",
            first_reply is not None
            and air_done is not None
            and first_reply < air_done,
        )
        add(
            "空调结果发生 backfill",
            bool(timeline.find("task.backfill", tool_name="car_control")),
        )
        add("至少产生两次工具后回复", len(replies) >= 2)
    elif case.name == "mixed_modes":
        add(
            "空调调用 with_async=False",
            air_call is not None
            and air_call.arguments is not None
            and air_call.arguments.get("with_async") is False,
        )
        add(
            "POI 调用 with_async=True",
            poi_call is not None
            and poi_call.arguments is not None
            and poi_call.arguments.get("with_async") is True,
        )
        add(
            "POI 未走澄清短路",
            poi_call is not None
            and poi_call.arguments is not None
            and not poi_call.arguments.get("clarify"),
        )
        add("空调不创建后台任务", not air_created)
        add("只有 POI 创建后台任务", poi_created)
        add(
            "首次工具后回复不早于空调 worker 完成",
            first_reply is not None
            and air_done is not None
            and first_reply >= air_done,
        )
        add(
            "POI 结果发生 backfill",
            bool(timeline.find("task.backfill", tool_name="地点搜索工具")),
        )
    elif case.name == "sync_poi_search":
        add(
            "POI 调用 with_async=False",
            poi_call is not None
            and poi_call.arguments is not None
            and poi_call.arguments.get("with_async") is False,
        )
        add(
            "POI 未走澄清短路",
            poi_call is not None
            and poi_call.arguments is not None
            and not poi_call.arguments.get("clarify"),
        )
        add("POI 不创建后台任务", not poi_created)
        add(
            "首次工具后回复不早于 POI worker 完成",
            first_reply is not None
            and poi_done is not None
            and first_reply >= poi_done,
        )
    else:
        raise ValueError(f"未知 case: {case.name}")

    print(f"\n[CASE SUMMARY] {case.name}")
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    for tool_name in case.expected_async_modes:
        call = calls_by_tool[tool_name]
        if call is not None and call.arguments is not None:
            print(f"  {tool_name} reason: {call.arguments.get('reason')}")
    if first_reply is not None:
        print(f"  首次工具后回复耗时: {first_reply:.3f}s")
    if air_done is not None:
        print(f"  空调 worker 完成耗时: {air_done:.3f}s")
    if poi_done is not None:
        print(f"  POI worker 完成耗时: {poi_done:.3f}s")

    passed = all(result for _, result in checks)
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


async def main() -> None:
    results: list[tuple[str, bool]] = []
    for case in CASES:
        timeline = await run_experiment_case(case)
        results.append((case.name, evaluate_case(case, timeline)))

    print(f"\n{'=' * 80}")
    print("ALL CASES")
    for case_name, passed in results:
        print(f"  {case_name}: {'PASS' if passed else 'FAIL'}")
    print(f"OVERALL: {'PASS' if all(passed for _, passed in results) else 'FAIL'}")


if __name__ == "__main__":
    anyio.run(main)
