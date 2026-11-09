from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from aicore.models.credentials import AsyncArk, create_client
from aicore.models.doubao_models import ModelName
from aicore.models.model_api import (
    ModelCallParams,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    ModelToolCallEvent,
    UserMessage,
    ToolResultsMessage,
    create_chat_model_api,
    create_responses_model_api,
)
from aicore.models.model_api.chat_adapter import ChatModelAPI
from aicore.tools.run import ToolRunResult

pytestmark = pytest.mark.asyncio


class TinyAnswer(BaseModel):
    value: int
    label: str


class WeatherArgs(BaseModel):
    location: str


class TurnOffLightArgs(BaseModel):
    room: str


class DummyWeatherTool:
    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Get weather for a city"

    @property
    def args_schema(self) -> type[WeatherArgs]:
        return WeatherArgs


class DummyTurnOffLightTool:
    @property
    def name(self) -> str:
        return "turn_off_room_light"

    @property
    def description(self) -> str:
        return (
            "关闭指定房间的灯。收到请求超时且要求重试的工具结果时，"
            "继续用相同房间再次调用这个工具。"
        )

    @property
    def args_schema(self) -> type[TurnOffLightArgs]:
        return TurnOffLightArgs


@pytest.fixture(
    params=[
        pytest.param(("chat", ModelName.SEED_1_8_251228), id="chat"),
        pytest.param(("responses", ModelName.SEED_1_8_251228), id="responses"),
    ],
)
def live_model_api(request):
    backend, model_name = request.param
    client, model = create_client(model_name, AsyncArk)
    if backend == "chat":
        return create_chat_model_api(client=client, model=model)
    return create_responses_model_api(client=client, model=model)


@pytest.fixture
def short_params() -> ModelCallParams:
    return ModelCallParams(
        temperature=0,
        max_output_tokens=1024,
        thinking="disabled",
    )


async def _collect_stream_events(stream):
    return [event async for event in stream]


async def test_live_invoke_text_smoke(live_model_api, short_params) -> None:
    response = await live_model_api.invoke(
        UserMessage(text="请只回复 OK"),
        state=live_model_api.initial_state(system_prompt="你是一个简洁的测试助手。"),
        params=short_params,
    )

    assert response.text
    if isinstance(live_model_api, ChatModelAPI):
        assert "chat_completion_id" in response.metadata
        assert "model" in response.metadata
        assert "finish_reason" in response.metadata
    assert response.state is not None


async def test_live_stream_text_events_smoke(live_model_api, short_params) -> None:
    stream = await live_model_api.stream(
        UserMessage(text="请只回复 OK"),
        state=live_model_api.initial_state(system_prompt="你是一个简洁的测试助手。"),
        params=short_params,
    )

    events = await _collect_stream_events(stream)

    assert any(isinstance(event, ModelTextDeltaEvent) for event in events)
    assert any(isinstance(event, ModelTextDoneEvent) for event in events)
    start_indexes = [
        index for index, event in enumerate(events)
        if isinstance(event, ModelTextStartEvent)
    ]
    delta_indexes = [
        index for index, event in enumerate(events)
        if isinstance(event, ModelTextDeltaEvent)
    ]
    if start_indexes and delta_indexes:
        assert start_indexes[0] < delta_indexes[0]
    assert stream.response is not None
    assert stream.response.text


async def test_live_invoke_state_remembers_previous_turn(
    live_model_api,
    short_params,
) -> None:
    token = "REDACTED"
    first = await live_model_api.invoke(
        UserMessage(text=f"请记住这个 token，并只回复 OK：{token}"),
        state=live_model_api.initial_state(),
        params=short_params,
    )

    second = await live_model_api.invoke(
        UserMessage(text="刚才的 token 是什么？请只输出 token。"),
        state=first.state,
        params=short_params,
    )

    assert second.text
    assert token in second.text


async def test_live_empty_state_does_not_leak_previous_turn(
    live_model_api,
    short_params,
) -> None:
    token = "REDACTED"
    first = await live_model_api.invoke(
        UserMessage(text=f"请记住这个 token，并只回复 OK：{token}"),
        state=live_model_api.initial_state(),
        params=short_params,
    )

    second = await live_model_api.invoke(
        UserMessage(text="刚才的 token 是什么？请只输出 token。"),
        state=live_model_api.initial_state(),
        params=short_params,
    )

    assert first.state is not None
    assert second.text
    assert token not in second.text


async def test_live_dump_restore_state_round_trip(
    live_model_api,
    short_params,
) -> None:
    token = "REDACTED"
    first = await live_model_api.invoke(
        UserMessage(text=f"请记住这个 token，并只回复 OK：{token}"),
        state=live_model_api.initial_state(),
        params=short_params,
    )

    dump = await live_model_api.dump_state(first.state)
    assert dump.object == "model_state_dump"
    expected_format = "model.history" if isinstance(live_model_api, ChatModelAPI) else "responses.state"
    assert dump.format == expected_format
    assert dump.format_version == 1
    assert json.loads(dump.serialized)

    restored = live_model_api.restore_state(dump)
    second = await live_model_api.invoke(
        UserMessage(text="刚才的 token 是什么？请只输出 token。"),
        state=restored,
        params=short_params,
    )

    assert second.text
    assert token in second.text


async def test_live_structured_output_smoke(live_model_api, short_params) -> None:
    response = await live_model_api.structured_output(
        UserMessage(text='返回 value=7, label="seven"。'),
        output_type=TinyAnswer,
        state=live_model_api.initial_state(system_prompt="只输出符合 schema 的 JSON。"),
        params=short_params,
    )

    assert response.text
    assert response.parsed is not None
    assert response.parsed.value == 7
    assert "seven" in response.parsed.label.lower()


async def test_live_invoke_tool_call_request(live_model_api, short_params) -> None:
    response = await live_model_api.invoke(
        UserMessage(text="必须调用 get_weather 工具查询上海天气，不要直接回答天气内容。"),
        state=live_model_api.initial_state(),
        tools=[DummyWeatherTool()],
        params=short_params,
    )

    assert response.tool_calls
    tool_call = response.tool_calls[0]
    assert tool_call.tool_name == "get_weather"
    assert tool_call.raw_arguments
    location = tool_call.arguments.get("location")
    assert isinstance(location, str)
    assert "上海" in location or "Shanghai" in location


async def test_live_tool_result_state(live_model_api, short_params) -> None:
    first = await live_model_api.invoke(
        UserMessage(text="必须调用 get_weather 工具查询上海天气，不要直接回答天气内容。"),
        state=live_model_api.initial_state(),
        tools=[DummyWeatherTool()],
        params=short_params,
    )
    assert first.tool_calls
    tool_call = first.tool_calls[0]

    second = await live_model_api.invoke(
        ToolResultsMessage(
            results=[
                ToolRunResult(
                    run_id=tool_call.run_id,
                    output="上海今天晴，气温 20 到 26 摄氏度。",
                )
            ]
        ),
        state=first.state,
        params=short_params,
    )

    assert second.text
    assert "摄氏度" in second.text


async def test_live_empty_tools_do_not_leak_previous_tool(
    live_model_api,
    short_params,
) -> None:
    """实验：观察工具调用历史是否会在后续回合泄露为新的 tool call。

    实验过程：
    1. 注册一个“关闭房间灯”的工具，让模型在工具返回“请求超时，请重试”
       后继续调用同一个工具，先稳定复现多轮工具调用链路。
    2. 达到指定轮数后，将本轮 tools 显式置空，并追加“当前无法继续执行
       任何工具，必须直接回答”的用户提示。
    3. 断言最后一轮不再产生 tool_calls。

    实验结论：
    只依赖“不再传 tools”并不稳妥；模型仍可能根据历史对话里的工具名称、
    参数和调用结果推测旧工具并继续发起 tool call。更稳妥的收口方式是：
    清空 tools 的同时，显式提示模型当前不能再调用工具，必须基于现有信息回答。
    """
    light_tool = DummyTurnOffLightTool()
    response = await live_model_api.invoke(
        UserMessage(text="请关闭书房的灯。必须调用 turn_off_room_light 工具，不要直接回答。"),
        state=live_model_api.initial_state(
            system_prompt=(
                "你是工具调用泄露测试助手。只要 turn_off_room_light 工具可用，"
                "收到工具结果“请求超时，请重试”后必须再次调用该工具，"
                "并保持 room 参数不变。"
                "不要直接输出自然语言答案。"
            ),
        ),
        tools=[light_tool],
        params=short_params,
    )

    assert response.tool_calls
    assert all(
        tool_call.tool_name == light_tool.name
        and isinstance(tool_call.arguments.get("room"), str)
        for tool_call in response.tool_calls
    )

    max_timeout_rounds = 4
    timeout_round = 0

    while response.tool_calls and timeout_round < max_timeout_rounds:
        timeout_round += 1
        tools = (
            [light_tool]
            if timeout_round < max_timeout_rounds
            else []
        )

        input_list = [ToolResultsMessage(
            results=[
                ToolRunResult(
                    run_id=tool_call.run_id,
                    output="请求超时，请重试",
                )
                for tool_call in response.tool_calls
            ]
        )]

        if not tools:
            input_list += [UserMessage(text="受限于工具调用次数，当前无法继续执行任何工具，必须根据现有信息直接给出回答！")]

        response = await live_model_api.invoke(
            input_list,
            state=response.state,
            tools=tools,
            params=short_params,
        )

        if not tools:
            assert response.tool_calls == []
            break

        assert response.tool_calls
        assert all(
            tool_call.tool_name == light_tool.name
            and isinstance(tool_call.arguments.get("room"), str)
            for tool_call in response.tool_calls
        )
    else:
        pytest.fail("模型在清空 tools 前没有稳定复现 tool 重试链路")


async def test_live_stream_tool_call_request(live_model_api, short_params) -> None:
    stream = await live_model_api.stream(
        UserMessage(text="必须调用 get_weather 工具查询上海天气，不要直接回答天气内容。"),
        state=live_model_api.initial_state(),
        tools=[DummyWeatherTool()],
        params=short_params,
    )

    events = await _collect_stream_events(stream)
    tool_events = [
        event for event in events
        if isinstance(event, ModelToolCallEvent)
    ]

    assert tool_events
    assert stream.response is not None
    assert stream.response.tool_calls == [
        event.tool_call for event in tool_events
    ]
