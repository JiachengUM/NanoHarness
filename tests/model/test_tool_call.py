from typing import Final, cast

import pytest
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)

from nanoai.model.config import (
    ModelName,
    create_client_model,
    create_client_async_model,
)


def _llm(
    client: OpenAI,
    model: str,
    messages: list[ChatCompletionMessageParam],
    tools: list[ChatCompletionToolParam],
    **kwargs,
) -> ChatCompletionMessage:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        **kwargs,
    )
    return response.choices[0].message


weather_tool: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取指定城市的天气信息",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称，如北京、上海等"},
                "date": {"type": "string", "description": "查询日期，格式为YYYY-MM-DD，默认为今天"},
            },
            "required": ["city", "date"],
        },
        "strict": True,
    },
}

booking_flight_tool: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "book_flight",
        "description": "预订从出发城市到目的地城市的机票",
        "parameters": {
            "type": "object",
            "properties": {
                "departure_city": {"type": "string", "description": "出发城市名称"},
                "destination_city": {"type": "string", "description": "目的地城市名称"},
                "departure_date": {"type": "string", "description": "出发日期，格式为YYYY-MM-DD"},
                "return_date": {"type": "string", "description": "返回日期，格式为YYYY-MM-DD，如果是单程票则不需要"},
                "passengers": {"type": "integer", "description": "乘客数量"},
                "class": {
                    "type": "string",
                    "description": "舱位等级，如经济舱、商务舱、头等舱",
                    "enum": ["economy", "business", "first"],
                },
            },
            "required": ["departure_city", "destination_city", "departure_date", "passengers"],
        },
        "strict": True,
    },
}

tourism_attractions_tool: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "get_tourist_attractions",
        "description": "获取指定城市的热门旅游景点信息",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称，如北京、上海等"},
                "category": {
                    "type": "string",
                    "description": "景点类别，如历史古迹、自然风光、博物馆等",
                    "enum": ["historical", "nature", "museums", "entertainment", "all"],
                },
                "count": {"type": "integer", "description": "返回的景点数量，默认为5个"},
            },
            "required": ["city"],
        },
        "strict": True,
    },
}

TOOLS: list[ChatCompletionToolParam] = [weather_tool, booking_flight_tool, tourism_attractions_tool]

user_requests = [
    ("""帮我订一张从深圳到哈尔滨的单程机票，8月5日出发，头等舱，1位乘客。""", ["book_flight"]),
    ("""请推荐北京的所有类型景点，限制返回前10个。""", ["get_tourist_attractions"]),
    ("""帮我查询北京、上海和广州三个城市明天的天气情况。""", ["get_weather", "get_weather", "get_weather"]),
    (
        """1. 查询北京一周后的天气情况。2. 帮我预订一张2023-07-21从上海到北京的机票，经济舱，1位乘客""",
        ["get_weather", "book_flight"],
    ),
    (
        """我计划下周去北京旅游，请查询北京2023-07-28的天气，并推荐5个北京的历史古迹景点。""",
        ["get_weather", "get_tourist_attractions"],
    ),
    (
        """帮我预订一张从广州到成都的机票，出发日期是2023-08-01，2位乘客，商务舱。另外，请推荐成都的3个自然风光景点。""",
        ["book_flight", "get_tourist_attractions"],
    ),
    (
        """我想知道杭州和西安这两个城市下周的天气如何？并且希望了解这两个城市各有哪些值得游览的景点。""",
        ["get_weather", "get_weather", "get_tourist_attractions", "get_tourist_attractions"],
    ),
    (
        """我计划带家人去厦门旅游，请查询厦门下周的天气，并帮我订一张从北京到厦门的机票，出发日期是2023-07-27，返回日期2023-08-02，4位乘客，经济舱。还有，请推荐厦门有哪些适合全家游玩的娱乐场所。""",
        ["get_weather", "book_flight", "get_tourist_attractions"],
    ),
]


@pytest.mark.parametrize("user_request, expected_tool_calls", user_requests)
def test_multi_tool_call(user_request: str, expected_tool_calls: list[str]) -> None:
    """测试强制使用多工具调用的场景

    Args:
        client: OpenAI客户端
        model: 模型名称
        user_request: 用户请求
        expected_tool_calls: 期望的工具调用，工具名称列表，如["get_weather", "book_flight"]
    """
    # 获取client和model
    client, model = create_client_model(ModelName.DOUBAO_SEED_1_6_FLASH_250615)

    # 创建消息
    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": """你是一个高效的助手，需要严格执行以下要求：
1. 用户的请求中可能包含多个任务。你必须使用提供的工具来响应每一个任务，不要遗漏任何任务。""",
        },
        {"role": "user", "content": f"""{user_request}"""},
    ]

    print(f"请求消息: {user_request}")

    # 调用_llm_tool函数
    res = _llm(client=client, model=model, messages=messages, tools=TOOLS, tool_choice="auto", temperature=0)

    # 打印响应和工具调用结果
    actual_tool_calls = res.tool_calls or []
    print(f"工具调用数量: {len(actual_tool_calls)}，结果如下")
    actual_tool_names = []
    for i, tool_call in enumerate(actual_tool_calls):
        tool_name = tool_call.function.name
        actual_tool_names.append(tool_name)
        print(f"工具 {i + 1}: {tool_name}")
        print(f"参数: {tool_call.function.arguments}")
        print("---")

    VERIFY_TOOL_CALLS: Final = False

    # 验证工具调用是否符合预期
    if VERIFY_TOOL_CALLS and expected_tool_calls:
        print("\n验证工具调用:")
        print(f"预期工具调用: {expected_tool_calls}")
        print(f"实际工具调用: {actual_tool_names}")

        # 检查每个预期工具是否都被调用
        missing_tools = [tool for tool in expected_tool_calls if tool not in actual_tool_names]
        unexpected_tools = [tool for tool in actual_tool_names if tool not in expected_tool_calls]

        # 检查调用次数是否匹配
        expected_counts = {tool: expected_tool_calls.count(tool) for tool in set(expected_tool_calls)}
        actual_counts = {tool: actual_tool_names.count(tool) for tool in set(actual_tool_names)}

        count_mismatches = []
        for tool, count in expected_counts.items():
            if tool in actual_counts and actual_counts[tool] != count:
                count_mismatches.append(f"{tool}: 预期{count}次，实际{actual_counts.get(tool, 0)}次")

        if not missing_tools and not unexpected_tools and not count_mismatches:
            print("✅ 工具调用验证通过!")
        else:
            if missing_tools:
                print(f"❌ 缺少工具调用: {', '.join(missing_tools)}")
            if unexpected_tools:
                print(f"❌ 意外的工具调用: {', '.join(unexpected_tools)}")
            if count_mismatches:
                print(f"❌ 工具调用次数不匹配: {'; '.join(count_mismatches)}")


def test_tool_call_multi_turn() -> None:
    """测试多轮对话中处理tool_calls的场景

    这个测试用例展示：
    1. 如何处理带有tool_calls的assistant消息
    2. 如何自动生成占位tool消息
    3. 如何继续对话
    """
    client, model = create_client_model(ModelName.DOUBAO_SEED_1_6_FLASH_250615)

    # 初始消息
    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": """你是一个高效的助手，需要严格执行以下要求：
1. 用户的请求中可能包含多个任务。你必须使用提供的工具来响应每一个任务，不要遗漏任何任务。
2. 如果工具调用失败，请继续对话，不要中断。""",
        },
        {"role": "user", "content": "请查询北京明天的天气，并推荐3个北京的历史古迹景点。"},
    ]

    print("\n=== 第一轮对话 ===")
    print(f"用户消息: {messages[-1].get('content', '')}")

    # 第一轮调用
    res = _llm(client=client, model=model, messages=messages, tools=TOOLS, tool_choice="auto", temperature=0)

    # 打印工具调用结果
    actual_tool_calls = res.tool_calls or []
    print(f"工具调用数量: {len(actual_tool_calls)}")
    for i, tool_call in enumerate(actual_tool_calls):
        print(f"工具 {i + 1}: {tool_call.function.name}")
        print(f"参数: {tool_call.function.arguments}")

    # 添加assistant消息到对话历史
    assistant_msg: ChatCompletionAssistantMessageParam = {
        "role": "assistant",
        "content": res.content if res.content is not None else "",
        "tool_calls": [cast(ChatCompletionMessageToolCallParam, tool_call) for tool_call in actual_tool_calls],
    }
    messages.append(assistant_msg)

    # 自动生成占位tool消息
    for tool_call in actual_tool_calls:
        tool_message: ChatCompletionToolMessageParam = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": "工具调用被跳过",  # 占位内容
        }
        messages.append(tool_message)
        print(f"\n添加占位tool消息: {tool_message}")

    # 第二轮对话
    print("\n=== 第二轮对话 ===")
    user_msg: ChatCompletionUserMessageParam = {"role": "user", "content": "好的，请继续。"}
    messages.append(user_msg)
    print(f"用户消息: {user_msg.get('content', '')}")

    # 第二轮调用
    res = _llm(client=client, model=model, messages=messages, tools=TOOLS, tool_choice="auto", temperature=0)

    # 打印最终响应
    print("\n=== 最终响应 ===")
    print(f"助手回复: {res.content if res.content is not None else ''}")


RUN_PYTEST: Final = False


def main() -> None:
    # test_ds_tool_call()
    test_tool_call_multi_turn()

    for user_request, expected_tool_calls in user_requests:
        test_multi_tool_call(user_request, expected_tool_calls)


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        main()
