from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import BaseModel, Field

from aicore.agents.plan.dag import DAG
from aicore.agents.plan.events import (
    PlanCreatedEvent,
    PlActFinishEvent,
    PlActRoundStartEvent,
)
from aicore.events.agent import (
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.models.model_api import (
    AssistantMessage,
    ModelState,
    SystemMessage,
    UserMessage,
)


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


class HistoryState(ModelState):
    messages: list[Any]


class RecordingHistoryAPI:
    def __init__(self) -> None:
        self.histories: list[list[Any]] = []

    def state_from_history(self, history: list[Any]) -> HistoryState:
        copied = list(history)
        self.histories.append(copied)
        return HistoryState(messages=copied)


def plact_module() -> Any:
    return importlib.import_module(
        "aicore.v2.experiments.v2_frontend_plact_agent"
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_adapter_forwards_plan_events_then_emits_existing_text_events() -> None:
    module = plact_module()
    api = RecordingHistoryAPI()
    calls: list[dict[str, Any]] = []

    async def fake_stream(query: str, **kwargs: Any):
        calls.append({"query": query, **kwargs})
        yield PlActRoundStartEvent(round=0)
        yield PlanCreatedEvent(plan=EmptyPlan(goal=query), round=0)
        yield PlActFinishEvent(response=f"answer:{query}", round=0)

    agent = module.PlActFrontendAgent(
        model_api=api,
        tools=[],
        spec=EmptySpec(),
        plact_stream=fake_stream,
    )

    events = [event async for event in agent.astream("first")]

    assert [event.type for event in events] == [
        "plact.round.start",
        "plan.created",
        "plact.finish",
        "agent.out.text.start",
        "agent.out.text.delta",
        "agent.out.text.done",
    ]
    assert isinstance(events[3], AgentOutTextStartEvent)
    assert isinstance(events[4], AgentOutTextDeltaEvent)
    assert events[4].delta == "answer:first"
    assert isinstance(events[5], AgentOutTextDoneEvent)
    assert agent.history == [
        UserMessage(text="first"),
        AssistantMessage(text="answer:first"),
    ]
    assert calls[0]["query"] == "first"


@pytest.mark.anyio
async def test_follow_up_rebuilds_planning_and_answer_states_from_history() -> None:
    module = plact_module()
    api = RecordingHistoryAPI()

    async def fake_stream(query: str, **kwargs: Any):
        yield PlActFinishEvent(response=f"answer:{query}", round=0)

    agent = module.PlActFrontendAgent(
        model_api=api,
        tools=[],
        spec=EmptySpec(),
        plact_stream=fake_stream,
    )
    _ = [event async for event in agent.astream("first")]
    _ = [event async for event in agent.astream("follow up")]

    assert len(api.histories) == 4
    second_planning_history = api.histories[2]
    second_answer_history = api.histories[3]
    assert isinstance(second_planning_history[0], SystemMessage)
    assert second_planning_history[1:] == [
        UserMessage(text="first"),
        AssistantMessage(text="answer:first"),
    ]
    assert second_answer_history == [
        UserMessage(text="first"),
        AssistantMessage(text="answer:first"),
    ]


@pytest.mark.anyio
async def test_interrupted_stream_does_not_append_completed_history() -> None:
    module = plact_module()
    api = RecordingHistoryAPI()

    async def failing_stream(query: str, **kwargs: Any):
        yield PlActRoundStartEvent(round=0)
        raise RuntimeError("stream failed")

    agent = module.PlActFrontendAgent(
        model_api=api,
        tools=[],
        spec=EmptySpec(),
        plact_stream=failing_stream,
    )

    with pytest.raises(RuntimeError, match="stream failed"):
        _ = [event async for event in agent.astream("first")]

    assert agent.history == []


def test_factory_uses_the_default_synchronous_plan_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = plact_module()
    api = RecordingHistoryAPI()
    synchronous_tool = object()
    captured_chat_ids: list[str] = []

    monkeypatch.setattr(module, "create_model_api", lambda **kwargs: api)

    def fake_get_default_tools(chat_id: str) -> list[object]:
        captured_chat_ids.append(chat_id)
        return [synchronous_tool]

    monkeypatch.setattr(module, "get_default_tools", fake_get_default_tools)

    agent = module.create_plact_frontend_agent(chat_id="frontend-chat")

    assert agent.tools == [synchronous_tool]
    assert captured_chat_ids == ["frontend-chat"]
