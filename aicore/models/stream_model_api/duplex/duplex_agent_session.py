"""Duplex Agent runtime built on the public ``StreamModelAPI`` boundary.

``DuplexAgentSession`` is the single consumer of ``model_api.events()``. It
owns audio I/O, function-call grouping and execution, TaskManager integration,
and the optional async placeholder/backfill compatibility policy. Raw Duplex
event dictionaries never cross into this module.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from aicore.events.task import (
    TaskCancelledEvent,
    TaskEvent,
    TaskFailureEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.models.stream_model_api.events import (
    StreamAudioDeltaEvent,
    StreamAudioDoneEvent,
    StreamAudioStartEvent,
    StreamModelErrorEvent,
    StreamModelEvent,
    StreamResponseCanceledEvent,
    StreamToolCallEvent,
    StreamTranscriptionDeltaEvent,
    StreamTranscriptionDoneEvent,
    StreamTranscriptionStartEvent,
)
from aicore.models.stream_model_api.inputs import (
    AudioChunkInput,
    AudioCommitInput,
    ContextItemRetrieveInput,
    ContextItemUpdateInput,
    ToolResultBatchInput,
    ToolResultInput,
)
from aicore.models.stream_model_api.protocol import ToolCallMode
from aicore.models.stream_model_api.duplex.duplex_stream_model_api import (
    DuplexStreamModelAPI,
)
from aicore.runtime.task import TaskManager
from aicore.runtime.task import TaskProgress, TaskSuccess
from aicore.tools.protocol import (
    TaskToolProtocolGeneral,
    validate_tool_arguments,
)
from aicore.tools.task_worker import bind_task_tool_worker
from aicore.utils.misc import model_to_dict
from aicore.utils.nl_repr import nl_repr
from aicore.v2.tools.async_task import AsyncTaskReceipt

from .async_backfill import (
    BackfillActivation,
    DuplexAsyncBackfillScheduler,
    DuplexAsyncCompatConfig,
)
from .config import DuplexConfig
from .diagnostics import print_duplex_task_event
from .local_audio import DuplexLocalAudio
from .media_port import DuplexMediaPort


FILE_CHUNK = 640
DEFAULT_OUTPUT_AUDIO_PATH = Path("output.pcm")
logger = logging.getLogger(__name__)

MicMode = Literal["space_gate", "continuous"]
_INLINE_CONTROL_TOOL_NAMES = {"cancel_task"}
_DUPLEX_METADATA_PREFIX = "duplex_"


@dataclass(slots=True)
class _PendingToolGroup:
    expected_size: int
    question_id: str | None = None
    events: list[StreamToolCallEvent] = field(
        default_factory=list[StreamToolCallEvent]
    )


type _TerminalTaskEvent = (
    TaskSuccessEvent | TaskFailureEvent | TaskCancelledEvent
)


@dataclass(slots=True)
class _ToolInvocation:
    task_id: str
    call_id: str
    group_id: str
    question_id: str | None
    tool_name: str
    order: int
    terminal_event: _TerminalTaskEvent | None = None
    backfill_enqueued: bool = False


@dataclass(slots=True)
class _ToolGroup:
    group_id: str
    question_id: str | None
    ordered_call_ids: tuple[str, ...]
    invocations: list[_ToolInvocation] = field(
        default_factory=list[_ToolInvocation]
    )
    immediate_results: dict[str, ToolResultInput] = field(
        default_factory=dict[str, ToolResultInput]
    )
    prepared: bool = False
    receipt_submitted: bool = False
    continuation_scheduled: bool = False


@dataclass(frozen=True, slots=True)
class _BackfillJob:
    question_id: str | None
    task_id: str
    tool_name: str
    result: object


class _ModelAudioInputSink:
    """Adapt local audio capture callbacks to the model session submit lane."""

    def __init__(self, model_api: DuplexStreamModelAPI) -> None:
        self.model_api = model_api
        self.microphone_enabled = True

    async def input_audio_append(self, data: bytes) -> None:
        # The compatibility trigger and live microphone share Duplex's single
        # upstream audio buffer. Drop microphone frames only while the local
        # trigger PCM is being uploaded; blocking would replay stale speech.
        if not self.microphone_enabled:
            return
        await self.model_api.submit(AudioChunkInput(data=data))

    def suspend_microphone(self) -> None:
        self.microphone_enabled = False

    def resume_microphone(self) -> None:
        self.microphone_enabled = True


class DuplexAgentSession:
    """Consume one Duplex ``StreamModelAPI`` session for its full lifetime.

    Ordering contracts:

    1. In :meth:`_consume_events`, tool events are dispatched before audio
       events of the same provider event. A Duplex FC event contains one
       complete concurrent batch in its ``items`` array; the adapter projects
       that boundary as a shared ``group_id`` and ``group_size`` on individual
       :class:`StreamToolCallEvent` objects.
    2. The session is the only consumer of ``TaskManager.astream()``. Runtime
       events are correlated through independent ``task_id`` values; provider
       ``call_id`` values are used only to close the originating FC.
    3. Async receipts have a per-group barrier: a fast worker result may be
       recorded immediately, but cannot enter the backfill queue until its own
       placeholder batch was accepted by the model API.
    """

    def __init__(
        self,
        *,
        model_api: DuplexStreamModelAPI,
        tools: Sequence[TaskToolProtocolGeneral],
        task_manager: TaskManager,
        tool_call_mode: ToolCallMode,
        config: DuplexConfig,
        audio_file: str = "",
        output_audio_path: Path = DEFAULT_OUTPUT_AUDIO_PATH,
        async_compat: DuplexAsyncCompatConfig | None = None,
        context_diagnostics: bool = True,
        task_event_observer: Callable[[TaskEvent], None] | None = None,
        runtime_event_observer: Callable[[str], None] | None = None,
        backfill_activation_observer: (
            Callable[[BackfillActivation], None] | None
        ) = None,
        model_event_observer: (
            Callable[[StreamModelEvent], Awaitable[None] | None] | None
        ) = None,
        media_port: DuplexMediaPort | None = None,
        mic_mode: MicMode = "continuous",
    ) -> None:
        if tool_call_mode not in ("sync", "async"):
            raise ValueError(f"unsupported Duplex tool_call_mode: {tool_call_mode}")
        if tool_call_mode == "async" and async_compat is None:
            raise ValueError("Duplex async tool_call_mode requires async_compat")
        if tool_call_mode == "sync" and async_compat is not None:
            raise ValueError("Duplex sync tool_call_mode does not use async_compat")
        if audio_file and tool_call_mode == "async":
            raise ValueError(
                "Duplex DynamicTask does not support audio-file sessions: "
                "the first reply is only the async placeholder"
            )
        self.model_api = model_api
        self.tools = tuple(tools)
        self._tools_by_name = {tool.name: tool for tool in self.tools}
        if len(self._tools_by_name) != len(self.tools):
            raise ValueError("Duplex tools must have unique names")
        self.config = config
        self.task_manager = task_manager
        self.tool_call_mode = tool_call_mode
        self.audio_file = audio_file
        self.output_audio_path = output_audio_path
        self._context_diagnostics = context_diagnostics
        self._task_event_observer = task_event_observer or print_duplex_task_event
        self._model_event_observer = model_event_observer
        self.mic_mode = mic_mode
        self._microphone_gate_open = mic_mode == "continuous"
        self._local_rule_vad_task: asyncio.Task[None] | None = None
        self._background_errors: asyncio.Queue[BaseException] = asyncio.Queue()

        self._audio_input_sink = _ModelAudioInputSink(model_api)
        self.local_audio: DuplexMediaPort = media_port or DuplexLocalAudio(
            client=self._audio_input_sink,
            config=config,
            input_transform=self._filter_microphone_audio,
            accumulate_output=bool(self.audio_file),
        )
        self.local_audio.bind_callbacks(
            playback_drained_callback=self._handle_playback_drained,
            error_callback=self._report_background_error,
        )
        self._pending_tool_groups: dict[str, _PendingToolGroup] = {}
        self._active_tool_groups: dict[str, _ToolGroup] = {}
        self._invocations_by_task_id: dict[str, _ToolInvocation] = {}
        self._seen_call_ids: set[str] = set()
        self._tool_group_tasks: set[asyncio.Task[None]] = set()
        self._continuation_tasks: set[asyncio.Task[None]] = set()
        self._backfill_queue: asyncio.Queue[_BackfillJob] = asyncio.Queue()
        self._backfill_dispatcher_task: asyncio.Task[None] | None = None
        self._task_manager_runtime_task: asyncio.Task[None] | None = None
        self._task_manager_listener_task: asyncio.Task[None] | None = None
        self._closing = False
        self._question_contexts: dict[str, str] = {}
        self._latest_question_id: str | None = None
        # Reply-lane state: set while the model is not producing a speech turn
        # (or the upstream buffer is not occupied), so the async backfill layer
        # knows it is safe to activate results already written into Context.
        self._reply_idle = asyncio.Event()
        self._reply_idle.set()
        # Provider generation and browser playback have different terminals:
        # output_audio.done ends provider generation, while browser playback may
        # still be draining queued PCM. Barge-in must not send response.cancel
        # merely because the browser still has audio left to play.
        self._active_provider_response_id: str | None = None
        self._canceling_response_id: str | None = None
        self._backfill_scheduler = (
            DuplexAsyncBackfillScheduler(
                session=self,
                config=async_compat,
                activation_observer=backfill_activation_observer,
                runtime_event_observer=runtime_event_observer,
            )
            if async_compat is not None
            else None
        )

    async def run(self) -> None:
        realtime_audio = not self.audio_file
        if realtime_audio:
            self.local_audio.ensure_realtime_audio_supported()

        await self.model_api.start()
        self._start_task_manager()
        try:
            if realtime_audio:
                self.local_audio.start(asyncio.get_running_loop())
                await self._consume_events_with_background_errors(
                    stop_after_audio=False
                )
            else:
                receiver = asyncio.create_task(
                    self._consume_events_with_background_errors(
                        stop_after_audio=True
                    ),
                    name="duplex-stream-model-events",
                )
                try:
                    await self._send_audio_file()
                    await receiver
                finally:
                    if not receiver.done():
                        receiver.cancel()
                        await asyncio.gather(receiver, return_exceptions=True)
        finally:
            self._closing = True
            self._cancel_local_rule_vad()
            await self._stop_tool_groups()
            await self._stop_task_manager()
            self.local_audio.stop_capture()
            self.local_audio.wake_playback()
            self.local_audio.join_threads()
            self.local_audio.close_devices()
            await self.model_api.aclose()
            if self.local_audio.output_audio:
                self.output_audio_path.write_bytes(self.local_audio.output_audio)
                print(f"saved output audio to {self.output_audio_path}")

    async def _send_audio_file(self) -> None:
        await self._submit_audio_path(Path(self.audio_file))

    async def _submit_audio_path(self, path: Path) -> None:
        data = path.read_bytes()
        if path.suffix.lower() == ".wav":
            data = data[44:]
        for position in range(0, len(data), FILE_CHUNK):
            await self.model_api.submit(
                AudioChunkInput(data=data[position : position + FILE_CHUNK])
            )
            await asyncio.sleep(0.02)
        await self.model_api.submit(AudioCommitInput())

    async def _consume_events_with_background_errors(
        self,
        *,
        stop_after_audio: bool,
    ) -> None:
        """Fail when any session-owned background task fails."""

        consumer = asyncio.create_task(
            self._consume_events(stop_after_audio=stop_after_audio),
            name="duplex-model-event-consumer",
        )
        background_error = asyncio.create_task(
            self._background_errors.get(),
            name="duplex-background-error",
        )
        watched = {consumer, background_error}
        if self._task_manager_runtime_task is not None:
            watched.add(self._task_manager_runtime_task)
        if self._task_manager_listener_task is not None:
            watched.add(self._task_manager_listener_task)
        dispatcher_task = self._backfill_dispatcher_task
        if dispatcher_task is not None:
            watched.add(dispatcher_task)
        scheduler_task = (
            self._backfill_scheduler.task
            if self._backfill_scheduler is not None
            else None
        )
        if scheduler_task is not None:
            watched.add(scheduler_task)
        try:
            done, _ = await asyncio.wait(
                watched,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if background_error in done:
                error = background_error.result()
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
                raise RuntimeError("Duplex background task failed") from error

            runtime = self._task_manager_runtime_task
            if runtime is not None and runtime in done:
                error = (
                    RuntimeError("TaskManager runtime was cancelled unexpectedly")
                    if runtime.cancelled()
                    else runtime.exception()
                )
                if error is None:
                    error = RuntimeError("TaskManager runtime ended unexpectedly")
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
                raise RuntimeError("Duplex TaskManager failed") from error

            listener = self._task_manager_listener_task
            if listener is not None and listener in done:
                error = (
                    RuntimeError("TaskManager event stream was cancelled unexpectedly")
                    if listener.cancelled()
                    else listener.exception()
                )
                if error is None:
                    error = RuntimeError("TaskManager event stream ended unexpectedly")
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
                raise RuntimeError("Duplex task event routing failed") from error

            if dispatcher_task is not None and dispatcher_task in done:
                error = (
                    RuntimeError("Duplex backfill dispatcher was cancelled unexpectedly")
                    if dispatcher_task.cancelled()
                    else dispatcher_task.exception()
                )
                if error is None:
                    error = RuntimeError(
                        "Duplex backfill dispatcher ended unexpectedly"
                    )
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
                raise RuntimeError("Duplex async backfill failed") from error

            if scheduler_task is not None and scheduler_task in done:
                error = (
                    RuntimeError("Duplex async scheduler was cancelled unexpectedly")
                    if scheduler_task.cancelled()
                    else scheduler_task.exception()
                )
                if error is None:
                    error = RuntimeError("Duplex async scheduler ended unexpectedly")
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
                raise RuntimeError("Duplex async activation failed") from error

            background_error.cancel()
            await asyncio.gather(background_error, return_exceptions=True)
            await consumer
        finally:
            for task in (consumer, background_error):
                if not task.done():
                    task.cancel()
            await asyncio.gather(consumer, background_error, return_exceptions=True)

    async def _consume_events(self, *, stop_after_audio: bool) -> None:
        """Consume the normalized model event lane for the whole session."""

        async for event in self.model_api.events():
            if self._should_discard_canceled_audio(event):
                continue
            await self._observe_model_event(event)
            self._handle_tool_event(event)
            # Speech transport has one authoritative reply terminal:
            # response.output_audio.done. Probe exactly once on that event.
            if self._context_diagnostics and isinstance(event, StreamAudioDoneEvent):
                await self._probe_recent_context()
            self._handle_audio_event(event)
            if isinstance(event, StreamModelErrorEvent):
                raise RuntimeError(event.error)
            if stop_after_audio and isinstance(event, StreamAudioDoneEvent):
                return

    async def _observe_model_event(self, event: StreamModelEvent) -> None:
        observer = self._model_event_observer
        if observer is None:
            return
        result = observer(event)
        if result is not None:
            await result

    async def _probe_recent_context(self) -> None:
        try:
            await self.submit_context_retrieve()
        except Exception:
            logger.exception("Duplex recent-context diagnostic retrieve failed")

    def _handle_audio_event(self, event: StreamModelEvent) -> None:
        if isinstance(event, StreamResponseCanceledEvent):
            # A delayed ACK may arrive after a different response has started.
            # In that case the new response already superseded the pending
            # cancel and must not have its playback cleared by the stale ACK.
            if self._canceling_response_id is None:
                return
            self._canceling_response_id = None
            self._active_provider_response_id = None
            self.local_audio.clear_playback()
            return
        if isinstance(event, StreamTranscriptionStartEvent):
            self._cancel_local_rule_vad()
            # TODO: 这是本地规则版 VAD，不是 Duplex 服务端事件契约：ASR
            # started 后若迟迟没有首个 delta，就由客户端主动 commit。
            # 厂商提供明确的客户端判停原语后，应替换这条本地规则。
            task = asyncio.create_task(
                self._commit_if_local_rule_vad_fires(),
                name="duplex-local-rule-vad",
            )
            self._local_rule_vad_task = task
            task.add_done_callback(self._local_rule_vad_done)
            self._reply_idle.clear()
            self.local_audio.clear_playback()
        elif isinstance(event, StreamTranscriptionDeltaEvent):
            self._cancel_local_rule_vad()
        elif isinstance(event, StreamTranscriptionDoneEvent):
            self._cancel_local_rule_vad()
            self._reply_idle.clear()
            self.close_microphone_after_user_input()
            if (
                self._backfill_scheduler is not None
                and self._backfill_scheduler.note_transcription_done()
            ):
                return
            if event.item_id:
                self._question_contexts[event.item_id] = event.transcript
                self._latest_question_id = event.item_id
        elif isinstance(event, StreamAudioStartEvent):
            self._active_provider_response_id = event.response_id
            self._reply_idle.clear()
            # A new reply invalidates any drain callback queued by an earlier
            # reply. That stale callback must not release an async activation
            # while the new reply is still playing.
            self.local_audio.invalidate_playback_boundary()
        elif isinstance(event, StreamAudioDeltaEvent):
            self.local_audio.enqueue_playback(event.delta)
        elif isinstance(event, StreamAudioDoneEvent):
            # This is the provider terminal, not the browser playback terminal.
            # Keep the media-port drain boundary below, but do not consider the
            # response cancellable after this point.
            if (
                event.response_id is None
                or event.response_id == self._active_provider_response_id
            ):
                self._active_provider_response_id = None
            # Provider done means no more audio bytes will arrive; realtime
            # playback may still have queued PCM. Only the playback-thread
            # boundary may release the next synthetic activation, otherwise
            # its ASR start clears the tail of the reply still being played.
            if self.local_audio.realtime_playback_active:
                self.local_audio.enqueue_playback_boundary()
            else:
                self._reply_idle.set()

    def _should_discard_canceled_audio(self, event: StreamModelEvent) -> bool:
        if self._canceling_response_id is None or not isinstance(
            event,
            (StreamAudioStartEvent, StreamAudioDeltaEvent, StreamAudioDoneEvent),
        ):
            return False

        # response.canceled is an acknowledgement, not a safe global gate.
        # Providers may omit or delay it. A different response_id proves that
        # the provider has moved on, so release the latch and deliver the new
        # response instead of muting every later turn.
        if (
            event.response_id is not None
            and event.response_id != self._canceling_response_id
        ):
            self._canceling_response_id = None
            return False

        # Only audio belonging to the response we asked to cancel is stale.
        return True

    def _cancel_local_rule_vad(self) -> None:
        task = self._local_rule_vad_task
        if task is None:
            return
        self._local_rule_vad_task = None
        task.cancel()

    def _local_rule_vad_done(self, task: asyncio.Task[None]) -> None:
        if self._local_rule_vad_task is task:
            self._local_rule_vad_task = None
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._report_background_error(error)

    def _report_background_error(self, error: BaseException) -> None:
        self._background_errors.put_nowait(error)

    async def _commit_if_local_rule_vad_fires(self) -> None:
        await asyncio.sleep(self.config.local_rule_vad_timeout_ms / 1000)
        await self.model_api.submit(AudioCommitInput())

    def _handle_playback_drained(self) -> None:
        """Release one queued activation after local speaker playback ends."""

        self._reply_idle.set()

    def _handle_tool_event(self, event: StreamModelEvent) -> None:
        if self._closing or not isinstance(event, StreamToolCallEvent):
            return

        self._reply_idle.clear()
        request = event.tool_call
        if request.run_id in self._seen_call_ids:
            return
        self._seen_call_ids.add(request.run_id)

        group_id = event.group_id or request.run_id
        group = self._pending_tool_groups.setdefault(
            group_id,
            _PendingToolGroup(
                expected_size=max(1, event.group_size),
                question_id=event.item_id or self._latest_question_id,
            ),
        )
        if event.item_id:
            group.question_id = event.item_id
        group.expected_size = max(group.expected_size, event.group_size)
        group.events.append(event)
        if len(group.events) < group.expected_size:
            return

        self._pending_tool_groups.pop(group_id, None)
        task = asyncio.create_task(
            self._prepare_tool_group(
                group_id,
                tuple(group.events),
                question_id=group.question_id,
            ),
            name=f"duplex-tool-group-{group_id}",
        )
        self._tool_group_tasks.add(task)
        task.add_done_callback(self._tool_group_done)

    async def _prepare_tool_group(
        self,
        group_id: str,
        events: tuple[StreamToolCallEvent, ...],
        *,
        question_id: str | None = None,
    ) -> None:
        if self._closing:
            return

        group = _ToolGroup(
            group_id=group_id,
            question_id=question_id,
            ordered_call_ids=tuple(event.tool_call.run_id for event in events),
        )
        self._active_tool_groups[group_id] = group

        for order, event in enumerate(events):
            if self._closing:
                return
            request = event.tool_call
            call_id = request.run_id
            tool_name = request.tool_name

            if event.input_error is not None:
                group.immediate_results[call_id] = ToolResultInput(
                    call_id=call_id,
                    output=f"{tool_name}工具调用无效：{event.input_error}",
                    success=False,
                )
                continue

            tool = self._tools_by_name.get(tool_name)
            if tool is None:
                group.immediate_results[call_id] = ToolResultInput(
                    call_id=call_id,
                    output=f"{tool_name}工具未注册",
                    success=False,
                )
                continue

            try:
                arguments = validate_tool_arguments(tool, request.arguments)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                group.immediate_results[call_id] = ToolResultInput(
                    call_id=call_id,
                    output=(
                        f"{tool_name}工具提交失败："
                        f"{type(error).__name__}: {error}"
                    ),
                    success=False,
                )
                continue

            if tool_name in _INLINE_CONTROL_TOOL_NAMES:
                # TODO: If more control tools appear, promote this name-based
                # exception to explicit tool metadata. Control work bypasses
                # TaskManager so cancellation remains available when all
                # business execution slots are occupied.
                group.immediate_results[call_id] = (
                    await self._execute_inline_control(
                        tool=tool,
                        arguments=arguments,
                        call_id=call_id,
                    )
                )
                continue

            invocation: _ToolInvocation | None = None
            try:
                worker = bind_task_tool_worker(tool, arguments)
                task_id = str(uuid.uuid4())
                invocation = _ToolInvocation(
                    task_id=task_id,
                    call_id=call_id,
                    group_id=group_id,
                    question_id=question_id,
                    tool_name=tool_name,
                    order=order,
                )
                # Establish correlation before submit_task emits TaskCreated.
                group.invocations.append(invocation)
                self._invocations_by_task_id[task_id] = invocation
                self.task_manager.submit_task(
                    worker,
                    task_id=task_id,
                    name=tool_name,
                    arguments=model_to_dict(arguments),
                    metadata={
                        f"{_DUPLEX_METADATA_PREFIX}call_id": call_id,
                        f"{_DUPLEX_METADATA_PREFIX}group_id": group_id,
                        f"{_DUPLEX_METADATA_PREFIX}question_id": question_id,
                        f"{_DUPLEX_METADATA_PREFIX}call_order": order,
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if invocation is not None:
                    self.task_manager.cancel_task(invocation.task_id)
                    group.invocations.remove(invocation)
                    self._invocations_by_task_id.pop(invocation.task_id, None)
                group.immediate_results[call_id] = ToolResultInput(
                    call_id=call_id,
                    output=(
                        f"{tool_name}工具提交失败："
                        f"{type(error).__name__}: {error}"
                    ),
                    success=False,
                )

        group.prepared = True
        if self.tool_call_mode == "sync":
            self._maybe_schedule_sync_continuation(group)
            return

        receipt_results = {
            invocation.call_id: ToolResultInput(
                call_id=invocation.call_id,
                output=nl_repr(
                    AsyncTaskReceipt(
                        task_id=invocation.task_id,
                        tool_name=invocation.tool_name,
                    )
                ),
            )
            for invocation in group.invocations
        }
        receipt_results.update(group.immediate_results)
        self._reply_idle.clear()
        await self.model_api.submit(
            self._ordered_tool_result_batch(group, receipt_results)
        )
        group.receipt_submitted = True
        self._enqueue_ready_backfills(group)

    async def _execute_inline_control(
        self,
        *,
        tool: TaskToolProtocolGeneral,
        arguments: BaseModel,
        call_id: str,
    ) -> ToolResultInput:
        worker = bind_task_tool_worker(tool, arguments)
        self._observe_task_event(TaskStartEvent(task_id=call_id))
        terminal: _TerminalTaskEvent | None = None
        try:
            async for event in worker():
                match event:
                    case TaskProgress():
                        if terminal is None:
                            self._observe_task_event(
                                TaskProgressEvent(
                                    task_id=call_id,
                                    progress=event.progress,
                                )
                            )
                    case TaskSuccess():
                        if terminal is None:
                            terminal = TaskSuccessEvent(
                                task_id=call_id,
                                result=event.result,
                            )
                    case _:
                        raise AssertionError(
                            f"unsupported inline task event: {type(event).__name__}"
                        )
        except asyncio.CancelledError:
            self._observe_task_event(
                TaskCancelledEvent(task_id=call_id, reason="Task was cancelled")
            )
            raise
        except Exception as error:
            if terminal is None:
                terminal = TaskFailureEvent(task_id=call_id, error=str(error))
            else:
                logger.warning(
                    "Inline control cleanup failed after success: call_id=%s",
                    call_id,
                    exc_info=error,
                )

        if terminal is None:
            terminal = TaskFailureEvent(
                task_id=call_id,
                error="Task completed without TaskSuccess",
            )
        self._observe_task_event(terminal)
        return self._terminal_tool_result(call_id, terminal)

    def _maybe_schedule_sync_continuation(self, group: _ToolGroup) -> None:
        if (
            self._closing
            or not group.prepared
            or group.continuation_scheduled
            or any(
                invocation.terminal_event is None
                for invocation in group.invocations
            )
        ):
            return
        group.continuation_scheduled = True
        task = asyncio.create_task(
            self._submit_sync_group(group),
            name=f"duplex-sync-continuation-{group.group_id}",
        )
        self._continuation_tasks.add(task)
        task.add_done_callback(self._continuation_done)

    async def _submit_sync_group(self, group: _ToolGroup) -> None:
        try:
            results = dict(group.immediate_results)
            for invocation in group.invocations:
                terminal = invocation.terminal_event
                assert terminal is not None
                results[invocation.call_id] = self._terminal_tool_result(
                    invocation.call_id,
                    terminal,
                )
            if not self._closing:
                self._reply_idle.clear()
                await self.model_api.submit(
                    self._ordered_tool_result_batch(group, results)
                )
        finally:
            self._drop_active_group(group)

    def _enqueue_ready_backfills(self, group: _ToolGroup) -> None:
        if not group.prepared or not group.receipt_submitted:
            return
        for invocation in group.invocations:
            terminal = invocation.terminal_event
            if (
                isinstance(terminal, TaskSuccessEvent)
                and not invocation.backfill_enqueued
            ):
                invocation.backfill_enqueued = True
                self._backfill_queue.put_nowait(
                    _BackfillJob(
                        question_id=invocation.question_id,
                        task_id=invocation.task_id,
                        tool_name=invocation.tool_name,
                        result=terminal.result,
                    )
                )

        if all(
            invocation.terminal_event is not None
            for invocation in group.invocations
        ):
            self._drop_active_group(group)

    async def _dispatch_backfills(self) -> None:
        assert self._backfill_scheduler is not None
        while True:
            job = await self._backfill_queue.get()
            try:
                if self._closing:
                    continue
                if not job.question_id:
                    logger.warning(
                        "Skip Duplex async backfill without origin question: task_id=%s",
                        job.task_id,
                    )
                    continue
                if job.question_id not in self._question_contexts:
                    logger.warning(
                        "Skip Duplex async backfill for unknown question: "
                        "task_id=%s question_id=%s",
                        job.task_id,
                        job.question_id,
                    )
                    continue
                await self._backfill_scheduler.publish_backfill(
                    question_id=job.question_id,
                    task_id=job.task_id,
                    tool_name=job.tool_name,
                    text=nl_repr(job.result),
                )
            finally:
                self._backfill_queue.task_done()

    def _terminal_tool_result(
        self,
        call_id: str,
        event: _TerminalTaskEvent,
    ) -> ToolResultInput:
        match event:
            case TaskSuccessEvent():
                output = (
                    event.result
                    if isinstance(event.result, str)
                    else nl_repr(event.result)
                )
                return ToolResultInput(
                    call_id=call_id,
                    output=output,
                    success=True,
                )
            case TaskFailureEvent():
                return ToolResultInput(
                    call_id=call_id,
                    output=f"工具调用失败：{event.error}",
                    success=False,
                )
            case TaskCancelledEvent():
                return ToolResultInput(
                    call_id=call_id,
                    output=f"工具调用被取消：{event.reason or '未知原因'}",
                    success=False,
                )

    def _ordered_tool_result_batch(
        self,
        group: _ToolGroup,
        results: dict[str, ToolResultInput],
    ) -> ToolResultBatchInput:
        return ToolResultBatchInput(
            results=tuple(results[call_id] for call_id in group.ordered_call_ids)
        )

    def _drop_active_group(self, group: _ToolGroup) -> None:
        if self._active_tool_groups.get(group.group_id) is group:
            self._active_tool_groups.pop(group.group_id, None)
        for invocation in group.invocations:
            if self._invocations_by_task_id.get(invocation.task_id) is invocation:
                self._invocations_by_task_id.pop(invocation.task_id, None)

    async def _stop_tool_groups(self) -> None:
        self._cancel_active_tool_tasks()
        tasks = [*self._tool_group_tasks, *self._continuation_tasks]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tool_group_tasks.clear()
        self._continuation_tasks.clear()
        # A preparation task can submit work immediately before cancellation.
        self._cancel_active_tool_tasks()
        self._pending_tool_groups.clear()
        self._seen_call_ids.clear()

    def _tool_group_done(self, task: asyncio.Task[None]) -> None:
        self._tool_group_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._report_background_error(error)

    def _continuation_done(self, task: asyncio.Task[None]) -> None:
        self._continuation_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._report_background_error(error)

    def _cancel_active_tool_tasks(self) -> None:
        for invocation in tuple(self._invocations_by_task_id.values()):
            if invocation.terminal_event is None:
                self.task_manager.cancel_task(invocation.task_id)

    def _start_task_manager(self) -> None:
        if self._task_manager_runtime_task is not None:
            return
        self._task_manager_runtime_task = asyncio.create_task(
            self.task_manager.run(),
            name="duplex-stream-model-task-manager",
        )
        self._task_manager_listener_task = asyncio.create_task(
            self._consume_task_manager_events(),
            name="duplex-stream-model-task-events",
        )
        if self._backfill_scheduler is not None:
            self._backfill_scheduler.start()
            self._backfill_dispatcher_task = asyncio.create_task(
                self._dispatch_backfills(),
                name="duplex-stream-model-backfill-dispatcher",
            )

    async def _consume_task_manager_events(self) -> None:
        async for event in self.task_manager.astream():
            self._observe_task_event(event)
            if not isinstance(
                event,
                (TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent),
            ):
                continue
            invocation = self._invocations_by_task_id.get(event.task_id)
            if invocation is None or invocation.terminal_event is not None:
                continue
            invocation.terminal_event = event
            group = self._active_tool_groups.get(invocation.group_id)
            if group is None or self._closing:
                continue
            if self.tool_call_mode == "sync":
                self._maybe_schedule_sync_continuation(group)
            else:
                # Failure/cancel remain visible in TaskManager projection and
                # diagnostics only. The inline cancel_task FC already informs
                # the model; async compatibility backfills successful facts.
                self._enqueue_ready_backfills(group)

    def _observe_task_event(self, event: TaskEvent) -> None:
        try:
            self._task_event_observer(event)
        except Exception:
            logger.exception("Duplex task event observer failed; ignoring")

    async def _stop_task_manager(self) -> None:
        dispatcher = self._backfill_dispatcher_task
        if dispatcher is not None:
            dispatcher.cancel()
            await asyncio.gather(dispatcher, return_exceptions=True)
        self._backfill_dispatcher_task = None
        if self._backfill_scheduler is not None:
            await self._backfill_scheduler.stop()

        tasks = [
            task
            for task in (
                self._task_manager_runtime_task,
                self._task_manager_listener_task,
            )
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._task_manager_runtime_task = None
        self._task_manager_listener_task = None
        self._active_tool_groups.clear()
        self._invocations_by_task_id.clear()

    async def submit_context_update(self, item_id: str, text: str) -> None:
        await self.model_api.submit(
            ContextItemUpdateInput(item_id=item_id, text=text)
        )

    async def submit_context_retrieve(self) -> None:
        await self.model_api.submit(ContextItemRetrieveInput())

    async def submit_audio_path(self, path: Path) -> None:
        await self._submit_audio_path(path)

    async def submit_audio_chunk(self, data: bytes) -> None:
        await self.model_api.submit(AudioChunkInput(data=data))

    async def commit_audio(self) -> None:
        await self.model_api.submit(AudioCommitInput())

    async def interrupt_response(self) -> bool:
        """Clear audible playback and return whether provider cancel was sent."""

        if not self.local_audio.realtime_playback_active:
            return False

        # Clearing queued PCM is always required for barge-in. It is independent
        # from provider cancellation because output_audio.done can precede the
        # moment when the browser finishes playing that same response.
        self.local_audio.clear_playback()
        if self._active_provider_response_id is None:
            return False
        if self._canceling_response_id is not None:
            return False

        self._canceling_response_id = self._active_provider_response_id
        await self.model_api.cancel_response()
        return True

    def question_transcript(self, question_id: str) -> str | None:
        return self._question_contexts.get(question_id)

    def is_synthetic_transcription_pending(self) -> bool:
        """True while the synthetic activation audio owns the ASR lane.

        Observers use this to avoid treating the async-backfill trigger
        audio as a real user utterance.
        """

        return bool(
            self._backfill_scheduler is not None
            and self._backfill_scheduler.synthetic_pending
        )

    async def wait_idle(self) -> None:
        await self._reply_idle.wait()

    def mark_busy(self) -> None:
        self._reply_idle.clear()

    def mark_idle(self) -> None:
        self._reply_idle.set()

    def begin_synthetic_turn(self) -> None:
        self._audio_input_sink.suspend_microphone()

    def end_synthetic_turn(self) -> None:
        self._audio_input_sink.resume_microphone()

    def open_microphone_for_user_input(self) -> bool:
        """Open one microphone turn; ASR completion closes it again."""

        if self.audio_file or self.mic_mode != "space_gate":
            return False
        if self._microphone_gate_open:
            return False
        self._microphone_gate_open = True
        print("[MIC] 麦克风已打开；本轮识别完成后自动关闭")
        return True

    def close_microphone_after_user_input(self) -> bool:
        if self.mic_mode != "space_gate" or not self._microphone_gate_open:
            return False
        self._microphone_gate_open = False
        print("[MIC] 本轮识别完成，麦克风已关闭")
        return True

    def _filter_microphone_audio(self, data: bytes) -> bytes:
        # Keep the provider's 20 ms audio cadence while the local microphone
        # gate is closed, but never expose ambient sound to server-side VAD.
        if self.mic_mode == "continuous" or self._microphone_gate_open:
            return data
        return b"\x00" * len(data)

__all__ = [
    "DEFAULT_OUTPUT_AUDIO_PATH",
    "DuplexAgentSession",
    "MicMode",
    "ToolCallMode",
]
