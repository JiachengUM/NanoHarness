from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest
from pydantic import BaseModel
from volcenginesdkarkruntime.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
)
from volcenginesdkarkruntime.types.chat.chat_completion import Choice
from volcenginesdkarkruntime.types.chat.chat_completion_chunk import (
    Choice as ChunkChoice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from volcenginesdkarkruntime.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from volcenginesdkarkruntime.types.completion_usage import CompletionUsage

from aicore.models.model_api.chat_adapter import (
    ChatModelAPI,
)
from aicore.models.model_api.events import (
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelToolCallEvent,
)
from aicore.models.model_api.types import (
    ModelCallParams,
    ModelState,
    ModelStateDump,
    UserMessage,
    ToolResultsMessage,
)
from aicore.tools.run import ToolRunRequest, ToolRunResult

pytestmark = pytest.mark.asyncio


class WeatherArgs(BaseModel):
    location: str


class OtherModelState(ModelState):
    pass


class DummyWeatherTool:
    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Get weather by location"

    @property
    def args_schema(self) -> type[WeatherArgs]:
        return WeatherArgs


class FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(deepcopy(kwargs))
        if not self._responses:
            raise AssertionError("FakeCompletions received an unexpected call")
        return self._responses.pop(0)


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.completions = FakeCompletions(responses)
        self.chat = FakeChat(self.completions)


class FakeAsyncStream:
    def __init__(
        self,
        chunks: list[ChatCompletionChunk],
        *,
        error_at: int | None = None,
    ) -> None:
        self._chunks = chunks
        self._error_at = error_at
        self.closed = False

    async def __aiter__(self) -> Any:
        for index, chunk in enumerate(self._chunks):
            if self._error_at == index:
                raise RuntimeError("stream exploded")
            yield chunk

        if self._error_at == len(self._chunks):
            raise RuntimeError("stream exploded")

    async def close(self) -> None:
        self.closed = True


def _api_with_responses(*responses: object) -> tuple[ChatModelAPI, FakeCompletions]:
    client = FakeClient(list(responses))
    return (
        ChatModelAPI(client=cast(Any, client), model="test-chat-model"),
        client.completions,
    )


def _usage() -> CompletionUsage:
    return CompletionUsage(
        completion_tokens=3,
        prompt_tokens=4,
        total_tokens=7,
    )


def _completion(
    *,
    content: str | None = "hello",
    tool_calls: list[ChatCompletionMessageToolCall] | None = None,
    finish_reason: str = "stop",
    completion_id: str = "cmpl-1",
    model: str = "test-chat-model",
    usage: CompletionUsage | None = None,
) -> ChatCompletion:
    return ChatCompletion(
        id=completion_id,
        choices=[
            Choice(
                finish_reason=cast(Any, finish_reason),
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                ),
            )
        ],
        created=1,
        model=model,
        service_tier=None,
        object="chat.completion",
        usage=usage,
    )


def _chunk(
    *,
    content: str | None = None,
    tool_calls: list[ChoiceDeltaToolCall] | None = None,
    reasoning_content: str | None = None,
    finish_reason: str | None = None,
    chunk_id: str = "chunk-1",
    model: str = "test-chat-model",
    usage: CompletionUsage | None = None,
) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        choices=[
            ChunkChoice(
                index=0,
                delta=ChoiceDelta(
                    content=content,
                    tool_calls=tool_calls,
                    reasoning_content=reasoning_content,
                ),
                finish_reason=cast(Any, finish_reason),
            )
        ],
        created=1,
        model=model,
        service_tier=None,
        object="chat.completion.chunk",
        usage=usage,
    )


def _tool_call(
    *,
    call_id: str = "call-1",
    name: str = "get_weather",
    arguments: str = '{"location":"上海"}',
) -> ChatCompletionMessageToolCall:
    return ChatCompletionMessageToolCall(
        id=call_id,
        type="function",
        function=Function(
            name=name,
            arguments=arguments,
        ),
    )


def _tool_delta(
    *,
    index: int = 0,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
    type_: str | None = "function",
) -> ChoiceDeltaToolCall:
    return ChoiceDeltaToolCall(
        index=index,
        id=call_id,
        type=cast(Any, type_),
        function=ChoiceDeltaToolCallFunction(
            name=name,
            arguments=arguments,
        ),
    )


async def _dumped_messages(
    api: ChatModelAPI,
    state: ModelState,
) -> list[dict[str, Any]]:
    dump = await api.dump_state(state)
    messages = cast(list[dict[str, Any]], json.loads(dump.serialized))
    result: list[dict[str, Any]] = []
    for message in messages:
        if message["type"] == "system":
            result.append({"role": "system", "content": message["text"]})
        elif message["type"] == "user":
            result.append({"role": "user", "content": message["text"]})
        elif message["type"] == "assistant":
            chat_message: dict[str, Any] = {"role": "assistant"}
            if message["text"] or not message["tool_calls"]:
                chat_message["content"] = message["text"]
            if message["tool_calls"]:
                chat_message["tool_calls"] = [
                    {
                        "id": tool_call["run_id"],
                        "type": "function",
                        "function": {
                            "name": tool_call["tool_name"],
                            "arguments": tool_call["raw_arguments"],
                        },
                    }
                    for tool_call in message["tool_calls"]
                ]
            result.append(chat_message)
        elif message["type"] == "tool_result":
            result.extend(
                {
                    "role": "tool",
                    "tool_call_id": tool_result["run_id"],
                    "content": tool_result["output"],
                }
                for tool_result in message["results"]
            )
    return result


async def test_invoke_sends_system_prompt_and_text_input() -> None:
    api, completions = _api_with_responses(_completion(content="hi"))

    response = await api.invoke(
        UserMessage(text="hello"),
        state=api.initial_state(system_prompt="be brief"),
    )

    assert completions.calls[0]["model"] == "test-chat-model"
    assert completions.calls[0]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
    ]
    assert "stream" not in completions.calls[0]
    assert response.text == "hi"
    assert await _dumped_messages(api, response.state) == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


async def test_invoke_appends_without_mutating_source_state() -> None:
    api, completions = _api_with_responses(
        _completion(content="old answer"),
        _completion(content="new answer"),
    )

    source = await api.invoke(
        UserMessage(text="old"),
        state=api.initial_state(),
    )

    response = await api.invoke(
        UserMessage(text="new question"),
        state=source.state,
    )

    source_messages = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "old answer"},
    ]
    assert completions.calls[1]["messages"] == [
        *source_messages,
        {"role": "user", "content": "new question"},
    ]
    assert await _dumped_messages(api, source.state) == source_messages
    assert await _dumped_messages(api, response.state) == [
        *source_messages,
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "new answer"},
    ]


async def test_invoke_expands_tool_results_in_order() -> None:
    api, completions = _api_with_responses(_completion(content="done"))

    await api.invoke(
        [
            ToolResultsMessage(
                results=[
                    ToolRunResult(run_id="call-1", output="first"),
                    ToolRunResult(run_id="call-2", output="second"),
                ]
            ),
            UserMessage(text="finish"),
        ],
        state=api.initial_state(),
    )

    assert completions.calls[0]["messages"] == [
        {"role": "tool", "tool_call_id": "call-1", "content": "first"},
        {"role": "tool", "tool_call_id": "call-2", "content": "second"},
        {"role": "user", "content": "finish"},
    ]


async def test_invoke_maps_params_and_tools() -> None:
    api, completions = _api_with_responses(_completion(content="using tool"))

    await api.invoke(
        UserMessage(text="weather"),
        state=api.initial_state(),
        tools=[DummyWeatherTool()],
        params=ModelCallParams(
            temperature=0.2,
            top_p=0.9,
            max_output_tokens=42,
        ),
    )

    call = completions.calls[0]
    assert call["temperature"] == 0.2
    assert call["top_p"] == 0.9
    assert call["max_tokens"] == 42
    assert call["tools"][0]["type"] == "function"
    assert call["tools"][0]["function"]["name"] == "get_weather"
    assert call["tools"][0]["function"]["description"] == "Get weather by location"
    assert call["tools"][0]["function"]["parameters"]["properties"]["location"][
        "type"
    ] == "string"


async def test_invoke_returns_text_response_and_metadata() -> None:
    api, _ = _api_with_responses(
        _completion(
            content="hello",
            completion_id="cmpl-42",
            model="model-from-provider",
            usage=_usage(),
        )
    )

    response = await api.invoke(
        UserMessage(text="hi"),
        state=api.initial_state(),
    )

    assert response.text == "hello"
    assert response.tool_calls == []
    assert response.metadata == {
        "chat_completion_id": "cmpl-42",
        "finish_reason": "stop",
        "model": "model-from-provider",
        "usage": {
            "completion_tokens": 3,
            "prompt_tokens": 4,
            "total_tokens": 7,
            "prompt_tokens_details": None,
            "completion_tokens_details": None,
        },
    }


async def test_invoke_returns_tool_calls_with_parsed_arguments() -> None:
    raw_arguments = '{"location":"上海","unit":"c"}'
    api, _ = _api_with_responses(
        _completion(
            content="checking",
            tool_calls=[
                _tool_call(
                    call_id="call-weather",
                    name="get_weather",
                    arguments=raw_arguments,
                )
            ],
            finish_reason="tool_calls",
        )
    )

    response = await api.invoke(
        UserMessage(text="weather"),
        state=api.initial_state(),
    )

    assert response.text == "checking"
    assert response.tool_calls == [
        ToolRunRequest(
            run_id="call-weather",
            tool_name="get_weather",
            arguments={"location": "上海", "unit": "c"},
            raw_arguments=raw_arguments,
        )
    ]
    assert (await _dumped_messages(api, response.state))[-1] == {
        "role": "assistant",
        "content": "checking",
        "tool_calls": [
            {
                "id": "call-weather",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": raw_arguments,
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("raw_arguments", "match"),
    [
        ("not-json", "not valid JSON"),
        ("[]", "must be a JSON object"),
    ],
)
async def test_invoke_rejects_invalid_tool_arguments(
    raw_arguments: str,
    match: str,
) -> None:
    api, _ = _api_with_responses(
        _completion(
            tool_calls=[_tool_call(arguments=raw_arguments)],
            finish_reason="tool_calls",
        )
    )

    with pytest.raises(ValueError, match=match):
        await api.invoke(
            UserMessage(text="weather"),
            state=api.initial_state(),
        )


async def test_invoke_adds_empty_assistant_content_for_empty_message() -> None:
    api, _ = _api_with_responses(_completion(content=None))

    response = await api.invoke(
        UserMessage(text="empty"),
        state=api.initial_state(),
    )

    assert response.text is None
    assert (await _dumped_messages(api, response.state))[-1] == {
        "role": "assistant",
        "content": "",
    }


async def test_structured_output_parses_valid_json() -> None:
    class TinyAnswer(BaseModel):
        value: int
        label: str

    api, completions = _api_with_responses(
        _completion(content='{"value":7,"label":"seven"}')
    )

    response = await api.structured_output(
        UserMessage(text="return json"),
        output_type=TinyAnswer,
        state=api.initial_state(),
    )

    assert isinstance(response.parsed, TinyAnswer)
    assert response.parsed.value == 7
    assert response.parsed.label == "seven"
    response_format = completions.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "response"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["properties"]["value"][
        "type"
    ] == "integer"
    assert "tools" not in completions.calls[0]


async def test_structured_output_records_parse_error() -> None:
    class TinyAnswer(BaseModel):
        value: int

    api, _ = _api_with_responses(_completion(content='{"value":"nope"}'))

    response = await api.structured_output(
        UserMessage(text="return json"),
        output_type=TinyAnswer,
        state=api.initial_state(),
    )

    assert response.parsed is None
    assert response.text == '{"value":"nope"}'
    assert "structured_output_error" in response.metadata
    assert await _dumped_messages(api, response.state) == [
        {"role": "user", "content": "return json"},
        {"role": "assistant", "content": '{"value":"nope"}'},
    ]


async def test_stream_emits_text_events_and_sets_response() -> None:
    fake_stream = FakeAsyncStream(
        [
            _chunk(content="he"),
            _chunk(content="llo", finish_reason="stop", usage=_usage()),
        ]
    )
    api, completions = _api_with_responses(fake_stream)

    stream = await api.stream(
        UserMessage(text="say hello"),
        state=api.initial_state(),
    )

    assert stream.response is None
    events = [event async for event in stream]

    assert fake_stream.closed is True
    assert completions.calls[0]["stream"] is True
    assert [event.type for event in events] == [
        "model.text.start",
        "model.text.delta",
        "model.text.delta",
        "model.text.done",
    ]
    assert [event.delta for event in events if isinstance(event, ModelTextDeltaEvent)] == [
        "he",
        "llo",
    ]
    assert [event.text for event in events if isinstance(event, ModelTextDoneEvent)] == [
        "hello"
    ]
    assert stream.response is not None
    assert stream.response.text == "hello"
    assert stream.response.metadata["finish_reason"] == "stop"
    assert (await _dumped_messages(api, stream.response.state))[-1] == {
        "role": "assistant",
        "content": "hello",
    }


async def test_stream_closes_provider_stream_on_error() -> None:
    fake_stream = FakeAsyncStream(
        [_chunk(content="partial")],
        error_at=1,
    )
    api, _ = _api_with_responses(fake_stream)
    stream = await api.stream(
        UserMessage(text="explode"),
        state=api.initial_state(),
    )

    with pytest.raises(RuntimeError, match="stream exploded"):
        _ = [event async for event in stream]

    assert fake_stream.closed is True
    assert stream.response is None


async def test_stream_aggregates_tool_call_deltas() -> None:
    fake_stream = FakeAsyncStream(
        [
            _chunk(reasoning_content="think "),
            _chunk(
                tool_calls=[
                    _tool_delta(
                        index=0,
                        call_id="call-1",
                        name="get_weather",
                        arguments='{"location"',
                    )
                ]
            ),
            _chunk(
                tool_calls=[
                    _tool_delta(
                        index=0,
                        arguments=':"上海"}',
                    )
                ],
                reasoning_content="hard",
                finish_reason="tool_calls",
            ),
        ]
    )
    api, _ = _api_with_responses(fake_stream)

    stream = await api.stream(
        UserMessage(text="weather"),
        state=api.initial_state(),
    )
    events = [event async for event in stream]

    assert len(events) == 1
    assert isinstance(events[0], ModelToolCallEvent)
    assert events[0].tool_call == ToolRunRequest(
        run_id="call-1",
        tool_name="get_weather",
        arguments={"location": "上海"},
        raw_arguments='{"location":"上海"}',
    )
    assert stream.response is not None
    assert stream.response.text is None
    assert stream.response.tool_calls == [events[0].tool_call]
    assert stream.response.metadata["reasoning_content"] == "think hard"


async def test_stream_orders_multiple_tool_calls_by_index() -> None:
    fake_stream = FakeAsyncStream(
        [
            _chunk(
                tool_calls=[
                    _tool_delta(
                        index=1,
                        call_id="call-b",
                        name="second_tool",
                        arguments='{"b":2}',
                    ),
                    _tool_delta(
                        index=0,
                        call_id="call-a",
                        name="first_tool",
                        arguments='{"a":1}',
                    ),
                ],
                finish_reason="tool_calls",
            ),
        ]
    )
    api, _ = _api_with_responses(fake_stream)

    stream = await api.stream(
        UserMessage(text="tools"),
        state=api.initial_state(),
    )
    events = [event async for event in stream]

    assert [event.tool_call.run_id for event in events] == ["call-a", "call-b"]
    assert [event.tool_call.arguments for event in events] == [{"a": 1}, {"b": 2}]


async def test_stream_rejects_invalid_tool_call_delta_type() -> None:
    invalid_delta = ChoiceDeltaToolCall.model_construct(
        index=0,
        id="call-1",
        type="unsupported",
        function=None,
    )
    fake_stream = FakeAsyncStream([_chunk(tool_calls=[invalid_delta])])
    api, _ = _api_with_responses(fake_stream)

    stream = await api.stream(
        UserMessage(text="tools"),
        state=api.initial_state(),
    )

    with pytest.raises(ValueError, match="Unsupported Chat tool call type"):
        _ = [event async for event in stream]

    assert fake_stream.closed is True


async def test_stream_rejects_changed_tool_call_id() -> None:
    fake_stream = FakeAsyncStream(
        [
            _chunk(
                tool_calls=[
                    _tool_delta(index=0, call_id="call-1", name="tool"),
                ]
            ),
            _chunk(
                tool_calls=[
                    _tool_delta(index=0, call_id="call-2", arguments="{}"),
                ],
            ),
        ]
    )
    api, _ = _api_with_responses(fake_stream)

    stream = await api.stream(
        UserMessage(text="tools"),
        state=api.initial_state(),
    )

    with pytest.raises(ValueError, match="changed tool call id"):
        _ = [event async for event in stream]


async def test_stream_rejects_missing_tool_call_name() -> None:
    fake_stream = FakeAsyncStream(
        [
            _chunk(
                tool_calls=[
                    _tool_delta(index=0, call_id="call-1", arguments="{}"),
                ],
                finish_reason="tool_calls",
            ),
        ]
    )
    api, _ = _api_with_responses(fake_stream)

    stream = await api.stream(
        UserMessage(text="tools"),
        state=api.initial_state(),
    )

    with pytest.raises(ValueError, match="missing function name"):
        _ = [event async for event in stream]


async def test_state_can_branch_without_mutating_source() -> None:
    api, completions = _api_with_responses(
        _completion(content="base answer"),
        _completion(content="left answer"),
        _completion(content="right answer"),
    )

    base = await api.invoke(
        UserMessage(text="base"),
        state=api.initial_state(),
    )

    left = await api.invoke(
        UserMessage(text="left"),
        state=base.state,
    )
    right = await api.invoke(
        UserMessage(text="right"),
        state=base.state,
    )

    base_messages = [
        {"role": "user", "content": "base"},
        {"role": "assistant", "content": "base answer"},
    ]
    assert completions.calls[1]["messages"] == [
        *base_messages,
        {"role": "user", "content": "left"},
    ]
    assert completions.calls[2]["messages"] == [
        *base_messages,
        {"role": "user", "content": "right"},
    ]
    assert await _dumped_messages(api, base.state) == base_messages
    assert await _dumped_messages(api, left.state) == [
        *base_messages,
        {"role": "user", "content": "left"},
        {"role": "assistant", "content": "left answer"},
    ]
    assert await _dumped_messages(api, right.state) == [
        *base_messages,
        {"role": "user", "content": "right"},
        {"role": "assistant", "content": "right answer"},
    ]


async def test_state_can_continue_with_new_adapter_instance() -> None:
    first_api, _ = _api_with_responses(_completion(content="first answer"))
    first = await first_api.invoke(
        UserMessage(text="first"),
        state=first_api.initial_state(),
    )

    second_api, second_completions = _api_with_responses(
        _completion(content="second answer")
    )
    second = await second_api.invoke(
        UserMessage(text="second"),
        state=first.state,
    )

    assert second_completions.calls[0]["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second"},
    ]
    assert await _dumped_messages(second_api, second.state) == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "second answer"},
    ]


async def test_dump_state_uses_top_level_envelope() -> None:
    messages = [
        {"type": "system", "text": "be brief"},
        {"type": "user", "text": "hello"},
        {"type": "assistant", "text": "hi", "tool_calls": []},
    ]
    api, _ = _api_with_responses(_completion(content="hi"))

    response = await api.invoke(
        UserMessage(text="hello"),
        state=api.initial_state(system_prompt="be brief"),
    )
    dump = await api.dump_state(response.state)

    assert dump.object == "model_state_dump"
    assert dump.format == "model.history"
    assert dump.format_version == 1
    assert dump.metadata == {"model": "test-chat-model"}
    assert json.loads(dump.serialized) == messages


async def test_dump_and_restore_state_round_trip() -> None:
    dumped_messages = [
        {"type": "user", "text": "hello"},
        {"type": "assistant", "text": "hi", "tool_calls": []},
    ]
    chat_messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    api, completions = _api_with_responses(
        _completion(content="hi"),
        _completion(content="there"),
    )

    first = await api.invoke(
        UserMessage(text="hello"),
        state=api.initial_state(),
    )
    dump = await api.dump_state(first.state)
    state = api.restore_state(dump)
    second = await api.invoke(
        UserMessage(text="again"),
        state=state,
    )

    assert json.loads(dump.serialized) == dumped_messages
    assert completions.calls[1]["messages"] == [
        *chat_messages,
        {"role": "user", "content": "again"},
    ]
    assert await _dumped_messages(api, second.state) == [
        *chat_messages,
        {"role": "user", "content": "again"},
        {"role": "assistant", "content": "there"},
    ]


@pytest.mark.parametrize(
    ("state", "operation"),
    [
        (OtherModelState(), "invoke"),
        (OtherModelState(), "dump"),
    ],
)
async def test_rejects_non_chat_state(
    state: ModelState,
    operation: str,
) -> None:
    api, _ = _api_with_responses(_completion(content="unused"))

    with pytest.raises(TypeError, match="not produced by ChatModelAPI"):
        if operation == "invoke":
            await api.invoke(
                UserMessage(text="hello"),
                state=state,
            )
        else:
            await api.dump_state(state)


@pytest.mark.parametrize(
    ("updates", "match"),
    [
        ({"object": "other"}, "unsupported object"),
        ({"format": "responses.history"}, "ChatModelAPI"),
        ({"format_version": 2}, "format version"),
    ],
)
async def test_restore_rejects_invalid_dump_envelope(
    updates: dict[str, object],
    match: str,
) -> None:
    dump = ModelStateDump(
        format="model.history",
        format_version=1,
        serialized=json.dumps([{"type": "user", "text": "hello"}]),
    ).model_copy(update=updates)
    api, _ = _api_with_responses()

    with pytest.raises(ValueError, match=match):
        api.restore_state(dump)


@pytest.mark.parametrize(
    ("serialized", "match"),
    [
        ("not json", "not valid model history"),
        (json.dumps({"messages": []}), "not valid model history"),
        (json.dumps([[]]), "not valid model history"),
        (json.dumps([{"text": "missing type"}]), "not valid model history"),
    ],
)
async def test_restore_rejects_invalid_dump_payload(
    serialized: str,
    match: str,
) -> None:
    dump = ModelStateDump(
        format="model.history",
        format_version=1,
        serialized=serialized,
    )
    api, _ = _api_with_responses()

    with pytest.raises(ValueError, match=match):
        api.restore_state(dump)


async def test_invoke_rejects_unsupported_input_item() -> None:
    api, _ = _api_with_responses(_completion(content="unused"))

    with pytest.raises(TypeError, match="not iterable"):
        await api.invoke(
            cast(Any, object()),
            state=api.initial_state(),
        )
