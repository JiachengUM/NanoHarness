"""Chat Completions backed implementation of the provider-neutral ModelAPI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Sequence, cast, assert_never

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from volcenginesdkarkruntime import AsyncArk # type: ignore
from volcenginesdkarkruntime._streaming import AsyncStream # type: ignore
from volcenginesdkarkruntime.types.chat import ( # type: ignore
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from volcenginesdkarkruntime.types.chat.chat_completion_chunk import ( # type: ignore
    ChoiceDeltaToolCall,
)
from volcenginesdkarkruntime.types.chat.chat_completion_message_tool_call import ( # type: ignore
    ChatCompletionMessageToolCall,
)
from volcenginesdkarkruntime.types.shared_params.response_format_json_schema import ( # type: ignore
    ResponseFormatJSONSchema,
)

from aicore.tools.protocol import ToolProtocol
from aicore.tools.run import ToolRunRequest
from aicore.utils.misc import safe_update
from aicore.utils.parent_pointer_tree import NodeId, ParentPointerTree

from .events import (
    ModelEvent,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    ModelToolCallEvent,
)
from .protocol import ModelAPI, ModelStream
from .types import (
    AssistantMessage,
    ModelCallParams,
    ModelInput,
    ModelMessage,
    ModelResponse,
    ModelState,
    ModelStateDump,
    StructuredModelResponse,
    SystemMessage,
    ToolResultsMessage,
    UserMessage,
)

_MODEL_STATE_DUMP_OBJECT = "model_state_dump"
_CHAT_MESSAGES_DUMP_FORMAT = "chat.messages"
_CHAT_MESSAGES_DUMP_FORMAT_VERSION = 1
_MODEL_MESSAGE_LIST_ADAPTER = TypeAdapter(list[ModelMessage])

type _ModelMessageSegment = tuple[ModelMessage, ...]

# 进程内唯一的 Chat transcript 树。
# ChatModelAPI 实例之间共享它，因此同一个 state 可以跨 adapter 实例继续使用；
# 但它不是持久化存储，跨进程/重启需要通过 dump_state/restore_state 重建。
# 使用(父指针树)[https://en.wikipedia.org/wiki/Parent_pointer_tree]而不是 list 维护所有的对话历史, 便于支持回溯和分叉
# TODO: 考虑清理机制, 避免超长对话导致 oom
_CHAT_TRANSCRIPT = ParentPointerTree[_ModelMessageSegment]()

class ChatModelState(ModelState):
    """Provider-owned Chat transcript handle used to continue a conversation.

    The transcript itself is stored in an adapter-owned parent-pointer tree.
    Agent code should pass this state back unchanged.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: NodeId


@dataclass
class _StreamingToolCallBuilder:
    """Accumulate one Chat streaming tool call until its JSON arguments are complete."""

    index: int
    call_id: str | None = None
    name_parts: list[str] = field(default_factory=list)
    argument_parts: list[str] = field(default_factory=list)

    def apply_delta(self, delta: ChoiceDeltaToolCall) -> None:
        """Merge one provider delta into this tool-call accumulator."""

        if delta.type is not None and delta.type != "function":
            raise ValueError(f"Unsupported Chat tool call type: {delta.type}")

        if delta.id is not None:
            if self.call_id is not None and self.call_id != delta.id:
                raise ValueError("Chat stream changed tool call id for one index")
            self.call_id = delta.id

        if delta.function is None:
            return

        # TODO: Provider fixtures would let us prove whether function.name is
        # always delivered once or may be split like arguments. Appending is the
        # OpenAI-compatible behavior, but this should be covered by adapter tests.
        if delta.function.name:
            self.name_parts.append(delta.function.name)
        if delta.function.arguments:
            self.argument_parts.append(delta.function.arguments)

    def build(self) -> ToolRunRequest:
        """Return the provider-neutral tool request once all deltas are present."""

        if self.call_id is None:
            raise ValueError("Chat stream tool call is missing id")

        tool_name = "".join(self.name_parts)
        if not tool_name:
            raise ValueError("Chat stream tool call is missing function name")

        raw_arguments = "".join(self.argument_parts)
        return ToolRunRequest(
            run_id=self.call_id,
            tool_name=tool_name,
            arguments=_parse_tool_arguments(raw_arguments),
            raw_arguments=raw_arguments,
        )


class ChatModelStream(ModelStream[ChatModelState]):
    """ModelStream wrapper that materializes a Chat stream into ModelAPI events."""

    def __init__(
        self,
        *,
        stream: AsyncStream[ChatCompletionChunk],
        state: ChatModelState,
    ) -> None:
        self._stream = stream
        self._state = state
        self._response: ModelResponse[ChatModelState] | None = None

    @property
    def response(self) -> ModelResponse[ChatModelState] | None:
        """Return the completed response after the Chat stream has been consumed."""

        return self._response

    async def __aiter__(self) -> AsyncIterator[ModelEvent]:
        """Yield provider-neutral events while preserving the final state."""

        text_started = False
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[ToolRunRequest] = []
        tool_call_builders: dict[int, _StreamingToolCallBuilder] = {}
        metadata: dict[str, object] = {}

        try:
            async for chunk in self._stream:
                metadata["chat_completion_id"] = chunk.id
                metadata["model"] = chunk.model
                if chunk.usage is not None:
                    metadata["usage"] = chunk.usage.model_dump()

                if chunk.choices:
                    choice = chunk.choices[0]
                    delta = choice.delta
                    metadata["finish_reason"] = choice.finish_reason

                    if delta.tool_calls:
                        _accumulate_stream_tool_call_deltas(
                            tool_call_builders,
                            delta.tool_calls,
                        )

                    if delta.content:
                        if not text_started:
                            text_started = True
                            yield ModelTextStartEvent()

                        text_parts.append(delta.content)
                        yield ModelTextDeltaEvent(delta=delta.content)

                    if delta.reasoning_content:
                        reasoning_parts.append(delta.reasoning_content)
        finally:
            await self._stream.close()

        text = "".join(text_parts) or None
        if reasoning_parts:
            metadata["reasoning_content"] = "".join(reasoning_parts)

        tool_calls = _tool_calls_from_stream_builders(tool_call_builders)
        if text_started:
            yield ModelTextDoneEvent(text=text or "")
        for tool_call in tool_calls:
            yield ModelToolCallEvent(tool_call=tool_call)

        next_state = _append_assistant_message(
            self._state,
            content=text,
            tool_calls=tool_calls,
        )
        self._response = ModelResponse(
            text=text,
            tool_calls=tool_calls,
            state=next_state,
            metadata=metadata,
        )


class ChatModelAPI(ModelAPI[ChatModelState]):
    """ModelAPI adapter for Chat Completions style providers.

    Chat has no server-side previous-response pointer, so the adapter owns the
    full message transcript behind `ChatModelState`.
    """

    def __init__(
        self,
        *,
        client: AsyncArk,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    @classmethod
    def initial_state(
        cls,
        *,
        system_prompt: str | None = None,
    ) -> ChatModelState:
        messages = (
            [SystemMessage(text=system_prompt)]
            if system_prompt is not None
            else []
        )
        return _state_from_history(messages)

    async def invoke(
        self,
        input: ModelInput,
        *,
        state: ChatModelState,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> ModelResponse[ChatModelState]:
        """Run a non-streaming Chat call and return a provider-neutral response."""

        messages, call_state = _messages_for_call(
            input,
            state=state,
        )
        response = await self._create_completion(
            messages,
            tools=tools,
            params=params,
        )
        return _model_response_from_completion(
            response,
            state=call_state,
        )

    async def structured_output[T](
        self,
        input: ModelInput,
        *,
        output_type: type[T],
        state: ChatModelState,
        params: ModelCallParams| None = ModelCallParams(),
    ) -> StructuredModelResponse[T, ChatModelState]:
        """Request JSON-schema output while preserving response state data."""

        messages, call_state = _messages_for_call(
            input,
            state=state,
        )
        response_format = ResponseFormatJSONSchema(
            type="json_schema",
            json_schema={
                "name": "response",
                "schema": TypeAdapter(output_type).json_schema(),
                "strict": True,
            },
        )
        response = await self._create_completion(
            messages,
            tools=None,
            params=params,
            response_format=response_format,
        )
        base_response = _model_response_from_completion(
            response,
            state=call_state,
        )

        parsed: T | None
        metadata = dict(base_response.metadata)
        try:
            if base_response.text is None:
                raise ValueError("structured output response has no text")
            parsed = TypeAdapter(output_type).validate_json(base_response.text)
        except (ValidationError, ValueError) as exc:
            parsed = None
            metadata["structured_output_error"] = str(exc)

        return StructuredModelResponse[T, ChatModelState](
            text=base_response.text,
            tool_calls=base_response.tool_calls,
            state=base_response.state,
            metadata=metadata,
            parsed=parsed,
        )

    async def stream(
        self,
        input: ModelInput,
        *,
        state: ChatModelState,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> ModelStream[ChatModelState]:
        """Start a Chat stream whose chunks are translated into ModelEvent values."""

        messages, call_state = _messages_for_call(
            input,
            state=state,
        )
        kwargs = self._completion_kwargs(params)
        kwargs.pop("stream", None)  # 由本函数固定为 True

        if tools:
            kwargs["tools"] = [_chat_param_from_tool(tool) for tool in tools]

        stream = cast(
            AsyncStream[ChatCompletionChunk],
            await self.client.chat.completions.create(
                model=self.model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                stream=True,
                **kwargs,
            ),
        )
        return ChatModelStream(stream=stream, state=call_state)

    async def dump_state(
        self,
        state: ChatModelState,
    ) -> ModelStateDump:
        """Materialize the Chat transcript behind state for persistence."""

        messages = await self.history(state)
        return ModelStateDump(
            format=_CHAT_MESSAGES_DUMP_FORMAT,
            format_version=_CHAT_MESSAGES_DUMP_FORMAT_VERSION,
            serialized=_MODEL_MESSAGE_LIST_ADAPTER.dump_json(messages).decode(),
            metadata={"model": self.model},
        )

    async def history(
        self,
        state: ChatModelState,
    ) -> list[ModelMessage]:
        state = _expect_chat_state(state)
        return _history_from_state(state)

    def state_from_history(
        self,
        history: Sequence[ModelMessage],
    ) -> ChatModelState:
        return _state_from_history(history)

    def restore_state(
        self,
        dump: ModelStateDump,
    ) -> ChatModelState:
        """Rebuild Chat state from a persisted dump."""

        return self.state_from_history(_history_from_dump(dump))

    async def _create_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = None,
        response_format: ResponseFormatJSONSchema | None = None,
    ) -> ChatCompletion:
        """Call Chat Completions after applying adapter-level parameter policy."""

        kwargs = self._completion_kwargs(params)
        kwargs.pop("stream", None)
        
        if tools:
            kwargs["tools"] = [_chat_param_from_tool(tool) for tool in tools]
        if response_format is not None:
            kwargs["response_format"] = response_format

        return cast(
            ChatCompletion,
            await self.client.chat.completions.create(
                model=self.model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                **kwargs,
            ),
        )

    def _completion_kwargs(
        self,
        params: ModelCallParams | None,
    ) -> dict[str, Any]:
        """Map provider-neutral per-call params to Chat Completions kwargs."""

        if params is None:
            params = ModelCallParams()

        kwargs: dict[str, Any] = {}

        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.top_p is not None:
            kwargs["top_p"] = params.top_p
        if params.max_output_tokens is not None:
            kwargs["max_tokens"] = params.max_output_tokens
        if params.thinking is not None:
            kwargs["thinking"] = {"type": params.thinking}

        if params.extra:
            safe_update(kwargs, params.extra)

        return kwargs


def _messages_for_call(
    input: ModelInput,
    *,
    state: ChatModelState,
) -> tuple[list[dict[str, Any]], ChatModelState]:
    """Build a fresh message transcript for one Chat provider call."""

    state = _state_with_appended_messages(
        _expect_chat_state(state),
        _messages_from_input(input),
    )
    return _chat_messages_from_history(_history_from_state(state)), state


def _messages_from_input(input: ModelInput) -> list[ModelMessage]:
    """Normalize ModelInput items while preserving item order."""

    items = [input] if isinstance(input, (UserMessage, ToolResultsMessage)) else input
    return list(items)


def _model_response_from_completion(
    completion: ChatCompletion,
    *,
    state: ChatModelState,
) -> ModelResponse[ChatModelState]:
    """Translate a completed Chat response into the ModelAPI response shape."""

    choice = completion.choices[0]
    message = choice.message
    tool_calls = _tool_calls_from_message(message)
    next_state = _append_assistant_message(
        state,
        content=message.content,
        tool_calls=tool_calls,
    )

    return ModelResponse(
        text=message.content,
        tool_calls=tool_calls,
        state=next_state,
        metadata={
            "chat_completion_id": completion.id,
            "finish_reason": choice.finish_reason,
            "model": completion.model,
            "usage": completion.usage.model_dump() if completion.usage else None,
        },
    )


def _append_assistant_message(
    state: ChatModelState,
    *,
    content: str | None,
    tool_calls: list[ToolRunRequest],
) -> ChatModelState:
    """Return a new state with the assistant response appended."""

    return _state_with_appended_messages(
        state,
        [
            AssistantMessage(
                text=content or "",
                tool_calls=tool_calls,
            )
        ],
    )


def _tool_calls_from_message(
    message: ChatCompletionMessage,
) -> list[ToolRunRequest]:
    """Parse Chat function calls into tool-layer run requests."""

    if not message.tool_calls:
        return []

    return [_run_request_from_tool_call(tool_call) for tool_call in message.tool_calls]


def _run_request_from_tool_call(
    tool_call: ChatCompletionMessageToolCall,
) -> ToolRunRequest:
    """Parse provider JSON arguments before they cross into agent core."""

    raw_arguments = tool_call.function.arguments
    arguments = _parse_tool_arguments(raw_arguments)
    return ToolRunRequest(
        run_id=tool_call.id,
        tool_name=tool_call.function.name,
        arguments=arguments,
        raw_arguments=raw_arguments,
    )


def _accumulate_stream_tool_call_deltas(
    builders: dict[int, _StreamingToolCallBuilder],
    deltas: list[ChoiceDeltaToolCall],
) -> None:
    """Accumulate indexed Chat tool-call deltas without exposing them to agents."""

    for delta in deltas:
        builder = builders.get(delta.index)
        if builder is None:
            builder = _StreamingToolCallBuilder(index=delta.index)
            builders[delta.index] = builder

        builder.apply_delta(delta)


def _tool_calls_from_stream_builders(
    builders: dict[int, _StreamingToolCallBuilder],
) -> list[ToolRunRequest]:
    """Build stream tool calls in provider index order after the stream completes."""

    return [
        builders[index].build()
        for index in sorted(builders)
    ]


def _parse_tool_arguments(raw_arguments: str) -> dict[str, object]:
    """Validate that provider tool arguments are a JSON object."""

    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("Chat tool arguments are not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Chat tool arguments must be a JSON object")

    return cast(dict[str, object], parsed)


def _chat_param_from_run_request(
    tool_call: ToolRunRequest,
) -> dict[str, Any]:
    """Serialize a tool run request back into an assistant tool_call message."""

    raw_arguments = tool_call.raw_arguments
    if raw_arguments is None:
        raw_arguments = json.dumps(tool_call.arguments, ensure_ascii=False)

    return {
        "id": tool_call.run_id,
        "type": "function",
        "function": {
            "name": tool_call.tool_name,
            "arguments": raw_arguments,
        },
    }


def _chat_param_from_tool(
    tool: ToolProtocol[BaseModel],
) -> ChatCompletionToolParam:
    """Create a Chat tool declaration from the project-level tool protocol."""

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_schema.model_json_schema(),
        },
    }


def _chat_messages_from_history(
    history: Sequence[ModelMessage],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in history:
        match message:
            case SystemMessage():
                messages.append({"role": "system", "content": message.text})
            case UserMessage():
                messages.append({"role": "user", "content": message.text})
            case AssistantMessage():
                chat_message: dict[str, Any] = {"role": "assistant"}
                if message.text or not message.tool_calls:
                    chat_message["content"] = message.text
                if message.tool_calls:
                    chat_message["tool_calls"] = [
                        _chat_param_from_run_request(tool_call)
                        for tool_call in message.tool_calls
                    ]
                messages.append(chat_message)
            case ToolResultsMessage():
                for result in message.results:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": result.run_id,
                            "content": result.output,
                        }
                    )
            case _:
                assert_never(message)
    return messages


def _state_from_history(
    messages: Sequence[ModelMessage],
) -> ChatModelState:
    """Create a root Chat state from one message segment."""

    # restore_state/initial_state 都从一个 root segment 开始。
    # 即使 messages 为空，也需要一个 root node 作为后续 append 的父节点。
    return ChatModelState(
        node_id=_CHAT_TRANSCRIPT.append(_message_segment(messages))
    )


def _state_with_appended_messages(
    state: ChatModelState,
    messages: Sequence[ModelMessage],
) -> ChatModelState:
    """Append one message segment under an existing Chat state."""

    if not messages:
        return state

    # 每次模型调用最多追加两个 segment：
    # 1. 用户输入/tool result
    # 2. assistant 响应
    # 历史长消息不会被复制，只在 materialize 给 Chat Completions 时沿 path 展开。
    return ChatModelState(
        node_id=_CHAT_TRANSCRIPT.append(
            _message_segment(messages),
            parent_id=state.node_id,
        )
    )


def _history_from_state(state: ChatModelState) -> list[ModelMessage]:
    """Materialize a Chat state into provider-neutral messages."""

    messages: list[ModelMessage] = []
    for segment in _CHAT_TRANSCRIPT.path(state.node_id):
        messages.extend(segment)
    return messages


def _message_segment(messages: Sequence[ModelMessage]) -> _ModelMessageSegment:
    """Store a small immutable segment of model messages."""

    return tuple(messages)


def _expect_chat_state(
    state: ModelState,
) -> ChatModelState:
    """Reject states that were not produced by ChatModelAPI."""

    if isinstance(state, ChatModelState):
        return state

    raise TypeError("ModelState was not produced by ChatModelAPI")


def _history_from_dump(dump: ModelStateDump) -> list[ModelMessage]:
    """Parse the Chat dump string and return model history messages."""

    if dump.object != _MODEL_STATE_DUMP_OBJECT:
        raise ValueError("ModelStateDump has unsupported object type")

    if dump.format != _CHAT_MESSAGES_DUMP_FORMAT:
        raise ValueError("ModelStateDump was not produced by ChatModelAPI")

    if dump.format_version != _CHAT_MESSAGES_DUMP_FORMAT_VERSION:
        raise ValueError("Unsupported Chat state dump format version")

    try:
        return _MODEL_MESSAGE_LIST_ADAPTER.validate_json(dump.serialized)
    except ValidationError as exc:
        raise ValueError("Chat state dump payload is not valid model history") from exc
