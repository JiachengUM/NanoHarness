from typing import Final

import asyncio

import json

import pytest
from pydantic import BaseModel, Field

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, Ark, AsyncArk
from aicore.models.responses.invocation import (
    invoke,
    ainvoke,
    invoke_output_by_json,
    ainvoke_output_by_json,
    ainvoke_output_by_schema,
    ResponseParams,
    FunctionToolParam,
)

from aicore.models.responses import system_msg, user_msg, assistant_msg, function_call_output, ResponseInputItemParam
from aicore.utils._concepts.person import PersonBasicInfo


class IntentJudge(BaseModel):
    """简单意图识别结构。"""
    intent: str = Field(default="", description="意图类别：导航/音乐/天气/闲聊")
    reason: str = Field(default="", description="简短判断依据")


model_names: Final[list[ModelName]] = [
        ModelName.SEED_1_8_251228,            # 最好的，没开启缓存服务
        # ModelName.SEED_1_6_251015,
        # ModelName.SEED_1_6_251015,
        # ModelName.SEED_1_6_FLASH_250828,      # 最快的
    ]


@pytest.mark.parametrize("model_name", model_names)
def test_invoke(model_name: ModelName) -> None:
    print("\n======================================================")
    print(f"测试invoke和ainvoke, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking = {"type": "disabled"})  # 关掉thinking快多了，没有ResponseReasoningItem
    #params = ResponseParams(thinking = {"type": "enabled"})

    query = "讲个笑话"
    print(f"Query: {query}")
    res = invoke(query, client=client, model=model, params=params)
    print("结果 with invoke:")
    print(res)

    query = "这个笑话的笑点在哪？"
    print(f"Query: {query}")
    res = invoke(query, res, client=client, model=model, params=params)
    print("结果 with invoke:")
    print(res)


def test_invoke_special() -> None:
    client, model = create_client(ModelName.SEED_1_8_251228, Ark)
    params = ResponseParams(thinking = {"type": "disabled"})  # 关掉thinking快多了，没有ResponseReasoningItem
    #params = ResponseParams(thinking = {"type": "enabled"})

    prompt = "请从用户输入中提取地址信息。必须是明确的可以搜索的地点，例如xx路, yy小区， zz广场，而不能是模糊的指代，如'附近'、'当前位置'’等。如果没有，请返回无。"
    #user_query = "帮我找下附近的海底捞"
    user_query = "帮我找下海淀小区的海底捞"
    query = f"{prompt}\n用户输入: {user_query}"
    print(f"Query: {query}")
    res = invoke(query, client=client, model=model, params=params)
    print(f"结果 with invoke: {res.raw_text}")
    # print(res)


@pytest.mark.parametrize("model_name", model_names)
def test_output_by_json(model_name: ModelName) -> None:
    print("\n======================================================")
    print(f"测试invoke_output_by_json, 模型: {model_name}")

    #params = ResponseParams(thinking = {"type": "enabled"})  # 打开thinking很慢，但是从reasoning_content中能看出非常多内容，对于如何更好的结构化输出有帮助
    params = ResponseParams(thinking = {"type": "disabled"})  # 关掉thinking快多了
    query = "请随机创建一个人物基本信息"

    client, model = create_client(model_name, Ark)
    print(f"Query: {query}")
    try:
        res, response = invoke_output_by_json(query, output_type=PersonBasicInfo, client=client, model=model, params=params)
        print("结果 with invoke_output_by_json:")
        print(res)
        print("原始响应:")
        print(response)
    except Exception as e:
        print(f"错误: {e}")


@pytest.mark.parametrize("model_name", model_names)
def test_output_by_schema(model_name: ModelName) -> None:
    print("\n======================================================")
    print(f"测试invoke_output_by_schema, 模型: {model_name}, ark目前还不支持json_schema")

    # params = ResponseParams(thinking={"type": "disabled"}, store=False,caching = None)
    params = ResponseParams(thinking={"type": "disabled"})

    query = "请随机创建一个人物基本信息"

    client, model = create_client(model_name, AsyncArk)
    print(f"Query: {query}")
    async def _run() -> None:
        try:
            res, response = await ainvoke_output_by_schema(query, output_type=PersonBasicInfo, client=client, model=model, params=params)
            print("结果 with invoke_output_by_schema:")
            print(res)
            print("原始响应:")
            print(response)

        except Exception as e:
            print(f"错误: {e}")
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke(model_name: ModelName) -> None:
    """测试异步 ainvoke（与 test_invoke 行为一致，使用 AsyncArk）"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 ainvoke, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        query = "讲个笑话"
        print(f"Query: {query}")
        res = await ainvoke(query, client=client, model=model, params=params)
        print("结果 with ainvoke:")
        print(res)

        query = "这个笑话的笑点在哪？"
        print(f"Query: {query}")
        res2 = await ainvoke(query, res, client=client, model=model, params=params)
        print("结果 with ainvoke:")
        print(res2)

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke_branch(model_name: ModelName) -> None:
    """分支测试，测试不同分支的Response。由同一个Response ID，生成不同分支的Response。验证max_output_tokens参数的效果。"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 ainvoke, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"}, caching={"type": "enabled"}, max_output_tokens=100)

        query = "简短介绍，你知道余弦相似度的原理吗？"
        print(f"Query: {query}")
        res = await ainvoke(query, client=client, model=model, params=params)
        # 深拷贝，避免修改原始response
        res_copy = res.model_copy(deep=True)
        print("\n结果 with ainvoke:")
        print("起始response:")
        print(res)
        print(res.raw_text)

        query = "简短介绍，我希望你可以用小学生都能听懂的方式来解释这个问题"
        print(f"Query: {query}")
        res2 = await ainvoke(query, res, client=client, model=model, params=params)
        print("\n结果 with ainvoke:")
        print("分支1response:")
        print(res2)
        print(res2.raw_text)

        query = "简短介绍，我希望你可以用教授的思考逻辑来解释这个问题"
        print(f"Query: {query}")
        res3 = await ainvoke(query, res_copy, client=client, model=model, params=params)
        print("\n结果 with ainvoke:")
        print("分支2response:")
        print(res3)
        print(res3.raw_text)

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke_output_by_json(model_name: ModelName) -> None:
    """测试异步 ainvoke_output_by_json（与 test_output_by_json 行为一致，使用 AsyncArk）"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 ainvoke_output_by_json, 模型: {model_name}")

        params = ResponseParams(thinking={"type": "disabled"})
        query = "请随机创建一个医生职业的人物基本信息"

        client, model = create_client(model_name, AsyncArk)
        print(f"Query: {query}")
        try:
            res, response = await ainvoke_output_by_json(
                query,
                output_type=PersonBasicInfo,
                client=client,
                model=model,
                params=params,
            )
            print("结果 with ainvoke_output_by_json:")
            print(res)
            print("原始响应:")
            print(response)
        except Exception as e:
            print(f"错误: {e}")
            raise

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_invoke_caching(model_name: ModelName) -> None:
    """
    缓存能力测试。测试前请确保模型支持缓存。
    """
    print("\n======================================================")
    print(f"测试invoke_caching, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(
        thinking={"type": "disabled"},
        caching={"type": "enabled"},
    )

    # 第一轮
    res1 = invoke("讲一个笑话", client=client, model=model, params=params)
    # 第二轮，通过previous_response_id 复用缓存
    res2 = invoke("这个笑话的笑点在哪？", res1, client=client, model=model, params=params)

    print(f"\n第一轮模型返回的Response:\n{res1}")
    print(f"\n第一轮response.id: {res1.id}")
    print()
    print(f"\n第二轮模型返回的Response:\n{res2}")
    print(f"\n第二轮response.id: {res2.id}")
    if res1.usage and res2.usage:
        print(f"\n第一轮usage: {res1.usage}")
        print(f"\n第二轮usage: {res2.usage}")
        print(f"\n第一轮总token: {res1.usage.total_tokens}")
        print("\n第二轮命中缓存cached_tokens:", res2.usage.input_tokens_details.cached_tokens)
        assert res2.usage.input_tokens_details.cached_tokens >= 0


@pytest.mark.asyncio
def test_ainvoke_caching_prefix(model_name: ModelName) -> None:
    """缓存能力：prefix=true 时模型不回复；（官方说prefix创建后，只用传入response_id 即可(无需再传入caching参数)，纯静态不可更新）
    previous_response_id 复用缓存"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试ainvoke_caching_prefix, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)

        # 1) 仅建前缀缓存，无回复
        prefix_params = ResponseParams(
            thinking={"type": "disabled"},
            caching={"type": "enabled", "prefix": True}
        )
        # 需要超过256 token！
        res_prefix = None
        from projects.mind.mem.benchi_demo.prompt import PLANNER_PROMPT
        try:
            res_prefix = await ainvoke(PLANNER_PROMPT, client=client, model=model, params=prefix_params)
        except Exception as e:
            print(f"错误: {e}")
        assert res_prefix is not None, "res_prefix should not be None"
        print(f"\n第一轮【前缀缓存】创建，模型返回的Response:\n{res_prefix}")
        
        total_tokens = res_prefix.usage.input_tokens if res_prefix.usage else None
        assert res_prefix.message is None   # 无回复
        assert res_prefix.tool_calls is None   # 无回复
        assert res_prefix.think is None   # 无回复
        try:
            # 创建 prifix 时，不可使用raw_text，因为模型无回复！
            _ = res_prefix.raw_text
        except RuntimeError as e:
            print(f"raw_text 异常: {e}, 符合预期")

        # 2 接着用 previous 做正常对话，应当命中缓存
        # 重点：参数一致性要求，否则火山api会报错。

        # 实验一 ：每轮都加上caching ，发现Prefix 缓存能记历史、缓存 Token 持续累加。
        chat_params1 = ResponseParams(thinking={"type": "disabled"},caching={"type": "enabled"})

        # 实验二 ：遵照官方文档，去掉caching参数(默认关闭)，发现只用了前缀缓存！第二轮的对话未缓存（计算层面），但是对话历史依旧在。
        chat_params2 = ResponseParams(thinking={"type": "disabled"})
        for params in [chat_params1, chat_params2]:
            print("*"*80)
            res_chat = await ainvoke("导航到上海迪士尼附近的咖啡店", res_prefix, client=client, model=model, params=params)
            print(f"\n第二轮【复用缓存】，模型返回的Response:\n{res_chat}")
            second_cached_tokens = res_chat.usage.input_tokens_details.cached_tokens if res_chat.usage else None

            assert res_chat.message is not None   # 有回复
            print(f"\n第二轮raw_text: {res_chat.raw_text}")

            third_response = await ainvoke("我刚刚说了什么", res_chat, client=client, model=model, params=params)
            print(f"\n第三轮【复用缓存】，模型返回的Response:\n{third_response}")
            third_cached_tokens = third_response.usage.input_tokens_details.cached_tokens if third_response.usage else None
            print(f"\n第三轮raw_text: {third_response.raw_text}")

            print(f"\n实验参数：{params}\n前缀缓存总token数：{total_tokens}\n第二轮cached_tokens：{second_cached_tokens}\n第三轮cached_tokens：{third_cached_tokens}\n")

        result = """\n
在prefix=true 前提下，传入previous_response_id。
结论：参数`previous_response_id`的串行传递和后续对话传入caching参数，实现缓存和历史的更新。
实验一：每轮都加上caching={'type': 'enabled'} 参数(默认关闭) ，发现缓存能命中，且能记历史、缓存 Token 持续累加。
实验二：caching={'type': 'disabled'} 参数(默认关闭)，发现只命中了前缀缓存的那一部分！第二轮的对话未缓存（计算层面），但历史依旧更新。
        """
        print(result)

    asyncio.run(_run())


def test_instructions(model_name: ModelName) -> None:
    """
    在Responses API中，instructions字段用于在特定轮次中补充系统提示词，其核心机制是在对话上下文头部新增一条系统提示信息，实现更灵活的输出。
    配置 instructions 字段后无法写入缓存以及使用缓存，即无法配置 caching 字段为{"type"："enabled"}，同时无法命中缓存
    """
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 补充系统提示词 instructions, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        input: list[ResponseInputItemParam] = [system_msg("你是一位数学老师，能够讲清楚相应的数学问题。")]
        response = await ainvoke(input, client=client, model=model, params=params)
        print("*"*80)
        print(f"\n第一轮response.raw_text: {response.raw_text}")

        secone_res = await ainvoke("请解释一下余弦相似度原理,简短回复", response, client=client, model=model, params=params)
        print("*"*80)
        print(f"\n第二轮response.raw_text: {secone_res.raw_text}")
        params1 = ResponseParams(
            thinking={"type": "disabled"}, 
            instructions="增加一个要求：我希望你可以用小学生能听懂的方式解释这个问题。"
            )
        third_res = await ainvoke("请解释一下余弦相似度原理,简短回复", secone_res, client=client, model=model, params=params1)
        print("*"*80)
        print(f"\n第三轮新增instruction的response.raw_text: {third_res.raw_text}")

        print(f"\n第三轮message_history: \n{third_res.message_history}")

    asyncio.run(_run())

@pytest.mark.parametrize("model_name", model_names)
def test_instructions_caching_conflict(model_name: ModelName) -> None:
    """instructions + caching=enabled → 抛异常"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试instructions_caching_conflict, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)

        params = ResponseParams(
            instructions="你是一位助手",          # 冲突字段
            caching={"type": "enabled"}            # 冲突字段
        )
        try:
            await ainvoke("讲一个冷笑话", client=client, model=model, params=params)
        except Exception as e:
            print(f"【报错表示正确！】: {e}")

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_invoke_with_system_prompt(model_name: ModelName) -> None:
    print("\n======================================================")
    print(f"测试invoke和ainvoke, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking = {"type": "disabled"})  # 关掉thinking快多了，没有ResponseReasoningItem
    #params = ResponseParams(thinking = {"type": "enabled"})

    query = "讲个笑话"
    print(f"Query: {query}")
    res = invoke(query,"先回复`你好我是小途`", client=client, model=model, params=params)
    print("结果 with invoke:")
    print(res)

    query = "这个笑话的笑点在哪？"
    print(f"Query: {query}")
    res = invoke(query, res, client=client, model=model, params=params)
    print("结果 with invoke:")
    print(res)


@pytest.mark.parametrize("model_name", model_names)
def test_invoke_with_input_items(model_name: ModelName) -> None:
    """手动构建的消息列表通过第一个参数 input 传入。"""
    print("\n======================================================")
    print(f"测试 invoke with previous input items, 从input传入消息列表, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})

    query = "讲个笑话"
    print(f"Query: {query}")
    messages: list[ResponseInputItemParam] = [
        system_msg("先回复`你好我是小途`"),
        user_msg(query),
    ]
    res = invoke(messages, client=client, model=model, params=params)
    print(f"结果 with invoke:{res.raw_text}")
    print(f"message_history: {res.message_history}")
    print()
    query = "这个笑话的笑点在哪？"
    print(f"Query: {query}")
    res = invoke(query, res, client=client, model=model, params=params)
    print(f"第二轮raw_text: {res.raw_text}")
    print(f"第二轮message_history: {res.message_history}")

weather_tool = FunctionToolParam(
    type="function",
    name="get_weather",
    description="根据城市名称查询该城市当日天气（含温度、天气状况）",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "城市名称，如北京、上海（仅支持国内地级市）"
            }
        },
        "required": ["location"]
    }
)

@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke_tool_with_system_prompt(model_name: ModelName) -> None:
    """自定义function calling 工具 + 系统提示词，确保工具调用前有回复"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试ainvoke_tool_with_system_prompt, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)

        params = ResponseParams(
            thinking={"type": "disabled"},
        )
        system_prompt = "打算调用工具时，请首先简要地回复用户打算做什么，再执行工具调用。回复时要先说`你好，我是小途`"
        query = "上海天气咋样"
        print(f"\n第一轮Query: {query}")
        print(f"\nsystem_prompt: {system_prompt}")
        result = await ainvoke(query, system_prompt, client=client, model=model, params=params, tools=[weather_tool])
        # print(f"\n第一轮result:\n{result}")
        # 带tool时先回复的情形，即tool_call 和 message 同时出现。
        assert result.message, "message should not be None"
        assert result.tool_calls, "tool_calls should not be None"
        print(f"\n第一轮message: {result.message}")
        print(f"\n第一轮tool_calls: {result.tool_calls}")
        print(f"\n第一轮message_history: \n{result.message_history}")
        print("*"*80)
        print("=== 模拟工具调用: Get Weather Results ===")
        tool_output = {
            "city": "上海",
            "date": "2025-10-13",
            "temperature": "18~28℃",
            "condition": "晴转多云",
            "wind": "东北风2级"
        }

        call_output = function_call_output(
            result.tool_calls[0].call_id,
            json.dumps(tool_output, ensure_ascii=False),
        )
        fc_result = await ainvoke(
            [call_output],
            result,
            client=client, 
            model=model, 
            tools=[weather_tool],
            params=params)
        print("\n结果 with invoke_with_tool:")
        # print(f"\nfc调用后,模型回复:\n{fc_result}")
        print(f"\nfc调用后,message_history: {fc_result.message_history}")

        query2 = "刚刚说了啥" 
        print("*"*80)
        print(f"\n第二轮query: {query2}")
        result = await ainvoke(query2, fc_result, client=client, model=model, params=params, tools=[weather_tool])
        # print(f"\n第二轮result:\n{result}")
        print(f"\n第二轮message_history: \n{result.message_history}")

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke_with_input_items(model_name: ModelName) -> None:
    """手动构建的消息列表通过第一个参数 input 传入。"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 ainvoke with previous input items, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        query = "讲个笑话"
        print(f"Query: {query}")
        messages: list[ResponseInputItemParam] = [
            system_msg("先回复`你好我是小途`"),
            user_msg(query),
        ]
        res = await ainvoke(messages, client=client, model=model, params=params)
        print(f"raw_text: {res.raw_text}")
        print(f"message_history: {res.message_history}")
        print()
        query = "这个笑话的笑点在哪？"
        print(f"Query: {query}")
        res = await ainvoke(query, res, client=client, model=model, params=params)
        print(f"第二轮raw_text: {res.raw_text}")
        print(f"第二轮message_history: {res.message_history}")

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_output_by_json_with_previous_response_id(model_name: ModelName) -> None:
    """首轮 input 传字符串，不支持传入list，连续对话通过response对象的id来实现。"""
    print("\n======================================================")
    print(f"测试 output_by_json_with_previous_response_id, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})

    print("*"*80)
    query = "我叫张三，男，28岁，是一名医生，本科。"
    print(f"\n首轮query: {query}")
    res, response = invoke_output_by_json(
        query,
        output_type=PersonBasicInfo,
        previous_response_or_system_prompt=None,
        client=client,
        model=model,
        params=params,
    )
    print(f"第一轮生成的结构化结果: {res}")

    query = "补充并更新：我现在32岁，已婚，联系方式是13800000000。"
    print(f"\n第二轮query: {query}")
    # 使用response对象的id继续对话
    res2, response2 = invoke_output_by_json(
        query,
        output_type=PersonBasicInfo,
        previous_response_or_system_prompt=response,
        client=client,
        model=model,
        params=params,
    )
    print(f"第二轮生成的结构化结果: {res2}")
    print(f"第二轮raw_text: {response2.raw_text}")
    print(f"第二轮message_history: {response2.message_history}")
    
    print("*"*80)


@pytest.mark.parametrize("model_name", model_names)
def test_invoke_output_by_json_intent(model_name: ModelName) -> None:
    """最简单真实场景：query 列表循环连续对话，打印 history 和回复。"""
    print("\n======================================================")
    print(f"测试 invoke_output_by_json 意图识别连续对话,后续使用response继续对话, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})
    sys_prompt = (
        "你是意图识别器。"
        "仅识别以下意图之一：导航、音乐、天气、闲聊。"
        "如果用户改口，以最后一句为准。"
    )
    queries = [
        "帮我导航去上海虹桥火车站",
        "算了不导航了，帮我放一首周杰伦的歌",
        "今天天气怎么样",
        "讲个笑话",
    ]
    print("\n系统提示词:", sys_prompt)
    print("*"*80)
    previous = sys_prompt
    for idx, query in enumerate(queries, start=1):
        print(f"Query{idx}: {query}")
        result, response = invoke_output_by_json(
            query,
            output_type=IntentJudge,
            previous_response_or_system_prompt=previous,
            client=client,
            model=model,
            params=params,
        )
        print(f"Round{idx} result: {result}")
        print(f"Round{idx} raw: {response.raw_text}")
        print(f"Round{idx} history: {response.message_history}")
        previous = response
        print("*"*80, "\n")


@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke_output_by_json_intent(model_name: ModelName) -> None:
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 ainvoke_output_by_json 意图识别连续对话,不传入sys_prompt,后续使用response继续对话, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        # TODO: 目前的逻辑，不传sys_prompt时，会用默认的。
        query = "帮我导航去上海虹桥火车站"
        print(f"Query1: {query}")
        res1, response1 = await ainvoke_output_by_json(
            query,
            output_type=IntentJudge,
            previous_response_or_system_prompt=None,
            client=client,
            model=model,
            params=params,
        )
        print(f"Round1: {res1}")
        print(f"Round1 message_history: {response1.message_history}")

        query = "算了不导航了，帮我放一首周杰伦的歌"
        print(f"Query2: {query}")
        res2, response2 = await ainvoke_output_by_json(
            query,
            output_type=IntentJudge,
            previous_response_or_system_prompt=response1,
            client=client,
            model=model,
            params=params,
        )
        print(f"Round2: {res2}")
        print(f"Round2 message_history: {response2.message_history}")
        print(f"Round2 raw: {response2.raw_text}")

        assert res1.intent in {"导航", "音乐", "天气", "闲聊"}
        assert res2.intent in {"导航", "音乐", "天气", "闲聊"}
        assert res1.intent != res2.intent
        assert res2.intent == "音乐"

    asyncio.run(_run())

def test_openai_sdk_json_schema(model_name: ModelName):
    print("\n======================================================")
    print(f"测试 openai sdk 的json_schema, 模型: {model_name}, 速度较慢。")
    from openai import AsyncOpenAI
    from aicore.models.credentials import ARK_API_KEY
    import time

    api_key = ARK_API_KEY
    client = AsyncOpenAI(
        base_url='https://ark.cn-beijing.volces.com/api/v3',
        api_key=api_key,
    )
    query = "请随机创建一个人物基本信息"

    async def _run() -> None:
        start_time = time.time()
        response = await client.responses.parse(
        model=model_name.value, 
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": query
                    }
                ]
            }
        ],
        text_format=PersonBasicInfo
    )
        print(f"耗时: {time.time() - start_time}秒")
        print(response.output_parsed)

    asyncio.run(_run())
    
# ============= 主函数 =============
RUN_PYTEST: Final = False


def main() -> None:
    # test_invoke_special()
    # return

    for model in model_names:
        test_invoke(model)
        test_output_by_json(model)
        test_ainvoke(model)
        test_ainvoke_output_by_json(model)
        
        # 同一id，创建不同分支
        test_ainvoke_branch(model)

        # # 缓存能力测试
        test_invoke_caching(model)
        test_ainvoke_caching_prefix(model)  
        
        # # # 补充系统提示词测试
        test_instructions(model)

        # # # instructions + caching=enabled → 抛异常
        test_instructions_caching_conflict(model)

        test_invoke_with_system_prompt(model)

        test_ainvoke_tool_with_system_prompt(model)

        # 从input传入消息列表
        test_invoke_with_input_items(model)
        test_ainvoke_with_input_items(model)

        # 通过response id连续对话
        test_output_by_json_with_previous_response_id(model)

        # 连续对话意图识别（同步），传入sys_prompt，后续使用response继续对话
        test_invoke_output_by_json_intent(model)
        # 连续对话意图识别（异步），不传入sys_prompt（会使用ainvoke自带的默认sys_prompt），后续使用response继续对话
        test_ainvoke_output_by_json_intent(model)

        # 目前ark sdk不支持json_schema
        test_output_by_schema(model)
        # 使用openai sdk的json_schema
        test_openai_sdk_json_schema(model)

        break  # 只跑第一个模型；要跑全部模型可删掉本行


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        #test_safe_update()
        main()
