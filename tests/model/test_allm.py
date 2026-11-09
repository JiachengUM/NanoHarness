from typing import Final

import pytest
import asyncio

from nanoai.model.config import ModelName
from nanoai.model.llm import allm, allm_stream, allm_output_by_schema, allm_output_by_tool
from nanoai.utils._concepts import PersonBasicInfo, Character

from tests.model.test_llm import models_to_test


@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test)
async def test_basic(model: ModelName) -> None:
    print(f"\n\n测试基本功能allm and allm_stream, 模型: {model}")
    query = "三加四是多少"

    print(f"Query: {query}")
    res = await allm(query, model=model)
    print("结果:")
    print("\n".join(res.details()))

    # 测试流式输出
    print("流式输出结果:", end="", flush=True)
    delta = True
    stream_res = await allm_stream(query, delta=delta, model=model)
    async for chunk in stream_res:
        print(chunk, end="", flush=True)
    print(f"\n流式输出最终结果: {stream_res.output}")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test)
async def test_conversation(model: ModelName) -> None:
    print(f"\n\n测试多轮对话allm_stream, 模型: {model}")
    """测试多轮对话，使用queries列表中的查询依次处理"""
    # queries = ["讲个笑话", "解释一下刚才的笑话", "再讲一个不同类型的笑话"]
    queries = ["你是谁?", "再见"]
    
    messages = []
    for query in queries:
        print(f"\n用户: {query}")
        
        stream_result = await allm_stream(query, messages or "你是一个有用的助手", model=model)
        print("助手: ", end="", flush=True)
        async for chunk in stream_result:
            print(chunk, end="", flush=True)
        
        messages = stream_result.messages


@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test)
async def test_output_by_schema(model: ModelName) -> None:
    print(f"\n\n测试结构化输出allm_output_by_schema, 模型: {model}")
    query = "请随机创建一个人物基本信息"
    try:
        res = await allm_output_by_schema(query, output_type=PersonBasicInfo, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")

    query = "请随机创建一个角色"
    try:
        res = await allm_output_by_schema(query, output_type=Character, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test)
async def test_output_by_tool(model: ModelName) -> None:
    print(f"\n\n测试结构化输出allm_output_by_tool, 模型: {model}")
    query = "请创建一个人物基本信息。随机的填写属性值。"
    try:
        res = await allm_output_by_tool(query, output_type=PersonBasicInfo, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")

    query = "请生成孙悟空角色。"
    try:
        res = await allm_output_by_tool(query, output_type=Character, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")

    # 测试list[T]的输出，对于qwen模型会死机
    query = "生成若干程序员。"
    try:
        res = await allm_output_by_tool(query, output_type=list[PersonBasicInfo], model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")


# ============= 主函数 =============
RUN_PYTEST: Final = False


async def main() -> None:
    """运行所有测试"""

    for model in models_to_test:
        await test_basic(model)
        await test_conversation(model)
        await test_output_by_schema(model)
        await test_output_by_tool(model)

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        asyncio.run(main())
        