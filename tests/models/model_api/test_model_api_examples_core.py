from __future__ import annotations

from pydantic import BaseModel, Field
from rich import print

from aicore.models.model_api import ModelCallParams, UserMessage, create_model_api

from tests.models.model_api._model_api_examples_common import (
    DummySendMessageTool,
    DummyWeatherTool,
    ModelExampleCase,
    iter_model_cases,
    print_case_header,
    print_exception,
    print_model_response,
    print_step,
    run_async,
    short_params,
    simulated_tool_results_input,
    text_input,
)


class TinyAnswer(BaseModel):
    value: int = Field(..., description="数值")
    label: str = Field(..., description="数值的英文标签")


class UserProfile(BaseModel):
    name: str = Field(..., description="姓名")
    city: str = Field(..., description="所在城市")
    preference: str = Field(..., description="偏好或补充信息")


async def example_core_model_api_flow(
    case: ModelExampleCase,
) -> None:
    """演示 ModelAPI 的基础使用流程。

    步骤包括：
    1. 使用 factory 创建指定 backend 的 ModelAPI 和 initial_state。
    2. 带 system_prompt 发起首轮 UserMessage 调用。
    3. 在同一流程中调整 ModelCallParams，展示采样、输出长度和 thinking 参数。
    4. 手动组合 list[ModelInputMessage]，展示多段输入如何进入一次模型调用。
    5. 请求 structured_output，将自然语言任务结果解析为 Pydantic 对象。
    6. 基于上一轮 state 做多轮结构化输出，展示结构化结果可以随上下文补充而更新。
    7. 注册天气工具，让模型返回 provider-neutral ToolRunRequest。
    8. 模拟执行工具，并把结果封装为 ToolResultsMessage 回填给模型。
    9. 扩展到天气工具和发送消息工具，展示多工具场景下的非流式调用流程。
    """
    print_case_header("ModelAPI core example", case)

    print_step("1. 使用 factory 创建 ModelAPI 和 initial_state")

    api = create_model_api(backend=case.backend, model=case.model_name)
    state = api.initial_state(system_prompt="你是一个简洁的 ModelAPI 示例助手。回答尽量短。")

    print(f"api: {type(api).__name__}")
    print(f"state: {type(state).__name__}")

    print_step("2. 带 system_prompt 发起首轮 UserMessage 调用")
    query = "用一句话说明 ModelAPI 解决了什么问题，30 字以内。"
    print(f"user: {query}")
    response = await api.invoke(
        text_input(query),
        state=state,
        params=short_params(max_output_tokens=128),
    )
    print_model_response("首轮回复", response)
    state = response.state

    print_step("3. 调整 ModelCallParams")
    query = "把上面的回答改写成更口语的一句话。"
    params = ModelCallParams(
        temperature=0,
        top_p=0.8,
        max_output_tokens=80,
        thinking="disabled",
    )
    print(f"user: {query}")
    print(f"params: {params}")
    response = await api.invoke(
        text_input(query),
        state=state,
        params=params,
    )
    print_model_response("参数化调用回复", response)
    state = response.state

    print_step("4. 手动组合 list[ModelInputMessage]")
    inputs = [
        UserMessage(text="下面两句话属于同一轮输入。"),
        UserMessage(text="请合并理解后，用一句话总结：我想做统一模型调用抽象。"),
    ]
    print(f"input items: {inputs}")
    response = await api.invoke(
        inputs,
        state=state,
        params=short_params(max_output_tokens=128),
    )
    print_model_response("多输入项调用回复", response)
    state = response.state

    print_step("5. structured_output 解析为 Pydantic 对象")
    query = '返回 value=7, label="seven"，只表达这个结构化结果。'
    print(f"user: {query}")
    try:
        structured = await api.structured_output(
            text_input(query),
            output_type=TinyAnswer,
            state=state,
            params=short_params(max_output_tokens=128),
        )
        print_model_response("结构化输出回复", structured)
        state = structured.state
    except Exception as exc:
        print_exception("structured_output 示例未完成", exc)

    print_step("6. 多轮结构化输出")
    previous_state = state
    for query in [
        "请提取用户信息：我叫张三，住在上海，喜欢安静的咖啡店。",
        "补充并更新用户信息：我现在更偏好适合办公的咖啡店。",
    ]:
        print(f"user: {query}")
        try:
            profile_response = await api.structured_output(
                text_input(query),
                output_type=UserProfile,
                state=previous_state,
                params=short_params(max_output_tokens=128),
            )
            print_model_response("用户信息结构化回复", profile_response)
            previous_state = profile_response.state
        except Exception as exc:
            print_exception("多轮 structured_output 示例未完成", exc)
            break
    state = previous_state

    print_step("7. 单工具调用：天气查询")
    weather_tool = DummyWeatherTool()
    tool_state = api.initial_state(
        system_prompt="需要天气信息时，优先调用可用工具，不要编造天气。",
    )
    query = "请调用 get_weather 工具查询上海天气，不要直接回答天气内容。"
    print(f"user: {query}")
    tool_response = await api.invoke(
        text_input(query),
        state=tool_state,
        tools=[weather_tool],
        params=short_params(max_output_tokens=128),
    )
    print_model_response("天气工具调用回复", tool_response)

    if tool_response.tool_calls:
        print_step("8. 模拟执行工具，并回填 ToolResultsMessage")
        tool_results = simulated_tool_results_input(tool_response.tool_calls)
        print(f"tool results input: {tool_results}")
        final_response = await api.invoke(
            tool_results,
            state=tool_response.state,
            params=short_params(max_output_tokens=256),
        )
        print_model_response("工具结果回填后的最终回复", final_response)
    else:
        print("模型本轮没有发起工具调用，跳过工具结果回填。")

    print_step("9. 多工具场景：天气查询 + 发送消息")
    send_message_tool = DummySendMessageTool()
    multi_tool_state = api.initial_state(
        system_prompt=(
            "需要外部信息或发送消息时调用工具。"
            "如果工具参数缺少真实结果，可以先调用已具备参数的工具。"
        ),
    )
    query = "请查询上海天气，并把天气摘要发送给张三。需要时调用工具。"
    print(f"user: {query}")
    multi_tool_response = await api.invoke(
        text_input(query),
        state=multi_tool_state,
        tools=[weather_tool, send_message_tool],
        params=short_params(max_output_tokens=256),
    )
    print_model_response("多工具调用回复", multi_tool_response)

    if multi_tool_response.tool_calls:
        tool_results = simulated_tool_results_input(multi_tool_response.tool_calls)
        print(f"tool results input: {tool_results}")
        follow_up = await api.invoke(
            tool_results,
            state=multi_tool_response.state,
            params=short_params(max_output_tokens=256),
        )
        print_model_response("多工具结果回填后的回复", follow_up)
    else:
        print("模型本轮没有发起工具调用，保留自然语言回复作为示例结果。")


def main() -> None:
    """运行 core 主流程示例，覆盖创建、调用、参数、输入组合、结构化输出和非流式工具调用。"""
    for case in iter_model_cases():
        try:
            run_async(example_core_model_api_flow(case))
        except Exception as exc:
            print_exception(f"core example failed: {case.label}", exc)


if __name__ == "__main__":
    main()
