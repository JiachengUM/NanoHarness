"""取消工具测评的观测、判分与命令行执行器。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import os
import sys
import time
from typing import Literal, Protocol

import anyio
from anyio.abc import ObjectReceiveStream, ObjectSendStream

from aicore.events.agent import AgentOutTextDeltaEvent, TaskCreatedEvent
from aicore.events.react import ToolCallStartEvent
from aicore.events.task import TaskSuccessEvent
from aicore.runtime.task import (
    TaskCancelOutcome,
    TaskManager,
    TaskProjection,
)
from aicore.v2.experiments.task_cancel_eval.cases import (
    CANCEL_TOOL_CASES,
    CancelExpectation,
    CancelToolCase,
    ExpectedCancelOutcome,
    ExpectedCancelTarget,
)
from aicore.v2.experiments.task_cancel_tool_v1 import _matching_tasks

__all__ = [
    "CancelEvaluationResult",
    "CancelEvaluationSettings",
    "CaseEvaluationResult",
    "EvaluationAgent",
    "EvaluationAgentBuilder",
    "ObservedCancelCall",
    "ObservedCancelToolCall",
    "ObservingTaskManager",
    "TurnEvaluationResult",
    "evaluate_cancel_evaluation",
    "evaluate_cancel_evaluation_case",
    "evaluate_cancel_expectation",
    "format_cancel_expectation",
    "run_cancel_evaluation",
    "run_cancel_evaluation_cli",
    "run_cancel_evaluation_case",
]


class EvaluationAgentState(Protocol):
    @property
    def trace(self) -> Sequence[object]: ...


class EvaluationAgent(Protocol):
    @property
    def state(self) -> EvaluationAgentState: ...

    def astream(
        self,
        input_data: str | TaskSuccessEvent[object],
    ) -> AsyncIterator[object]: ...


type EvaluationAgentBuilder = Callable[
    [TaskManager, CancelToolCase],
    EvaluationAgent,
]


@dataclass(frozen=True)
class CancelEvaluationSettings:
    delay_scale: float = 0.01
    case_timeout: float = 180.0
    case_concurrency: int = 1

    def __post_init__(self) -> None:
        if self.delay_scale < 0:
            raise ValueError("delay_scale 不能小于 0")
        if self.case_timeout <= 0:
            raise ValueError("case_timeout 必须大于 0")
        if self.case_concurrency <= 0:
            raise ValueError("case_concurrency 必须大于 0")

    @classmethod
    def from_env(cls) -> CancelEvaluationSettings:
        return cls(
            delay_scale=float(
                os.getenv("TASK_CANCEL_EVALUATION_DELAY_SCALE", "0.01")
            ),
            case_timeout=float(
                os.getenv("TASK_CANCEL_EVALUATION_CASE_TIMEOUT", "180")
            ),
            case_concurrency=int(
                os.getenv("TASK_CANCEL_EVALUATION_CONCURRENCY", "1")
            ),
        )


@dataclass(frozen=True)
class ObservedCancelCall:
    task_id: str
    projection: TaskProjection | None
    outcome: TaskCancelOutcome


@dataclass(frozen=True)
class ObservedCancelToolCall:
    name: str
    arguments: dict[str, object]
    active_tasks: tuple[TaskProjection, ...] = ()
    matched_task_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TurnEvaluationResult:
    index: int
    query: str
    expectation: CancelExpectation
    passed: bool
    reasons: tuple[str, ...]
    assistant_text: str
    observed_tool_calls: tuple[ObservedCancelToolCall, ...]
    observed_calls: tuple[ObservedCancelCall, ...]
    duration_s: float
    active_tasks_before: tuple[TaskProjection, ...] = ()
    active_tasks_after: tuple[TaskProjection, ...] = ()


@dataclass(frozen=True)
class CaseEvaluationResult:
    case_name: str
    turns: tuple[TurnEvaluationResult, ...]
    total_turns: int
    duration_s: float
    error_type: Literal["timeout", "exception"] | None = None
    error: str | None = None

    @property
    def passed_turns(self) -> int:
        return sum(result.passed for result in self.turns)

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and len(self.turns) == self.total_turns
            and self.passed_turns == self.total_turns
        )


@dataclass(frozen=True)
class CancelEvaluationResult:
    cases: tuple[CaseEvaluationResult, ...]

    @property
    def passed_cases(self) -> int:
        return sum(result.passed for result in self.cases)

    @property
    def total_cases(self) -> int:
        return len(self.cases)

    @property
    def passed_turns(self) -> int:
        return sum(result.passed_turns for result in self.cases)

    @property
    def total_turns(self) -> int:
        return sum(result.total_turns for result in self.cases)

    @property
    def passed(self) -> bool:
        return self.passed_cases == self.total_cases

    @property
    def cancel_tool_calls(self) -> int:
        return sum(
            len(turn.observed_tool_calls)
            for case in self.cases
            for turn in case.turns
        )

    @property
    def manager_cancel_calls(self) -> int:
        return sum(
            len(turn.observed_calls)
            for case in self.cases
            for turn in case.turns
        )

    @property
    def expected_cancel_turns(self) -> int:
        return sum(
            turn.expectation.decision == "call"
            for case in self.cases
            for turn in case.turns
        )

    @property
    def passed_cancel_turns(self) -> int:
        return sum(
            turn.passed and turn.expectation.decision == "call"
            for case in self.cases
            for turn in case.turns
        )


class ObservingTaskManager(TaskManager):
    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls: list[ObservedCancelCall] = []

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        projection = self.get_projection(task_id)
        outcome = super().cancel_task(task_id)
        self.cancel_calls.append(
            ObservedCancelCall(
                task_id=task_id,
                projection=projection,
                outcome=outcome,
            )
        )
        return outcome


async def _sleep(delay: float) -> None:
    await anyio.sleep(delay)


def _snapshot_active_tasks(
    task_manager: TaskManager,
) -> tuple[TaskProjection, ...]:
    return tuple(
        projection.model_copy(deep=True)
        for projection in task_manager.get_active_task_projections()
    )


def _agent_trace_snapshot(agent: EvaluationAgent) -> tuple[object, ...]:
    return tuple(agent.state.trace)


def _cancel_tool_calls_from_trace(
    trace: Sequence[object],
    active_tasks: Sequence[TaskProjection],
) -> tuple[ObservedCancelToolCall, ...]:
    calls: list[ObservedCancelToolCall] = []
    for event in trace:
        if not isinstance(event, ToolCallStartEvent):
            continue
        if event.name != "cancel_task":
            continue

        arguments = dict(event.arguments)
        matched_task_ids: tuple[str, ...] | None = None
        if "target_hint" in arguments:
            raw_target_hint = arguments.get("target_hint")
            target_hint = (
                raw_target_hint
                if isinstance(raw_target_hint, str)
                else None
            )
            matched_task_ids = tuple(
                task.task_id
                for task in _matching_tasks(list(active_tasks), target_hint)
            )

        calls.append(
            ObservedCancelToolCall(
                name=event.name,
                arguments=arguments,
                active_tasks=tuple(active_tasks),
                matched_task_ids=matched_task_ids,
            )
        )
    return tuple(calls)


def _format_expected_target(
    target: ExpectedCancelTarget,
    outcome: ExpectedCancelOutcome,
) -> str:
    arguments = ", ".join(
        f"{key}~{value}"
        for key, value in target.argument_contains
    )
    return f"{target.tool_name}({arguments}) -> {outcome}"


def format_cancel_expectation(expectation: CancelExpectation) -> str:
    if expectation.decision != "call":
        return f"{expectation.decision}: {expectation.note}"

    targets = (
        _format_expected_target(target, outcome)
        for target, outcome in zip(
            expectation.targets,
            expectation.outcomes,
            strict=True,
        )
    )
    return f"call: {'; '.join(targets)} | {expectation.note}"


def _target_matches(
    call: ObservedCancelCall,
    target: ExpectedCancelTarget,
    outcome: ExpectedCancelOutcome,
) -> bool:
    projection = call.projection
    if (
        projection is None
        or projection.tool_name != target.tool_name
        or call.outcome.status != outcome
    ):
        return False

    for key, expected in target.argument_contains:
        actual = projection.arguments.get(key)
        if actual is None or expected.casefold() not in str(actual).casefold():
            return False
    return True


def _looks_like_clarification(text: str) -> bool:
    markers = (
        "?",
        "？",
        "哪个",
        "哪一个",
        "具体",
        "请明确",
        "请说明",
        "请指定",
        "还是",
    )
    normalized = text.strip()
    return bool(normalized) and any(marker in normalized for marker in markers)


def evaluate_cancel_expectation(
    expectation: CancelExpectation,
    actual_calls: Sequence[ObservedCancelCall],
    assistant_text: str,
    *,
    actual_tool_calls: Sequence[ObservedCancelToolCall] = (),
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []

    if expectation.decision != "call":
        if actual_calls:
            reasons.append(
                "预期不执行取消，TaskManager 实际收到 "
                f"{len(actual_calls)} 次取消调用"
            )
        if (
            expectation.decision in {"none", "reject"}
            and actual_tool_calls
        ):
            reasons.append(
                "预期模型不调用取消工具，实际调用 "
                f"{len(actual_tool_calls)} 次"
            )
        if (
            expectation.decision == "clarify"
            and not _looks_like_clarification(assistant_text)
        ):
            reasons.append("预期澄清，但回复不像澄清问题")
        return not reasons, tuple(reasons)

    if len(actual_calls) != len(expectation.targets):
        reasons.append(
            f"预期取消 {len(expectation.targets)} 个任务，"
            "TaskManager 实际收到 "
            f"{len(actual_calls)} 次取消调用"
        )

    unmatched = set(range(len(actual_calls)))
    for target, outcome in zip(
        expectation.targets,
        expectation.outcomes,
        strict=True,
    ):
        matched_index = next(
            (
                index
                for index in unmatched
                if _target_matches(actual_calls[index], target, outcome)
            ),
            None,
        )
        if matched_index is None:
            reasons.append(
                "未观察到预期取消结果: "
                + _format_expected_target(target, outcome)
            )
        else:
            unmatched.remove(matched_index)

    return not reasons, tuple(reasons)


def _format_observed_call(call: ObservedCancelCall) -> str:
    projection = call.projection
    if projection is None:
        target = f"task_id={call.task_id}"
    else:
        arguments = ", ".join(
            f"{key}={value}"
            for key, value in projection.arguments.items()
        )
        target = f"{projection.tool_name}({arguments})"
    return f"{target} -> {call.outcome.status}"


def _format_observed_tool_call(call: ObservedCancelToolCall) -> str:
    arguments = json.dumps(
        call.arguments,
        ensure_ascii=False,
        sort_keys=True,
    )
    result = f"{call.name}({arguments})"
    if call.matched_task_ids is not None:
        result += (
            " | matcher="
            f"{len(call.matched_task_ids)} match(es)"
            f" {list(call.matched_task_ids)}"
        )
    return result


def _format_active_task(task: TaskProjection) -> str:
    arguments = json.dumps(
        task.arguments,
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        f"{task.task_id}: {task.tool_name}({arguments})"
        f" [{task.status.value}]"
    )


async def _run_agent_input(
    agent: EvaluationAgent,
    input_data: str | TaskSuccessEvent[object],
    *,
    print_events: bool,
) -> str:
    text_parts: list[str] = []
    async for event in agent.astream(input_data):
        if isinstance(event, AgentOutTextDeltaEvent):
            text_parts.append(event.delta)
            if print_events:
                print(event.delta, end="", flush=True)
        elif print_events and isinstance(event, TaskCreatedEvent):
            print(
                f"\n      [submitted] {event.name}"
                f" task_id={event.task_id} arguments={event.arguments}"
            )
    if print_events and text_parts:
        print()
    return "".join(text_parts).strip()


async def _collect_task_successes(
    task_manager: TaskManager,
    send_stream: ObjectSendStream[TaskSuccessEvent[object]],
) -> None:
    async with send_stream:
        async for event in task_manager.astream():
            if isinstance(event, TaskSuccessEvent):
                await send_stream.send(event)


async def _backfill_task_successes(
    agent: EvaluationAgent,
    receive_stream: ObjectReceiveStream[TaskSuccessEvent[object]],
    *,
    verbose: bool,
) -> None:
    await _sleep(0)
    while True:
        try:
            event = receive_stream.receive_nowait()
        except (anyio.WouldBlock, anyio.EndOfStream):
            return
        if verbose:
            print(f"      [backfill] task_id={event.task_id}")
        await _run_agent_input(agent, event, print_events=False)


async def evaluate_cancel_evaluation_case(
    case_name: str,
    *,
    case: CancelToolCase,
    agent_builder: EvaluationAgentBuilder,
    delay_scale: float,
    verbose: bool = False,
) -> CaseEvaluationResult:
    case_started = time.perf_counter()
    task_manager = ObservingTaskManager()
    agent = agent_builder(task_manager, case)
    success_send, success_receive = anyio.create_memory_object_stream[
        TaskSuccessEvent[object]
    ](100)
    turn_results: list[TurnEvaluationResult] = []

    if verbose:
        print(f"\n{'=' * 72}")
        print(f"[CASE] {case_name}")
        print(f"{'=' * 72}")

    async with success_receive, anyio.create_task_group() as task_group:
        task_group.start_soon(task_manager.run)
        task_group.start_soon(
            _collect_task_successes,
            task_manager,
            success_send,
        )

        for index, turn in enumerate(case.turns):
            delay = turn.delay * delay_scale
            if delay:
                await _sleep(delay)
            await _backfill_task_successes(
                agent,
                success_receive,
                verbose=verbose,
            )

            if verbose:
                print(f"\n  [TURN {index}] {turn.query}")
                print(
                    "    expected: "
                    + format_cancel_expectation(turn.expectation)
                )
            call_start = len(task_manager.cancel_calls)
            active_tasks_before = _snapshot_active_tasks(task_manager)
            trace_start = len(_agent_trace_snapshot(agent))
            turn_started = time.perf_counter()
            assistant_text = await _run_agent_input(
                agent,
                turn.query,
                print_events=verbose,
            )
            turn_duration = time.perf_counter() - turn_started
            actual_tool_calls = _cancel_tool_calls_from_trace(
                _agent_trace_snapshot(agent)[trace_start:],
                active_tasks_before,
            )
            actual_calls = tuple(task_manager.cancel_calls[call_start:])
            active_tasks_after = _snapshot_active_tasks(task_manager)
            passed, reasons = evaluate_cancel_expectation(
                turn.expectation,
                actual_calls,
                assistant_text,
                actual_tool_calls=actual_tool_calls,
            )
            if turn.expected_active_tasks_after is not None:
                active_task_count = len(
                    task_manager.get_active_task_projections()
                )
                if active_task_count != turn.expected_active_tasks_after:
                    reasons = (
                        *reasons,
                        "预期本轮结束后有 "
                        f"{turn.expected_active_tasks_after} 个活跃任务，"
                        f"实际为 {active_task_count} 个",
                    )
                    passed = False
            turn_result = TurnEvaluationResult(
                index=index,
                query=turn.query,
                expectation=turn.expectation,
                passed=passed,
                reasons=reasons,
                assistant_text=assistant_text,
                observed_tool_calls=actual_tool_calls,
                observed_calls=actual_calls,
                duration_s=turn_duration,
                active_tasks_before=active_tasks_before,
                active_tasks_after=active_tasks_after,
            )
            turn_results.append(turn_result)

            if verbose:
                tool_arguments = (
                    "; ".join(
                        map(_format_observed_tool_call, actual_tool_calls)
                    )
                    if actual_tool_calls
                    else "no cancel tool call"
                )
                actual = (
                    "; ".join(map(_format_observed_call, actual_calls))
                    if actual_calls
                    else "no manager cancel call"
                )
                print(f"    model:    {tool_arguments}")
                print(f"    resolved: {actual}")
                if active_tasks_before:
                    print("    active before:")
                    for task in active_tasks_before:
                        print(f"      - {_format_active_task(task)}")
                if active_tasks_after:
                    print("    active after:")
                    for task in active_tasks_after:
                        print(f"      - {_format_active_task(task)}")
                if assistant_text:
                    print(f"    reply:    {assistant_text}")
                print(
                    f"    duration: {turn_duration:.3f}s\n"
                    f"    result:   {'PASS' if passed else 'FAIL'}"
                )
                for reason in reasons:
                    print(f"      - {reason}")

        task_group.cancel_scope.cancel()

    result = CaseEvaluationResult(
        case_name=case_name,
        turns=tuple(turn_results),
        total_turns=len(case.turns),
        duration_s=time.perf_counter() - case_started,
    )
    if verbose:
        print(
            f"\n[CASE {'PASS' if result.passed else 'FAIL'}] "
            f"{case_name}: {result.passed_turns}/{result.total_turns} turns "
            f"in {result.duration_s:.3f}s"
        )
    return result


async def run_cancel_evaluation_case(
    case_name: str,
    *,
    case: CancelToolCase,
    agent_builder: EvaluationAgentBuilder,
    delay_scale: float,
) -> tuple[int, int]:
    result = await evaluate_cancel_evaluation_case(
        case_name,
        case=case,
        agent_builder=agent_builder,
        delay_scale=delay_scale,
        verbose=True,
    )
    return result.passed_turns, result.total_turns


def _selected_case_names(
    case_names: str | Sequence[str] | None,
    cases: Mapping[str, CancelToolCase],
) -> list[str]:
    if case_names is None:
        return list(cases)

    names = [case_names] if isinstance(case_names, str) else list(case_names)
    if not names:
        return list(cases)
    if "all" in names:
        if len(names) != 1:
            raise ValueError("all 不能和具体 cancel case 同时指定")
        return list(cases)

    selected: list[str] = []
    for case_name in names:
        if case_name not in cases:
            available = ", ".join(cases)
            raise ValueError(
                f"未知 cancel case: {case_name!r}. 可选: all, {available}"
            )
        if case_name not in selected:
            selected.append(case_name)
    return selected


async def _evaluate_case_safely(
    case_name: str,
    *,
    case: CancelToolCase,
    agent_builder: EvaluationAgentBuilder,
    settings: CancelEvaluationSettings,
    verbose: bool,
) -> CaseEvaluationResult:
    case_started = time.perf_counter()
    try:
        with anyio.fail_after(settings.case_timeout):
            return await evaluate_cancel_evaluation_case(
                case_name,
                case=case,
                agent_builder=agent_builder,
                delay_scale=settings.delay_scale,
                verbose=verbose,
            )
    except TimeoutError:
        result = CaseEvaluationResult(
            case_name=case_name,
            turns=(),
            total_turns=len(case.turns),
            duration_s=time.perf_counter() - case_started,
            error_type="timeout",
            error=f"超过 {settings.case_timeout:g}s 超时",
        )
    except Exception as exc:
        result = CaseEvaluationResult(
            case_name=case_name,
            turns=(),
            total_turns=len(case.turns),
            duration_s=time.perf_counter() - case_started,
            error_type="exception",
            error=_format_exception(exc),
        )

    if verbose:
        print(f"\n[CASE FAIL] {case_name}: {result.error}")
    return result


def _format_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        nested = "; ".join(
            _format_exception(error)
            for error in exc.exceptions
        )
        return f"{type(exc).__name__}: {nested}"
    return f"{type(exc).__name__}: {exc}"


async def evaluate_cancel_evaluation(
    case_names: str | Sequence[str] | None = None,
    *,
    agent_builder: EvaluationAgentBuilder,
    cases: Mapping[str, CancelToolCase] = CANCEL_TOOL_CASES,
    settings: CancelEvaluationSettings | None = None,
    verbose: bool = False,
) -> CancelEvaluationResult:
    settings = settings or CancelEvaluationSettings.from_env()
    selected_cases = _selected_case_names(case_names, cases)
    results: list[CaseEvaluationResult | None] = [
        None
        for _ in selected_cases
    ]
    semaphore = anyio.Semaphore(settings.case_concurrency)

    async def evaluate_one(index: int, case_name: str) -> None:
        async with semaphore:
            results[index] = await _evaluate_case_safely(
                case_name,
                case=cases[case_name],
                agent_builder=agent_builder,
                settings=settings,
                verbose=verbose,
            )

    async with anyio.create_task_group() as task_group:
        for index, case_name in enumerate(selected_cases):
            task_group.start_soon(evaluate_one, index, case_name)

    completed_results = tuple(
        result
        for result in results
        if result is not None
    )
    if len(completed_results) != len(selected_cases):
        raise RuntimeError("取消评测存在未完成的 case")

    evaluation = CancelEvaluationResult(cases=completed_results)
    if verbose:
        print(f"\n{'#' * 72}")
        print(
            f"[SUMMARY] {'PASS' if evaluation.passed else 'FAIL'} | "
            f"cases={evaluation.passed_cases}/{evaluation.total_cases} | "
            f"turns={evaluation.passed_turns}/{evaluation.total_turns}"
        )
        print(
            "[CANCEL] "
            f"model_calls={evaluation.cancel_tool_calls} | "
            f"manager_calls={evaluation.manager_cancel_calls} | "
            "passed_cancel_turns="
            f"{evaluation.passed_cancel_turns}/"
            f"{evaluation.expected_cancel_turns}"
        )
        print(f"{'#' * 72}")
    return evaluation


async def run_cancel_evaluation(
    case_name: str | None = None,
    *,
    agent_builder: EvaluationAgentBuilder,
    cases: Mapping[str, CancelToolCase] = CANCEL_TOOL_CASES,
    settings: CancelEvaluationSettings | None = None,
) -> bool:
    settings = settings or CancelEvaluationSettings.from_env()
    selected_cases = _selected_case_names(case_name, cases)
    passed_cases = 0
    passed_turns = 0
    total_turns = 0

    for selected_case in selected_cases:
        case = cases[selected_case]
        try:
            with anyio.fail_after(settings.case_timeout):
                case_passed, case_total = await run_cancel_evaluation_case(
                    selected_case,
                    case=case,
                    agent_builder=agent_builder,
                    delay_scale=settings.delay_scale,
                )
        except TimeoutError:
            case_passed = 0
            case_total = len(case.turns)
            print(
                f"\n[CASE FAIL] {selected_case}: "
                f"超过 {settings.case_timeout:g}s 超时"
            )
        except Exception as exc:
            case_passed = 0
            case_total = len(case.turns)
            print(
                f"\n[CASE FAIL] {selected_case}: "
                f"{type(exc).__name__}: {exc}"
            )

        passed_turns += case_passed
        total_turns += case_total
        passed_cases += int(case_passed == case_total)

    all_passed = passed_cases == len(selected_cases)
    print(f"\n{'#' * 72}")
    print(
        f"[SUMMARY] {'PASS' if all_passed else 'FAIL'} | "
        f"cases={passed_cases}/{len(selected_cases)} | "
        f"turns={passed_turns}/{total_turns}"
    )
    print(f"{'#' * 72}")
    return all_passed


def run_cancel_evaluation_cli(
    agent_builder: EvaluationAgentBuilder,
    *,
    program_name: str,
    argv: Sequence[str] | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        print(f"用法: python {program_name} [case_name|all]")
        return 2

    case_name = arguments[0] if arguments else None

    async def run() -> bool:
        evaluation = await evaluate_cancel_evaluation(
            case_name,
            agent_builder=agent_builder,
            verbose=True,
        )
        return evaluation.passed

    try:
        passed = anyio.run(run)
    except ValueError as exc:
        print(exc)
        return 2
    return 0 if passed else 1
