from __future__ import annotations

import asyncio

import pytest

from aicore.events.agent import (
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.events.task import TaskStartEvent
from aicore.models.stream_model_api import (
    AudioChunkInput,
    StreamAudioDeltaEvent,
    StreamAudioDoneEvent,
    StreamAudioStartEvent,
    StreamTextDeltaEvent,
    StreamTextDoneEvent,
    StreamTranscriptionDeltaEvent,
    StreamTranscriptionDoneEvent,
    StreamTranscriptionStartEvent,
)
from aicore.models.stream_model_api.duplex import DuplexAgentSession, DuplexConfig
from aicore.models.stream_model_api.duplex.async_backfill import (
    BackfillActivation,
    DuplexAsyncCompatConfig,
)
from aicore.models.stream_model_api.events import StreamResponseCanceledEvent
from aicore.session import SessionOutput
from aicore.v2.experiments.duplex_native_session import (
    DuplexNativeSession,
    NativeVoiceEvent,
)
from aicore.v2.experiments.v2_frontend_backend import (
    ClientCommandEnvelope,
    PROTOCOL_VERSION,
    WebSocketAgentSession,
    handle_client_command,
)


class QueueModelAPI:
    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.events_claimed = 0
        self.submissions: list[object] = []
        self.response_cancels = 0
        self.queue: asyncio.Queue[object] = asyncio.Queue()

    async def start(self) -> None:
        self.started = True

    async def submit(self, input: object) -> None:
        self.submissions.append(input)

    async def cancel_response(self) -> None:
        self.response_cancels += 1

    async def events(self):
        self.events_claimed += 1
        while True:
            event = await self.queue.get()
            if event is None:
                return
            if isinstance(event, BaseException):
                raise event
            yield event

    async def aclose(self) -> None:
        self.closed = True


def build_native_factory(model_api: QueueModelAPI):
    def factory(**kwargs: object) -> DuplexAgentSession:
        return DuplexAgentSession(
            model_api=model_api,  # type: ignore[arg-type]
            tools=(),
            task_manager=kwargs["task_manager"],  # type: ignore[arg-type]
            tool_call_mode="sync",
            config=DuplexConfig(),
            context_diagnostics=False,
            media_port=kwargs["media_port"],  # type: ignore[arg-type]
            model_event_observer=kwargs["model_event_observer"],  # type: ignore[arg-type]
            task_event_observer=kwargs["task_event_observer"],  # type: ignore[arg-type]
            backfill_activation_observer=kwargs[
                "backfill_activation_observer"
            ],  # type: ignore[arg-type]
        )

    return factory


async def wait_for_outputs(outputs: list[SessionOutput], count: int) -> None:
    async with asyncio.timeout(1):
        while len(outputs) < count:
            await asyncio.sleep(0)


async def wait_until(predicate, *, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_duplex_native_session_maps_audio_turn_and_waits_for_browser_drain() -> (
    None
):
    model_api = QueueModelAPI()
    outputs: list[SessionOutput] = []

    async def collect(output: SessionOutput) -> None:
        outputs.append(output)

    session = DuplexNativeSession(
        session_id="native-session",
        agent_session_factory=build_native_factory(model_api),
        output_listener=collect,
    )

    ready = await session.start()
    await session.feed_audio(b"\x01\x00")
    for event in (
        StreamTranscriptionStartEvent(session_id="provider", item_id="q1"),
        StreamTranscriptionDeltaEvent(session_id="provider", item_id="q1", delta="你"),
        StreamTranscriptionDoneEvent(
            session_id="provider", item_id="q1", transcript="你好"
        ),
        StreamTextDeltaEvent(session_id="provider", item_id="q1", delta="您好"),
        StreamTextDoneEvent(session_id="provider", item_id="q1", text="您好"),
        StreamAudioStartEvent(session_id="provider", item_id="q1"),
        StreamAudioDeltaEvent(session_id="provider", item_id="q1", delta=b"\x00\x40"),
        StreamAudioDoneEvent(session_id="provider", item_id="q1"),
    ):
        await model_api.queue.put(event)

    await wait_for_outputs(outputs, 9)

    assert ready["output_format"] == "f32le"
    assert model_api.events_claimed == 1
    assert isinstance(model_api.submissions[0], AudioChunkInput)
    assert all(output.turn_id == "native-turn-q1" for output in outputs)
    assert any(isinstance(output.data, bytes) for output in outputs)
    asr_final = next(
        output.data
        for output in outputs
        if isinstance(output.data, NativeVoiceEvent)
        and output.data.event_type == "voice.asr.final"
    )
    assert asr_final.payload == {
        "turn_id": "native-turn-q1",
        "user_message_id": "native-user-native-turn-q1",
        "assistant_message_id": "native-assistant-native-turn-q1",
        "text": "你好",
    }
    assert not session.agent_session._reply_idle.is_set()

    async def worker():
        if False:
            yield

    session.task_manager.submit_task(
        worker,
        task_id="task-q1",
        name="test",
        metadata={"duplex_question_id": "q1"},
    )
    session._observe_task_event(TaskStartEvent(task_id="task-q1"))
    await wait_for_outputs(outputs, 10)
    assert outputs[-1].turn_id == "native-turn-q1"
    assert outputs[-1].metadata["source_task_id"] == "task-q1"

    await session.on_playback_ended()
    assert session.agent_session._reply_idle.is_set()
    assert isinstance(outputs[-1].data, NativeVoiceEvent)
    assert outputs[-1].data.payload == {"phase": "listening"}

    await session.close()
    await session.close()
    assert model_api.closed is True


@pytest.mark.asyncio
async def test_native_barge_in_cancels_response_and_clears_browser_playback() -> None:
    model_api = QueueModelAPI()
    outputs: list[SessionOutput] = []

    async def collect(output: SessionOutput) -> None:
        outputs.append(output)

    session = DuplexNativeSession(
        session_id="native-barge-in",
        agent_session_factory=build_native_factory(model_api),
        output_listener=collect,
    )
    await session.start()
    for event in (
        StreamAudioStartEvent(session_id="provider", response_id="response-1"),
        StreamAudioDeltaEvent(
            session_id="provider", response_id="response-1", delta=b"\x00\x40"
        ),
    ):
        await model_api.queue.put(event)
    await wait_until(lambda: session.media_port.realtime_playback_active)

    await model_api.queue.put(
        StreamTranscriptionStartEvent(session_id="provider", item_id="q2")
    )
    await wait_until(lambda: model_api.response_cancels == 1)

    assert session.media_port.realtime_playback_active is False
    interrupted = [
        output.data
        for output in outputs
        if isinstance(output.data, NativeVoiceEvent)
        and output.data.event_type == "voice.interrupted"
    ]
    assert len(interrupted) == 1
    assert interrupted[0].payload == {"reason": "barge_in"}

    audio_count = sum(isinstance(output.data, bytes) for output in outputs)
    await model_api.queue.put(
        StreamAudioDeltaEvent(
            session_id="provider", response_id="response-1", delta=b"\x00\x20"
        )
    )
    await wait_until(model_api.queue.empty)
    await asyncio.sleep(0)
    assert sum(isinstance(output.data, bytes) for output in outputs) == audio_count

    # A different response supersedes a missing response.canceled ACK.
    for event in (
        StreamAudioStartEvent(session_id="provider", response_id="response-2"),
        StreamAudioDeltaEvent(
            session_id="provider", response_id="response-2", delta=b"\x00\x10"
        ),
    ):
        await model_api.queue.put(event)
    await wait_until(
        lambda: sum(isinstance(output.data, bytes) for output in outputs)
        == audio_count + 1
    )
    assert session.media_port.realtime_playback_active is True

    # A late ACK belongs to response-1 and must not clear response-2 playback.
    await model_api.queue.put(
        StreamResponseCanceledEvent(
            session_id="provider", provider_event_id="event-late"
        )
    )
    await asyncio.sleep(0)
    assert session.media_port.realtime_playback_active is True

    await session.close()


@pytest.mark.asyncio
async def test_native_barge_in_after_provider_done_only_clears_browser_playback() -> (
    None
):
    model_api = QueueModelAPI()
    outputs: list[SessionOutput] = []

    async def collect(output: SessionOutput) -> None:
        outputs.append(output)

    session = DuplexNativeSession(
        session_id="native-playback-only-barge-in",
        agent_session_factory=build_native_factory(model_api),
        output_listener=collect,
    )
    await session.start()
    for event in (
        StreamAudioStartEvent(session_id="provider", response_id="response-1"),
        StreamAudioDeltaEvent(
            session_id="provider", response_id="response-1", delta=b"\x00\x40"
        ),
        StreamAudioDoneEvent(session_id="provider", response_id="response-1"),
    ):
        await model_api.queue.put(event)
    await wait_until(model_api.queue.empty)
    await asyncio.sleep(0)

    await model_api.queue.put(
        StreamTranscriptionStartEvent(session_id="provider", item_id="q2")
    )
    await wait_until(
        lambda: any(
            isinstance(output.data, NativeVoiceEvent)
            and output.data.event_type == "voice.interrupted"
            for output in outputs
        )
    )

    assert model_api.response_cancels == 0
    assert session.media_port.realtime_playback_active is False

    audio_count = sum(isinstance(output.data, bytes) for output in outputs)
    for event in (
        StreamAudioStartEvent(session_id="provider", response_id="response-2"),
        StreamAudioDeltaEvent(
            session_id="provider", response_id="response-2", delta=b"\x00\x20"
        ),
        StreamAudioDoneEvent(session_id="provider", response_id="response-2"),
    ):
        await model_api.queue.put(event)
    await wait_until(
        lambda: sum(isinstance(output.data, bytes) for output in outputs)
        == audio_count + 1
    )

    await session.on_playback_ended()
    assert session.agent_session._reply_idle.is_set()
    await session.close()


@pytest.mark.asyncio
async def test_gateway_selects_native_profile_and_rejects_text_capability() -> None:
    model_api = QueueModelAPI()
    session = WebSocketAgentSession(
        runtime_profile="duplex_native",
        native_agent_session_factory=build_native_factory(model_api),
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="native-text",
            command="agent.run",
            payload={"query": "hello", "message_id": "agent-1"},
        ),
    )
    rejected = await session._outbound_queue.get()
    assert rejected["error"]["code"] == "UNSUPPORTED_CAPABILITY"

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="native-start",
            command="voice.start",
            payload={},
        ),
    )
    started = await session._outbound_queue.get()
    assert started["ok"] is True
    assert started["payload"]["output_format"] == "f32le"
    assert model_api.started is True

    await session.stop()


@pytest.mark.asyncio
async def test_gateway_restarts_native_runtime_after_voice_stop() -> None:
    model_apis: list[QueueModelAPI] = []

    def build_fresh_native_session(**kwargs: object) -> DuplexAgentSession:
        model_api = QueueModelAPI()
        model_apis.append(model_api)
        return build_native_factory(model_api)(**kwargs)

    session = WebSocketAgentSession(
        runtime_profile="duplex_native",
        native_agent_session_factory=build_fresh_native_session,
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="native-start-1",
            command="voice.start",
            payload={},
        ),
    )
    first_started = await session._outbound_queue.get()
    first_runtime = session._runtime
    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="native-stop",
            command="voice.stop",
            payload={},
        ),
    )
    stopped = await session._outbound_queue.get()
    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="native-start-2",
            command="voice.start",
            payload={},
        ),
    )
    second_started = await session._outbound_queue.get()

    assert first_started["ok"] is True
    assert stopped["ok"] is True
    assert second_started["ok"] is True
    assert session._runtime is not first_runtime
    assert len(model_apis) == 2
    assert model_apis[0].closed is True
    assert model_apis[1].started is True

    await session.feed_voice_audio(b"\x01\x00")
    assert isinstance(model_apis[1].submissions[0], AudioChunkInput)

    await session.stop()
    assert model_apis[1].closed is True


@pytest.mark.asyncio
async def test_gateway_restarts_native_runtime_after_provider_failure() -> None:
    model_apis: list[QueueModelAPI] = []

    def build_fresh_native_session(**kwargs: object) -> DuplexAgentSession:
        model_api = QueueModelAPI()
        model_apis.append(model_api)
        return build_native_factory(model_api)(**kwargs)

    session = WebSocketAgentSession(
        runtime_profile="duplex_native",
        native_agent_session_factory=build_fresh_native_session,
    )
    await session.start_voice()
    first_runtime = session._runtime
    await session.open_voice_microphone()
    listening = await session._outbound_queue.get()
    assert listening["type"] == "voice.phase"

    await model_apis[0].queue.put(RuntimeError("provider boom"))
    assert isinstance(first_runtime, DuplexNativeSession)
    assert first_runtime.run_task is not None
    await asyncio.gather(first_runtime.run_task, return_exceptions=True)
    failure = await asyncio.wait_for(session._outbound_queue.get(), timeout=1)
    assert failure["error"]["code"] == "AGENT_RUNTIME_FAILED"
    await asyncio.sleep(0)
    assert session._outbound_queue.empty()

    await session.start_voice()
    assert session._runtime is not first_runtime
    assert len(model_apis) == 2
    assert model_apis[1].started is True

    await session.stop()
    assert model_apis[1].closed is True


@pytest.mark.asyncio
async def test_gateway_reset_selects_exactly_one_runtime_selector() -> None:
    model_api = QueueModelAPI()
    session = WebSocketAgentSession(
        native_agent_session_factory=build_native_factory(model_api),
    )

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="reset-native",
            command="session.reset",
            payload={"runtime_profile": "duplex_native"},
        ),
    )
    reset = await session._outbound_queue.get()
    assert reset["payload"]["runtime_profile"] == "duplex_native"
    assert reset["payload"]["capabilities"]["native_audio_output"] is True

    await handle_client_command(
        session,
        ClientCommandEnvelope(
            v=PROTOCOL_VERSION,
            kind="command",
            command_id="reset-conflict",
            command="session.reset",
            payload={"agent_mode": "react", "runtime_profile": "react_s2s"},
        ),
    )
    conflict = await session._outbound_queue.get()
    assert conflict["error"]["code"] == "INVALID_PAYLOAD"

    await session.stop()


def build_async_compat_factory(model_api: QueueModelAPI):
    def factory(**kwargs: object) -> DuplexAgentSession:
        return DuplexAgentSession(
            model_api=model_api,  # type: ignore[arg-type]
            tools=(),
            task_manager=kwargs["task_manager"],  # type: ignore[arg-type]
            tool_call_mode="async",
            config=DuplexConfig(),
            context_diagnostics=False,
            async_compat=DuplexAsyncCompatConfig(),
            media_port=kwargs["media_port"],  # type: ignore[arg-type]
            model_event_observer=kwargs["model_event_observer"],  # type: ignore[arg-type]
            task_event_observer=kwargs["task_event_observer"],  # type: ignore[arg-type]
        )

    return factory


@pytest.mark.asyncio
async def test_native_synthetic_transcription_does_not_create_turn() -> None:
    model_api = QueueModelAPI()
    outputs: list[SessionOutput] = []

    async def collect(output: SessionOutput) -> None:
        outputs.append(output)

    session = DuplexNativeSession(
        session_id="native-synthetic",
        agent_session_factory=build_async_compat_factory(model_api),
        output_listener=collect,
    )
    await session.start()
    scheduler = session.agent_session._backfill_scheduler
    assert scheduler is not None
    scheduler._synthetic_pending = True

    for event in (
        StreamTranscriptionStartEvent(session_id="provider", item_id="trigger-1"),
        StreamTranscriptionDeltaEvent(
            session_id="provider", item_id="trigger-1", delta="结果"
        ),
        StreamTranscriptionDoneEvent(
            session_id="provider", item_id="trigger-1", transcript="结果已返回"
        ),
        StreamTranscriptionStartEvent(session_id="provider", item_id="q1"),
        StreamTranscriptionDoneEvent(
            session_id="provider", item_id="q1", transcript="你好"
        ),
        StreamAudioDoneEvent(session_id="provider", item_id="q1"),
    ):
        await model_api.queue.put(event)

    # Only the real question produces outputs: phase listening, asr final,
    # phase processing. The synthetic trigger transcription must not surface.
    await wait_for_outputs(outputs, 3)

    assert {output.turn_id for output in outputs} == {"native-turn-q1"}
    serialized = [str(output.data) for output in outputs]
    assert not any("trigger-1" in entry for entry in serialized)
    assert not any("结果已返回" in entry for entry in serialized)
    await session.close()


@pytest.mark.asyncio
async def test_native_projects_multi_task_activation_to_one_output_run() -> None:
    model_api = QueueModelAPI()
    outputs: list[SessionOutput] = []

    async def collect(output: SessionOutput) -> None:
        outputs.append(output)

    session = DuplexNativeSession(
        session_id="native-correlation",
        agent_session_factory=build_native_factory(model_api),
        output_listener=collect,
    )
    session._question_turns.update({"q1": "turn-1", "q2": "turn-2"})
    session._observe_backfill_activation(
        BackfillActivation(
            activation_id="activation-1",
            question_ids=("q1", "q2"),
            task_ids=("task-a", "task-b"),
        )
    )

    await session._observe_model_event(
        StreamTextDeltaEvent(
            session_id="provider",
            response_id="provider-response",
            delta="结果",
        )
    )
    await session._observe_model_event(
        StreamTextDoneEvent(
            session_id="provider",
            response_id="provider-response",
            text="结果",
        )
    )

    agent_outputs = [
        output
        for output in outputs
        if isinstance(
            output.data,
            (
                AgentOutTextStartEvent,
                AgentOutTextDeltaEvent,
                AgentOutTextDoneEvent,
            ),
        )
    ]
    assert len(agent_outputs) == 3
    assert all(
        output.metadata["conversation_turn_id"] is None
        and output.metadata["output_run_id"] == "activation-1"
        and output.metadata["triggering_task_ids"] == ("task-a", "task-b")
        for output in agent_outputs
    )

    session._question_turns["q3"] = "turn-1"
    session._observe_backfill_activation(
        BackfillActivation(
            activation_id="activation-2",
            question_ids=("q1", "q3"),
            task_ids=("task-c", "task-d"),
        )
    )
    await session._observe_model_event(
        StreamTextDoneEvent(session_id="provider", text="同轮结果")
    )
    same_turn_outputs = outputs[-2:]
    assert all(
        output.metadata["conversation_turn_id"] == "turn-1"
        and output.metadata["output_run_id"] == "activation-2"
        and output.metadata["triggering_task_ids"] == ("task-c", "task-d")
        for output in same_turn_outputs
    )

    await session.close()
