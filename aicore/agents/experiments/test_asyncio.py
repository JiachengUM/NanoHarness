import asyncio

async def test_wait_for():
    """测试 asyncio.wait_for 函数"""
    async def task():
        await asyncio.sleep(2)
        print("任务完成")
        
    try:
        await asyncio.wait_for(task(), timeout=1)
    except asyncio.TimeoutError:
        print("任务超时")


if __name__ == "__main__":
    asyncio.run(test_wait_for())