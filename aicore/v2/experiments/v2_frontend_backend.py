from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, model_validator

from aicore.core.event import EventBase
from aicore.events.task import is_task_event
from aicore.runtime.task import TaskCancelOutcome, TaskManager
from aicore.session import SessionOutput
from aicore.v2.experiments.latency_trace import trace_latency
from aicore.v2.experiments.v2_agent_session import (
    EventContext,
    QueueUserDataSource,
    QueuedUserInput,
    SessionBoundAgent,
    V2AgentSession,
)
from aicore.v2.experiments.v2_frontend_utils import maybe_await
from aicore.v2.experiments.v2_frontend_voice_protocol import (
    BrowserVoiceSession,
    ExternalAgentSpeechSink,
    VoiceTextQueryCapability,
)
from aicore.v2.experiments.duplex_native_session import (
    DuplexNativeSession,
    NativeAgentSessionFactory,
    NativeVoiceEvent,
    default_native_agent_session_factory,
)
from aicore.v2.experiments.v2_runtime_profiles import (
    RuntimeProfile,
    agent_mode_for,
    capabilities_for,
    profile_for_agent_mode,
)

_CLIENT_COMMANDS_PATH = (
    Path(__file__).with_name("v2_frontend") / "protocol" / "client_commands.json"
)


def _load_client_command_protocol() -> dict[str, Any]:
    with _CLIENT_COMMANDS_PATH.open(encoding="utf-8") as file:
        protocol = json.load(file)
    if not isinstance(protocol, dict):
        raise RuntimeError("Client command protocol descriptor must be a JSON object.")
    return protocol


CLIENT_COMMAND_PROTOCOL = _load_client_command_protocol()
PROTOCOL_VERSION = int(CLIENT_COMMAND_PROTOCOL["protocol_version"])
_CLIENT_COMMANDS = CLIENT_COMMAND_PROTOCOL["commands"]
SUPPORTED_COMMANDS = frozenset(str(item["command"]) for item in _CLIENT_COMMANDS)
_COMMAND_SUCCESS_STATUSES = {
    str(item["command"]): str(item["success_status"]) for item in _CLIENT_COMMANDS
}
logger = logging.getLogger(__name__)

ConsoleEventEnvelope = dict[str, Any]
ServerMessage = dict[str, Any]
OutboundMessage = ServerMessage | bytes | None
VoiceBridgeFactory = Callable[..., BrowserVoiceSession]
CommandPayload = BaseModel | None
type AgentMode = Literal["react", "plact"]
DEFAULT_AGENT_MODE: AgentMode = "react"
DEFAULT_RUNTIME_PROFILE: RuntimeProfile = "react_s2s"
CHAT_ID = "v2-frontend-agent"
CommandHandler = Callable[
    ["WebSocketAgentSession", CommandPayload],
    Awaitable[dict[str, Any]],
]


class UnsupportedCapabilityError(RuntimeError):
    pass


class ClientCommandEnvelope(BaseModel):
    v: int
    kind: str
    command_id: str = Field(..., min_length=1)
    command: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentRunCommandPayload(BaseModel):
    query: str = Field(..., min_length=1)
    message_id: str = Field(
        ...,
        min_length=1,
        description="Frontend assistant message id for this turn.",
    )


class TaskCancelCommandPayload(BaseModel):
    task_id: str = Field(..., min_length=1)


class VoiceTextQueryCommandPayload(BaseModel):
    query: str = Field(..., min_length=1)


class SessionResetCommandPayload(BaseModel):
    agent_mode: AgentMode | None = None
    runtime_profile: RuntimeProfile | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> SessionResetCommandPayload:
        if (self.agent_mode is None) == (self.runtime_profile is None):
            raise ValueError("exactly one of agent_mode or runtime_profile is required")
        return self


@dataclass(frozen=True)
class CommandHandlerSpec:
    command: str
    payload_model: type[BaseModel] | None
    handler: CommandHandler
    success_status: str
    voice_error: bool = False


@dataclass(frozen=True)
class FrontendEventCorrelation:
    conversation_turn_id: str | None = None
    output_run_id: str | None = None
    triggering_task_ids: tuple[str, ...] = ()


def serialize_console_event(
    event: EventBase,
    *,
    message_id: str | None = None,
    origin_message_id: str | None = None,
    source_task_id: str | None = None,
    round: int | None = None,
    correlation: FrontendEventCorrelation | None = None,
) -> ConsoleEventEnvelope:
    payload = event.model_dump(mode="json")
    resolved_correlation = correlation or FrontendEventCorrelation()
    payload["conversation_turn_id"] = resolved_correlation.conversation_turn_id
    payload["output_run_id"] = resolved_correlation.output_run_id
    payload["triggering_task_ids"] = list(resolved_correlation.triggering_task_ids)
    if message_id is not None:
        payload["message_id"] = message_id
    if origin_message_id is not None:
        payload["origin_message_id"] = origin_message_id
    if source_task_id is not None:
        payload["source_task_id"] = source_task_id
    if round is not None:
        payload["round"] = round
    return {
        "id": str(payload["event_id"]),
        "type": str(payload["type"]),
        "timestamp": str(payload["timestamp"]),
        "payload": payload,
    }


def _server_time() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validation_message(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )


def _exception_summary(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup):
        summaries = [_exception_summary(child) for child in error.exceptions[:3]]
        remaining = len(error.exceptions) - len(summaries)
        suffix = f"; +{remaining} more" if remaining > 0 else ""
        return f"{type(error).__name__}: {'; '.join(summaries)}{suffix}"

    return f"{type(error).__name__}: {error}"


def hello_message(
    *,
    connection_id: str,
    session_id: str,
    generation: int,
    runtime_profile: RuntimeProfile | None = None,
    capabilities: dict[str, Any] | None = None,
) -> ServerMessage:
    message: ServerMessage = {
        "v": PROTOCOL_VERSION,
        "kind": "hello",
        "connection_id": connection_id,
        "session_id": session_id,
        "generation": generation,
        "server_time": _server_time(),
    }
    if runtime_profile is not None:
        message["runtime_profile"] = runtime_profile
    if capabilities is not None:
        message["capabilities"] = capabilities
    return message


def voice_message(
    session_id: str,
    generation: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> ServerMessage:
    return {
        "v": 1,
        "kind": "voice",
        "session_id": session_id,
        "generation": generation,
        "type": event_type,
        "payload": payload or {},
    }


def ack_message(
    *,
    command_id: str,
    command: str,
    ok: bool,
    status: str,
    payload: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> ServerMessage:
    message: ServerMessage = {
        "v": PROTOCOL_VERSION,
        "kind": "ack",
        "command_id": command_id,
        "command": command,
        "ok": ok,
        "status": status,
        "server_time": _server_time(),
    }
    if payload is not None:
        message["payload"] = payload
    if error is not None:
        message["error"] = error
    return message


def error_payload(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
    }


def error_message(
    *,
    code: str,
    message: str,
    command_id: str | None = None,
    command: str | None = None,
    retryable: bool = False,
) -> ServerMessage:
    result: ServerMessage = {
        "v": PROTOCOL_VERSION,
        "kind": "error",
        "server_time": _server_time(),
        "error": error_payload(code, message, retryable=retryable),
    }
    if command_id is not None:
        result["command_id"] = command_id
    if command is not None:
        result["command"] = command
    return result


def event_message(
    *,
    session_id: str,
    generation: int,
    event: ConsoleEventEnvelope,
) -> ServerMessage:
    return {
        "v": PROTOCOL_VERSION,
        "kind": "event",
        "session_id": session_id,
        "generation": generation,
        "event": event,
    }


def _build_agent(task_manager: TaskManager, mode: AgentMode):
    from aicore.models.credentials import ModelName

    if mode == "plact":
        from aicore.v2.experiments.v2_frontend_plact_agent import (
            create_plact_frontend_agent,
        )

        return create_plact_frontend_agent(
            chat_id=CHAT_ID,
            model=ModelName.SEED_2_0_PRO_260215,
        )

    from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT
    from aicore.v2.experiments.react_agent_with_task_runner import (
        create_react_agent_with_task_runner,
    )
    from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
    from projects.mind.toolset.experiments.async_task_tools import get_async_task_tools

    tools = [
        *get_async_task_tools(CHAT_ID, task_manager),
        create_task_cancel_tool(task_manager=task_manager),
    ]
    return create_react_agent_with_task_runner(
        model=ModelName.SEED_2_0_PRO_260215,
        tools=tools,
        system_prompt=ASYNC_REACT_SYSTEM_PROMPT,
        max_turns=5,
    )


def _build_runner(
    *,
    user_data: QueueUserDataSource,
    agent: SessionBoundAgent,
    task_manager: TaskManager,
    client: Callable[[EventBase], None],
):
    from aicore.v2.agent_runner import AgentRunner

    return AgentRunner(
        user_data=user_data,
        agent=agent,
        task_manager=task_manager,
        client=client,
    )


def _build_voice_bridge(**kwargs: Any) -> Any:
    from aicore.v2.experiments.v2_frontend_voice import FrontendVoiceBridge

    return FrontendVoiceBridge(**kwargs)


def _build_duplex_voice_bridge(**kwargs: Any) -> Any:
    from aicore.v2.experiments.v2_frontend_duplex_voice import (
        DuplexFrontendVoiceBridge,
    )

    return DuplexFrontendVoiceBridge(**kwargs)


class WebSocketAgentSession:
    """Connection-local session whose agent instance survives across user turns."""

    def __init__(
        self,
        *,
        agent_factory: Callable[[TaskManager, AgentMode], Any] = _build_agent,
        runner_factory: Callable[..., Any] = _build_runner,
        voice_bridge_factory: VoiceBridgeFactory | None = None,
        runtime_profile: RuntimeProfile = DEFAULT_RUNTIME_PROFILE,
        native_agent_session_factory: NativeAgentSessionFactory = (
            default_native_agent_session_factory
        ),
        outbound_queue_size: int = 100,
    ) -> None:
        self._agent_factory = agent_factory
        self._runner_factory = runner_factory
        self._s2s_voice_bridge_factory = voice_bridge_factory or _build_voice_bridge
        self._duplex_voice_bridge_factory = (
            voice_bridge_factory or _build_duplex_voice_bridge
        )
        self._native_agent_session_factory = native_agent_session_factory
        self._default_voice_family: Literal["s2s", "duplex_shell"] = (
            "duplex_shell" if "duplex_shell" in runtime_profile else "s2s"
        )
        self._voice_bridge_factory = (
            self._duplex_voice_bridge_factory
            if self._default_voice_family == "duplex_shell"
            else self._s2s_voice_bridge_factory
        )
        self._outbound_queue: asyncio.Queue[OutboundMessage] = asyncio.Queue(
            maxsize=outbound_queue_size
        )
        self._start_lock = asyncio.Lock()
        self._voice_lifecycle_lock = asyncio.Lock()
        self.connection_id = f"conn-{uuid4()}"
        self.session_id = f"sess-{uuid4()}"
        self.generation = 1
        self.runtime_profile = runtime_profile
        self.agent_mode: AgentMode = agent_mode_for(runtime_profile)
        self.voice_bridge: BrowserVoiceSession | None = None
        self._voice_ready_payload: dict[str, Any] | None = None
        self._voice_turn_seq = 0
        self._reset_runtime()

    def _reset_runtime(self) -> None:
        if self.runtime_profile == "duplex_native":
            self._runtime = DuplexNativeSession(
                session_id=self.session_id,
                agent_session_factory=self._native_agent_session_factory,
                output_listener=self._emit_native_output,
            )
        else:
            self._runtime = V2AgentSession(
                agent_mode=self.agent_mode,
                agent_factory=self._agent_factory,
                runner_factory=self._runner_factory,
                on_input_dequeued=self._trace_input_dequeued,
                output_listener=self._emit_runtime_output,
            )
        self._traced_first_delta_message_ids: set[str] = set()

    @property
    def task_manager(self) -> TaskManager:
        return self._runtime.task_manager

    @property
    def user_data(self) -> QueueUserDataSource:
        if not isinstance(self._runtime, V2AgentSession):
            raise UnsupportedCapabilityError("Runtime profile has no text input queue")
        return self._runtime.user_data

    @property
    def _agent(self) -> SessionBoundAgent | None:
        return self._runtime.agent if isinstance(self._runtime, V2AgentSession) else None

    @_agent.setter
    def _agent(self, value: SessionBoundAgent | None) -> None:
        if not isinstance(self._runtime, V2AgentSession):
            raise UnsupportedCapabilityError("Runtime profile has no external Agent")
        self._runtime.agent = value

    @property
    def _runner_task(self) -> asyncio.Task[None] | None:
        return (
            self._runtime.runner_task
            if isinstance(self._runtime, V2AgentSession)
            else self._runtime.run_task
        )

    @_runner_task.setter
    def _runner_task(self, value: asyncio.Task[None] | None) -> None:
        if isinstance(self._runtime, V2AgentSession):
            self._runtime.runner_task = value
        else:
            self._runtime.run_task = value

    @property
    def capabilities(self) -> dict[str, Any]:
        return capabilities_for(self.runtime_profile)

    def _trace_input_dequeued(self, data: QueuedUserInput) -> None:
        trace_latency(
            "agent.input.dequeued",
            message_id=data.message_id,
            session_id=self.session_id,
            generation=self.generation,
        )

    async def send(self, message: ServerMessage) -> None:
        await self._outbound_queue.put(message)

    async def send_bytes(self, payload: bytes) -> None:
        await self._outbound_queue.put(payload)

    async def close_outbound(self) -> None:
        with suppress(asyncio.QueueFull):
            self._outbound_queue.put_nowait(None)

    async def write_to(self, websocket: WebSocket) -> None:
        while True:
            message = await self._outbound_queue.get()
            if message is None:
                return
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
                continue
            await websocket.send_json(message)

    def _emit_runtime_output(self, event: EventBase, context: EventContext) -> None:
        self._emit(event, context=context)

    async def _emit_native_output(self, output: SessionOutput) -> None:
        data = output.data
        if isinstance(data, bytes):
            await self.send_bytes(data)
            return
        if isinstance(data, NativeVoiceEvent):
            await self.send(
                voice_message(
                    self.session_id,
                    self.generation,
                    data.event_type,
                    data.payload,
                )
            )
            return
        if isinstance(data, EventBase):
            raw_task_ids = output.metadata.get("triggering_task_ids", ())
            triggering_task_ids = tuple(
                str(task_id)
                for task_id in raw_task_ids
                if isinstance(task_id, str) and task_id
            ) if isinstance(raw_task_ids, (list, tuple)) else ()
            self._emit(
                data,
                context=EventContext(
                    message_id=output.metadata.get("message_id"),
                    origin_message_id=output.turn_id,
                    source_task_id=output.metadata.get("source_task_id"),
                ),
                correlation=FrontendEventCorrelation(
                    conversation_turn_id=(
                        (
                            str(output.metadata["conversation_turn_id"])
                            if output.metadata["conversation_turn_id"] is not None
                            else None
                        )
                        if "conversation_turn_id" in output.metadata
                        else output.turn_id
                    ),
                    output_run_id=(
                        str(output.metadata["output_run_id"])
                        if output.metadata.get("output_run_id") is not None
                        else None
                    ),
                    triggering_task_ids=triggering_task_ids,
                ),
            )

    def _emit(
        self,
        event: EventBase,
        *,
        context: EventContext | None = None,
        correlation: FrontendEventCorrelation | None = None,
    ) -> None:
        if context is None:
            context = (
                self._agent.context_for(event)
                if self._agent is not None
                else EventContext()
            )
        if is_task_event(event):
            task = self.task_manager.get_task(event.task_id)
            origin_message_id = (
                str(task.metadata.get("origin_message_id"))
                if task is not None and task.metadata.get("origin_message_id")
                else None
            )
            if origin_message_id is not None:
                context = replace(
                    context,
                    origin_message_id=origin_message_id,
                )
        if correlation is None:
            if is_task_event(event):
                correlation = FrontendEventCorrelation(
                    conversation_turn_id=(
                        context.origin_message_id or context.message_id
                    ),
                )
            else:
                correlation = FrontendEventCorrelation(
                    conversation_turn_id=(
                        context.origin_message_id or context.message_id
                    ),
                    output_run_id=context.message_id,
                    triggering_task_ids=(
                        (context.source_task_id,)
                        if context.source_task_id is not None
                        else ()
                    ),
                )
        event_type = str(getattr(event, "type", ""))
        if (
            event_type == "agent.out.text.delta"
            and context.message_id is not None
            and context.message_id not in self._traced_first_delta_message_ids
        ):
            self._traced_first_delta_message_ids.add(context.message_id)
            trace_latency(
                "agent.first_delta",
                message_id=context.message_id,
                origin_message_id=context.origin_message_id,
                task_id=context.source_task_id,
                session_id=self.session_id,
                generation=self.generation,
            )
        if event_type == "task.cancelled":
            trace_latency(
                "task.cancelled",
                origin_message_id=context.origin_message_id,
                task_id=str(event.task_id),
                session_id=self.session_id,
                generation=self.generation,
            )
        bridge = self.voice_bridge
        if isinstance(bridge, ExternalAgentSpeechSink):
            try:
                bridge.on_agent_event(event, message_id=context.message_id)
            except Exception:
                logger.exception("Voice bridge failed to consume agent event.")

        envelope = serialize_console_event(
            event,
            message_id=context.message_id,
            origin_message_id=context.origin_message_id,
            source_task_id=context.source_task_id,
            round=context.round,
            correlation=correlation,
        )
        message = event_message(
            session_id=self.session_id,
            generation=self.generation,
            event=envelope,
        )
        try:
            self._outbound_queue.put_nowait(message)
        except asyncio.QueueFull:
            with suppress(asyncio.QueueFull):
                self._outbound_queue.put_nowait(
                    error_message(
                        code="BACKPRESSURE_OVERFLOW",
                        message="WebSocket outbound queue is full; dropping agent event.",
                        retryable=True,
                    )
                )

    def _on_runner_done(self, runner_task: asyncio.Task[None]) -> None:
        if runner_task.cancelled():
            return

        error = runner_task.exception()
        if error is None:
            return

        summary = _exception_summary(error)
        logger.exception("WebSocket agent runner failed: %s", summary, exc_info=error)
        with suppress(asyncio.QueueFull):
            self._outbound_queue.put_nowait(
                error_message(
                    code="AGENT_RUNTIME_FAILED",
                    message=f"Agent runtime failed: {summary}",
                    retryable=True,
                )
            )

    async def _ensure_started(self) -> None:
        if not isinstance(self._runtime, V2AgentSession):
            raise UnsupportedCapabilityError(
                "Duplex native profile accepts realtime audio, not agent.run"
            )
        previous = self._runner_task
        await self._runtime.start()
        if self._runner_task is not previous and self._runner_task is not None:
            self._runner_task.add_done_callback(self._on_runner_done)

    async def submit(self, query: str, *, message_id: str) -> None:
        await self._ensure_started()
        await self._runtime.submit(query, message_id=message_id)
        trace_latency(
            "agent.input.enqueued",
            message_id=message_id,
            session_id=self.session_id,
            generation=self.generation,
        )

    def _create_voice_bridge(self) -> BrowserVoiceSession:
        if isinstance(self._runtime, DuplexNativeSession):
            return self._runtime
        factory = (
            self._duplex_voice_bridge_factory
            if "duplex_shell" in self.runtime_profile
            else self._s2s_voice_bridge_factory
        )
        return factory(
            submit_text=self.prepare_voice_text,
            commit_text=self.commit_voice_text,
            send_json=self.send,
            send_audio=self.send_bytes,
            session_id=lambda: self.session_id,
            generation=lambda: self.generation,
        )

    def _prepare_voice_output_locked(self) -> BrowserVoiceSession:
        if (
            isinstance(self._runtime, DuplexNativeSession)
            and self._runtime.restart_required
        ):
            self.voice_bridge = None
            self._voice_ready_payload = None
            self._reset_runtime()
        if self.voice_bridge is None:
            self.voice_bridge = self._create_voice_bridge()
        return self.voice_bridge

    async def prepare_voice_output(self) -> BrowserVoiceSession:
        async with self._voice_lifecycle_lock:
            return self._prepare_voice_output_locked()

    async def start_voice(self) -> dict[str, Any]:
        async with self._voice_lifecycle_lock:
            _, ready_payload = await self._start_voice_locked()
            return ready_payload

    async def _start_voice_locked(
        self,
    ) -> tuple[BrowserVoiceSession, dict[str, Any]]:
        bridge = self._prepare_voice_output_locked()
        previous_runner = (
            self._runtime.run_task
            if isinstance(self._runtime, DuplexNativeSession)
            else None
        )
        try:
            ready_payload = await bridge.start()
            if isinstance(self._runtime, DuplexNativeSession):
                run_task = self._runtime.run_task
                if run_task is not None and run_task is not previous_runner:
                    run_task.add_done_callback(self._on_runner_done)
            self._voice_ready_payload = dict(ready_payload or {})
        except Exception:
            if self.voice_bridge is bridge:
                self.voice_bridge = None
                self._voice_ready_payload = None
            raise

        return bridge, self._voice_ready_payload

    async def prepare_voice_text(self, text: str) -> dict[str, str]:
        clean = text.strip()
        if not clean:
            raise ValueError("Voice text must not be empty")

        self._voice_turn_seq += 1
        turn_number = self._voice_turn_seq
        return {
            "text": clean,
            "turn_id": f"voice-turn-{turn_number}",
            "user_message_id": f"voice-user-{turn_number}",
            "assistant_message_id": f"voice-assistant-{turn_number}",
        }

    async def commit_voice_text(self, payload: dict[str, str]) -> None:
        await self.submit(payload["text"], message_id=payload["assistant_message_id"])

    async def submit_voice_text(self, text: str) -> dict[str, str]:
        payload = await self.prepare_voice_text(text)
        await self.commit_voice_text(payload)
        return payload

    async def submit_voice_text_query(self, query: str) -> dict[str, Any]:
        clean = query.strip()
        if not clean:
            raise ValueError("Voice text query must not be empty")

        async with self._voice_lifecycle_lock:
            bridge, _ = await self._start_voice_locked()
            if not isinstance(bridge, VoiceTextQueryCapability):
                raise UnsupportedCapabilityError(
                    "Voice session does not support text query submission"
                )

            await bridge.submit_text_query(clean)
            return {
                "session_id": self.session_id,
                "generation": self.generation,
            }

    async def open_voice_microphone(self) -> None:
        async with self._voice_lifecycle_lock:
            bridge, _ = await self._start_voice_locked()
            await bridge.open_microphone()

    async def on_voice_playback_ended(self) -> None:
        async with self._voice_lifecycle_lock:
            bridge = self.voice_bridge
            if bridge is None:
                return
            await bridge.on_playback_ended()

    async def close_voice_microphone(self) -> None:
        async with self._voice_lifecycle_lock:
            bridge = self.voice_bridge
            if bridge is None:
                return
            await bridge.close_microphone()

    async def feed_voice_audio(self, chunk: bytes) -> None:
        if self.voice_bridge is None:
            return
        await self.voice_bridge.feed_audio(chunk)

    async def stop_voice(self) -> None:
        async with self._voice_lifecycle_lock:
            await self._stop_voice_locked()

    async def _stop_voice_locked(self) -> None:
        bridge = self.voice_bridge
        if bridge is None:
            self._voice_ready_payload = None
            return

        await bridge.stop()
        if self.voice_bridge is bridge:
            self.voice_bridge = None
            self._voice_ready_payload = None

    async def _cleanup_voice_for_shutdown(self) -> None:
        async with self._voice_lifecycle_lock:
            bridge = self.voice_bridge
            try:
                await self._stop_voice_locked()
            except Exception:
                logger.exception(
                    "Voice bridge cleanup failed during WebSocket session shutdown."
                )
                if self.voice_bridge is bridge:
                    self.voice_bridge = None
                    self._voice_ready_payload = None

    async def stop(self) -> None:
        await self._cleanup_voice_for_shutdown()
        await self._runtime.close()

    async def reset(
        self,
        agent_mode: AgentMode | None = None,
        runtime_profile: RuntimeProfile | None = None,
    ) -> dict[str, Any]:
        await self.stop()
        if runtime_profile is not None:
            self.runtime_profile = runtime_profile
            self.agent_mode = agent_mode_for(runtime_profile)
        elif agent_mode is not None:
            self.agent_mode = agent_mode
            self.runtime_profile = profile_for_agent_mode(
                agent_mode,
                voice_family=self._default_voice_family,
            )
        else:
            raise ValueError("agent_mode or runtime_profile is required")
        self.session_id = f"sess-{uuid4()}"
        self.generation += 1
        self._voice_turn_seq = 0
        self._reset_runtime()
        return {
            "session_id": self.session_id,
            "generation": self.generation,
            "agent_mode": self.agent_mode,
            "runtime_profile": self.runtime_profile,
            "capabilities": self.capabilities,
        }

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        return self.task_manager.cancel_task(task_id)


COMMAND_HANDLERS: dict[str, CommandHandlerSpec] = {}


def _register_command(
    command: str,
    *,
    payload_model: type[BaseModel] | None = None,
    voice_error: bool = False,
):
    def decorator(handler: CommandHandler) -> CommandHandler:
        COMMAND_HANDLERS[command] = CommandHandlerSpec(
            command=command,
            payload_model=payload_model,
            handler=handler,
            success_status=_COMMAND_SUCCESS_STATUSES[command],
            voice_error=voice_error,
        )
        return handler
    return decorator


@_register_command("agent.run", payload_model=AgentRunCommandPayload)
async def _handle_agent_run(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    assert isinstance(payload, AgentRunCommandPayload)
    await session.prepare_voice_output()
    await session.submit(payload.query, message_id=payload.message_id)
    return {
        "message_id": payload.message_id,
        "session_id": session.session_id,
        "generation": session.generation,
    }


@_register_command("task.cancel", payload_model=TaskCancelCommandPayload)
async def _handle_task_cancel(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    assert isinstance(payload, TaskCancelCommandPayload)
    outcome = session.cancel_task(payload.task_id)
    return {
        "task_id": payload.task_id,
        "outcome": outcome.model_dump(mode="json"),
    }


@_register_command("session.reset", payload_model=SessionResetCommandPayload)
async def _handle_session_reset(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    assert isinstance(payload, SessionResetCommandPayload)
    return await session.reset(
        agent_mode=payload.agent_mode,
        runtime_profile=payload.runtime_profile,
    )


@_register_command("voice.start", voice_error=True)
async def _handle_voice_start(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    return await session.start_voice()


@_register_command("voice.stop", voice_error=True)
async def _handle_voice_stop(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    await session.stop_voice()
    return {}


@_register_command("voice.text.query", payload_model=VoiceTextQueryCommandPayload, voice_error=True)
async def _handle_voice_text_query(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    assert isinstance(payload, VoiceTextQueryCommandPayload)
    return await session.submit_voice_text_query(payload.query)


@_register_command("voice.mic.open", voice_error=True)
async def _handle_voice_mic_open(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    await session.open_voice_microphone()
    return {}


@_register_command("voice.mic.close", voice_error=True)
async def _handle_voice_mic_close(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    await session.close_voice_microphone()
    return {}


@_register_command("voice.playback.ended", voice_error=True)
async def _handle_voice_playback_ended(
    session: WebSocketAgentSession, payload: CommandPayload,
) -> dict[str, Any]:
    await session.on_voice_playback_ended()
    return {}

if set(COMMAND_HANDLERS) != SUPPORTED_COMMANDS:
    missing_commands = sorted(SUPPORTED_COMMANDS - set(COMMAND_HANDLERS))
    extra_commands = sorted(set(COMMAND_HANDLERS) - SUPPORTED_COMMANDS)
    raise RuntimeError(
        "Client command handler table does not match protocol descriptor: "
        f"missing={missing_commands}, extra={extra_commands}"
    )


app = FastAPI(
    title="v2 Agent Frontend Demo Backend",
    description="WebSocket bridge for the standalone v2 agent console prototype.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.frontend_session_factory = WebSocketAgentSession


def _command_validation_context(raw: object) -> tuple[str | None, str | None]:
    if not isinstance(raw, dict):
        return None, None
    command_id = raw.get("command_id")
    command = raw.get("command")
    return (
        command_id if isinstance(command_id, str) else None,
        command if isinstance(command, str) else None,
    )


async def parse_client_command(
    raw: str,
    *,
    session: WebSocketAgentSession,
) -> ClientCommandEnvelope | None:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        await session.send(
            error_message(
                code="INVALID_JSON",
                message="Client command must be valid JSON.",
            )
        )
        return None

    command_id, command = _command_validation_context(decoded)
    try:
        return ClientCommandEnvelope.model_validate(decoded)
    except ValidationError as error:
        message = _validation_message(error)
        if command_id is not None and command is not None:
            await session.send(
                ack_message(
                    command_id=command_id,
                    command=command,
                    ok=False,
                    status="rejected",
                    error=error_payload("INVALID_PAYLOAD", message),
                )
            )
        else:
            await session.send(
                error_message(
                    code="INVALID_PAYLOAD",
                    message=message,
                    command_id=command_id,
                    command=command,
                )
            )
        return None


def _payload_error(command: ClientCommandEnvelope, error: ValidationError) -> ServerMessage:
    return ack_message(
        command_id=command.command_id,
        command=command.command,
        ok=False,
        status="rejected",
        error=error_payload("INVALID_PAYLOAD", _validation_message(error)),
    )


async def _reject_voice_command(
    session: WebSocketAgentSession,
    command: ClientCommandEnvelope,
    error: Exception,
) -> None:
    error_code = (
        "UNSUPPORTED_CAPABILITY"
        if isinstance(error, UnsupportedCapabilityError)
        else "VOICE_COMMAND_FAILED"
    )
    await session.send(
        ack_message(
            command_id=command.command_id,
            command=command.command,
            ok=False,
            status="rejected",
            error=error_payload(
                error_code,
                f"Voice command failed: {_exception_summary(error)}",
            ),
        )
    )


async def handle_client_command(
    session: WebSocketAgentSession,
    command: ClientCommandEnvelope,
) -> None:
    raw_message_id = command.payload.get("message_id")
    raw_task_id = command.payload.get("task_id")
    trace_latency(
        "ws.command.received",
        command_id=command.command_id,
        command=command.command,
        message_id=raw_message_id if isinstance(raw_message_id, str) else None,
        task_id=raw_task_id if isinstance(raw_task_id, str) else None,
        session_id=session.session_id,
        generation=session.generation,
    )
    if command.v != PROTOCOL_VERSION:
        await session.send(
            ack_message(
                command_id=command.command_id,
                command=command.command,
                ok=False,
                status="rejected",
                error=error_payload(
                    "UNSUPPORTED_VERSION",
                    f"Unsupported protocol version: {command.v}.",
                ),
            )
        )
        return

    if command.kind != "command":
        await session.send(
            ack_message(
                command_id=command.command_id,
                command=command.command,
                ok=False,
                status="rejected",
                error=error_payload("INVALID_PAYLOAD", "kind must be 'command'."),
            )
        )
        return

    spec = COMMAND_HANDLERS.get(command.command)
    if spec is None:
        await session.send(
            ack_message(
                command_id=command.command_id,
                command=command.command,
                ok=False,
                status="rejected",
                error=error_payload("UNKNOWN_COMMAND", f"Unknown command: {command.command}."),
            )
        )
        return

    payload: CommandPayload = None
    if spec.payload_model is not None:
        try:
            payload = spec.payload_model.model_validate(command.payload)
        except ValidationError as error:
            await session.send(_payload_error(command, error))
            return

    if isinstance(payload, TaskCancelCommandPayload):
        trace_latency(
            "task.cancel.requested",
            command_id=command.command_id,
            command=command.command,
            task_id=payload.task_id,
            session_id=session.session_id,
            generation=session.generation,
        )

    try:
        result = await spec.handler(session, payload)
    except Exception as error:
        if isinstance(error, UnsupportedCapabilityError):
            await session.send(
                ack_message(
                    command_id=command.command_id,
                    command=command.command,
                    ok=False,
                    status="rejected",
                    error=error_payload("UNSUPPORTED_CAPABILITY", str(error)),
                )
            )
            return
        if spec.voice_error:
            await _reject_voice_command(session, command, error)
            return
        raise

    await session.send(
        ack_message(
            command_id=command.command_id,
            command=command.command,
            ok=True,
            status=spec.success_status,
            payload=result,
        )
    )


@app.websocket("/v2/frontend/ws")
async def frontend_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    session_factory = app.state.frontend_session_factory
    session = session_factory()
    writer_task = asyncio.create_task(session.write_to(websocket))
    await session.send(
        hello_message(
            connection_id=session.connection_id,
            session_id=session.session_id,
            generation=session.generation,
            runtime_profile=session.runtime_profile,
            capabilities=session.capabilities,
        )
    )

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            raw = message.get("text")
            if raw is not None:
                command = await parse_client_command(raw, session=session)
                if command is not None:
                    await handle_client_command(session, command)
                continue

            chunk = message.get("bytes")
            if chunk is not None:
                await session.feed_voice_audio(chunk)
    except WebSocketDisconnect:
        pass
    finally:
        await session.stop()
        await session.close_outbound()
        writer_task.cancel()
        with suppress(asyncio.CancelledError):
            await writer_task


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8799)
