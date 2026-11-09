from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

import aicore.agents.plan.core as plan_core
from aicore.agents.plan.core import astream_plact, create_plan
from aicore.agents.plan.criterion import KIND_JQ
from aicore.agents.plan.dag import DAG
from aicore.agents.plan.errors import PlanRepairContext, RepairPolicy
from aicore.agents.plan.events import PlActFinishEvent
from aicore.models.model_api import ModelResponse, ModelState, StructuredModelResponse


class FakeState(ModelState):
    marker: str


class EmptyPlan(BaseModel):
    goal: str = "empty"
    steps: list[Any] = Field(default_factory=list)


class EmptySpec:
    name = "empty"
    plan_type = EmptyPlan

    def build_sys_prompt(self, tools: list[Any]) -> str:
        return "planner system"

    def build_dag(self, plan: EmptyPlan) -> DAG[Any, Any]:
        return DAG(nodes=[], edges=[])


class RecordingModelAPI:
    def __init__(self) -> None:
        self.structured_calls: list[tuple[str, FakeState]] = []
        self.invoke_calls: list[tuple[str, FakeState]] = []

    def initial_state(self, *, system_prompt: str) -> FakeState:
        return FakeState(marker=system_prompt)

    async def structured_output(
        self,
        message: Any,
        *,
        output_type: type[EmptyPlan],
        state: FakeState,
        params: Any = None,
    ) -> StructuredModelResponse[EmptyPlan, FakeState]:
        self.structured_calls.append((message.text, state))
        return StructuredModelResponse(
            parsed=EmptyPlan(),
            text="plan",
            state=FakeState(marker="planned"),
        )

    async def invoke(
        self,
        message: Any,
        *,
        state: FakeState,
        params: Any = None,
    ) -> ModelResponse[FakeState]:
        self.invoke_calls.append((message.text, state))
        return ModelResponse(text="answer", state=FakeState(marker="answered"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_create_plan_uses_current_query_for_seeded_non_repair_state() -> None:
    api = RecordingModelAPI()
    seeded = FakeState(marker="history")

    plan, next_state = await create_plan(
        "follow up",
        model_api=api,  # type: ignore[arg-type]
        tools=[],
        spec=EmptySpec(),  # type: ignore[arg-type]
        criterion=KIND_JQ,
        state=seeded,
    )

    assert plan.goal == "empty"
    assert next_state.marker == "planned"
    assert api.structured_calls == [("follow up", seeded)]


@pytest.mark.anyio
async def test_create_plan_without_seed_uses_spec_system_prompt() -> None:
    api = RecordingModelAPI()

    await create_plan(
        "first query",
        model_api=api,  # type: ignore[arg-type]
        tools=[],
        spec=EmptySpec(),  # type: ignore[arg-type]
        criterion=KIND_JQ,
    )

    assert api.structured_calls[0][0] == "first query"
    assert api.structured_calls[0][1].marker == "planner system"


@pytest.mark.anyio
async def test_create_plan_still_formats_repair_message() -> None:
    api = RecordingModelAPI()
    repair = PlanRepairContext(
        errors=[],
        failed_plan=None,
        policy=RepairPolicy.REGENERATE_PLAN,
        round=1,
    )

    await create_plan(
        "original query",
        model_api=api,  # type: ignore[arg-type]
        tools=[],
        spec=EmptySpec(),  # type: ignore[arg-type]
        criterion=KIND_JQ,
        state=FakeState(marker="previous plan"),
        repair_context=repair,
    )

    assert "上一轮计划" in api.structured_calls[0][0]
    assert "original query" not in api.structured_calls[0][0]


@pytest.mark.anyio
async def test_astream_uses_injected_plan_state_on_first_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = RecordingModelAPI()
    seeded = FakeState(marker="planning history")
    captured_states: list[FakeState | None] = []

    async def fake_create_plan(query: str, **kwargs: Any) -> tuple[EmptyPlan, FakeState]:
        captured_states.append(kwargs["state"])
        return EmptyPlan(), FakeState(marker="planned")

    monkeypatch.setattr(plan_core, "create_plan", fake_create_plan)
    events = [
        event
        async for event in astream_plact(
            "follow up",
            model_api=api,  # type: ignore[arg-type]
            state=FakeState(marker="answer history"),
            plan_state=seeded,
            tools=[],
            spec=EmptySpec(),  # type: ignore[arg-type]
            max_turns=1,
        )
    ]

    assert captured_states == [seeded]
    assert isinstance(events[-1], PlActFinishEvent)
    assert events[-1].response == "answer"


@pytest.mark.anyio
async def test_repair_round_reuses_the_updated_planning_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.agents._plan_verify_helpers import build, step

    api = RecordingModelAPI()
    captured_states: list[FakeState | None] = []
    call_number = 0

    async def fake_create_plan(query: str, **kwargs: Any) -> tuple[EmptyPlan, FakeState]:
        nonlocal call_number
        call_number += 1
        captured_states.append(kwargs["state"])
        return EmptyPlan(), FakeState(marker=f"planned-{call_number}")

    class InvalidSpec(EmptySpec):
        def build_dag(self, plan: EmptyPlan) -> Any:
            return build([step("s1", op="missing_tool", inputs={})])

    monkeypatch.setattr(plan_core, "create_plan", fake_create_plan)
    _ = [
        event
        async for event in astream_plact(
            "follow up",
            model_api=api,  # type: ignore[arg-type]
            state=FakeState(marker="answer history"),
            plan_state=FakeState(marker="planning history"),
            tools=[],
            spec=InvalidSpec(),  # type: ignore[arg-type]
            max_turns=2,
        )
    ]

    assert [state.marker if state else None for state in captured_states] == [
        "planning history",
        "planned-1",
    ]
