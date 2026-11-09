from __future__ import annotations

from typing import Any

from rich import print

from aicore.models.model_api import create_model_api

from tests.models.model_api._model_api_examples_common import (
    DummyWeatherTool,
    ModelExampleCase,
    iter_model_cases,
    print_case_header,
    print_event_summary,
    print_exception,
    print_model_event,
    print_model_response,
    print_step,
    run_async,
    short_params,
    simulated_tool_results_input,
    text_input,
)


async def _consume_stream(title: str, stream: Any) -> list[Any]:
    print(f"\n[bold]{title} events[/bold]")
    events: list[Any] = []
    async for event in stream:
        events.append(event)
        print_model_event(event)

    print_event_summary(events)
    print_model_response(f"{title} final response", stream.response)
    return events


async def example_streaming_model_api_flow(
    case: ModelExampleCase,
) -> None:
    """演示 ModelAPI streaming 的一条完整使用流程。

    步骤包括：
    1. 发起文本 stream，逐个消费 ModelTextStartEvent、ModelTextDeltaEvent 和 ModelTextDoneEvent。
    2. stream 被完整消费后，通过 stream.response 读取最终 ModelResponse。
    3. 注册工具并发起 stream，读取 ModelToolCallEvent。
    4. 模拟执行流式工具调用，并把 ToolResultsMessage 回填给模型继续生成最终回答。
    5. 使用循环处理模型请求工具、执行工具、回填结果、继续流式调用，直到模型给出最终回答。
    6. 结束工具阶段后清空 tools，并通过用户提示把流程收束到直接回答。
    7. 按 ModelEvent 类型统计本轮事件，展示不同 backend 在同一抽象层下的事件形态。
    """
    print_case_header("ModelAPI streaming example", case)
    api = create_model_api(backend=case.backend, model=case.model_name)
    params = short_params(max_output_tokens=256)

    print_step("1. 文本 stream：逐个消费 ModelEvent")
    state = api.initial_state(system_prompt="你是一个简洁的流式输出示例助手。")
    query = "用一句话介绍上海，控制在 30 字以内。"
    print(f"user: {query}")
    stream = await api.stream(
        text_input(query),
        state=state,
        params=params,
    )
    await _consume_stream("文本 stream", stream)

    if stream.response is None:
        print("文本 stream 没有最终 response，后续依赖 state 的步骤跳过。")
        return

    state = stream.response.state

    print_step("2. 使用 stream.response 继续下一轮")
    query = "把上面的回答改成英文，仍然保持一句话。"
    print(f"user: {query}")
    stream = await api.stream(
        text_input(query),
        state=state,
        params=params,
    )
    await _consume_stream("续聊文本 stream", stream)

    print_step("3. 流式工具调用：读取 ModelToolCallEvent")
    weather_tool = DummyWeatherTool()
    tool_state = api.initial_state(
        system_prompt="需要天气信息时调用 get_weather 工具，不要编造天气。",
    )
    query = "请调用 get_weather 工具查询上海天气，不要直接回答天气内容。"
    print(f"user: {query}")
    tool_stream = await api.stream(
        text_input(query),
        state=tool_state,
        tools=[weather_tool],
        params=params,
    )
    await _consume_stream("工具调用 stream", tool_stream)

    print_step("4. 模拟执行流式工具调用，并回填 ToolResultsMessage")
    if tool_stream.response is None:
        print("工具 stream 没有最终 response，跳过工具回填。")
    elif not tool_stream.response.tool_calls:
        print("模型本轮没有发起工具调用，跳过工具回填。")
    else:
        tool_results = simulated_tool_results_input(tool_stream.response.tool_calls)
        print(f"tool results input: {tool_results}")
        result_stream = await api.stream(
            tool_results,
            state=tool_stream.response.state,
            params=params,
        )
        await _consume_stream("工具结果回填 stream", result_stream)

    print_step("5. 工具循环：请求工具、执行工具、回填结果，直到出现最终回答")
    loop_state = api.initial_state(
        system_prompt="你是一个工具调用示例助手。需要天气信息时先调用工具。",
    )
    current_input: Any = text_input("请查询上海天气，再根据天气给一句出行建议。")
    current_tools: list[Any] | None = [weather_tool]
    latest_response: Any = None

    for round_index in range(1, 4):
        print(f"\n[bold]tool loop round {round_index}[/bold]")
        loop_stream = await api.stream(
            current_input,
            state=loop_state,
            tools=current_tools,
            params=params,
        )
        await _consume_stream(f"工具循环 round {round_index}", loop_stream)

        latest_response = loop_stream.response
        if latest_response is None:
            print("本轮 stream 没有最终 response，结束工具循环。")
            break

        loop_state = latest_response.state
        if not latest_response.tool_calls:
            print("本轮已经得到自然语言回复，结束工具循环。")
            break

        current_input = simulated_tool_results_input(latest_response.tool_calls)
        print(f"下一轮输入改为工具结果: {current_input}")
        current_tools = []

    print_step("6. 清空 tools 后，将流程收束到直接回答")
    if latest_response is None:
        print("没有可继续的 latest_response，跳过收束步骤。")
    else:
        query = "当前不再提供工具。请基于已有信息，用一句话总结给用户。"
        print(f"user: {query}")
        closing_stream = await api.stream(
            text_input(query),
            state=latest_response.state,
            tools=[],
            params=params,
        )
        await _consume_stream("清空 tools 后的收束 stream", closing_stream)


def main() -> None:
    """运行 streaming 主流程示例，覆盖文本事件、最终 response、流式工具调用、工具回填和事件统计。"""
    for case in iter_model_cases():
        try:
            run_async(example_streaming_model_api_flow(case))
        except Exception as exc:
            print_exception(f"streaming example failed: {case.label}", exc)


if __name__ == "__main__":
    main()
