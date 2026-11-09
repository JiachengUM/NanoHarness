from typing import Final

import asyncio

import json

import pytest

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, Ark, AsyncArk
from aicore.models.responses.streaming import (
    ResponseParams,
    FunctionToolParam,
    StreamVerbosity,
    stream,
    astream,
    stream_run,
    astream_run,
    EVENTS_IGNORE,
    DefaultStreamEventHandler,
)

from aicore.models.responses import function_call_output, system_msg,user_msg, ResponseInputItemParam

from aicore.models.responses.streaming import (
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
    ResponseCompletedEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseCreatedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDoneEvent,
    ResponseReasoningSummaryTextDoneEvent,
)

model_names: Final[list[ModelName]] = [
        # ModelName.SEED_1_8_251228,            # 最好的，没开启缓存服务
        ModelName.SEED_1_8_251228,
        # ModelName.SEED_1_6_251015,
        # ModelName.SEED_1_6_FLASH_250828,      # 最快的
    ]


@pytest.mark.parametrize("model_name", model_names)
def test_stream(model_name: ModelName) -> None:
    """测试同步流式 invoke_stream（使用 Ark）"""
    print("\n======================================================")
    print(f"测试 stream, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})
    
    query = "用一句话介绍北京"

    print(f"Query: {query}")
    print("stream 输出结果:", end="", flush=True)
    stream_res = stream_run(query, client=client, model=model, params=params, verbosity=StreamVerbosity.MAXIMAL)
    
    print("\nstream 输出最终结果")
    print(stream_res)

    query = "将上面的回答改成英文"
    print(f"Query: {query}")
    print("stream 输出结果:", end="", flush=True)
    stream_res1 = stream_run(query, stream_res, client=client, model=model, params=params)
    
    print("\nstream 输出最终结果")
    print(stream_res1)


@pytest.mark.parametrize("model_name", model_names)
def test_astream(model_name: ModelName) -> None:
    """测试异步流式 astream（使用 AsyncArk）"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 astream, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        query = "讲一个20个字的短笑话"

        print(f"Query: {query}")
        print("astream 输出结果:\n")

        stream_res = await astream_run(query, client=client, model=model, params=params)
        print()
        print("新一轮","*"*100)
        # exit()
        query = "20字讲述一下笑点在哪"
        print(f"Query: {query}")
        print("第二轮astream 输出结果:\n")
        stream_res1 = await astream_run(query, stream_res, client=client, model=model, params=params)

        print("\nastream 输出最终结果")
        print(stream_res1)

    asyncio.run(_run())


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


def test_stream_tool(model_name: ModelName) -> None:
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试stream_tool, 模型: {model_name}")
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})
        query = "上海天气咋样"
        stream_res = await astream_run(query, client=client, model=model, params=params, tools=[weather_tool])

        # print(f"stream_res: {stream_res}")
        assert stream_res is not None, "response should not be None"

        assert stream_res.tool_calls is not None, "tool_calls should not be None"
        # print("第一个tool_call:")
        # print(stream_res.tool_calls[0])

        print("=== Simulate Tool Execution: Get Weather Results ===")
        tool_output = {
            "city": "上海",
            "date": "2025-10-13",
            "temperature": "18~28℃",
            "condition": "晴转多云",
            "wind": "东北风2级"
        }

        call_output = function_call_output(
            stream_res.tool_calls[0].call_id,
            json.dumps(tool_output, ensure_ascii=False),
        )

        try:
            stream_res = await astream_run(
                [call_output], 
                stream_res,
                client=client, 
                model=model, 
                params=params)
            print("\n最终响应结果:")
            print(stream_res)
        except Exception as e:
            print(f"错误: {e}")
        
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_astream_events_minimal_text(model_name: ModelName) -> None:
    """测试纯文本场景下 MINIMAL 模式的事件过滤：只捕获实质性结果事件"""
    async def _run() -> None:
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})
        query = "用5个字问候"

        event_handler = DefaultStreamEventHandler(print_fn=print, do_stats=True, do_print=False)
        
        stream_result = await astream_run(query, client=client, model=model, params=params, verbosity=StreamVerbosity.MINIMAL, event_handler=event_handler)

        print(f"✅ 纯文本 MINIMAL 模式 event stat with query: {query}")
        event_handler.stats()
                
        # 验证关键事件都被捕获到了
        assert ResponseCreatedEvent in event_handler.event_types, "应该捕获响应创建事件"
        assert ResponseTextDeltaEvent in event_handler.event_types, "应该捕获文本增量事件"
        assert ResponseTextDoneEvent in event_handler.event_types, "应该捕获文本完成事件"
        assert ResponseCompletedEvent in event_handler.event_types, "应该捕获响应完成事件"

        print(stream_result)
        
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_astream_events_minimal_with_thinking(model_name: ModelName) -> None:
    """测试开启 thinking 时 MINIMAL 模式的事件过滤：应该捕获 reasoning 相关事件"""
    async def _run() -> None:
       
        client, model = create_client(model_name, AsyncArk)
        # 启用 thinking 模式
        params = ResponseParams(thinking={"type": "enabled"})
        query = "计算 23 * 47，展示推理过程"

        event_handler = DefaultStreamEventHandler(print_fn=print, do_stats=True, do_print=False)
        
        stream_result = await astream_run(query, client=client, model=model, params=params, verbosity=StreamVerbosity.MINIMAL, event_handler=event_handler)
        
        print(f"✅Thinking 模式 event stat with query: {query}")
        event_handler.stats()
                
        # 验证：应该包含 reasoning 相关事件
        assert ResponseReasoningSummaryTextDeltaEvent in event_handler.event_types, "应该捕获推理增量事件"
        assert ResponseReasoningSummaryTextDoneEvent in event_handler.event_types, "应该捕获推理完成事件"
        assert ResponseCreatedEvent in event_handler.event_types, "应该捕获响应创建事件"
        assert ResponseCompletedEvent in event_handler.event_types, "应该捕获响应完成事件"

        print(stream_result)
                
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_astream_events_minimal_with_tool(model_name: ModelName) -> None:
    """测试带 tool 调用时 MINIMAL 模式的事件过滤：应该捕获 FC 相关事件"""
    async def _run() -> None:
        
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})
        query = "上海天气咋样"

        event_handler = DefaultStreamEventHandler(print_fn=print, do_stats=True, do_print=False)
        
        stream_result = await astream_run(query, client=client, model=model, params=params, tools=[weather_tool], verbosity=StreamVerbosity.MINIMAL, event_handler=event_handler)
        
        print(f"\n✅ Tool 调用模式 event stat with query: {query}")
        event_handler.stats()        
        
        # 验证 FC 事件被捕获
        assert ResponseFunctionCallArgumentsDoneEvent in event_handler.event_types, "应该捕获FC参数完成事件"
        assert ResponseOutputItemDoneEvent in event_handler.event_types, "应该捕获FC输出项完成事件"

        print(stream_result)

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_stream_supports_previous_response_input_items(model_name: ModelName) -> None:
    """测试同步 stream ，目前手动构建的list输入只能通过第一个参数传入。"""
    print("\n======================================================")
    print(f"测试 stream with previous input items, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})
    messages :list[ResponseInputItemParam] = [system_msg("你是一个翻译助手")]

    query = "把'你好，北京'翻译成英文，只输出结果"
    print(f"Query: {query}")
    print("stream 输出结果:", end="", flush=True)
    messages.append(user_msg(query))

    stream_result = stream(
        messages,
        None,
        client=client,
        model=model,
        params=params,
    )

    for event in stream_result:
        if isinstance(event, ResponseTextDeltaEvent):
            print(event.delta, end="", flush=True)
        else:
            pass

    print("\nstream 输出最终结果")
    print(stream_result)


@pytest.mark.parametrize("model_name", model_names)
def test_stream_run_supports_previous_response_input_items(model_name: ModelName) -> None:
    """目前手动构建的list输入只能通过第一个参数传入。"""
    print("\n======================================================")
    print(f"测试 stream_run with previous input items, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})
    messages:list[ResponseInputItemParam] = [system_msg("你是一个翻译助手")]

    query = "把'你好，北京'翻译成英文，只输出结果"
    print(f"Query: {query}")
    print("stream_run 输出结果:", end="", flush=True)
    messages.append(user_msg(query))

    response = stream_run(
        messages,
        None,
        client=client,
        model=model,
        params=params,
    )

    print("\nstream_run 输出最终结果")
    assert response is not None
    print(response.raw_text)


@pytest.mark.parametrize("model_name", model_names)
def test_astream_run_supports_previous_response_input_items(model_name: ModelName) -> None:
    """测试异步 astream_run 支持 list[ResponseInputItemParam] 作为 previous 输入"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 astream_run with previous input items, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})
        messages:list[ResponseInputItemParam] = [system_msg("你是一个翻译助手")]

        query = "把'你好，北京'翻译成英文，只输出结果"
        print(f"Query: {query}")
        print("astream_run 输出结果:\n")
        messages.append(user_msg(query))
        response = await astream_run(
            messages,
            None,
            client=client,
            model=model,
            params=params,
        )
        print("\nastream_run 输出最终结果")
        assert response is not None
        print(response.raw_text)

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_astream_events_ignore_filtered(model_name: ModelName) -> None:
    """验证 EVENTS_IGNORE 中的事件确实被过滤掉了（不被捕获）"""
    async def _run() -> None:
        client, model = create_client(model_name, AsyncArk)
        # 使用 MAXIMAL 模式获取更多事件，这样才能验证过滤
        params = ResponseParams(thinking={"type": "enabled"})
        query = "上海天气咋样"
        
        # 对比测试：先收集 MAXIMAL 模式下的事件（不过滤）
        event_handler_max = DefaultStreamEventHandler(print_fn=print, do_stats=True, do_print=False)
        stream_result_max = await astream_run(query, client=client, model=model, params=params, tools=[weather_tool], verbosity=StreamVerbosity.MAXIMAL, event_handler=event_handler_max)
        
        print(f"\n✅ MAXIMAL 模式 event stat with query: {query}")
        event_handler_max.stats()

        print(stream_result_max)
        
        # 再收集 MINIMAL 模式下的事件（有过滤）
        event_handler_min = DefaultStreamEventHandler(print_fn=print, do_stats=True, do_print=False)
        stream_result_min = await astream_run(query, client=client, model=model, params=params, tools=[weather_tool], verbosity=StreamVerbosity.MINIMAL, event_handler=event_handler_min)
        
        print(f"\n✅ MINIMAL 模式 event stat with query: {query}")
        event_handler_min.stats()
        
        print(stream_result_min)
                
        # 验证 MAXIMAL 模式下可能包含被忽略的事件（如果有的话）
        maximal_event_set = set(event_handler_max.event_types)
        minimal_event_set = set(event_handler_min.event_types)  
        
        # 验证 MINIMAL 模式下绝对没有 EVENTS_IGNORE 中的事件
        for ignored_type in EVENTS_IGNORE:
            assert ignored_type not in minimal_event_set, f"MINIMAL 模式下不应该有 {ignored_type}"
            assert ignored_type not in maximal_event_set, f"MAXIMAL 模式下不应该有 {ignored_type}"
        
    asyncio.run(_run())

@pytest.mark.parametrize("model_name", model_names)
def test_stream_with_system_prompt(model_name: ModelName) -> None:
    """测试同步流式 invoke_stream（使用 Ark）"""
    print("\n======================================================")
    print(f"测试 stream, 模型: {model_name}")

    client, model = create_client(model_name, Ark)
    params = ResponseParams(thinking={"type": "disabled"})
    
    query = "用一句话介绍北京"

    print(f"Query: {query}")
    print("stream 输出结果:", end="", flush=True)
    stream_res = stream_run(query, "回复前需要说`你好我是小途`", client=client, model=model, params=params, verbosity=StreamVerbosity.MAXIMAL)
    
    print("\nstream 输出最终结果")
    print(stream_res)

    query = "将上面的回答改成英文"
    print(f"Query: {query}")
    print("stream 输出结果:", end="", flush=True)
    stream_res1 = stream_run(query, stream_res, client=client, model=model, params=params)
    
    print("\nstream 输出最终结果")
    print(stream_res1)

@pytest.mark.parametrize("model_name", model_names)
def test_astream_with_system_prompt(model_name: ModelName) -> None:
    """测试异步流式 astream（使用 AsyncArk）"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 astream, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        query = "讲一个20个字的短笑话"

        print(f"Query: {query}")
        print("astream 输出结果:\n")

        stream_res = await astream_run(query, "回复前需要说`你好我是小途`", client=client, model=model, params=params)
        print()
        print("新一轮","*"*100)
        # exit()
        query = "20字讲述一下笑点在哪"
        print(f"Query: {query}")
        print("第二轮astream 输出结果:\n")
        stream_res1 = await astream_run(query, stream_res, client=client, model=model, params=params)

        print("\nastream 输出最终结果")
        print(stream_res1)

    asyncio.run(_run())

def test_astream_tool_with_system_prompt(model_name: ModelName) -> None:
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试stream_tool, 模型: {model_name}")
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})
        query = "上海天气咋样"
        stream_res = await astream_run(query, "回复前需要说`你好我是小途`", client=client, model=model, params=params, tools=[weather_tool])

        # print(f"stream_res: {stream_res}")
        assert stream_res is not None, "response should not be None"

        assert stream_res.tool_calls is not None, "tool_calls should not be None"
        # print("第一个tool_call:")
        # print(stream_res.tool_calls[0])

        print("=== Simulate Tool Execution: Get Weather Results ===")
        tool_output = {
            "city": "上海",
            "date": "2025-10-13",
            "temperature": "18~28℃",
            "condition": "晴转多云",
            "wind": "东北风2级"
        }

        call_output = function_call_output(
            stream_res.tool_calls[0].call_id,
            json.dumps(tool_output, ensure_ascii=False),
        )

        try:
            stream_res = await astream_run(
                [call_output], 
                stream_res,
                client=client, 
                model=model, 
                params=params)
            print("\n最终响应结果:")
            print(stream_res)
        except Exception as e:
            print(f"错误: {e}")
        
    asyncio.run(_run())

# ============= 主函数 =============
RUN_PYTEST: Final = False


def main() -> None:
    for model in model_names:
        test_stream(model)
        test_astream(model)
        test_stream_tool(model)
        
        test_astream_events_minimal_text(model)
        test_astream_events_minimal_with_thinking(model)
        test_astream_events_minimal_with_tool(model)
        test_astream_events_ignore_filtered(model)

        test_stream_with_system_prompt(model)
        test_astream_with_system_prompt(model)
        test_astream_tool_with_system_prompt(model)

        test_stream_supports_previous_response_input_items(model)
        test_stream_run_supports_previous_response_input_items(model)
        test_astream_run_supports_previous_response_input_items(model)
        break  # 只跑第一个模型；要跑全部模型可删掉本行


if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main(["-vs", __file__])
    else:
        main()
