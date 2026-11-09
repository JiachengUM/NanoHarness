import asyncio
import random

from pydantic import BaseModel, Field

from aicore.tools import TaskTool


class DummyInput(BaseModel):
    input: str = Field(..., description="输入字符串")

class DummyWorker:
    def __init__(self, error_prob: float = 0.5, name: str | None = None):
        # 按照改概率抛出异常
        self.error_prob = error_prob
        self.name = name
    
    async def __call__(self, input: str) -> str:
        # 随机 sleep 0-1 秒之间的时间
        sleep_time = random.uniform(0, 1)
        await asyncio.sleep(sleep_time)
        
        # 随机 raise 异常或 return 结果
        if random.random() < self.error_prob:
            raise ValueError(f"测试异常 (sleep_time: {sleep_time:.2f}s)")
        else:
            return f"{self.name}: {input.upper()}" if self.name else input.upper()

# TODO: 最后一个类型参数按说应该是[str]，但居然会报type check error。
def create_dummy_tool(timeout: float | None = None) -> TaskTool[DummyInput, str, None, ...]:
    worker = DummyWorker()

    return TaskTool[DummyInput, str, None, ...](
        name="字符串工具",
        description="将输入转换为大写",
        args_schema=DummyInput,
        worker=worker,
        timeout=timeout,
    )
    
    # return create_tool(
    #     name="字符串工具",
    #     description="将输入转换为大写",
    #     args_schema=DummyInput,
    #     worker=worker,
    #     timeout=timeout,
    # )
