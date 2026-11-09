from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, Field

from aicore.agents.plan.diagnosis import (
    AcceptDegraded,
    DiagnosisResult,
    Replan,
)
from aicore.agents.plan.events import (
    PlanRunnerErrorEvent,
    PlanStepDiagnosisCompletedEvent,
    PlanStepDiagnosisStartedEvent,
    PlanStepDoneEvent,
    PlanStepSkippedEvent,
)
from aicore.agents.plan.plan_dag_runner import PlanDAGRunner
from aicore.models.model_api import ModelState, StructuredModelResponse
from aicore.tools import TaskTool
from tests.agents._plan_verify_helpers import build, outputs, step


class ToolInput(BaseModel):
    q: str = Field(...)


async def _identity_projection(raw: Any, *args: Any, **kwargs: Any) -> Any:
    return SimpleNamespace(data=raw, error=None, item_errors=[])


def tool(name: str, value: Any) -> TaskTool[ToolInput, object, None, Any]:
    async def worker(q: str) -> object:
        return value

    return TaskTool[ToolInput, object, None, Any](
        name=name,
        description="test tool",
        args_schema=ToolInput,
        worker=worker,
    )


class DiagnosisModelAPI:
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises

    def initial_state(self, *, system_prompt: str | None = None) -> ModelState:
        return ModelState()

    async def structured_output(
        self,
        message: Any,
        *,
        output_type: type[Any],
        state: ModelState,
        params: Any = None,
    ) -> StructuredModelResponse[Any, ModelState]:
        if self.raises:
            raise RuntimeError("diagnosis boom")
        return StructuredModelResponse(parsed=None, state=state)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_valid_layer_emits_all_started_events_before_any_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aicore.agents.plan.plan_dag_runner.concept_tool_outputs",
        _identity_projection,
    )
    runner = PlanDAGRunner(
        [
            tool("search_a", [{"field": "a"}]),
            tool("search_b", [{"field": "b"}]),
        ]
    )
    dag = build(
        [
            step(
                "s1",
                op="search_a",
                inputs={"q": "raw-a"},
                step_outputs=outputs("A"),
            ),
            step(
                "s2",
                op="search_b",
                inputs={"q": "raw-b"},
                step_outputs=outputs("B"),
            ),
        ]
    )

    events = [event async for event in runner.run(dag)]

    assert [event.type for event in events] == [
        "plan.step.started",
        "plan.step.started",
        "plan.step.done",
        "plan.step.done",
    ]
    started = [event for event in events if event.type == "plan.step.started"]
    assert [
        (getattr(event, "step_id"), getattr(event, "resolved_inputs"))
        for event in started
    ] == [
        ("s1", {"q": "raw-a"}),
        ("s2", {"q": "raw-b"}),
    ]
    assert all(isinstance(event, PlanStepDoneEvent) for event in events[2:])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_api",
    [
        None,
        DiagnosisModelAPI(raises=True),
        DiagnosisModelAPI(),
    ],
    ids=["model-api-missing", "diagnosis-raises", "diagnosis-parse-fails"],
)
async def test_diagnose_failure_reports_fallback_replan(
    model_api: Any,
) -> None:
    runner = PlanDAGRunner([tool("search", [{"field": "one"}])], model_api=model_api)
    failed_step = step(
        "s1",
        op="search",
        inputs={"q": "x"},
        step_outputs=outputs("R"),
    )

    result = await runner._diagnose_failure(
        failed_step,
        failed_step.success_check,
        "success_check evaluated to false",
        {},
        {"status": "empty"},
    )

    assert result.source == "fallback"
    assert result.decision.outcome == "replan"


@pytest.mark.anyio
async def test_failed_success_check_emits_truthful_diagnosis_lifecycle_before_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aicore.agents.plan.plan_dag_runner.concept_tool_outputs",
        _identity_projection,
    )
    raw = [{"field": "one"}]
    runner = PlanDAGRunner([tool("search", raw)], model_api=None)
    dag = build(
        [
            step(
                "s1",
                op="search",
                inputs={"q": "x"},
                step_outputs=outputs("R"),
                success_check="((.s1.outputs.R // []) | length) > 1",
            )
        ]
    )

    events = [event async for event in runner.run(dag)]

    assert [event.type for event in events] == [
        "plan.step.started",
        "plan.step.diagnosis.started",
        "plan.step.diagnosis.completed",
        "plan.step.done",
        "plan.runner.error",
    ]
    diagnosis_started = events[1]
    assert isinstance(diagnosis_started, PlanStepDiagnosisStartedEvent)
    assert diagnosis_started.failure_message == "success_check evaluated to false"
    assert diagnosis_started.process_error_kind is None
    diagnosis_completed = events[2]
    assert isinstance(diagnosis_completed, PlanStepDiagnosisCompletedEvent)
    assert diagnosis_completed.source == "fallback"
    assert diagnosis_completed.decision.outcome == "replan"
    done = events[3]
    assert isinstance(done, PlanStepDoneEvent)
    assert done.tool_output.data == raw
    assert done.concept_output == {"R": raw}
    assert done.process_error is None
    error = events[4]
    assert isinstance(error, PlanRunnerErrorEvent)
    assert len(error.errors) == 1
    assert error.errors[0].detail.message == "success_check evaluated to false"


@pytest.mark.anyio
async def test_same_layer_replans_preserve_all_done_evidence_before_one_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aicore.agents.plan.plan_dag_runner.concept_tool_outputs",
        _identity_projection,
    )
    runner = PlanDAGRunner(
        [
            tool("search_a", [{"field": "a"}]),
            tool("search_b", [{"field": "b"}]),
            tool("dependent", [{"field": "never"}]),
        ]
    )
    runner._diagnose_failure = _replan_by_rule  # type: ignore[method-assign]
    dag = build(
        [
            step(
                "s1",
                op="search_a",
                inputs={"q": "a"},
                step_outputs=outputs("A"),
                success_check="((.s1.outputs.A // []) | length) > 1",
            ),
            step(
                "s2",
                op="search_b",
                inputs={"q": "b"},
                step_outputs=outputs("B"),
                success_check="((.s2.outputs.B // []) | length) > 1",
            ),
            step(
                "next",
                op="dependent",
                depends_on=["s1", "s2"],
                inputs={"q": "never"},
                step_outputs=outputs("Next"),
            ),
        ]
    )

    events = [event async for event in runner.run(dag)]

    assert [event.type for event in events] == [
        "plan.step.started",
        "plan.step.started",
        "plan.step.diagnosis.started",
        "plan.step.diagnosis.completed",
        "plan.step.done",
        "plan.step.diagnosis.started",
        "plan.step.diagnosis.completed",
        "plan.step.done",
        "plan.runner.error",
    ]
    assert [event.step_id for event in events[:2]] == ["s1", "s2"]
    assert sum(event.type == "plan.step.diagnosis.started" for event in events) == 2
    assert sum(event.type == "plan.step.diagnosis.completed" for event in events) == 2
    done = [event for event in events if isinstance(event, PlanStepDoneEvent)]
    assert [event.step_id for event in done] == ["s1", "s2"]
    assert [event.tool_output.data for event in done] == [
        [{"field": "a"}],
        [{"field": "b"}],
    ]
    errors = [event for event in events if isinstance(event, PlanRunnerErrorEvent)]
    assert len(errors) == 1
    assert [error.detail.step_id for error in errors[0].errors] == ["s1", "s2"]
    assert not any(getattr(event, "step_id", None) == "next" for event in events)


@pytest.mark.anyio
async def test_skipped_and_invalid_steps_do_not_emit_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "aicore.agents.plan.plan_dag_runner.concept_tool_outputs",
        _identity_projection,
    )
    runner = PlanDAGRunner([tool("search", [{"field": "ok"}])])
    runner._diagnose_failure = _accept_degraded  # type: ignore[method-assign]
    dag = build(
        [
            step(
                "condition_false",
                op="search",
                inputs={"q": "x"},
                condition="false",
            ),
            step(
                "downstream",
                op="search",
                depends_on=["condition_false"],
                inputs={"q": "x"},
            ),
            step("bad_params", op="search", inputs={}),
            step(
                "condition_error",
                op="search",
                inputs={"q": "x"},
                condition="1",
            ),
        ]
    )

    events = [event async for event in runner.run(dag)]

    assert not any(event.type == "plan.step.started" for event in events)
    assert any(
        isinstance(event, PlanStepSkippedEvent)
        and event.step_id == "condition_false"
        for event in events
    )
    assert any(
        isinstance(event, PlanStepSkippedEvent)
        and event.step_id == "downstream"
        and event.reason == "upstream_skipped"
        for event in events
    )


async def _accept_degraded(*args: Any, **kwargs: Any) -> DiagnosisResult:
    return DiagnosisResult(
        source="rule",
        decision=AcceptDegraded(limitation="deterministic test verdict"),
    )


async def _replan_by_rule(step_: Any, *args: Any, **kwargs: Any) -> DiagnosisResult:
    return DiagnosisResult(
        source="rule",
        decision=Replan(
            failed_assumption=f"{step_.step_id} failed",
            retry_direction=f"retry {step_.step_id}",
        ),
    )


# ────────────────────────── 判定接缝（_decide_step / _verify_step）──────────────────────────


@pytest.mark.anyio
async def test_decision_hook_runs_once_per_non_skipped_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接缝契约：每个进入验证尾段的 outcome 恰好判定一次，被跳过的 step 不进判定。"""
    monkeypatch.setattr(
        "aicore.agents.plan.plan_dag_runner.concept_tool_outputs",
        _identity_projection,
    )
    runner = PlanDAGRunner([tool("search", [{"field": "ok"}])])
    decided: list[str] = []
    decide = runner._decide_step

    async def spy(oc: Any, verdict: Any) -> Any:
        decided.append(oc.step.step_id)
        async for event in decide(oc, verdict):
            yield event

    runner._decide_step = spy  # type: ignore[method-assign]
    dag = build(
        [
            step("condition_false", op="search", inputs={"q": "x"}, condition="false"),
            step("downstream", op="search", depends_on=["condition_false"], inputs={"q": "x"}),
            step("s1", op="search", inputs={"q": "x"}),
            step("s2", op="search", inputs={"q": "x"}),
        ]
    )

    _ = [event async for event in runner.run(dag)]

    assert sorted(decided) == ["s1", "s2"]


@pytest.mark.anyio
async def test_diagnosis_started_event_precedes_the_judge_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """diagnosis.started 必须在判定调用之前被消费方看到。

    它到 diagnosis.completed 的间隔就是判定耗时（trace 靠它归因延迟）。若把判定钩子写成
    "先 await 判定、再一次性回传裁决"，两个事件的间隔会被抹平成 0——本用例就是钉住这点。
    """
    monkeypatch.setattr(
        "aicore.agents.plan.plan_dag_runner.concept_tool_outputs",
        _identity_projection,
    )
    runner = PlanDAGRunner([tool("search", [{"field": "one"}])], model_api=None)
    order: list[str] = []

    async def probe(step_: Any, *args: Any, **kwargs: Any) -> DiagnosisResult:
        order.append("judge_call")
        return await _replan_by_rule(step_, *args, **kwargs)

    runner._diagnose_failure = probe  # type: ignore[method-assign]
    dag = build(
        [
            step(
                "s1",
                op="search",
                inputs={"q": "x"},
                step_outputs=outputs("R"),
                success_check="((.s1.outputs.R // []) | length) > 1",
            )
        ]
    )

    async for event in runner.run(dag):
        order.append(event.type)

    assert order == [
        "plan.step.started",
        "plan.step.diagnosis.started",
        "judge_call",
        "plan.step.diagnosis.completed",
        "plan.step.done",
        "plan.runner.error",
    ]
