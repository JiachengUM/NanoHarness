from typing import Final, Literal

import asyncio

import json

import pytest

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, AsyncArk
from aicore.models.responses import (
    ResponseParams,
    FunctionToolParam,
    function_call_output,
    ainvoke,
    astream,
    astream_run,
    Response
)
from aicore.models.responses.streaming import DefaultStreamEventHandler


model_names: Final[list[ModelName]] = [
        # ModelName.SEED_1_8_251228,            # 最好的，已开通缓存服务
        ModelName.SEED_1_8_251228,
        # ModelName.SEED_1_6_251015,
        # ModelName.SEED_1_6_FLASH_250828,      # 最快的
    ]


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


send_message_tool = FunctionToolParam(
    type="function",
    name="send_message",
    description="向指定接收人发送消息",
    parameters={
        "type": "object",
        "properties": {
            # 必选：接收人
            "receiver": {
                "type": "string",
                "description": "消息接收人标识，如张三、李四、王五"
            },
            # 必选：消息内容（文本）
            "content": {
                "type": "string",
                "description": "消息内容：文本直接传字符串"
            },
        },
        "required": ["receiver", "content"]
    }
)


media_tool = FunctionToolParam(
    type="function",
    name="media",
    description="播放媒体内容，如广播、音乐等",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "媒体播放命令，如'播放上海交通广播'"
            }
        },
        "required": ["command"]
    }
)


@pytest.mark.parametrize("model_name", model_names)
def test_tool_caching_conflict(model_name: ModelName) -> None:
    """自定义function calling 工具 + caching=enabled，与previous_response_id 冲突 → 抛异常"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试tool_caching_conflict, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)

        params = ResponseParams(
            thinking={"type": "disabled"},
            caching={"type": "enabled"}            # 与tool 冲突字段
        )
        print("支持自定义function calling 工具时，caching=enabled 不会抛异常")
        try:
            query = "上海天气咋样"
            print(f"\n第一轮Query: {query}")
            result = await ainvoke(query, client=client, model=model, params=params, tools=[weather_tool])
            print(f"\n第一轮result:\n{result}")
            assert result.tool_calls, "tool_calls should not be None"

            print("\n证明caching开启，支持自定义function calling 工具")

            # print(result.tool_calls[0])
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
                # tools=[weather_tool],
                params=params)
            print("\n结果 with invoke_with_tool:")
            print(f"\nfc调用后,模型回复:\n{fc_result}")
            # 深拷贝，避免修改原始response
            fc_reuslt_copy = fc_result.model_copy(deep=True)

        except Exception as e:
            print(f"\n【0报错表示失败，因为支持自定义function calling 工具时，caching=enabled 不会抛异常！】: {e}")

        query2 = "我刚刚说了啥,复述一遍" 
        try:
            print("\n======================================================")
            print("\n当前验证：使用同一个带缓存的previous id + tools，抛异常\n")
            print(f"\n第二轮Query: {query2}")
            # 使用同一个带缓存的previous id + tools，抛异常
            result = await ainvoke(query2, fc_result, client=client, model=model, params=params, tools=[weather_tool])
            print(f"\n第二轮result:\n{result}")
        except Exception as e:
            print(f"\n【1报错表示正确！】: {e}")
            print("\n说明：这里传入了自定义tools以及上一轮带caching的response.id，证明：复用带缓存的历史响应 ID（previous_response_id）时，不允许在当前请求中设置 tools 参数")

        try:
            print("\n======================================================")
            print("\n当前验证：使用同一个带缓存的previous id 不带tools，可运行\n")
            print(f"\n新第二轮Query: {query2}")
            # 使用同一个带缓存的previous id 不带tools，可运行
            result = await ainvoke(query2, fc_reuslt_copy, client=client, model=model, params=params)
            print(f"\n新起一轮对话，新第二轮result:\n{result}")
            print("\n说明：这里传入了第一轮带caching的response.id，证明：无tools时，复用带缓存的历史响应 ID（previous_response_id）时，可正常运行")
        except Exception as e:
            print(f"\n【2报错表示正确！】: {e}")

        
        print("*"*80)
        result = f"""\n参数：{params}\n 结论：\n
        1. 自定义function calling  + caching=enabled 支持缓存。
        但是后续请求，tools 和previous_response_id 不能同时使用。(即使用tools时，无法享受上下文缓存和上下文历史记忆)。
        
        2. 即使caching=disabled 时（无缓存）。后续请求，tools 和previous_response_id 也不能同时使用。"""
        print(result)

    asyncio.run(_run())



@pytest.mark.parametrize("model_name", model_names)
def test_stream_caching_prefix_error(model_name: ModelName) -> None:
    """创建前缀缓存Input tokens需要大于等于 256 tokens，否则会报错；stream参数不能设置为true。
    """
    print("\n======================================================")
    print(f"测试stream_caching_prefix_error, 模型: {model_name}")
    async def _run() -> None:
        
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"},caching={"type": "enabled", "prefix": True})
        print(f"\n参数: {params}")
        try:
            print("\n创建前缀缓存，Input tokens需要大于等于 256 tokens")
            _ = await ainvoke("讲一个冷笑话", client=client, model=model, params=params)
        except Exception as e:
            print(f"\n【报错表示正确！】: {e}")

        try:
            print("\nstream 创建前缀缓存，stream参数不能设置为true。")
            _ = await astream("讲一个冷笑话", client=client, model=model, params=params)
        except Exception as e:
            print(f"\n【报错表示正确！】: {e}")
        
        try:
            params = ResponseParams(thinking={"type": "disabled"},caching={"type": "enabled"})

            print("\nstream 创建缓存，不使用前缀缓存")
            stream_res = await astream_run("讲一个冷笑话", client=client, model=model, params=params)
            
            print("\nstream 输出最终结果:")
            print(stream_res)
        except Exception as e:
            print(f"\n【报错表示失败！】: {e}")
     
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_multiple_function_calling(model_name: ModelName) -> None:
    """多function calling 工具调用"""
    print("\n======================================================")
    print(f"测试multiple_function_calling, 模型: {model_name}")
    async def _run() -> None:
        print("循环处理多轮工具调用：自动检测工具调用→执行→回填，直到无工具调用")
        # 1. 初始化客户端和基础参数
        client, model = create_client(model_name, AsyncArk)
        # params = ResponseParams(thinking={"type": "disabled"},caching={"type": "enabled"}) #cache开启状态，后续请求不传tool（一定不能传tool，否则会报错）

        params = ResponseParams(thinking={"type": "disabled"},caching={"type": "disabled"}) #cache关闭状态，后续请求可不传tool（也可传tool），依旧可以进行tool调用
        query = "为我查询下上海天气，再发送'生日快乐'连同天气信息发给张三"
        
        # 2. 循环变量初始化
        previous_response: Response | None = None  # 上一轮响应（用于缓存/上下文）
        current_input = query  # 初始输入是用户问题，后续是工具结果列表
        has_more_tool_calls = True  # 是否还有工具调用需要处理
        round_num = 0  # 记录轮次
        
        # 3. 核心循环：处理工具调用直到无工具
        while has_more_tool_calls:
            round_num += 1
            print(f"\n===== 第 {round_num} 轮调用 =====")
            
            # 3.1 调用大模型（流式）
            print(f"当前输入: {current_input if isinstance(current_input, str) else '工具结果列表'}")
            print("流式输出：", end="")
            stream_res = await astream_run(
                current_input,
                previous_response,
                client=client,
                model=model,
                params=params,
                tools=[weather_tool, send_message_tool] if round_num == 1 else None, # 首轮传工具，后续无需重复传
                event_handler=DefaultStreamEventHandler(do_print=False) # 关闭流式输出打印
            )
            
            print(f"\n第 {round_num} 轮最终结果: {stream_res}")
            assert stream_res is not None
            
            # 3.3 更新上一轮响应ID（用于下一轮回填）
            previous_response = stream_res
            
            # 3.4 检查是否有工具调用
            tool_calls = stream_res.tool_calls
            if tool_calls and len(tool_calls) > 0:
                print(f"\n检测到 {len(tool_calls)} 个工具调用，执行工具...")
                # 执行所有工具调用，生成回填结果
                call_outputs = []
                for call in tool_calls:
                    assert call.id is not None
                    print(f"执行工具：{call.name} (ID: {call.id})")
                    # 模拟工具执行
                    if call.name == "get_weather":
                        tool_output = {
                            "city": "上海",
                            "date": "2025-10-13",
                            "temperature": "18~28℃",
                            "condition": "晴转多云",
                            "wind": "东北风2级"
                        }
                    elif call.name == "send_message":
                        tool_output = {
                            "status": "success",
                            "message": "消息发送成功"
                        }
                    else:
                        tool_output = {"error": "Unknown tool"}
                    # 封装工具结果
                    call_output = function_call_output(
                        call.id,
                        json.dumps(tool_output, ensure_ascii=False),
                    )
                    call_outputs.append(call_output)
                # 下一轮输入改为工具结果列表
                current_input = call_outputs
                print(f"工具执行完成，回填结果：{call_outputs}")
            else:
                # 无工具调用，结束循环
                has_more_tool_calls = False
                print("\n无更多工具调用，结束循环！")

        assert stream_res is not None

        print(stream_res.id)

        # 用instructions引导模型直接生成最终答案？https://www.volcengine.com/docs/82379/1569618?lang=zh 好像没用
        params.instructions = "绝对不可以调用tools！！直接回复！"
        stream_res = await astream_run(
                "重新查下北京的天气。",
                previous_response,
                client=client,
                model=model,
                params=params,
                tools=None, 
                event_handler=DefaultStreamEventHandler(do_print=False) # 关闭流式输出打印
            )
            
        print(f"\n基于前文的不带tool配置的约束，最终结果: {stream_res}")
        assert stream_res is not None
        tool_calls = stream_res.tool_calls
        assert tool_calls is None, "期望没有工具调用,但是实际存在工具调用"
        
    asyncio.run(_run())

@pytest.mark.parametrize("model_name", model_names)
def test_message_and_tool_calls_both_non_none(model_name: ModelName = ModelName.SEED_1_8_251228) -> None:
    """多function calling 工具调用，同时存在message和tool_calls，冲突"""
    print("\n======================================================")
    print(f"测试多轮工具调用，同时存在message和tool_calls, 模型: {model_name}")
    async def _run() -> None:
        print("循环处理多轮工具调用：自动检测工具调用→执行→回填，直到无工具调用")
        # 1. 初始化客户端和基础参数
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"},caching={"type": "disabled"})

        # 报错，message和tool_calls同时存在（1.8模型会出现该情况，1.6暂未发现） 
        query = "获取上海明后天的天气，如果温度超过25度，打开空调到凉爽模式24度,并播放上海交通广播" 
        # 通过
        # query = "获取上海明后天的天气，如果温度超过25度，打开空调到凉爽模式24度,否则播放上海交通广播" 

        # 2. 循环变量初始化
        previous_response: Response | None = None  # 上一轮响应（用于缓存/上下文）
        current_input = query  # 初始输入是用户问题，后续是工具结果列表
        has_more_tool_calls = True  # 是否还有工具调用需要处理
        round_num = 0  # 记录轮次
        
        # 3. 核心循环：处理工具调用直到无工具
        while has_more_tool_calls:
            round_num += 1
            print(f"\n===== 第 {round_num} 轮调用 =====")
            
            # 3.1 调用大模型
            print(f"当前输入: {current_input if isinstance(current_input, str) else '工具结果列表'}")
    
            res = await ainvoke(
                current_input,
                previous_response,
                client=client,
                model=model,
                params=params,
                tools=[weather_tool, media_tool] # 如果开启caching，这里必须只在首轮传工具，后续不重复传
            )
            if res.message is not None and res.tool_calls is not None:
                print(f"message和tool_calls同时存在，\n {res}")
                print()
                print(f"\n当前message: {res.message}")
                print(f"\n当前tool_calls: {res.tool_calls}")
                break
            
            # 3.2 输出并打印
            print(f"\n第 {round_num} 轮最终结果: {res}")
            assert res is not None
            
            # 3.3 更新上一轮响应ID（用于下一轮回填）
            previous_response = res
            
            # 3.4 检查是否有工具调用
            tool_calls = res.tool_calls
            if tool_calls and len(tool_calls) > 0:
                print(f"\n检测到 {len(tool_calls)} 个工具调用，执行工具...")
                # 执行所有工具调用，生成回填结果
                call_outputs = []
                for call in tool_calls:
                    assert call.id is not None
                    print(f"执行工具：{call.name} (ID: {call.id})")
                    # 模拟工具执行
                    if call.name == "get_weather":
                        tool_output = {
                            "city": "上海",
                            "date": "明后天",
                            "temperature": "14℃和15℃，",
                            "condition": "晴转多云",
                            "wind": "东北风2级"
                        }
                    elif call.name == "media":
                        tool_output = {
                            "status": "success",
                            "message": "媒体播放成功"
                        }
                    else:
                        tool_output = {"error": "Unknown tool"}
                    # 封装工具结果
                    call_output = function_call_output(
                        call.id,
                        json.dumps(tool_output, ensure_ascii=False),
                    )
                    call_outputs.append(call_output)
                # 下一轮输入改为工具结果列表
                current_input = call_outputs
                print(f"工具执行完成，回填结果：{call_outputs}")
            else:
                # 无工具调用，结束循环
                has_more_tool_calls = False
                print(f"第 {round_num} 的模型输出：\n\n{res.raw_text}")
                print("\n无更多工具调用，结束循环！")
        
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_function_calls_elapsed_with_cache_comparison(model_name: ModelName) -> None:
    """function calling 工具调用，主要测试缓存开启和关闭的加速情况"""
    # print("\n======================================================")
    # print(f"测试function_calling_elapsed, 模型: {model_name}")

    async def _run(caching_mode: Literal["disabled","enabled"]):
        # print("循环处理多轮工具调用：自动检测工具调用→执行→回填，直到无工具调用")

        # print(f"caching_mode: {caching_mode}")
        # 1. 初始化客户端和基础参数
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(temperature=0.01,thinking={"type": "disabled"},caching={"type": caching_mode})
        query = "为我查询下上海天气"
        
        # 2. 循环变量初始化
        previous_response: Response | None = None  # 上一轮响应（用于缓存/上下文）
        current_input = query  # 初始输入是用户问题，后续是工具结果列表
        has_more_tool_calls = True  # 是否还有工具调用需要处理
        round_num = 0  # 记录轮次
        import time 
        start_time = time.time()
        # 3. 核心循环：处理工具调用直到无工具
        while has_more_tool_calls:
            round_num += 1
            # print(f"\n===== 第 {round_num} 轮调用 =====")
            
            # 3.1 调用大模型（流式）
            # print(f"当前输入: {current_input if isinstance(current_input, str) else '工具结果列表'}")
            res = await ainvoke(
                current_input,
                previous_response,
                client=client,
                model=model,
                params=params,
                tools=[weather_tool] if (round_num == 1) else []  # 均首轮传工具，后续无需重复传，这里只调用一个tool
            )
            
            # 3.2 输出并打印
            # print(f"\n第 {round_num} 轮最终结果: {res}")
            assert res is not None
            
            # 3.3 更新上一轮响应ID（用于下一轮回填）
            previous_response = res
            
            # 3.4 检查是否有工具调用
            tool_calls = res.tool_calls
            if tool_calls and len(tool_calls) > 0:
                # print(f"\n检测到 {len(tool_calls)} 个工具调用，执行工具...")
                # 执行所有工具调用，生成回填结果
                call_outputs = []
                for call in tool_calls:
                    assert call.id is not None
                    # print(f"执行工具：{call.name} (ID: {call.id})")
                    # 模拟工具执行
                    if call.name == "get_weather":
                        tool_output = {
                            "city": "上海",
                            "date": "2025-10-13",
                            "temperature": "18~28℃",
                            "condition": "晴转多云",
                            "wind": "东北风2级"
                        }
                    elif call.name == "send_message":
                        tool_output = {
                            "status": "success",
                            "message": "消息发送成功"
                        }
                    else:
                        tool_output = {"error": "Unknown tool"}
                    # 封装工具结果
                    call_output = function_call_output(
                        call.id,
                        json.dumps(tool_output, ensure_ascii=False),
                    )
                    call_outputs.append(call_output)
                # 下一轮输入改为工具结果列表
                current_input = call_outputs
                # print(f"工具执行完成，回填结果：{call_outputs}")
            else:
                # 无工具调用，结束循环
                has_more_tool_calls = False
                # print("\n无更多工具调用，结束循环！")

        return res.usage, int((time.time() - start_time)*1000)

    async def main_async(num_runs: int = 40):
        semaphore = asyncio.Semaphore(20)
        
        async def run_one(mode: Literal["disabled","enabled"], idx: int) -> tuple[str, int]:
            """单次运行"""
            async with semaphore:
                usage, elapsed = await _run(mode)
                print(f"【{mode}】 第{idx+1}次: {elapsed}ms")
                return mode, elapsed
        
        # 创建所有任务
        tasks = [
            run_one(mode, i) for i in range(num_runs) for mode in ["enabled", "disabled"]  # type: ignore
        ]
        
        print(f"\n========== 开始并发跑 {len(tasks)} 次测试 ==========")
        results: list[tuple[str, int]] = await asyncio.gather(*tasks)
        
        # 统计
        enable_times = [t for mode, t in results if mode == "enabled"]
        disable_times = [t for mode, t in results if mode == "disabled"]
        avg_enable = sum(enable_times) / len(enable_times)
        avg_disable = sum(disable_times) / len(disable_times)
        
        print("\n========== 并发统计结果 ==========")
        print(f"有缓存平均: {avg_enable:.0f}ms (min={min(enable_times)}ms, max={max(enable_times)}ms)")
        print(f"无缓存平均: {avg_disable:.0f}ms (min={min(disable_times)}ms, max={max(disable_times)}ms)")
        print(f"提速比: {avg_disable:.0f}/{avg_enable:.0f} = {avg_disable/avg_enable:.2f}倍")
        
    asyncio.run(main_async(num_runs=20))
# ============= 主函数 =============
RUN_PYTEST: Final = False


def main() -> None:
    for model in model_names:        
        # #自定义function calling 工具 + caching=enabled 与previous_response_id 冲突 → 抛异常
        test_tool_caching_conflict(model)

        # #创建前缀缓存Input tokens需要大于等于 256 tokens，否则会报错；stream参数不能设置为true。stream参数不能设置为true
        # test_stream_caching_prefix_error(model)

        # # #多function calling 工具调用, 可以开启cache，再第一轮传入tool，后续不传tool参数，实现多轮工具调用。cache关闭时，首轮传了tool之后，后续传不传均可。react agent中是不是可以换成这个逻辑？
        # test_multiple_function_calling(model)

        # # 实现多轮工具调用，复现bug，message和tool_calls有概率同时存在。官方文档：( https://www.volcengine.com/docs/82379/1262342?lang=zh#ff6e0fcb )
        # test_message_and_tool_calls_both_non_none()

        # # 测试开启缓存以及关闭缓存的加速情况,实测提速1.1X左右
        # test_function_calls_elapsed_with_cache_comparison(model)
        break  # 只跑第一个模型；要跑全部模型可删掉本行


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        #test_safe_update()
        main()
