from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
import pytest

from aicore.events.agent import AgentOutTextDeltaEvent
from aicore.models.credentials import ModelName
from aicore.runtime.task import (
    TaskCancelOutcome,
    TaskManager,
    TaskProjection,
)
from aicore.v2.experiments.task_cancel_eval import (
    batch_eval,
    runner as evaluation_runner,
)
from aicore.v2.experiments.task_cancel_eval.batch_eval import (
    BatchRunResult,
    DEFAULT_MODELS,
    DEFAULT_VARIANTS,
    batch_evaluation_to_dict,
    format_batch_report,
    run_batch_evaluation,
    summarize_batch_runs,
    write_batch_evaluation_json,
    write_batch_evaluation_jsonl,
)
from aicore.v2.experiments.task_cancel_eval.cases import (
    CANCEL_TOOL_CASES,
    CancelCaseTurn,
    CancelExpectation,
    CancelToolCase,
)
from aicore.v2.experiments.task_cancel_eval.eval import (
    DEFAULT_MODEL,
    build_v0_agent,
    build_v1_agent,
    normalize_cancel_variant,
)
from aicore.v2.experiments.task_cancel_eval.runner import (
    CancelEvaluationResult,
    CancelEvaluationSettings,
    CaseEvaluationResult,
    ObservedCancelCall,
    ObservedCancelToolCall,
    TurnEvaluationResult,
    evaluate_cancel_evaluation,
    evaluate_cancel_evaluation_case,
)


def _none_expectation() -> CancelExpectation:
    return CancelExpectation(
        decision="none",
        note="不应调用取消工具",
    )


def _case(
    query: str,
    *,
    delay: float = 0,
) -> CancelToolCase:
    return CancelToolCase(
        turns=(
            CancelCaseTurn(
                query=query,
                delay=delay,
                expectation=_none_expectation(),
            ),
        ),
    )


def _turn_result(
    index: int,
    *,
    passed: bool = True,
    duration_s: float = 1,
    observed_tool_calls: tuple[ObservedCancelToolCall, ...] = (),
    observed_calls: tuple[ObservedCancelCall, ...] = (),
) -> TurnEvaluationResult:
    return TurnEvaluationResult(
        index=index,
        query=f"query-{index}",
        expectation=_none_expectation(),
        passed=passed,
        reasons=() if passed else ("failed",),
        assistant_text="ok",
        observed_tool_calls=observed_tool_calls,
        observed_calls=observed_calls,
        duration_s=duration_s,
    )


def test_agent_builders_accept_model_and_keep_default() -> None:
    manager = TaskManager()
    case = CANCEL_TOOL_CASES["running_task_cancel"]

    v0 = build_v0_agent(
        manager,
        case,
        model=ModelName.SEED_2_0_MINI_260428,
    )
    v1 = build_v1_agent(
        TaskManager(),
        case,
        model=ModelName.SEED_2_0_PRO_260215,
    )
    default_agent = build_v0_agent(TaskManager(), case)

    assert (
        v0.context.model_params.model
        == ModelName.SEED_2_0_MINI_260428.value
    )
    assert (
        v1.context.model_params.model
        == ModelName.SEED_2_0_PRO_260215.value
    )
    assert default_agent.context.model_params.model == DEFAULT_MODEL.value
    assert normalize_cancel_variant("target_hint") == "v1"
    assert normalize_cancel_variant("v1") == "v1"


@pytest.mark.asyncio
async def test_turn_timing_excludes_delay_and_backfill(
    monkeypatch,
    capsys,
) -> None:
    clock = [0.0]

    async def fake_sleep(delay: float) -> None:
        clock[0] += delay

    async def fake_backfill(*args, **kwargs) -> None:
        clock[0] += 3

    class FakeAgent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(trace=[])

        async def astream(self, input_data):
            clock[0] += 2
            yield AgentOutTextDeltaEvent(delta="ok")

    monkeypatch.setattr(
        evaluation_runner.time,
        "perf_counter",
        lambda: clock[0],
    )
    monkeypatch.setattr(evaluation_runner, "_sleep", fake_sleep)
    monkeypatch.setattr(
        evaluation_runner,
        "_backfill_task_successes",
        fake_backfill,
    )

    result = await evaluate_cancel_evaluation_case(
        "timing",
        case=_case("hello", delay=5),
        agent_builder=lambda manager, case: FakeAgent(),
        delay_scale=1,
        verbose=False,
    )

    assert result.passed
    assert result.turns[0].duration_s == 2
    assert result.duration_s == 10
    assert capsys.readouterr().out == ""


@pytest.mark.asyncio
async def test_case_concurrency_preserves_input_order() -> None:
    cases = {
        "slow": _case("slow"),
        "fast": _case("fast"),
        "last": _case("last"),
    }
    delays = {"slow": 0.03, "fast": 0.01, "last": 0.01}
    active = 0
    max_active = 0

    class FakeAgent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(trace=[])

        async def astream(self, input_data):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            try:
                await anyio.sleep(delays[input_data])
                yield AgentOutTextDeltaEvent(delta="ok")
            finally:
                active -= 1

    result = await evaluate_cancel_evaluation(
        agent_builder=lambda manager, case: FakeAgent(),
        cases=cases,
        settings=CancelEvaluationSettings(
            delay_scale=0,
            case_timeout=1,
            case_concurrency=2,
        ),
    )

    assert max_active == 2
    assert [case.case_name for case in result.cases] == list(cases)
    assert result.passed


@pytest.mark.asyncio
async def test_case_errors_and_timeouts_are_isolated() -> None:
    cases = {
        "good": _case("good"),
        "broken": _case("broken"),
        "timeout": _case("timeout"),
    }

    class FakeAgent:
        def __init__(self) -> None:
            self.state = SimpleNamespace(trace=[])

        async def astream(self, input_data):
            if input_data == "broken":
                raise RuntimeError("boom")
            if input_data == "timeout":
                await anyio.sleep_forever()
            yield AgentOutTextDeltaEvent(delta="ok")

    result = await evaluate_cancel_evaluation(
        agent_builder=lambda manager, case: FakeAgent(),
        cases=cases,
        settings=CancelEvaluationSettings(
            delay_scale=0,
            case_timeout=0.02,
            case_concurrency=3,
        ),
    )

    assert [case.case_name for case in result.cases] == list(cases)
    assert result.cases[0].passed
    assert result.cases[1].error_type == "exception"
    assert "boom" in (result.cases[1].error or "")
    assert result.cases[2].error_type == "timeout"
    assert result.cases[1].total_turns == 1
    assert result.cases[2].total_turns == 1


@pytest.mark.asyncio
async def test_default_batch_matrix_and_cli_overrides(
    monkeypatch,
) -> None:
    observed: list[
        tuple[tuple[str, ...] | None, int, bool]
    ] = []
    evaluation = CancelEvaluationResult(
        cases=(
            CaseEvaluationResult(
                case_name="fake",
                turns=(_turn_result(0),),
                total_turns=1,
                duration_s=2,
            ),
        )
    )

    async def fake_evaluate(
        case_names,
        *,
        agent_builder,
        settings,
        verbose,
    ):
        observed.append((case_names, settings.case_concurrency, verbose))
        return evaluation

    monkeypatch.setattr(
        batch_eval,
        "evaluate_cancel_evaluation",
        fake_evaluate,
    )

    result = await run_batch_evaluation(
        settings=CancelEvaluationSettings(
            delay_scale=0,
            case_timeout=1,
        ),
    )

    assert result.models == tuple(model.value for model in DEFAULT_MODELS)
    assert result.variants == DEFAULT_VARIANTS
    assert [
        (run.model, run.variant)
        for run in result.runs
    ] == [
        (model.value, variant)
        for model in DEFAULT_MODELS
        for variant in DEFAULT_VARIANTS
    ]
    assert len(observed) == 6
    assert all(concurrency == 4 for _, concurrency, _ in observed)

    args = batch_eval._parse_args(
        [
            "--model",
            "SEED_2_0_MINI_260428",
            "--variant",
            "v1",
            "--case",
            "running_task_cancel",
            "--case",
            "single_task_status_query",
            "--repeat",
            "2",
            "--concurrency",
            "2",
            "--verbose",
            "--report",
            "all",
            "--output-report",
            "/tmp/task-cancel-report.md",
            "--output-jsonl",
            "/tmp/task-cancel-log.jsonl",
        ]
    )
    assert args.models == [ModelName.SEED_2_0_MINI_260428.value]
    assert args.variants == ["v1"]
    assert args.case_names == [
        "running_task_cancel",
        "single_task_status_query",
    ]
    assert args.repeat == 2
    assert args.concurrency == 2
    assert args.verbose
    assert args.report == "all"
    assert args.output_report.name == "task-cancel-report.md"
    assert args.output_jsonl.name == "task-cancel-log.jsonl"


def test_batch_summary_and_json_are_structured(tmp_path) -> None:
    observed_tool_call = ObservedCancelToolCall(
        name="cancel_task",
        arguments={"target_hint": "上海"},
    )
    observed_call = ObservedCancelCall(
        task_id="task-1",
        projection=TaskProjection(
            task_id="task-1",
            tool_name="天气查询工具",
            arguments={"query": "上海"},
        ),
        outcome=TaskCancelOutcome(
            status="accepted",
            task_id="task-1",
        ),
    )
    success = CaseEvaluationResult(
        case_name="success",
        turns=(
            _turn_result(
                0,
                duration_s=1,
                observed_tool_calls=(observed_tool_call,),
                observed_calls=(observed_call,),
            ),
            _turn_result(1, duration_s=3),
        ),
        total_turns=2,
        duration_s=5,
    )
    timeout = CaseEvaluationResult(
        case_name="timeout",
        turns=(),
        total_turns=2,
        duration_s=7,
        error_type="timeout",
        error="timeout",
    )
    runs = (
        BatchRunResult(
            model=ModelName.SEED_2_0_MINI_260428.value,
            variant="v0",
            repetition=1,
            evaluation=CancelEvaluationResult(cases=(success,)),
        ),
        BatchRunResult(
            model=ModelName.SEED_2_0_MINI_260428.value,
            variant="v0",
            repetition=2,
            evaluation=CancelEvaluationResult(cases=(timeout,)),
        ),
    )

    summary = summarize_batch_runs(runs)[0]

    assert (summary.passed_cases, summary.total_cases) == (1, 2)
    assert (summary.passed_turns, summary.total_turns) == (2, 4)
    assert summary.case_pass_rate == 0.5
    assert summary.turn_pass_rate == 0.5
    assert summary.average_turn_duration_s == 2
    assert summary.total_case_duration_s == 12
    assert summary.average_case_duration_s == 6
    assert summary.timeout_cases == 1
    assert summary.error_cases == 0
    assert summary.passed_cancel_turns == 0
    assert summary.expected_cancel_turns == 0

    result = batch_eval.BatchEvaluationResult(
        models=(ModelName.SEED_2_0_MINI_260428.value,),
        variants=("v0",),
        case_names=None,
        repeat=2,
        concurrency=4,
        delay_scale=0.01,
        case_timeout=180,
        runs=runs,
    )
    output_path = tmp_path / "batch.json"
    write_batch_evaluation_json(result, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == batch_evaluation_to_dict(result)
    call = payload["runs"][0]["evaluation"]["cases"][0]["turns"][0][
        "observed_calls"
    ][0]
    tool_call = payload["runs"][0]["evaluation"]["cases"][0]["turns"][0][
        "observed_tool_calls"
    ][0]
    assert tool_call == {
        "name": "cancel_task",
        "arguments": {"target_hint": "上海"},
        "active_tasks": [],
        "matched_task_ids": None,
    }
    assert call["projection"]["tool_name"] == "天气查询工具"
    assert call["outcome"]["status"] == "accepted"


def test_report_and_jsonl_keep_raw_error_evidence_without_inferred_labels(
    tmp_path,
) -> None:
    active_task = TaskProjection(
        task_id="weather-hong-kong",
        tool_name="天气查询工具",
        arguments={"query": "香港今天的天气"},
    )
    expectation = CancelExpectation(
        decision="call",
        targets=(
            CANCEL_TOOL_CASES["cancel_then_late_result_should_not_backfill"]
            .turns[1]
            .expectation.targets[0],
        ),
        outcomes=("accepted",),
        note="应该取消香港天气",
    )
    failed_turn = TurnEvaluationResult(
        index=1,
        query="取消天气",
        expectation=expectation,
        passed=False,
        reasons=(
            "预期取消 1 个任务，TaskManager 实际收到 0 次取消调用",
            "未观察到预期取消结果: 天气查询工具(query~香港) -> accepted",
        ),
        assistant_text="请问要取消哪个？",
        observed_tool_calls=(
            ObservedCancelToolCall(
                name="cancel_task",
                arguments={"target_hint": "天气预报"},
                active_tasks=(active_task,),
                matched_task_ids=(),
            ),
        ),
        observed_calls=(),
        duration_s=1.2,
        active_tasks_before=(active_task,),
        active_tasks_after=(active_task,),
    )
    v1_case = CaseEvaluationResult(
        case_name="matcher-gap",
        turns=(failed_turn,),
        total_turns=1,
        duration_s=2,
    )
    v0_case = CaseEvaluationResult(
        case_name="matcher-gap",
        turns=(_turn_result(0),),
        total_turns=1,
        duration_s=1,
    )
    result = batch_eval.BatchEvaluationResult(
        models=(ModelName.SEED_2_1_PRO_260628.value,),
        variants=("v0", "v1"),
        case_names=("matcher-gap",),
        repeat=1,
        concurrency=1,
        delay_scale=0,
        case_timeout=10,
        runs=(
            BatchRunResult(
                model=ModelName.SEED_2_1_PRO_260628.value,
                variant="v0",
                repetition=1,
                evaluation=CancelEvaluationResult(cases=(v0_case,)),
            ),
            BatchRunResult(
                model=ModelName.SEED_2_1_PRO_260628.value,
                variant="v1",
                repetition=1,
                evaluation=CancelEvaluationResult(cases=(v1_case,)),
            ),
        ),
    )

    report = format_batch_report(result)
    assert "v0 通过、v1 失败：`matcher-gap`" in report
    assert "[错误]" in report
    assert "- 结果：错误" in report
    assert "应调用取消工具" in report
    assert "失败类型汇总" not in report
    assert "wrong_cancel_target" not in report
    assert '"target_hint": "天气预报"' in report
    assert "v1 后台匹配命中：0 个" in report
    assert "weather-hong-kong" in report

    output_path = tmp_path / "turns.jsonl"
    write_batch_evaluation_jsonl(result, output_path)
    records = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    failed_record = records[1]
    assert failed_record["status"] == "error"
    assert "failure_categories" not in failed_record
    assert failed_record["turn"]["reasons"] == [
        "预期取消 1 个任务，TaskManager 实际收到 0 次取消调用",
        "未观察到预期取消结果: 天气查询工具(query~香港) -> accepted",
    ]
    assert failed_record["turn"]["observed_tool_calls"][0][
        "matched_task_ids"
    ] == []
    assert failed_record["turn"]["active_tasks_before"][0][
        "task_id"
    ] == "weather-hong-kong"
