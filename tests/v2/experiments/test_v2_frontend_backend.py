from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import datetime

import anyio
import pytest
from pydantic import BaseModel

import aicore.v2.experiments.v2_frontend_backend as frontend_backend

from aicore.agents.plan.criterion import jq_expr
from aicore.agents.plan.events import (
    PlanCreatedEvent,
    PlanStepDiagnosisCompletedEvent,
    PlanStepDiagnosisStartedEvent,
    PlanStepStartedEvent,
    PlActRoundStartEvent,
)
from aicore.agents.plan.diagnosis import Replan
from aicore.events.agent import (
    AgentOutTextDeltaEvent,
)
from aicore.events.task import TaskCancelledEvent, TaskStartEvent, TaskSuccessEvent
from aicore.runtime.task import TaskManager, TaskSuccess
from aicore.v2.experiments.v2_frontend_voice import FrontendVoiceBridge
from aicore.v2.experiments.v2_frontend_backend import (
    ClientCommandEnvelope,
    EventContext,
    FrontendEventCorrelation,
    PROTOCOL_VERSION,
    QueuedUserInput,
    SUPPORTED_COMMANDS,
    SessionBoundAgent,
    WebSocketAgentSession,
    app,
    handle_client_command,
    serialize_console_event,
)
from fastapi.testclient import TestClient
from projects.voice_test.schemas.events import (
    ASREnded,
    ASRFinal,
    AsrTextPayload,
    EmptyPayload,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class RecordingCommandSession:
    def __init__(self) -> None:
        self.session_id = "sess-command"
        self.generation = 3
        self.messages: list[dict[str, object]] = []

    async def send(self, message: dict[str, object]) -> None:
        self.messages.append(message)


class SerializedPlan(BaseModel):
    goal: str
    steps: list[dict[str, str]]


def test_serializes_event_envelope_with_optional_frontend_message_id() -> None:
    envelope = serialize_console_event(
        AgentOutTextDeltaEvent(
            event_id="event-1",
            timestamp=datetime(2026, 6, 16, 10, 30, 0),
            delta="partial",
        ),
        message_id="agent-1",
    )

    assert envelope == {
        "id": "event-1",
        "type": "agent.out.text.delta",
        "timestamp": "2026-06-16T10:30:00",
        "payload": {
            "event_id": "event-1",
            "timestamp": "2026-06-16T10:30:00",
            "type": "agent.out.text.delta",
            "delta": "partial",
            "conversation_turn_id": None,
            "output_run_id": None,
            "triggering_task_ids": [],
            "message_id": "agent-1",
        },
    }


def test_serializes_task_result_source_context() -> None:
    envelope = serialize_console_event(
        AgentOutTextDeltaEvent(delta="result"),
        message_id="task-result-poi-1",
        origin_message_id="agent-1",
        source_task_id="poi-1",
    )

    assert envelope["payload"]["message_id"] == "task-result-poi-1"
    assert envelope["payload"]["origin_message_id"] == "agent-1"
    assert envelope["payload"]["source_task_id"] == "poi-1"


def test_serializes_frontend_event_correlation_alongside_legacy_fields() -> None:
    envelope = serialize_console_event(
        AgentOutTextDeltaEvent(delta="result"),
        message_id="task-result-poi-1",
        origin_message_id="agent-1",
        source_task_id="poi-1",
        correlation=FrontendEventCorrelation(
            conversation_turn_id="agent-1",
            output_run_id="task-result-poi-1",
            triggering_task_ids=("poi-1", "parking-1"),
        ),
    )

    payload = envelope["payload"]
    assert payload["conversation_turn_id"] == "agent-1"
    assert payload["output_run_id"] == "task-result-poi-1"
    assert payload["triggering_task_ids"] == ["poi-1", "parking-1"]
    assert payload["origin_message_id"] == "agent-1"
    assert payload["source_task_id"] == "poi-1"


def test_serializes_concrete_plan_fields_in_plan_created_event() -> None:
    envelope = serialize_console_event(
        PlanCreatedEvent(
            plan=SerializedPlan(
                goal="find a place",
                steps=[{"step_id": "lookup", "op": "search"}],
            ),
            round=0,
        ),
        message_id="agent-1",
        round=0,
    )

    assert envelope["payload"]["plan"] == {
        "goal": "find a place",
        "steps": [{"step_id": "lookup", "op": "search"}],
    }


def test_protocol_v4_keeps_only_live_client_commands() -> None:
    assert PROTOCOL_VERSION == 4
    assert SUPPORTED_COMMANDS == {
        "agent.run",
        "task.cancel",
        "session.reset",
        "voice.start",
        "voice.stop",
        "voice.text.query",
        "voice.mic.open",
        "voice.mic.close",
        "voice.playback.ended",
    }


def test_ts_runtime_command_set_is_exported_and_matches_json_descriptor() -> None:
    ts_path = (
        frontend_backend._CLIENT_COMMANDS_PATH.parent.parent
        / "src"
        / "adapters"
        / "clientCommands.ts"
    )
    source = ts_path.read_text(encoding="utf-8")
    match = re.search(r"const CLIENT_COMMANDS = \[(.*?)\] as const", source, re.DOTALL)
    assert match is not None
    literal_commands = set(re.findall(r"'([^']+)'", match.group(1)))
    descriptor_commands = {
        item["command"] for item in frontend_backend.CLIENT_COMMAND_PROTOCOL["commands"]
    }

    assert literal_commands == descriptor_commands
    assert "export const RUNTIME_CLIENT_COMMANDS" in source


def test_react_prompt_does_not_instruct_the_removed_dag_tool() -> None:
    from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT

    assert "DAG" not in ASYNC_REACT_SYSTEM_PROMPT


def test_react_prompt_preserves_core_async_voice_contracts() -> None:
    from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT

    assert "同一次模型响应中发出全部必要的工具调用" in ASYNC_REACT_SYSTEM_PROMPT
    assert "[占位回执]" in ASYNC_REACT_SYSTEM_PROMPT
    assert "[工具结果回灌]" in ASYNC_REACT_SYSTEM_PROMPT
    assert "根据历史业务工具调用和占位回执找到目标 task_id" in (
        ASYNC_REACT_SYSTEM_PROMPT
    )
    assert "call_id" not in ASYNC_REACT_SYSTEM_PROMPT
    assert "cancel_task" in ASYNC_REACT_SYSTEM_PROMPT
    assert "一个自然短句" in ASYNC_REACT_SYSTEM_PROMPT
    assert "这是「修改任务」，不是独立新需求" in ASYNC_REACT_SYSTEM_PROMPT
    assert "用户不需要明确说出「取消」" in ASYNC_REACT_SYSTEM_PROMPT
    assert "不得出现在同一次模型响应中" in ASYNC_REACT_SYSTEM_PROMPT
    assert "取消范围必须由用户明确授权" in ASYNC_REACT_SYSTEM_PROMPT


def test_serialize_console_event_adds_transport_round_without_changing_event() -> None:
    event = PlanStepStartedEvent(
        step_id="s1",
        step_goal="search",
        resolved_inputs={"query": "coffee"},
    )
    envelope = serialize_console_event(event, message_id="agent-1", round=3)

    assert envelope["payload"]["message_id"] == "agent-1"
    assert envelope["payload"]["round"] == 3
    assert not hasattr(event, "round")


def test_serializes_plan_step_diagnosis_events() -> None:
    started = serialize_console_event(
        PlanStepDiagnosisStartedEvent(
            step_id="s1",
            step_goal="find candidates",
            success_check=jq_expr("(.s1.outputs.Place | length) > 0"),
            failure_message="no candidate",
            process_error_kind=None,
        ),
        message_id="agent-1",
        round=2,
    )
    completed = serialize_console_event(
        PlanStepDiagnosisCompletedEvent(
            step_id="s1",
            step_goal="find candidates",
            source="llm",
            decision=Replan(
                failed_assumption="search radius was too narrow",
                retry_direction="expand the radius",
            ),
        ),
        message_id="agent-1",
        round=2,
    )

    assert started["payload"]["type"] == "plan.step.diagnosis.started"
    assert started["payload"]["step_id"] == "s1"
    assert started["payload"]["failure_message"] == "no candidate"
    assert started["payload"]["message_id"] == "agent-1"
    assert started["payload"]["round"] == 2
    assert completed["payload"]["source"] == "llm"
    assert completed["payload"]["decision"] == {
        "outcome": "replan",
        "failed_assumption": "search radius was too narrow",
        "retry_direction": "expand the radius",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("command", "expected_code"),
    [
        (
            ClientCommandEnvelope(
                v=99,
                kind="command",
                command_id="cmd-version",
                command="agent.run",
                payload={"query": "hello", "message_id": "agent-live-1"},
            ),
            "UNSUPPORTED_VERSION",
        ),
        (
            ClientCommandEnvelope(
                v=PROTOCOL_VERSION,
                kind="event",
                command_id="cmd-kind",
                command="agent.run",
                payload={"query": "hello", "message_id": "agent-live-1"},
            ),
            "INVALID_PAYLOAD",
        ),
        (
            ClientCommandEnvelope(
                v=PROTOCOL_VERSION,
                kind="command",
                command_id="cmd-unknown",
                command="unknown.command",
                payload={},
            ),
            "UNKNOWN_COMMAND",
        ),
    ],
)
async def test_command_dispatch_rejects_invalid_envelope_before_handler(
    command: ClientCommandEnvelope,
    expected_code: str,
) -> None:
    session = RecordingCommandSession()

    await handle_client_command(session, command)  # type: ignore[arg-type]

    ack = session.messages[0]
    assert ack["kind"] == "ack"
    assert ack["command_id"] == command.command_id
    assert ack["command"] == command.command
    assert ack["ok"] is False
    assert ack["status"] == "rejected"
    assert ack["error"]["code"] == expected_code
    assert ack["error"]["retryable"] is False


@pytest.mark.anyio
async def test_command_dispatch_rejects_invalid_payload_before_handler() -> None:
    session = RecordingCommandSession()
    command = ClientCommandEnvelope(
        v=PROTOCOL_VERSION,
        kind="command",
        command_id="cmd-invalid-payload",
        command="agent.run",
        payload={"query": "hello"},
    )

    await handle_client_command(session, command)  # type: ignore[arg-type]

    ack = session.messages[0]
    assert ack["kind"] == "ack"
    assert ack["command"] == "agent.run"
    assert ack["ok"] is False
    assert ack["status"] == "rejected"
    assert ack["error"]["code"] == "INVALID_PAYLOAD"
    assert "message_id" in ack["error"]["message"]


@pytest.mark.anyio
async def test_v1_command_is_explicitly_rejected() -> None:
    session = RecordingCommandSession()
    await handle_client_command(
        session,  # type: ignore[arg-type]
        ClientCommandEnvelope(
            v=1,
            kind="command",
            command_id="cmd-old",
            command="agent.run",
            payload={"query": "hello", "message_id": "agent-1"},
        ),
    )

    assert session.messages[0]["error"]["code"] == "UNSUPPORTED_VERSION"


@pytest.mark.anyio
async def test_session_bound_agent_correlates_message_and_round() -> None:
    class FakeAgent:
        async def astream(self, input_event: object, **kwargs: object):
            yield PlActRoundStartEvent(round=2)
            yield PlanStepStartedEvent(
                step_id="s1",
                step_goal="search",
                resolved_inputs={"query": "coffee"},
            )
            yield AgentOutTextDeltaEvent(
                event_id="event-1",
                timestamp=datetime(2026, 6, 16, 10, 30, 0),
                delta="done",
            )

    agent = SessionBoundAgent(FakeAgent(), task_manager=TaskManager())
    events = [
        event
        async for event in agent.astream(QueuedUserInput(query="hello", message_id="agent-1"))
    ]

    assert agent.context_for(events[0]) == EventContext(message_id="agent-1", round=2)
    assert agent.context_for(events[1]) == EventContext(message_id="agent-1", round=2)
    assert agent.context_for(events[2]) == EventContext(message_id="agent-1", round=2)
    assert agent.context_for(events[2]) == EventContext()


@pytest.mark.anyio
async def test_react_event_context_has_no_plan_round() -> None:
    class FakeAgent:
        async def astream(self, input_event: object, **kwargs: object):
            yield AgentOutTextDeltaEvent(delta="react text")

    agent = SessionBoundAgent(FakeAgent(), task_manager=TaskManager())
    events = [
        event
        async for event in agent.astream(
            QueuedUserInput(query="hello", message_id="agent-react")
        )
    ]

    assert agent.context_for(events[0]) == EventContext(
        message_id="agent-react",
        round=None,
    )


@pytest.mark.anyio
async def test_session_bound_agent_saves_task_origin_from_user_turn() -> None:
    manager = TaskManager()

    async def worker():
        yield TaskSuccess(result="done")

    class FakeAgent:
        async def astream(self, input_event: object, **kwargs: object):
            manager.submit_task(
                worker,
                task_id="poi-1",
                name="地点搜索工具",
            )
            yield AgentOutTextDeltaEvent(delta="正在查询")

    agent = SessionBoundAgent(FakeAgent(), task_manager=manager)
    events = [
        event
        async for event in agent.astream(
            QueuedUserInput(query="找餐厅", message_id="agent-origin")
        )
    ]

    task = manager.get_task("poi-1")
    assert task is not None
    assert task.metadata["origin_message_id"] == "agent-origin"
    assert agent.context_for(events[0]) == EventContext(message_id="agent-origin")


@pytest.mark.anyio
async def test_task_success_reply_uses_independent_result_context() -> None:
    manager = TaskManager()

    async def worker():
        yield TaskSuccess(result="done")

    manager.submit_task(
        worker,
        task_id="poi-1",
        name="地点搜索工具",
        metadata={"origin_message_id": "agent-origin"},
    )

    class FakeAgent:
        async def astream(self, input_event: object, **kwargs: object):
            yield AgentOutTextDeltaEvent(delta="找到三家餐厅")

    agent = SessionBoundAgent(FakeAgent(), task_manager=manager)
    events = [
        event
        async for event in agent.astream(
            TaskSuccessEvent(task_id="poi-1", result="done")
        )
    ]

    assert agent.context_for(events[0]) == EventContext(
        message_id="task-result-poi-1",
        origin_message_id="agent-origin",
        source_task_id="poi-1",
    )


@pytest.mark.anyio
async def test_task_lifecycle_event_envelope_keeps_origin_message_id() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )

    async def worker():
        yield TaskSuccess(result="done")

    session.task_manager.submit_task(
        worker,
        task_id="poi-1",
        name="地点搜索工具",
        metadata={"origin_message_id": "agent-origin"},
    )

    session._emit(TaskStartEvent(task_id="poi-1"))

    message = await session._outbound_queue.get()
    assert message["event"]["payload"]["origin_message_id"] == "agent-origin"
    assert message["event"]["payload"]["conversation_turn_id"] == "agent-origin"
    assert message["event"]["payload"]["output_run_id"] is None
    assert message["event"]["payload"]["triggering_task_ids"] == []

    await session.stop()


@pytest.mark.anyio
async def test_gateway_projects_v2_task_result_correlation() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    session._emit(
        AgentOutTextDeltaEvent(delta="result"),
        context=EventContext(
            message_id="task-result-poi-1",
            origin_message_id="agent-origin",
            source_task_id="poi-1",
        ),
    )

    message = await session._outbound_queue.get()
    payload = message["event"]["payload"]
    assert payload["conversation_turn_id"] == "agent-origin"
    assert payload["output_run_id"] == "task-result-poi-1"
    assert payload["triggering_task_ids"] == ["poi-1"]
    assert payload["origin_message_id"] == "agent-origin"
    assert payload["source_task_id"] == "poi-1"

    await session.stop()


@pytest.mark.anyio
async def test_websocket_agent_session_reuses_one_agent_runner_for_follow_up_turns() -> None:
    built_agents: list[tuple[object, str]] = []
    built_runners: list[FakeRunner] = []

    def build_agent(task_manager: object, mode: str) -> object:
        agent = object()
        built_agents.append((agent, mode))
        return agent

    def build_runner(**kwargs: object) -> "FakeRunner":
        runner = FakeRunner(kwargs["user_data"])
        built_runners.append(runner)
        return runner

    session = WebSocketAgentSession(
        agent_factory=build_agent,
        runner_factory=build_runner,
    )

    await session.submit("first", message_id="agent-1")
    await session.submit("follow up", message_id="agent-2")

    assert len(built_agents) == 1
    assert built_agents[0][1] == "react"
    assert len(built_runners) == 1

    first = await built_runners[0].user_data._queue.get()
    second = await built_runners[0].user_data._queue.get()
    assert first == QueuedUserInput(query="first", message_id="agent-1")
    assert second == QueuedUserInput(query="follow up", message_id="agent-2")

    await session.stop()


@pytest.mark.anyio
async def test_websocket_agent_session_stop_cancels_the_bound_runner() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    await session.submit("first", message_id="agent-1")
    runner_task = session._runner_task

    await session.stop()

    assert runner_task is not None
    assert runner_task.done()
    assert runner_task.cancelled()
    with suppress(asyncio.CancelledError):
        await runner_task


@pytest.mark.anyio
async def test_websocket_agent_session_reports_runner_failure_to_client() -> None:
    class FailingRunner:
        async def run(self) -> None:
            raise RuntimeError("runner boom")

    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FailingRunner(),
    )

    await session.submit("hello", message_id="agent-1")

    message = await asyncio.wait_for(session._outbound_queue.get(), timeout=1)
    assert message["kind"] == "error"
    assert message["error"]["code"] == "AGENT_RUNTIME_FAILED"
    assert "RuntimeError: runner boom" in message["error"]["message"]

    await session.stop()


@pytest.mark.anyio
async def test_agent_run_command_acks_and_queues_the_frontend_message_id() -> None:
    built_runners: list[FakeRunner] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: built_runners.append(FakeRunner(kwargs["user_data"]))
        or built_runners[-1],
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-run-1",
            command="agent.run",
            payload={"query": "hello", "message_id": "agent-live-1"},
        ),
    )

    ack = await session._outbound_queue.get()
    assert ack["kind"] == "ack"
    assert ack["command_id"] == "cmd-run-1"
    assert ack["command"] == "agent.run"
    assert ack["status"] == "accepted"
    assert ack["payload"]["message_id"] == "agent-live-1"

    assert len(built_runners) == 1
    queued = await built_runners[0].user_data._queue.get()
    assert queued == QueuedUserInput(query="hello", message_id="agent-live-1")

    await session.stop()


@pytest.mark.anyio
async def test_backend_traces_command_queue_first_delta_and_cancellation_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict[str, object]] = []

    def record(event: str, **fields: object) -> None:
        records.append({"event": event, **fields})

    monkeypatch.setattr(frontend_backend, "trace_latency", record)
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-run-trace",
            command="agent.run",
            payload={"query": "sensitive user text", "message_id": "agent-1"},
        ),
    )
    await session._outbound_queue.get()

    inputs = session.user_data().__aiter__()
    assert await anext(inputs) == QueuedUserInput(
        query="sensitive user text",
        message_id="agent-1",
    )
    await inputs.aclose()

    session._agent = ContextAgent(EventContext(message_id="agent-1"))  # type: ignore[assignment]
    session._emit(AgentOutTextDeltaEvent(delta="first"))
    session._emit(AgentOutTextDeltaEvent(delta="second"))
    session._emit(TaskCancelledEvent(task_id="task-1", reason="cancelled"))

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-cancel-trace",
            command="task.cancel",
            payload={"task_id": "task-1"},
        ),
    )

    assert any(
        record == {
            "event": "ws.command.received",
            "command_id": "cmd-run-trace",
            "command": "agent.run",
            "message_id": "agent-1",
            "task_id": None,
            "session_id": session.session_id,
            "generation": session.generation,
        }
        for record in records
    )
    assert any(record["event"] == "agent.input.enqueued" for record in records)
    assert any(record["event"] == "agent.input.dequeued" for record in records)
    assert len([record for record in records if record["event"] == "agent.first_delta"]) == 1
    assert any(record["event"] == "task.cancel.requested" for record in records)
    assert any(record["event"] == "task.cancelled" for record in records)
    assert "sensitive user text" not in str(records)

    await session.stop()


@pytest.mark.anyio
async def test_agent_run_prepares_voice_bridge_before_voice_start() -> None:
    built_bridges: list[FakeVoiceBridge] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
        voice_bridge_factory=lambda **kwargs: built_bridges.append(FakeVoiceBridge(**kwargs))
        or built_bridges[-1],
    )
    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-run-voice-buffer",
            command="agent.run",
            payload={"query": "hello", "message_id": "agent-live-1"},
        ),
    )
    await session._outbound_queue.get()

    assert len(built_bridges) == 1
    assert session.voice_bridge is built_bridges[0]
    assert built_bridges[0].start_count == 0

    event = AgentOutTextDeltaEvent(delta="early")
    session._emit(event)

    assert built_bridges[0].agent_events == [(event, None)]

    await session.start_voice()
    assert session.voice_bridge is built_bridges[0]
    assert built_bridges[0].start_count == 1

    await session.stop()


@pytest.mark.anyio
async def test_voice_bridge_factory_receives_no_router_or_gate_context() -> None:
    built_kwargs: list[dict[str, object]] = []

    def build_bridge(**kwargs: object) -> FakeVoiceBridge:
        built_kwargs.append(kwargs)
        return FakeVoiceBridge(**kwargs)

    first = WebSocketAgentSession(voice_bridge_factory=build_bridge)
    second = WebSocketAgentSession(voice_bridge_factory=build_bridge)

    await first.prepare_voice_output()
    await second.prepare_voice_output()

    assert "turn_gate" not in built_kwargs[0]
    assert "turn_gate" not in built_kwargs[1]
    assert "active_task_provider" not in built_kwargs[0]
    assert "active_task_provider" not in built_kwargs[1]


@pytest.mark.anyio
async def test_voice_start_command_acks_ready_without_starting_second_runner() -> None:
    built_runners: list[FakeRunner] = []
    built_bridges: list[FakeVoiceBridge] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: built_runners.append(FakeRunner(kwargs["user_data"]))
        or built_runners[-1],
        voice_bridge_factory=lambda **kwargs: built_bridges.append(FakeVoiceBridge(**kwargs))
        or built_bridges[-1],
    )
    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-run-1",
            command="agent.run",
            payload={"query": "hello", "message_id": "agent-live-1"},
        ),
    )
    await session._outbound_queue.get()

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-voice-start-1",
            command="voice.start",
            payload={},
        ),
    )

    ack = await session._outbound_queue.get()
    assert ack["kind"] == "ack"
    assert ack["command"] == "voice.start"
    assert ack["status"] == "completed"
    assert ack["payload"] == {
        "input_sample_rate": 16000,
        "output_sample_rate": 24000,
        "output_format": "f32le",
    }
    assert len(built_runners) == 1
    assert len(built_bridges) == 1
    assert built_bridges[0].start_count == 1

    await session.stop()


@pytest.mark.anyio
async def test_session_restarts_real_bridge_after_autonomous_background_shutdown() -> None:
    clients: list[RestartableRealtimeClient] = []

    def build_bridge(**kwargs: object) -> FrontendVoiceBridge:
        def build_client(session_id: str) -> RestartableRealtimeClient:
            client = RestartableRealtimeClient()
            clients.append(client)
            return client

        return FrontendVoiceBridge(
            **kwargs,
            realtime_client_factory=build_client,
        )

    session = WebSocketAgentSession(voice_bridge_factory=build_bridge)
    first_ready = await session.start_voice()
    bridge = session.voice_bridge
    assert isinstance(bridge, FrontendVoiceBridge)
    assert bridge.running is True
    assert len(clients) == 1

    await bridge._handle_background_error(RuntimeError("background receive failed"))
    assert bridge.running is False
    assert bridge.client is None
    assert session._voice_ready_payload == first_ready

    second_ready = await session.start_voice()

    assert second_ready == first_ready
    assert bridge.running is True
    assert len(clients) == 2
    assert clients[1].start_count == 1

    concurrent = await asyncio.gather(session.start_voice(), session.start_voice())
    assert concurrent == [first_ready, first_ready]
    assert len(clients) == 2

    await session.stop()


@pytest.mark.anyio
async def test_concurrent_cold_start_failure_cannot_clear_successful_retry() -> None:
    clients: list[RestartableRealtimeClient] = []
    first_started = asyncio.Event()
    first_release = asyncio.Event()

    def build_bridge(**kwargs: object) -> FrontendVoiceBridge:
        def build_client(session_id: str) -> RestartableRealtimeClient:
            client = RestartableRealtimeClient(
                start_started=first_started if not clients else None,
                start_release=first_release if not clients else None,
                start_error=(RuntimeError("first start failed") if not clients else None),
            )
            clients.append(client)
            return client

        return FrontendVoiceBridge(
            **kwargs,
            realtime_client_factory=build_client,
        )

    session = WebSocketAgentSession(voice_bridge_factory=build_bridge)
    first_start = asyncio.create_task(session.start_voice())
    await first_started.wait()
    second_start = asyncio.create_task(session.start_voice())
    await asyncio.sleep(0)
    first_release.set()
    results = await asyncio.gather(first_start, second_start, return_exceptions=True)

    assert len([result for result in results if isinstance(result, RuntimeError)]) == 1
    assert len([result for result in results if isinstance(result, dict)]) == 1
    assert len(clients) == 2
    assert session.voice_bridge is not None
    assert session.voice_bridge.running is True

    await session.stop()


@pytest.mark.anyio
async def test_twenty_concurrent_cold_starts_create_one_realtime_client() -> None:
    clients: list[RestartableRealtimeClient] = []

    session = WebSocketAgentSession(
        voice_bridge_factory=lambda **kwargs: FrontendVoiceBridge(
            **kwargs,
            realtime_client_factory=lambda session_id: clients.append(
                RestartableRealtimeClient()
            )
            or clients[-1],
        )
    )

    ready_payloads = await asyncio.gather(
        *(session.start_voice() for _ in range(20))
    )

    assert len(clients) == 1
    assert clients[0].start_count == 1
    assert all(payload == ready_payloads[0] for payload in ready_payloads)
    assert session.voice_bridge is not None and session.voice_bridge.running is True

    await session.stop()


@pytest.mark.anyio
async def test_concurrent_stop_and_start_never_leave_a_running_orphan_bridge() -> None:
    bridges: list[LifecycleRaceVoiceBridge] = []

    def build_bridge(**kwargs: object) -> LifecycleRaceVoiceBridge:
        bridge = LifecycleRaceVoiceBridge(
            **kwargs,
            block_stop=not bridges,
        )
        bridges.append(bridge)
        return bridge

    session = WebSocketAgentSession(voice_bridge_factory=build_bridge)
    await session.start_voice()
    first_bridge = bridges[0]

    stop_task = asyncio.create_task(session.stop_voice())
    await first_bridge.stop_started.wait()
    start_task = asyncio.create_task(session.start_voice())
    await asyncio.sleep(0)
    first_bridge.stop_release.set()
    await asyncio.gather(stop_task, start_task)

    running_bridges = [bridge for bridge in bridges if bridge.running]
    if session.voice_bridge is None:
        assert running_bridges == []
        assert all(bridge.stopped for bridge in bridges)
    else:
        assert running_bridges == [session.voice_bridge]

    for bridge in bridges:
        bridge.stop_release.set()
    await session.stop()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "operation",
    ["open_microphone", "text_query"],
)
async def test_voice_composite_operation_holds_session_lifecycle_ownership(
    operation: str,
) -> None:
    bridges: list[LifecycleRaceVoiceBridge] = []
    session = WebSocketAgentSession(
        voice_bridge_factory=lambda **kwargs: bridges.append(
            LifecycleRaceVoiceBridge(**kwargs, block_action=True)
        )
        or bridges[-1]
    )

    if operation == "open_microphone":
        operation_task = asyncio.create_task(session.open_voice_microphone())
    else:
        operation_task = asyncio.create_task(session.submit_voice_text_query("hello"))

    while not bridges:
        await asyncio.sleep(0)
    bridge = bridges[0]
    await bridge.action_started.wait()
    stop_task = asyncio.create_task(session.stop_voice())
    await asyncio.sleep(0)
    try:
        assert not bridge.stop_started.is_set()
        assert session.voice_bridge is bridge
    finally:
        bridge.action_release.set()
        await asyncio.gather(operation_task, stop_task, return_exceptions=True)

    assert bridge.stopped is True
    assert session.voice_bridge is None


@pytest.mark.anyio
async def test_session_forwards_agent_text_events_to_voice_bridge() -> None:
    bridge = FakeVoiceBridge(
        submit_text=object(),
        send_json=object(),
        send_audio=object(),
        session_id=object(),
        generation=object(),
    )
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    session.voice_bridge = bridge
    session._agent = ContextAgent(EventContext(message_id="agent-1"))
    event = AgentOutTextDeltaEvent(
        event_id="event-1",
        timestamp=datetime(2026, 6, 16, 10, 30, 0),
        delta="partial",
    )

    session._emit(event)

    assert bridge.agent_events == [(event, "agent-1")]


@pytest.mark.anyio
async def test_session_emit_still_enqueues_event_when_voice_bridge_forwarding_fails() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    session.voice_bridge = RaisingVoiceBridge()
    event = AgentOutTextDeltaEvent(
        event_id="event-1",
        timestamp=datetime(2026, 6, 16, 10, 30, 0),
        delta="partial",
    )

    session._emit(event)

    message = await asyncio.wait_for(session._outbound_queue.get(), timeout=1)
    assert message["kind"] == "event"
    assert message["event"]["type"] == "agent.out.text.delta"
    assert message["event"]["payload"]["delta"] == "partial"


@pytest.mark.anyio
async def test_voice_start_failure_rejects_ack_and_clears_bridge() -> None:
    built_bridges: list[FakeVoiceBridge] = []
    factory_calls = 0

    def build_voice_bridge(**kwargs: object) -> object:
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            return FailingVoiceBridge()
        bridge = FakeVoiceBridge(**kwargs)
        built_bridges.append(bridge)
        return bridge

    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
        voice_bridge_factory=build_voice_bridge,
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-voice-start-fail",
            command="voice.start",
            payload={},
        ),
    )

    rejected_ack = await session._outbound_queue.get()
    assert rejected_ack["kind"] == "ack"
    assert rejected_ack["command"] == "voice.start"
    assert rejected_ack["ok"] is False
    assert rejected_ack["status"] == "rejected"
    assert rejected_ack["error"]["code"] == "VOICE_COMMAND_FAILED"
    assert "voice boom" in rejected_ack["error"]["message"]
    assert session.voice_bridge is None

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-voice-start-retry",
            command="voice.start",
            payload={},
        ),
    )

    ready_ack = await session._outbound_queue.get()
    assert ready_ack["kind"] == "ack"
    assert ready_ack["command"] == "voice.start"
    assert ready_ack["ok"] is True
    assert ready_ack["status"] == "completed"
    assert ready_ack["payload"]["input_sample_rate"] == 16000
    assert session.voice_bridge is built_bridges[0]
    assert built_bridges[0].start_count == 1

    await session.stop()


@pytest.mark.anyio
async def test_voice_microphone_commands_route_to_bridge_and_ack_completed() -> None:
    built_bridges: list[FakeVoiceBridge] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
        voice_bridge_factory=lambda **kwargs: built_bridges.append(FakeVoiceBridge(**kwargs))
        or built_bridges[-1],
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-mic-open-1",
            command="voice.mic.open",
            payload={},
        ),
    )
    open_ack = await session._outbound_queue.get()
    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-mic-close-1",
            command="voice.mic.close",
            payload={},
        ),
    )
    close_ack = await session._outbound_queue.get()

    assert open_ack["kind"] == "ack"
    assert open_ack["command"] == "voice.mic.open"
    assert open_ack["status"] == "completed"
    assert open_ack.get("payload") == {}
    assert close_ack["kind"] == "ack"
    assert close_ack["command"] == "voice.mic.close"
    assert close_ack["status"] == "completed"
    assert close_ack.get("payload") == {}
    assert len(built_bridges) == 1
    assert built_bridges[0].open_microphone_count == 1
    assert built_bridges[0].close_microphone_count == 1

    await session.stop()


@pytest.mark.anyio
async def test_playback_ended_command_forwards_to_bridge() -> None:
    built_bridges: list[FakeVoiceBridge] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
        voice_bridge_factory=lambda **kwargs: built_bridges.append(FakeVoiceBridge(**kwargs))
        or built_bridges[-1],
    )
    await session.prepare_voice_output()

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-playback-ended",
            command="voice.playback.ended",
            payload={},
        ),
    )
    ack = await session._outbound_queue.get()
    assert ack["status"] == "completed"
    assert built_bridges[0].playback_ended_count == 1

    await session.stop()


@pytest.mark.anyio
async def test_voice_text_query_command_routes_to_bridge_and_does_not_queue_agent_run() -> None:
    built_runners: list[FakeRunner] = []
    built_bridges: list[FakeVoiceBridge] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: built_runners.append(FakeRunner(kwargs["user_data"]))
        or built_runners[-1],
        voice_bridge_factory=lambda **kwargs: built_bridges.append(FakeVoiceBridge(**kwargs))
        or built_bridges[-1],
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-voice-text-1",
            command="voice.text.query",
            payload={"query": "  hello text  "},
        ),
    )

    ack = await session._outbound_queue.get()
    assert ack["kind"] == "ack"
    assert ack["command"] == "voice.text.query"
    assert ack["status"] == "completed"
    assert ack["payload"] == {
        "session_id": session.session_id,
        "generation": session.generation,
    }
    assert built_runners == []
    assert len(built_bridges) == 1
    assert built_bridges[0].start_count == 1
    assert built_bridges[0].text_queries == ["hello text"]

    await session.stop()


@pytest.mark.anyio
async def test_voice_stop_failure_rejects_ack_and_retains_bridge_for_retry() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    bridge = FailingStopVoiceBridge()
    session.voice_bridge = bridge
    session._voice_ready_payload = {
        "input_sample_rate": 16000,
        "output_sample_rate": 24000,
        "output_format": "f32le",
    }

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-voice-stop-fail",
            command="voice.stop",
            payload={},
        ),
    )

    ack = await session._outbound_queue.get()
    assert ack["kind"] == "ack"
    assert ack["command"] == "voice.stop"
    assert ack["ok"] is False
    assert ack["status"] == "rejected"
    assert ack["error"]["code"] == "VOICE_COMMAND_FAILED"
    assert "stop boom" in ack["error"]["message"]
    assert session.voice_bridge is bridge
    assert bridge.stop_count == 1

    session.voice_bridge = None


@pytest.mark.anyio
async def test_session_stop_cancels_runner_and_clears_bridge_when_voice_cleanup_fails() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    await session.submit("hello", message_id="agent-live-1")
    runner_task = session._runner_task
    bridge = FailingStopVoiceBridge()
    session.voice_bridge = bridge

    await session.stop()

    assert runner_task is not None
    assert runner_task.done()
    assert runner_task.cancelled()
    assert session.voice_bridge is None
    assert bridge.stop_count == 1


@pytest.mark.anyio
async def test_stop_and_reset_build_fresh_voice_bridges() -> None:
    built_bridges: list[FakeVoiceBridge] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
        voice_bridge_factory=lambda **kwargs: built_bridges.append(FakeVoiceBridge(**kwargs))
        or built_bridges[-1],
    )

    first_bridge = await session.prepare_voice_output()

    await session.stop_voice()
    second_bridge = await session.prepare_voice_output()
    assert second_bridge is not first_bridge

    await session.reset("plact")
    third_bridge = await session.prepare_voice_output()
    assert third_bridge is not second_bridge

    await session.stop()


@pytest.mark.anyio
async def test_submit_voice_text_strips_text_and_queues_voice_turn_ids() -> None:
    built_runners: list[FakeRunner] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: built_runners.append(FakeRunner(kwargs["user_data"]))
        or built_runners[-1],
    )

    result = await session.submit_voice_text("  hello from voice  ")

    assert result == {
        "text": "hello from voice",
        "turn_id": "voice-turn-1",
        "user_message_id": "voice-user-1",
        "assistant_message_id": "voice-assistant-1",
    }
    queued = await built_runners[0].user_data._queue.get()
    assert queued == QueuedUserInput(query="hello from voice", message_id="voice-assistant-1")
    with pytest.raises(ValueError, match="Voice text must not be empty"):
        await session.submit_voice_text("   ")

    await session.stop()


@pytest.mark.anyio
async def test_prepare_voice_text_allocates_ids_without_queueing_until_commit() -> None:
    built_runners: list[FakeRunner] = []
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: built_runners.append(FakeRunner(kwargs["user_data"]))
        or built_runners[-1],
    )

    payload = await session.prepare_voice_text("  hello from voice  ")

    assert payload == {
        "text": "hello from voice",
        "turn_id": "voice-turn-1",
        "user_message_id": "voice-user-1",
        "assistant_message_id": "voice-assistant-1",
    }
    assert built_runners == []

    await session.commit_voice_text(payload)

    assert len(built_runners) == 1
    queued = await built_runners[0].user_data._queue.get()
    assert queued == QueuedUserInput(query="hello from voice", message_id="voice-assistant-1")

    second_payload = await session.prepare_voice_text("follow up")
    assert second_payload == {
        "text": "follow up",
        "turn_id": "voice-turn-2",
        "user_message_id": "voice-user-2",
        "assistant_message_id": "voice-assistant-2",
    }
    with pytest.raises(ValueError, match="Voice text must not be empty"):
        await session.prepare_voice_text("   ")

    await session.stop()


@pytest.mark.anyio
async def test_real_bridge_commit_failure_reports_after_final_without_reenqueue() -> None:
    runner_attempts = 0
    runner_user_data: list[object] = []

    def fail_runner(**kwargs: object) -> object:
        nonlocal runner_attempts
        runner_attempts += 1
        runner_user_data.append(kwargs["user_data"])
        raise RuntimeError("runner unavailable")

    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=fail_runner,
        voice_bridge_factory=lambda **kwargs: FrontendVoiceBridge(
            **kwargs,
            realtime_client_factory=lambda session_id: object(),
        ),
    )
    bridge = await session.prepare_voice_output()
    assert bridge.submit_text == session.prepare_voice_text
    assert bridge.commit_text == session.commit_voice_text

    await bridge._handle_server_event(
        ASRFinal(message_type="server", payload=AsrTextPayload(text="查天气"))
    )
    await bridge._handle_server_event(
        ASREnded(message_type="server", payload=EmptyPayload())
    )

    outbound: list[dict[str, object]] = []
    while not session._outbound_queue.empty():
        message = session._outbound_queue.get_nowait()
        assert isinstance(message, dict)
        outbound.append(message)
    voice_types = [
        str(message["type"])
        for message in outbound
        if message.get("kind") == "voice"
    ]

    assert voice_types.index("voice.asr.final") < voice_types.index(
        "voice.submit.failed"
    )
    assert runner_attempts == 1
    assert len(runner_user_data) == 1
    assert runner_user_data[0]._queue.empty()
    await asyncio.sleep(0)
    assert runner_attempts == 1

    await session.stop()


@pytest.mark.anyio
async def test_task_cancel_command_returns_completed_ack_with_outcome_payload() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-cancel-1",
            command="task.cancel",
            payload={"task_id": "missing-task"},
        ),
    )

    ack = await session._outbound_queue.get()
    assert ack["kind"] == "ack"
    assert ack["status"] == "completed"
    assert ack["payload"]["task_id"] == "missing-task"
    assert ack["payload"]["outcome"]["status"] == "not_found"


@pytest.mark.anyio
async def test_task_cancel_command_reaches_runner_and_cancels_live_worker() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    worker_started = anyio.Event()
    worker_cancelled = anyio.Event()
    task_events: list[object] = []

    async def worker():
        try:
            worker_started.set()
            await anyio.sleep_forever()
        finally:
            worker_cancelled.set()
        yield TaskSuccess(result="unreachable")

    task_id = session.task_manager.submit_task(
        worker,
        name="long_running_search",
        arguments={"query": "咖啡店"},
    )

    async def collect_until_cancelled() -> None:
        async for event in session.task_manager.astream():
            task_events.append(event)
            if isinstance(event, TaskCancelledEvent):
                return

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(session.task_manager.run)
        task_group.start_soon(collect_until_cancelled)
        with anyio.fail_after(1):
            await worker_started.wait()

        await handle_client_command(
            session,
            ClientCommandEnvelope(
                v=PROTOCOL_VERSION,
                kind="command",
                command_id="cmd-cancel-live-worker",
                command="task.cancel",
                payload={"task_id": task_id},
            ),
        )

        ack = await session._outbound_queue.get()
        assert ack["payload"]["outcome"]["status"] == "accepted"
        with anyio.fail_after(1):
            await worker_cancelled.wait()
        with anyio.fail_after(1):
            while not any(
                isinstance(event, TaskCancelledEvent)
                for event in task_events
            ):
                await anyio.sleep(0)
        task_group.cancel_scope.cancel()

    projection = session.task_manager.get_task(task_id)
    assert projection is not None
    assert projection.status.value == "cancelled"
    assert any(
        isinstance(event, TaskCancelledEvent)
        and event.task_id == task_id
        for event in task_events
    )


@pytest.mark.anyio
async def test_session_reset_command_cancels_runner_and_advances_generation() -> None:
    session = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    await session.submit("hello", message_id="agent-live-1")
    runner_task = session._runner_task

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-reset-1",
            command="session.reset",
            payload={"agent_mode": "plact"},
        ),
    )

    ack = await session._outbound_queue.get()
    assert runner_task is not None
    assert runner_task.done()
    assert runner_task.cancelled()
    assert ack["kind"] == "ack"
    assert ack["status"] == "completed"
    assert ack["payload"]["generation"] == 2
    assert ack["payload"]["session_id"].startswith("sess-")
    assert ack["payload"]["agent_mode"] == "plact"


@pytest.mark.anyio
async def test_session_reset_switches_mode_and_rebuilds_the_agent() -> None:
    built_modes: list[str] = []

    def build_agent(task_manager: object, mode: str) -> object:
        built_modes.append(mode)
        return object()

    session = WebSocketAgentSession(
        agent_factory=build_agent,
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    assert session.agent_mode == "react"
    await session.submit("first", message_id="agent-1")
    first_runner = session._runner_task

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="cmd-reset-mode",
            command="session.reset",
            payload={"agent_mode": "plact"},
        ),
    )
    ack = await session._outbound_queue.get()

    assert ack["payload"]["agent_mode"] == "plact"
    assert session.agent_mode == "plact"
    assert first_runner is not None and first_runner.cancelled()

    await session.submit("second", message_id="agent-2")
    assert built_modes == ["react", "plact"]
    await session.stop()


@pytest.mark.anyio
async def test_stopping_one_websocket_session_does_not_stop_another() -> None:
    first = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    second = WebSocketAgentSession(
        agent_factory=lambda task_manager, mode: object(),
        runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
    )
    await first.submit("first", message_id="agent-live-1")
    await second.submit("second", message_id="agent-live-2")
    first_runner = first._runner_task
    second_runner = second._runner_task

    await first.stop()

    assert first_runner is not None
    assert first_runner.done()
    assert second_runner is not None
    assert not second_runner.done()

    await second.stop()


def test_websocket_endpoint_sends_hello_and_rejects_invalid_json() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/v2/frontend/ws") as websocket:
            hello = websocket.receive_json()
            assert set(hello) == {
                "v",
                "kind",
                "connection_id",
                "session_id",
                "generation",
                "server_time",
                "runtime_profile",
                "capabilities",
            }
            assert hello["runtime_profile"] == "react_s2s"
            assert hello["capabilities"]["text_input"] is True
            assert hello["kind"] == "hello"
            assert hello["v"] == PROTOCOL_VERSION

            websocket.send_text("{")
            response = websocket.receive_json()
            assert response["kind"] == "error"
            assert response["error"]["code"] == "INVALID_JSON"


def test_websocket_endpoint_rejects_unknown_command_with_ack() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/v2/frontend/ws") as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "v": PROTOCOL_VERSION,
                    "kind": "command",
                    "command_id": "cmd-unknown-1",
                    "command": "unknown.command",
                    "payload": {},
                }
            )
            response = websocket.receive_json()
            assert response["kind"] == "ack"
            assert response["ok"] is False
            assert response["status"] == "rejected"
            assert response["error"]["code"] == "UNKNOWN_COMMAND"


def test_websocket_endpoint_routes_binary_audio_to_voice_bridge() -> None:
    built_bridges: list[FakeVoiceBridge] = []

    class SessionWithFakeVoice(WebSocketAgentSession):
        def __init__(self) -> None:
            super().__init__(
                agent_factory=lambda task_manager, mode: object(),
                runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
                voice_bridge_factory=lambda **kwargs: built_bridges.append(
                    FakeVoiceBridge(**kwargs)
                )
                or built_bridges[-1],
            )

    previous_factory = getattr(app.state, "frontend_session_factory", None)
    app.state.frontend_session_factory = SessionWithFakeVoice
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/v2/frontend/ws") as websocket:
                websocket.receive_json()
                websocket.send_json(
                    {
                        "v": PROTOCOL_VERSION,
                        "kind": "command",
                        "command_id": "cmd-voice-start-1",
                        "command": "voice.start",
                        "payload": {},
                    }
                )
                start_ack = websocket.receive_json()
                websocket.send_bytes(b"pcm")
                websocket.send_json(
                    {
                        "v": PROTOCOL_VERSION,
                        "kind": "command",
                        "command_id": "cmd-voice-stop-1",
                        "command": "voice.stop",
                        "payload": {},
                    }
                )
                stop_ack = websocket.receive_json()
    finally:
        if previous_factory is None:
            delattr(app.state, "frontend_session_factory")
        else:
            app.state.frontend_session_factory = previous_factory

    assert start_ack["status"] == "completed"
    assert stop_ack["kind"] == "ack"
    assert stop_ack["command"] == "voice.stop"
    assert stop_ack["status"] == "completed"
    assert len(built_bridges) == 1
    assert built_bridges[0].audio_chunks == [b"pcm"]
    assert built_bridges[0].stop_count == 1


def test_websocket_disconnect_stops_and_clears_voice_bridge() -> None:
    built_sessions: list[WebSocketAgentSession] = []
    built_bridges: list[FakeVoiceBridge] = []

    class SessionWithActiveVoice(WebSocketAgentSession):
        def __init__(self) -> None:
            super().__init__(
                agent_factory=lambda task_manager, mode: object(),
                runner_factory=lambda **kwargs: FakeRunner(kwargs["user_data"]),
                voice_bridge_factory=lambda **kwargs: built_bridges.append(
                    FakeVoiceBridge(**kwargs)
                )
                or built_bridges[-1],
            )
            built_sessions.append(self)

    previous_factory = getattr(app.state, "frontend_session_factory", None)
    app.state.frontend_session_factory = SessionWithActiveVoice
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/v2/frontend/ws") as websocket:
                websocket.receive_json()
                websocket.send_json(
                    {
                        "v": PROTOCOL_VERSION,
                        "kind": "command",
                        "command_id": "cmd-start-before-disconnect",
                        "command": "voice.start",
                        "payload": {},
                    }
                )
                ack = websocket.receive_json()
                session = built_sessions[0]
                bridge = built_bridges[0]
                assert ack["status"] == "completed"
    finally:
        if previous_factory is None:
            delattr(app.state, "frontend_session_factory")
        else:
            app.state.frontend_session_factory = previous_factory

    assert bridge.stop_count == 1
    assert session.voice_bridge is None


class RestartableRealtimeClient:
    def __init__(
        self,
        *,
        start_started: asyncio.Event | None = None,
        start_release: asyncio.Event | None = None,
        start_error: Exception | None = None,
    ) -> None:
        self.start_count = 0
        self.stop_session_count = 0
        self.stop_connection_count = 0
        self.close_count = 0
        self.events: asyncio.Queue[object] = asyncio.Queue()
        self.start_started = start_started
        self.start_release = start_release
        self.start_error = start_error

    async def start(self) -> None:
        self.start_count += 1
        if self.start_started is not None:
            self.start_started.set()
        if self.start_release is not None:
            await self.start_release.wait()
        if self.start_error is not None:
            raise self.start_error

    async def send_audio_chunk(self, chunk: bytes) -> None:
        return None

    async def send_chat_tts_text(self, payload: object) -> None:
        return None

    async def send_chat_text(self, payload: object) -> None:
        return None

    async def receive_event(self) -> object:
        return await self.events.get()

    async def stop_session(self) -> None:
        self.stop_session_count += 1

    async def stop_connection(self) -> None:
        self.stop_connection_count += 1

    async def close(self) -> None:
        self.close_count += 1


class LifecycleRaceVoiceBridge:
    def __init__(
        self,
        *,
        submit_text: object,
        commit_text: object,
        send_json: object,
        send_audio: object,
        session_id: object,
        generation: object,
        block_stop: bool = False,
        block_action: bool = False,
    ) -> None:
        self.block_stop = block_stop
        self.block_action = block_action
        self.running = False
        self.stopped = False
        self.stop_started = asyncio.Event()
        self.stop_release = asyncio.Event()
        self.action_started = asyncio.Event()
        self.action_release = asyncio.Event()

    async def start(self) -> dict[str, object]:
        self.running = True
        self.stopped = False
        return {"input_sample_rate": 16000}

    async def _run_action(self) -> None:
        self.action_started.set()
        if self.block_action:
            await self.action_release.wait()

    async def open_microphone(self) -> None:
        await self._run_action()

    async def submit_text_query(self, text: str) -> None:
        await self._run_action()

    async def stop(self) -> None:
        self.stop_started.set()
        self.running = False
        self.stopped = True
        if self.block_stop:
            await self.stop_release.wait()


class FakeRunner:
    def __init__(self, user_data: object) -> None:
        self.user_data = user_data

    async def run(self) -> None:
        await anyio.sleep_forever()


class FakeVoiceBridge:
    def __init__(
        self,
        *,
        submit_text: object,
        send_json: object,
        send_audio: object,
        session_id: object,
        generation: object,
        commit_text: object | None = None,
    ) -> None:
        self.submit_text = submit_text
        self.send_json = send_json
        self.send_audio = send_audio
        self.session_id = session_id
        self.generation = generation
        self.commit_text = commit_text
        self.start_count = 0
        self.open_microphone_count = 0
        self.close_microphone_count = 0
        self.stop_count = 0
        self.audio_chunks: list[bytes] = []
        self.agent_events: list[object] = []
        self.text_queries: list[str] = []
        self.playback_ended_count = 0

    async def start(self) -> dict[str, object]:
        self.start_count += 1
        return {
            "input_sample_rate": 16000,
            "output_sample_rate": 24000,
            "output_format": "f32le",
        }

    async def open_microphone(self) -> None:
        self.open_microphone_count += 1

    async def close_microphone(self) -> None:
        self.close_microphone_count += 1

    async def feed_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)

    async def submit_text_query(self, text: str) -> None:
        self.text_queries.append(text.strip())

    async def on_playback_ended(self) -> None:
        self.playback_ended_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

    def on_agent_event(self, event: object, *, message_id: str | None) -> None:
        self.agent_events.append((event, message_id))


class FailingVoiceBridge:
    async def start(self) -> dict[str, object]:
        raise RuntimeError("voice boom")


class RaisingVoiceBridge:
    def on_agent_event(self, event: object, *, message_id: str | None) -> None:
        raise RuntimeError("bridge forward boom")


class ContextAgent:
    def __init__(self, context: EventContext) -> None:
        self.context = context

    def context_for(self, event: object) -> EventContext:
        return self.context


class FailingStopVoiceBridge:
    def __init__(self) -> None:
        self.stop_count = 0

    async def stop(self) -> None:
        self.stop_count += 1
        raise RuntimeError("stop boom")
