"""Experimental Responses-backed stream model session (protocol validation).

This module validates that the session-scoped ``StreamModelAPI`` protocol can
accommodate a Responses-style agent conversation: a serial FIFO model lane
where user queries, placeholder continuations and real tool-result backfills
share one mailbox. Tool calls are emitted as events and an external business
layer executes them, then submits terminal results back into this session.

It is deliberately experimental: there is no production consumer yet. Keep
this module only while the protocol compatibility claim needs a reference
implementation; rename/remove it when a real consumer lands.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import anyio
from anyio.abc import TaskGroup
from pydantic import BaseModel

from aicore.models.model_api import (
    ModelAPI,
    ModelCallParams,
    ModelInput,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    ModelToolCallEvent,
    ToolResultsMessage,
    UserMessage,
)
from aicore.models.model_api.responses_adapter import ResponsesModelState
from aicore.tools.protocol import ToolProtocol
from aicore.tools.run import ToolRunRequest, ToolRunResult

from aicore.models.stream_model_api.events import (
    StreamModelEvent,
    StreamQueryDoneEvent,
    StreamQueryErrorEvent,
    StreamQueryStartEvent,
    StreamStructuredDoneEvent,
    StreamTextDeltaEvent,
    StreamTextDoneEvent,
    StreamTextStartEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
)
from aicore.models.stream_model_api.inputs import (
    AudioChunkInput,
    AudioCommitInput,
    ContextItemRetrieveInput,
    ContextItemUpdateInput,
    QueryInput,
    StreamModelInput,
    ToolResultBatchInput,
    ToolResultInput,
)
from aicore.models.stream_model_api.protocol import ToolCallMode

type ActivationSource = Literal["user", "tool_result", "placeholder"]


@dataclass(frozen=True)
class _Activation:
    query_id: str
    root_query_id: str
    input: ModelInput
    source: ActivationSource
    output_type: type[Any] | None = None
    completed_call_ids: tuple[str, ...] = ()


@dataclass
class _RootQuery:
    pending_calls: set[str] = field(default_factory=set[str])
    activation_count: int = 0


@dataclass
class _PendingToolCall:
    root_query_id: str
    request: ToolRunRequest
    group_id: str | None = None
    result_submitted: bool = False
    output: str | None = None


@dataclass(frozen=True)
class _ToolCallGroup:
    call_ids: tuple[str, ...]


class ResponsesStreamModelAPI:
    """Experimental ``StreamModelAPI`` implementation on ``ResponsesModelAPI``.

    Validates that the session-scoped protocol fits a Responses-style agent
    conversation. The model lane is serial: user queries, automatic
    placeholders, and real tool-result backfills share one FIFO mailbox. Tool
    execution is deliberately outside this class.
    """

    def __init__(
        self,
        *,
        model_api: ModelAPI[ResponsesModelState],
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        system_prompt: str | None = None,
        params: ModelCallParams | None = None,
        tool_call_mode: ToolCallMode = "async",
        ignore_placeholder_response_text: bool = False,
        pending_receipt_prefix: str = "[占位回执]",
        tool_result_prefix: str = "[工具结果回灌]",
    ) -> None:
        self.model_api = model_api
        self.tools = list(tools or [])
        self.system_prompt = system_prompt
        self.params = params
        if tool_call_mode not in ("sync", "async"):
            raise ValueError(f"unsupported tool_call_mode: {tool_call_mode}")
        self.tool_call_mode = tool_call_mode
        self.ignore_placeholder_response_text = ignore_placeholder_response_text
        self.session_id = uuid.uuid4().hex
        self._pending_receipt_prefix = pending_receipt_prefix
        self._tool_result_prefix = tool_result_prefix

        self._state: ResponsesModelState = model_api.initial_state(
            system_prompt=system_prompt
        )
        self._mailbox_send, self._mailbox_receive = anyio.create_memory_object_stream[
            _Activation
        ](math.inf)
        self._event_send, self._event_receive = anyio.create_memory_object_stream[
            StreamModelEvent
        ](math.inf)
        self._roots: dict[str, _RootQuery] = {}
        self._pending_calls: dict[str, _PendingToolCall] = {}
        self._tool_call_groups: dict[str, _ToolCallGroup] = {}
        self._known_query_ids: set[str] = set()
        self._task_group: TaskGroup | None = None
        self._lock = anyio.Lock()
        self._start_lock = anyio.Lock()
        self._closed = False

    async def __aenter__(self) -> ResponsesStreamModelAPI:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def start(self) -> None:
        async with self._start_lock:
            if self._closed:
                raise RuntimeError("stream model session is closed")
            if self._task_group is not None:
                return
            task_group = anyio.create_task_group()
            await task_group.__aenter__()
            task_group.start_soon(self._run_mailbox)
            self._task_group = task_group

    async def submit(
        self,
        input: StreamModelInput,
        *,
        query_id: str | None = None,
        output_type: type[Any] | None = None,
    ) -> str:
        """Submit one input; query inputs return their stable root id."""

        if isinstance(input, ToolResultInput):
            if output_type is not None:
                raise ValueError("tool results do not support structured output")
            return await self.submit_tool_result(
                call_id=input.call_id,
                output=input.output,
                success=input.success,
                query_id=query_id,
            )
        if isinstance(input, ToolResultBatchInput):
            if output_type is not None:
                raise ValueError("tool results do not support structured output")
            if query_id is not None and len(input.results) > 1:
                raise ValueError("query_id cannot identify multiple tool results")
            continuation_id = ""
            for result in input.results:
                continuation_id = await self.submit_tool_result(
                    call_id=result.call_id,
                    output=result.output,
                    success=result.success,
                    query_id=query_id,
                )
            return continuation_id
        if isinstance(
            input,
            (
                AudioChunkInput,
                AudioCommitInput,
                ContextItemRetrieveInput,
                ContextItemUpdateInput,
            ),
        ):
            raise TypeError(
                "ResponsesStreamModelAPI does not accept "
                f"{type(input).__name__} input"
            )

        await self.start()
        resolved_query_id = query_id or uuid.uuid4().hex
        activation = _Activation(
            query_id=resolved_query_id,
            root_query_id=resolved_query_id,
            input=_normalize_input(input),
            source="user",
            output_type=output_type,
        )
        async with self._lock:
            self._register_root_activation(activation)
            await self._mailbox_send.send(activation)
        return resolved_query_id

    async def submit_tool_result(
        self,
        *,
        call_id: str,
        output: str,
        success: bool = True,
        query_id: str | None = None,
    ) -> str:
        """Submit one externally executed tool's terminal result.

        Sync mode sends the real paired function-call output. Async mode has
        already consumed that output slot with a placeholder, so the real
        result becomes a regular backfill query.
        """

        await self.start()
        async with self._lock:
            pending = self._pending_calls.get(call_id)
            if pending is None:
                raise KeyError(f"unknown pending tool call: {call_id}")
            if pending.result_submitted:
                raise ValueError(f"tool result already submitted: {call_id}")
            pending.result_submitted = True
            pending.output = output
            root = self._roots[pending.root_query_id]
            resolved_query_id = query_id or f"tool-{call_id}-{uuid.uuid4().hex[:8]}"
            self._reserve_continuation_id(resolved_query_id)
            await self._publish(
                StreamToolResultEvent(
                    session_id=self.session_id,
                    query_id=resolved_query_id,
                    root_query_id=pending.root_query_id,
                    call_id=call_id,
                    tool_name=pending.request.tool_name,
                    output=output,
                    success=success,
                )
            )

            if self.tool_call_mode == "async":
                activation = _Activation(
                    query_id=resolved_query_id,
                    root_query_id=pending.root_query_id,
                    input=UserMessage(
                        text=self._render_tool_result_backfill(
                            request=pending.request,
                            output=output,
                            success=success,
                        )
                    ),
                    source="tool_result",
                    completed_call_ids=(call_id,),
                )
                root.activation_count += 1
                await self._mailbox_send.send(activation)
                return resolved_query_id

            assert pending.group_id is not None
            group = self._tool_call_groups[pending.group_id]
            group_calls = [self._pending_calls[item] for item in group.call_ids]
            if not all(item.result_submitted for item in group_calls):
                return resolved_query_id

            activation = _Activation(
                query_id=resolved_query_id,
                root_query_id=pending.root_query_id,
                input=ToolResultsMessage(
                    results=[
                        ToolRunResult(
                            run_id=item.request.run_id,
                            output=self._submitted_output(item),
                        )
                        for item in group_calls
                    ]
                ),
                source="tool_result",
                completed_call_ids=group.call_ids,
            )
            root.activation_count += 1
            await self._mailbox_send.send(activation)
            return resolved_query_id

    async def events(self) -> AsyncIterator[StreamModelEvent]:
        """Yield the session-wide event stream for one consumer."""

        async for event in self._event_receive:
            yield event

    async def aclose(self) -> None:
        async with self._start_lock:
            if self._closed:
                return
            self._closed = True
            await self._mailbox_send.aclose()
            if self._task_group is not None:
                await self._task_group.__aexit__(None, None, None)
                self._task_group = None

            self._roots.clear()
            self._pending_calls.clear()
            self._tool_call_groups.clear()
            await self._event_send.aclose()

    def _register_root_activation(self, activation: _Activation) -> _RootQuery:
        if self._closed:
            raise RuntimeError("stream model session is closed")
        if activation.query_id in self._known_query_ids:
            raise ValueError(f"duplicate query_id: {activation.query_id}")
        if activation.root_query_id in self._roots:
            raise ValueError(f"duplicate root query_id: {activation.root_query_id}")
        self._known_query_ids.add(activation.query_id)
        root = _RootQuery(activation_count=1)
        self._roots[activation.root_query_id] = root
        return root

    def _reserve_continuation_id(self, query_id: str) -> None:
        if query_id in self._known_query_ids:
            raise ValueError(f"duplicate query_id: {query_id}")
        self._known_query_ids.add(query_id)

    async def _run_mailbox(self) -> None:
        async with self._mailbox_receive:
            async for activation in self._mailbox_receive:
                await self._run_activation(activation)

    async def _run_activation(self, activation: _Activation) -> None:
        await self._publish(
            StreamQueryStartEvent(
                session_id=self.session_id,
                query_id=activation.query_id,
                root_query_id=activation.root_query_id,
                source=activation.source,
            )
        )
        try:
            if activation.output_type is not None:
                await self._run_structured_activation(activation)
            else:
                await self._run_text_activation(activation)
        except Exception as exc:
            await self._publish(
                StreamQueryErrorEvent(
                    session_id=self.session_id,
                    query_id=activation.query_id,
                    root_query_id=activation.root_query_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        finally:
            await self._finish_activation(activation)

    async def _run_text_activation(self, activation: _Activation) -> None:
        stream = await self.model_api.stream(
            activation.input,
            state=self._state,
            tools=self.tools,
            params=self.params,
        )
        emitted_call_ids: set[str] = set()
        observed_calls: list[ToolRunRequest] = []
        suppress_text = (
            activation.source == "placeholder" and self.ignore_placeholder_response_text
        )
        async for event in stream:
            common = {
                "session_id": self.session_id,
                "query_id": activation.query_id,
                "root_query_id": activation.root_query_id,
            }
            if isinstance(event, ModelTextStartEvent):
                if not suppress_text:
                    await self._publish(StreamTextStartEvent(**common))
            elif isinstance(event, ModelTextDeltaEvent):
                if not suppress_text:
                    await self._publish(
                        StreamTextDeltaEvent(delta=event.delta, **common)
                    )
            elif isinstance(event, ModelTextDoneEvent):
                if not suppress_text:
                    await self._publish(StreamTextDoneEvent(text=event.text, **common))
            elif isinstance(event, ModelToolCallEvent):
                emitted_call_ids.add(event.tool_call.run_id)
                observed_calls.append(event.tool_call)

        response = stream.response
        if response is None:
            raise RuntimeError("responses model stream ended without a response")
        self._state = response.state
        for tool_call in response.tool_calls:
            if tool_call.run_id not in emitted_call_ids:
                observed_calls.append(tool_call)
        await self._observe_tool_calls(activation, observed_calls)

    async def _run_structured_activation(self, activation: _Activation) -> None:
        assert activation.output_type is not None
        response = await self.model_api.structured_output(
            activation.input,
            output_type=activation.output_type,
            state=self._state,
            params=self.params,
        )
        self._state = response.state
        error = response.metadata.get("structured_output_error")
        await self._publish(
            StreamStructuredDoneEvent(
                session_id=self.session_id,
                query_id=activation.query_id,
                root_query_id=activation.root_query_id,
                parsed=response.parsed,
                text=response.text,
                error=str(error) if error is not None else None,
            )
        )

    async def _observe_tool_calls(
        self,
        activation: _Activation,
        tool_calls: Sequence[ToolRunRequest],
    ) -> None:
        new_calls: list[ToolRunRequest] = []
        async with self._lock:
            root = self._roots[activation.root_query_id]
            for tool_call in tool_calls:
                if tool_call.run_id in self._pending_calls:
                    continue
                new_calls.append(tool_call)

            group_id: str | None = None
            if self.tool_call_mode == "sync" and new_calls:
                group_id = f"group-{uuid.uuid4().hex}"
                self._tool_call_groups[group_id] = _ToolCallGroup(
                    call_ids=tuple(call.run_id for call in new_calls),
                )

            for tool_call in new_calls:
                root.pending_calls.add(tool_call.run_id)
                self._pending_calls[tool_call.run_id] = _PendingToolCall(
                    root_query_id=activation.root_query_id,
                    request=tool_call,
                    group_id=group_id,
                )

            if self.tool_call_mode == "async" and new_calls:
                placeholder_id = (
                    f"placeholder-{new_calls[0].run_id}-{uuid.uuid4().hex[:8]}"
                )
                self._reserve_continuation_id(placeholder_id)
                root.activation_count += 1
                await self._mailbox_send.send(
                    _Activation(
                        query_id=placeholder_id,
                        root_query_id=activation.root_query_id,
                        source="placeholder",
                        input=ToolResultsMessage(
                            results=[
                                ToolRunResult(
                                    run_id=tool_call.run_id,
                                    output=self._render_pending_receipt(tool_call),
                                )
                                for tool_call in new_calls
                            ]
                        ),
                    )
                )

        for tool_call in new_calls:
            common = {
                "session_id": self.session_id,
                "query_id": activation.query_id,
                "root_query_id": activation.root_query_id,
                "tool_call": tool_call,
            }
            await self._publish(
                StreamToolCallEvent(
                    # One provider turn's calls belong to one group.  Sync mode
                    # pairs the group id explicitly; async mode treats every
                    # call as its own standalone group (the placeholder closes
                    # each call immediately).
                    group_id=group_id,
                    group_size=len(new_calls) if group_id is not None else 1,
                    **common,
                )
            )

    async def _finish_activation(self, activation: _Activation) -> None:
        async with self._lock:
            root = self._roots.get(activation.root_query_id)
            if root is None:
                return
            completed_groups: set[str] = set()
            for call_id in activation.completed_call_ids:
                root.pending_calls.discard(call_id)
                pending = self._pending_calls.pop(call_id, None)
                if pending is not None and pending.group_id is not None:
                    completed_groups.add(pending.group_id)
            for group_id in completed_groups:
                self._tool_call_groups.pop(group_id, None)
            root.activation_count -= 1
            pending_count = len(root.pending_calls)
            if root.activation_count == 0 and not root.pending_calls:
                del self._roots[activation.root_query_id]

        await self._publish(
            StreamQueryDoneEvent(
                session_id=self.session_id,
                query_id=activation.query_id,
                root_query_id=activation.root_query_id,
                pending_tool_calls=pending_count,
            )
        )

    async def _publish(self, event: StreamModelEvent) -> None:
        await self._event_send.send(event)

    def _render_pending_receipt(self, tool_call: ToolRunRequest) -> str:
        return (
            f"{self._pending_receipt_prefix} {tool_call.tool_name} "
            "仍在后台执行，真实结果稍后回灌。"
        )

    @staticmethod
    def _submitted_output(pending: _PendingToolCall) -> str:
        if pending.output is None:
            raise RuntimeError(f"tool result has no output: {pending.request.run_id}")
        return pending.output

    def _render_tool_result_backfill(
        self,
        *,
        request: ToolRunRequest,
        output: str,
        success: bool,
    ) -> str:
        status = "成功" if success else "失败"
        return (
            f"{self._tool_result_prefix}\n"
            f"原始工具调用: {request.tool_name}\n"
            f"call_id: {request.run_id}\n"
            f"执行状态: {status}\n"
            f"真实结果:\n{output}\n"
            "请只根据该结果和当前对话上下文回答，不要重复调用该工具。"
        )


def _normalize_input(input: QueryInput) -> ModelInput:
    return UserMessage(text=input) if isinstance(input, str) else input


__all__ = [
    "ResponsesStreamModelAPI",
    "QueryInput",
    "ToolCallMode",
]
