from projects.uiagent.core import InfoTask,InfoExecMode
from projects.uiagent.jie_parking.data_define import (
    PlateNumber,
    UserMeaning,
    UserMeaningPureString
)
from openai.types.chat import ChatCompletionSystemMessageParam
import asyncio
from nanoai.model.config import AsyncOpenAI, ModelName, create_client
from nanoai.model.llm import allm_output
import time
from typing import Dict

# 定义要测试的模型
MODELS_TO_TEST = [
    ModelName.DOUBAO_SEED_1_6_FLASH_250715,
    ModelName.DOUBAO_SEED_1_6_FLASH_250615,
    ModelName.DOUBAO_SEED_1_6_FLASH_250828,
]

car_plate_info_task = InfoTask(
            brief="询问给哪辆车缴费",
            info_type=PlateNumber,
            validator=PlateNumber.validator,
            exec_mode=InfoExecMode.NL_ANY,
        )

user_meaning = InfoTask(
            brief="""根据最新的用户对话记录，提取和总结用户最新的表达意思的小结。""",
            info_type=UserMeaning,
            validator=UserMeaning.validator,
            # info_type=UserMeaningPureString,
            exec_mode=InfoExecMode.NL_ANY,
        )

query = "帮我给沪A12345停车缴费"
tools = {"tool_name_1":"maker", "tool_name_2":"car_plate_info_task"}
tool_names = list(tools.keys())
prompt = f"""Respond to the human as helpfully and accurately as possible. You have access to the following tools:

{tools}

Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).

Valid "action" values: "Final Answer" or {tool_names}

Provide only ONE action per $JSON_BLOB, as shown:

```json
{{
  "action": $TOOL_NAME,
  "action_input": $INPUT
}}
```
Let's start!

User: I want to make an 12-inch cake.Pick a tool for me.
"""

extra_body = {
        "thinking": {
            "type": "disabled",
        }
    }

messages = [ChatCompletionSystemMessageParam({"role": "system", "content": prompt})] # 必须要有至少1条systemt message，否则task.arun报错说头部必有system message


async def test_model_with_thinking(
    model_name: ModelName,
    thinking_enabled: bool,
    test_name: str
) -> Dict[str, float]:
    """测试指定模型在 thinking 或 non-thinking 模式下的耗时"""
    client, model = create_client(model_name, AsyncOpenAI)
    results = {}
    
    print(f"\n{'='*60}")
    print(f"测试: {model_name.value} - {test_name}")
    print(f"{'='*60}")
    
    # 准备 extra_body 参数
    extra_body = None if thinking_enabled else {
        "thinking": {
            "type": "disabled",
        }
    }
    
    # 准备 kwargs，用于传递给 InfoTask.arun
    kwargs = {}
    if extra_body:
        kwargs["extra_body"] = extra_body
    
    # 测试 1: user_meaning.arun
    start = time.time()
    try:
        user_meaning_info = await user_meaning.arun(query, messages, model=model, client=client, **kwargs)
        elapsed = time.time() - start
        results["user_meaning"] = elapsed
        print(f" 提取 user_meaning 耗时: {elapsed:.2f} 秒 ({test_name})")
    except Exception as e:
        print(f" user_meaning 测试失败: {e}")
        results["user_meaning"] = -1
    
    # 测试 2: car_plate_info_task.arun
    start = time.time()
    try:
        car_plate_info = await car_plate_info_task.arun(query, messages, model=model, client=client, **kwargs)
        elapsed = time.time() - start
        results["car_plate_info"] = elapsed
        print(f" 提取 car_plate_info 耗时: {elapsed:.2f} 秒 ({test_name})")
    except Exception as e:
        print(f" car_plate_info 测试失败: {e}")
        results["car_plate_info"] = -1
    
    # 测试 3: 使用 allm_output 进行结构化输出测试（可以控制 thinking 模式）
    # 使用 PlateNumber 作为测试的结构化输出类型
    start = time.time()
    try:
        kwargs = {}
        if extra_body:
            kwargs["extra_body"] = extra_body
        
        # 使用 allm_output 进行结构化输出，这样可以控制 thinking 模式
        result = await allm_output(
            query,
            messages,
            output_type=PlateNumber,
            model=model,
            client=client,
            **kwargs
        )
        elapsed = time.time() - start
        results["structured_output"] = elapsed
        print(f" 结构化输出（PlateNumber）耗时: {elapsed:.2f} 秒 ({test_name})")
        print(f"  提取结果: {result.output}")
    except Exception as e:
        print(f" 结构化输出测试失败: {e}")
        results["structured_output"] = -1
    
    return results


async def compare_models():
    """对比三个模型在 thinking 和 non-thinking 模式下的结构化输出性能"""
    print("\n" + "="*80)
    print("开始对比测试：三个模型在 thinking 和 non-thinking 模式下的结构化输出耗时")
    print("="*80)
    
    all_results: Dict[str, Dict[str, Dict[str, float]]] = {}
    
    for model_name in MODELS_TO_TEST:
        model_key = model_name.value
        all_results[model_key] = {}
        
        # 测试 thinking 模式（默认）
        all_results[model_key]["thinking"] = await test_model_with_thinking(
            model_name, thinking_enabled=True, test_name="Thinking 模式"
        )
        
        # 等待一下，避免请求过快
        await asyncio.sleep(1)
        
        # 测试 non-thinking 模式
        all_results[model_key]["non_thinking"] = await test_model_with_thinking(
            model_name, thinking_enabled=False, test_name="Non-Thinking 模式"
        )
        
        # 等待一下，避免请求过快
        await asyncio.sleep(1)
    
    # 打印对比结果
    print("\n" + "="*80)
    print("性能对比结果汇总")
    print("="*80)
    
    # 1. 结构化输出对比（可以控制 thinking 模式）
    print(f"\n【structured_output - 使用 allm_output 进行结构化输出（PlateNumber）】")
    print("-" * 80)
    print(f"{'模型':<40} {'Thinking':<15} {'Non-Thinking':<15} {'加速比':<10}")
    print("-" * 80)
    
    for model_key in all_results.keys():
        thinking_time = all_results[model_key]["thinking"].get("structured_output", -1)
        non_thinking_time = all_results[model_key]["non_thinking"].get("structured_output", -1)
        
        if thinking_time > 0 and non_thinking_time > 0:
            speedup = thinking_time / non_thinking_time
            print(f"{model_key:<40} {thinking_time:>8.2f}s     {non_thinking_time:>8.2f}s     {speedup:>6.2f}x")
        elif thinking_time > 0:
            print(f"{model_key:<40} {thinking_time:>8.2f}s     {'失败':<15} {'N/A':<10}")
        elif non_thinking_time > 0:
            print(f"{model_key:<40} {'失败':<15} {non_thinking_time:>8.2f}s     {'N/A':<10}")
        else:
            print(f"{model_key:<40} {'失败':<15} {'失败':<15} {'N/A':<10}")
    
    # 2. InfoTask 测试结果对比（user_meaning）
    print(f"\n【InfoTask - user_meaning 对比】")
    print("-" * 80)
    print(f"{'模型':<40} {'Thinking':<15} {'Non-Thinking':<15} {'加速比':<10}")
    print("-" * 80)
    
    for model_key in all_results.keys():
        thinking_time = all_results[model_key]["thinking"].get("user_meaning", -1)
        non_thinking_time = all_results[model_key]["non_thinking"].get("user_meaning", -1)
        
        if thinking_time > 0 and non_thinking_time > 0:
            speedup = thinking_time / non_thinking_time
            print(f"{model_key:<40} {thinking_time:>8.2f}s     {non_thinking_time:>8.2f}s     {speedup:>6.2f}x")
        elif thinking_time > 0:
            print(f"{model_key:<40} {thinking_time:>8.2f}s     {'失败':<15} {'N/A':<10}")
        elif non_thinking_time > 0:
            print(f"{model_key:<40} {'失败':<15} {non_thinking_time:>8.2f}s     {'N/A':<10}")
        else:
            print(f"{model_key:<40} {'失败':<15} {'失败':<15} {'N/A':<10}")
    
    # 3. InfoTask 测试结果对比（car_plate_info）
    print(f"\n【InfoTask - car_plate_info 对比】")
    print("-" * 80)
    print(f"{'模型':<40} {'Thinking':<15} {'Non-Thinking':<15} {'加速比':<10}")
    print("-" * 80)
    
    for model_key in all_results.keys():
        thinking_time = all_results[model_key]["thinking"].get("car_plate_info", -1)
        non_thinking_time = all_results[model_key]["non_thinking"].get("car_plate_info", -1)
        
        if thinking_time > 0 and non_thinking_time > 0:
            speedup = thinking_time / non_thinking_time
            print(f"{model_key:<40} {thinking_time:>8.2f}s     {non_thinking_time:>8.2f}s     {speedup:>6.2f}x")
        elif thinking_time > 0:
            print(f"{model_key:<40} {thinking_time:>8.2f}s     {'失败':<15} {'N/A':<10}")
        elif non_thinking_time > 0:
            print(f"{model_key:<40} {'失败':<15} {non_thinking_time:>8.2f}s     {'N/A':<10}")
        else:
            print(f"{model_key:<40} {'失败':<15} {'失败':<15} {'N/A':<10}")
    
    # 模型间对比（Thinking 模式 - 结构化输出）
    print("\n" + "="*80)
    print("模型间对比（Thinking 模式 - 结构化输出）")
    print("="*80)
    print(f"{'模型':<40} {'structured_output':<20}")
    print("-" * 80)
    thinking_times = []
    for model_key in all_results.keys():
        thinking_time = all_results[model_key]["thinking"].get("structured_output", -1)
        if thinking_time > 0:
            thinking_times.append((model_key, thinking_time))
            print(f"{model_key:<40} {thinking_time:>8.2f}s")
    
    if thinking_times:
        fastest = min(thinking_times, key=lambda x: x[1])
        print(f"\n最快模型（Thinking 模式）: {fastest[0]} ({fastest[1]:.2f}s)")
    
    # 模型间对比（Non-Thinking 模式 - 结构化输出）
    print("\n" + "="*80)
    print("模型间对比（Non-Thinking 模式 - 结构化输出）")
    print("="*80)
    print(f"{'模型':<40} {'structured_output':<20}")
    print("-" * 80)
    non_thinking_times = []
    for model_key in all_results.keys():
        non_thinking_time = all_results[model_key]["non_thinking"].get("structured_output", -1)
        if non_thinking_time > 0:
            non_thinking_times.append((model_key, non_thinking_time))
            print(f"{model_key:<40} {non_thinking_time:>8.2f}s")
    
    if non_thinking_times:
        fastest = min(non_thinking_times, key=lambda x: x[1])
        print(f"\n最快模型（Non-Thinking 模式）: {fastest[0]} ({fastest[1]:.2f}s)")


if __name__ == "__main__":
    asyncio.run(compare_models())
