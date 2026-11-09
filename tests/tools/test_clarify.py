import anyio
from pydantic import BaseModel, ConfigDict, Field
from rich import print

from aicore.runtime.task import TaskSuccess
from aicore.tools import TaskTool
from aicore.tools.decorators import ClarifyTaskTool, clarify_response


class WeatherInput(BaseModel):
    city: str = Field(..., description="查询城市名称")
    time_range: str | None = Field(default="today", description="查询时间范围")
    criteria: list[str] | None = Field(default=None, description="天气查询条件")


class WeatherOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    city: str
    condition: str
    temperature: str


async def weather_worker(
    city: str,
    time_range: str | None = None,
    criteria: list[str] | None = None,
) -> WeatherOutput:
    return WeatherOutput(city=city, condition="晴", temperature="15-25C")


def create_clarify_weather_tool():
    base_tool = TaskTool[WeatherInput, WeatherOutput, str, ...](
        name="天气查询工具",
        description="查询指定城市天气",
        args_schema=WeatherInput,
        worker=weather_worker,
    )
    return ClarifyTaskTool(base_tool)


async def test_clarify_schema():
    print("\n***** test_clarify_schema *****")
    tool = create_clarify_weather_tool()
    fields = tool.args_schema.model_fields
    print(fields)

    assert "city" in fields
    assert "description" in fields
    assert "clarify" in fields


async def test_clarify_simple_worker_normal():
    print("\n***** test_clarify_simple_worker_normal *****")
    tool = create_clarify_weather_tool()

    result = await tool.simple_worker(
        city="香港",
        description="查询香港今日天气",
        criteria=["是否下雨"],
    )()
    print(result)

    assert isinstance(result, WeatherOutput)
    assert result.city == "香港"


async def test_clarify_simple_worker_short_circuit():
    print("\n***** test_clarify_simple_worker_short_circuit *****")
    tool = create_clarify_weather_tool()

    result = await tool.simple_worker(
        description="用户想查天气但缺少城市",
        clarify="请问要查询哪个城市？",
    )()
    print(result)

    assert result == clarify_response("请问要查询哪个城市？")


async def test_clarify_stream_worker_short_circuit():
    print("\n***** test_clarify_stream_worker_short_circuit *****")
    tool = create_clarify_weather_tool()

    chunks = [
        chunk
        async for chunk in tool.stream_worker_factory(
            description="用户想查天气但缺少城市",
            clarify="请问要查询哪个城市？",
        )()
    ]
    print(chunks)

    assert len(chunks) == 1
    assert isinstance(chunks[0], TaskSuccess)
    assert chunks[0].result == clarify_response("请问要查询哪个城市？")


async def main():
    await test_clarify_schema()
    await test_clarify_simple_worker_normal()
    await test_clarify_simple_worker_short_circuit()
    await test_clarify_stream_worker_short_circuit()


if __name__ == "__main__":
    anyio.run(main)
