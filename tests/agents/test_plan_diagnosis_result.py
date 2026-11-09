from typing import Any

import pytest

from aicore.agents.plan.diagnosis import (
    AcceptDegraded,
    Replan,
    diagnose_success_check_failure,
)
from aicore.models.model_api import ModelState, StructuredModelResponse


class FakeState(ModelState):
    pass


class UnexpectedModelAPI:
    def initial_state(self, *, system_prompt: str | None = None) -> FakeState:
        raise AssertionError("rule-based diagnosis must not call the model")


class RecordingModelAPI:
    def __init__(self, decision: AcceptDegraded) -> None:
        self.decision = decision
        self.structured_calls = 0

    def initial_state(self, *, system_prompt: str | None = None) -> FakeState:
        return FakeState()

    async def structured_output(
        self,
        message: Any,
        *,
        output_type: type[Any],
        state: FakeState,
        params: Any = None,
    ) -> StructuredModelResponse[Any, FakeState]:
        self.structured_calls += 1
        return StructuredModelResponse(
            parsed=output_type(decision=self.decision),
            state=state,
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rule_based_diagnosis_reports_rule_source() -> None:
    result = await diagnose_success_check_failure(
        query="find somewhere nearby",
        step_goal="find candidates",
        op="poi_search",
        inputs={},
        success_check="false",
        outputs_snapshot={},
        tool_output={"status": "error"},
        failure_message="tool execution failed",
        model_api=UnexpectedModelAPI(),  # type: ignore[arg-type]
        process_error_kind="execution",
    )

    assert result.source == "rule"
    assert isinstance(result.decision, Replan)


@pytest.mark.anyio
async def test_llm_diagnosis_reports_llm_source_and_decision() -> None:
    expected = AcceptDegraded(limitation="only one candidate")
    api = RecordingModelAPI(expected)

    result = await diagnose_success_check_failure(
        query="find somewhere nearby",
        step_goal="find candidates",
        op="poi_search",
        inputs={},
        success_check="false",
        outputs_snapshot={"candidates": ["one"]},
        tool_output={"candidates": ["one"]},
        failure_message="candidate count below target",
        model_api=api,  # type: ignore[arg-type]
    )

    assert result.source == "llm"
    assert result.decision == expected
    assert api.structured_calls == 1
