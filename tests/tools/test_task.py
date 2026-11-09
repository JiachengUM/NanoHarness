import asyncio
from rich import print
from pydantic import BaseModel, Field

from aicore.tools.builtin import create_dummy_tool
from aicore.tools.decorators import extend_model_with_goal_generation


async def test_basic():
    tool = create_dummy_tool()
    input = "hello"

    # 测试多次执行，模拟真实情况
    print("\n测试多次执行，模拟真实情况:")
    for i in range(3):
        print(f"\n执行 #{i+1}")
        res = await tool._arun(input)
        if res.is_success:
            print(f"成功: {res.data}")
        else:
            print(f"失败: {res.error}")


async def test_stream_worker():
    tool = create_dummy_tool()
    input = "hello"
    #input = 1   # tool.stream_worker_factory 会报type error。赞！
    
    
    print("\n测试流式输出:")
    async for event in tool.stream_worker_factory(input)():
        print(event)


async def test_on_error():
    # 测试自定义错误处理
    tool = create_dummy_tool()
    input = "hello"
    
    print("\n测试自定义错误处理:")
    tool.on_error = lambda e: f"自定义错误处理: {e}"
    res = await tool._arun(input)
    print(f"自定义错误处理: {res}")


async def test_timeout():
    # 测试超时
    tool = create_dummy_tool(timeout=0.5)
    input = "hello"
    
    print("\n测试超时情况 (timeout=0.5):")
    for i in range(3):
        print(f"\n执行 #{i+1}")
        res = await tool._arun(input)
        if res.is_success:
            print(f"成功: {res.data}")
        else:
            print(f"超时: {res.error}")


async def test_boundary_cases():
    print("\n测试边界情况")
    # 测试超时时间为 0
    tool = create_dummy_tool()
    input = "hello"
    res = await tool._arun(input)
    print(f"超时时间为 0: {res}")
    # 测试超时时间为负数
    tool.timeout = -1
    res = await tool._arun(input)
    print(f"超时时间为负数: {res}")


def test_extend_model_with_goal_generation():
    class TestSchema(BaseModel):
        my_value: str = Field(default=..., title="我的值", description="我的值")
    
    print("\n测试extend_model_with_goal_generation")
    extended = extend_model_with_goal_generation(TestSchema)
    print(extended.__name__)

    fields = extended.model_fields
    print(fields)


async def main():
    test_extend_model_with_goal_generation()
    return

    await test_basic()
    return

    await test_stream_worker()
    await test_on_error()
    await test_timeout()
    await test_boundary_cases()


if __name__ == "__main__":
    asyncio.run(main())
