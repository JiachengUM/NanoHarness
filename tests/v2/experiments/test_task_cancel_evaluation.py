from __future__ import annotations

from types import SimpleNamespace

import anyio
import pytest

from aicore.events.agent import AgentOutTextDeltaEvent, TaskCreatedEvent
from aicore.events.react import ToolCallStartEvent
from aicore.events.task import TaskSuccessEvent
from aicore.runtime.task import (
    TaskCancelOutcome,
    TaskManager,
    TaskProjection,
    TaskStatus,
    TaskSuccess,
)
from aicore.v2.experiments.task_cancel_eval import (
    runner as evaluation_runner,
)
from aicore.v2.experiments.task_cancel_eval.cases import (
    CANCEL_TOOL_CASES,
    CancelCaseTurn,
    CancelExpectation,
    CancelToolCase,
    ExpectedCancelTarget,
    build_simulated_business_tools,
)
from aicore.v2.experiments.task_cancel_eval.runner import (
    CancelEvaluationSettings,
    ObservedCancelCall,
    ObservedCancelToolCall,
    ObservingTaskManager,
    evaluate_cancel_expectation,
    format_cancel_expectation,
    run_cancel_evaluation,
)
from aicore.v2.tools.async_task import AsyncTaskReceipt


def test_cases_have_explicit_tool_agnostic_expectations() -> None:
    assert set(CANCEL_TOOL_CASES) == {
        "running_task_cancel",
        "ambiguous_cancel_multiple_tasks",
        "targeted_cancel_one_of_many",
        "cancel_already_terminal_task",
        "single_task_status_query",
        "modify_task_supersedes_old",
        "modify_poi_add_filters",
        "double_cancel_same_task",
        "cancel_then_late_result_should_not_backfill",
        "double_cancel_ask_history",
        "cancel_all_then_new_task_same_turn",
        "cancel_one_then_follow_other",
        "cancel_task_which_not_right",
        "ambiguous_clarify_then_cancel",
        "cancel_control_not_async_task",
        "cancel_search_with_sync_control",
        "same_tool_two_instances_targeted_cancel",
        "same_argument_collision_needs_clarification",
        "negative_cancel_utterance",
        "cancel_without_active_task",
        "cancel_then_restart_same_goal",
        "async_and_sync",
        "five_active_easy_unique_target",
        "five_active_same_tool_target",
        "conjunctive_target_not_expressible",
        "non_string_argument_target",
        "cancel_subset_of_five",
        "stale_task_id_history",
        "restart_same_goal_cancel_new_instance",
    }

    decisions = set()
    outcomes = set()
    target_tool_names = set()
    queries = []
    for case in CANCEL_TOOL_CASES.values():
        assert case.turns
        for turn in case.turns:
            expectation = turn.expectation
            decisions.add(expectation.decision)
            outcomes.update(expectation.outcomes)
            target_tool_names.update(
                target.tool_name
                for target in expectation.targets
            )
            queries.append(turn.query)
            assert expectation.note
            assert format_cancel_expectation(expectation)

    assert decisions == {"none", "call", "clarify", "reject"}
    assert outcomes == {"accepted"}
    assert target_tool_names == {"天气查询工具", "地点搜索工具"}
    assert all("导航" not in query for query in queries)
    assert all("播放" not in query for query in queries)


def test_evaluator_matches_semantic_target() -> None:
    expectation = CancelExpectation(
        decision="call",
        targets=(
            ExpectedCancelTarget(
                tool_name="天气查询工具",
                argument_contains=(("query", "上海"),),
            ),
        ),
        outcomes=("accepted",),
        note="取消上海天气",
    )
    call = ObservedCancelCall(
        task_id="weather-shanghai",
        projection=TaskProjection(
            task_id="weather-shanghai",
            tool_name="天气查询工具",
            arguments={"query": "上海今天的天气"},
        ),
        outcome=TaskCancelOutcome(
            status="accepted",
            task_id="weather-shanghai",
        ),
    )

    passed, reasons = evaluate_cancel_expectation(
        expectation,
        [call],
        "已取消上海天气查询",
    )

    assert passed
    assert reasons == ()


def test_evaluator_checks_clarification_text() -> None:
    expectation = CancelExpectation(
        decision="clarify",
        note="多个任务时询问具体目标",
    )

    passed, _ = evaluate_cancel_expectation(
        expectation,
        [],
        "您想取消天气还是酒店查询？",
    )
    failed, reasons = evaluate_cancel_expectation(
        expectation,
        [],
        "好的",
    )

    assert passed
    assert not failed
    assert reasons == ("预期澄清，但回复不像澄清问题",)


def test_evaluator_rejects_unexpected_raw_cancel_tool_call() -> None:
    expectation = CancelExpectation(
        decision="reject",
        note="没有活跃任务时不能调用取消工具",
    )
    tool_call = ObservedCancelToolCall(
        name="cancel_task",
        arguments={"target_hint": None},
    )

    passed, reasons = evaluate_cancel_expectation(
        expectation,
        [],
        "现在没有正在执行的任务",
        actual_tool_calls=[tool_call],
    )

    assert not passed
    assert reasons == (
        "预期模型不调用取消工具，实际调用 1 次",
    )


def test_cancel_trace_consumer_records_only_raw_cancel_arguments() -> None:
    for arguments in [
        {"target_hint": "酒店"},
        {"task_id": "task-1"},
    ]:
        calls = evaluation_runner._cancel_tool_calls_from_trace(
            [
                ToolCallStartEvent(
                    name="天气查询工具",
                    arguments={"query": "香港天气"},
                    round=1,
                ),
                ToolCallStartEvent(
                    name="cancel_task",
                    arguments=arguments,
                    round=1,
                ),
            ],
            (),
        )

        assert len(calls) == 1
        call = calls[0]
        assert call.name == "cancel_task"
        assert call.arguments == arguments
        assert call.active_tasks == ()
        assert call.matched_task_ids == (
            () if "target_hint" in arguments else None
        )


def test_v1_trace_consumer_records_active_tasks_and_exact_match_candidates() -> None:
    manager = ObservingTaskManager()
    manager.apply_created(
        TaskCreatedEvent(
            task_id="poi-hotel",
            name="地点搜索工具",
            arguments={"query": "酒店", "city": "上海"},
        )
    )
    active_tasks = tuple(manager.get_active_task_projections())
    calls = evaluation_runner._cancel_tool_calls_from_trace(
        [
            ToolCallStartEvent(
                name="cancel_task",
                arguments={"target_hint": "酒店"},
                round=1,
            )
        ],
        active_tasks,
    )

    call = calls[0]
    assert [task.task_id for task in call.active_tasks] == ["poi-hotel"]
    assert call.matched_task_ids == ("poi-hotel",)


@pytest.mark.asyncio
async def test_runner_defaults_to_all_or_one_case(monkeypatch) -> None:
    observed_cases: list[str] = []

    def unused_agent_builder(manager, case):
        raise AssertionError("fake case runner should not build an agent")

    async def fake_run_case(
        case_name: str,
        *,
        case,
        agent_builder,
        delay_scale: float,
    ) -> tuple[int, int]:
        observed_cases.append(case_name)
        turn_count = len(case.turns)
        return turn_count, turn_count

    monkeypatch.setattr(
        evaluation_runner,
        "run_cancel_evaluation_case",
        fake_run_case,
    )
    settings = CancelEvaluationSettings(delay_scale=0, case_timeout=1)

    assert await run_cancel_evaluation(
        agent_builder=unused_agent_builder,
        settings=settings,
    )
    assert observed_cases == list(CANCEL_TOOL_CASES)

    observed_cases.clear()
    assert await run_cancel_evaluation(
        "running_task_cancel",
        agent_builder=unused_agent_builder,
        settings=settings,
    )
    assert observed_cases == ["running_task_cancel"]


@pytest.mark.asyncio
async def test_observable_case_runner_evaluates_and_finishes(capsys) -> None:
    class FakeAgent:
        def __init__(self, manager: TaskManager) -> None:
            self.manager = manager
            self.state = SimpleNamespace(trace=[])

        async def astream(self, input_data):
            if isinstance(input_data, TaskSuccessEvent):
                return

            if input_data.startswith("帮我在上海徐家汇"):
                async def pending_worker():
                    await anyio.sleep_forever()
                    yield TaskSuccess(result="never")

                arguments = {
                    "query": "酒店",
                    "city": "上海",
                    "address": "徐家汇",
                    "criteria": ["人均100左右"],
                    "radius": 3000,
                }
                self.manager.submit_task(
                    factory=pending_worker,
                    task_id="poi-shanghai-hotel",
                    name="地点搜索工具",
                    arguments=arguments,
                )
                yield TaskCreatedEvent(
                    task_id="poi-shanghai-hotel",
                    name="地点搜索工具",
                    arguments=arguments,
                )
                yield AgentOutTextDeltaEvent(delta="正在查询酒店")
                return

            self.state.trace.append(
                ToolCallStartEvent(
                    name="cancel_task",
                    arguments={"target_hint": "酒店"},
                    round=1,
                )
            )
            self.manager.cancel_task("poi-shanghai-hotel")
            yield AgentOutTextDeltaEvent(delta="已取消酒店查询")

    def fake_agent_builder(manager: TaskManager, case) -> FakeAgent:
        assert case is CANCEL_TOOL_CASES["running_task_cancel"]
        return FakeAgent(manager)

    passed_turns, total_turns = (
        await evaluation_runner.run_cancel_evaluation_case(
            "running_task_cancel",
            case=CANCEL_TOOL_CASES["running_task_cancel"],
            agent_builder=fake_agent_builder,
            delay_scale=0,
        )
    )

    assert (passed_turns, total_turns) == (2, 2)
    assert "[CASE PASS] running_task_cancel" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_case_runner_checks_expected_active_task_count() -> None:
    case = CancelToolCase(
        turns=(
            CancelCaseTurn(
                query="提交五个任务",
                delay=0,
                expectation=CancelExpectation(
                    decision="none",
                    note="提交任务但不取消",
                ),
                expected_active_tasks_after=5,
            ),
        )
    )

    class FakeAgent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(trace=[])

        async def astream(self, input_data):
            yield AgentOutTextDeltaEvent(delta="已提交")

    result = await evaluation_runner.evaluate_cancel_evaluation_case(
        "active-count",
        case=case,
        agent_builder=lambda manager, case: FakeAgent(),
        delay_scale=0,
    )

    assert not result.passed
    assert result.turns[0].reasons == (
        "预期本轮结束后有 5 个活跃任务，实际为 0 个",
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "天气查询工具",
            {"query": "香港今天的天气", "criteria": []},
        ),
        (
            "地点搜索工具",
            {
                "query": "酒店",
                "city": "上海",
                "address": "徐家汇",
                "criteria": ["人均100左右"],
                "radius": 3000,
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_simulated_async_tools_submit_real_pending_tasks(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    manager = TaskManager()
    tools = build_simulated_business_tools(
        task_manager=manager,
        case=CANCEL_TOOL_CASES["running_task_cancel"],
    )
    tool = next(tool for tool in tools if tool.name == tool_name)

    events = [
        event
        async for event in tool.stream_worker_factory(**arguments)()
    ]

    assert len(events) == 1
    assert isinstance(events[0], TaskSuccess)
    receipt = events[0].result
    assert isinstance(receipt, AsyncTaskReceipt)
    assert receipt.tool_name == tool_name

    projection = manager.get_projection(receipt.task_id)
    assert projection is not None
    assert projection.status == TaskStatus.PENDING
    assert projection.tool_name == tool_name
    assert projection.arguments == arguments
