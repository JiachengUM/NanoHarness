"""
通用的天气查询数据结构和API。和具体实现无关。
"""

import asyncio
import random

from pydantic import BaseModel, Field, ConfigDict

from aicore.tools import TaskToolType, create_tool, TaskAWorker, TaskAStreamWorker
from aicore.tools.runner.task_tool_runner import TaskToolRunner

__all__ = [
    "WeatherInput",
    "WeatherOutput",
    "create_weather_search_tool",
    "_weather_dummy",
]

class WeatherInput(BaseModel):
    # 天气查询输入参数

    city: str = Field(..., description="查询城市名称")

    time_range: str | None = Field(default="today", description="查询时间范围: today(今天), tomorrow(明天), 7days(未来7天)")

    criteria: list[str] | None = Field(default=None, description="天气查询的具体需求，如湿度、风力等")


class WeatherOutput(BaseModel):
    """天气信息项"""

    model_config = ConfigDict(frozen=True)

    # 必填字段
    date: str = Field(..., title="日期", description="日期，格式如: 2026-04-13")

    condition: str = Field(..., title="天气状况", description="天气状况，如: 晴、多云、小雨")

    temperature: str = Field(..., title="温度范围", description="温度范围，如: 15-25°C")

    # 可选字段
    humidity: str | None = Field(default=None, title="湿度", description="相对湿度，如: 60%")

    wind: str | None = Field(default=None, title="风力", description="风力等级，如: 微风 3级")


# 支持str类型方便开发和调试
type WeatherOutputLike = WeatherOutput | str
type WeatherWorker = TaskAWorker[WeatherOutputLike]
type WeatherStreamWorker = TaskAStreamWorker[str, WeatherOutputLike, ...]

def create_weather_search_tool(
    worker: WeatherWorker | WeatherStreamWorker,
    with_clarify: bool = False,
    ) -> TaskToolType[WeatherInput, WeatherOutputLike, str, ...]:
    """通用的天气查询工具。"""

    if with_clarify:
        description = """基于用户表达的需求，生成天气查询所需的信息: 城市、时间范围等，并执行查询，返回天气信息。
如缺少关键信息，无法执行查询，该工具会返回向用户的提问。
注意，只有当缺乏关键细节，或者用户表达过于模糊时，才需要向用户提问。尽量避免。"""
    else:
        description= "查询指定城市在指定日期的天气信息。"

    return create_tool(
        name="通用天气查询工具",
        description=description,
        args_schema=WeatherInput,
        worker=worker,
        with_clarify=with_clarify,
    )

############## 以下是测试

async def _weather_dummy(city: str, description: str | None = None, time_range: str | None = None, details: bool | None = None, criteria: list[str] | None = None) -> WeatherOutput:
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    #if random.random() < 0.5:
    #    raise ValueError("music search failed")

    weather_data = WeatherOutput(
        date="2026-04-13",
        condition="晴",
        temperature="15-25°C",
        humidity="60%",
        wind="微风 3级"
    )
    return weather_data


async def test_weather_tool_basic():
    tool = create_weather_search_tool(worker=_weather_dummy)
    runner = TaskToolRunner()
    runner.add_tool(tool, {"city": "北京", "time_range": "today"})
    async for event in runner.run():
        print(event.output)

if __name__ == "__main__":
    asyncio.run(test_weather_tool_basic())