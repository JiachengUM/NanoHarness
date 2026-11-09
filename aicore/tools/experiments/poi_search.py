"""
通用的poi search数据结构和API。和具体实现无关。
"""

import random
import asyncio

from rich import print

from pydantic import BaseModel, Field, ConfigDict

from aicore.tools import (
    TaskToolType,
    create_tool,
    TaskAWorker,
    TaskAStreamWorker,
    TaskProgress,
    TaskSuccess,
)
from aicore.tools.runner import StreamTaskToolRunner
from aicore.tools.runner.task_tool_runner import TaskToolRunner

__all__ = [
    "PoiSearchInput",
    "PoiItem",
    "PoiSearchOutput",
    "create_poi_search_tool",
    "_poi_search_dummy",
]


class PoiSearchInput(BaseModel):
    # POI搜索输入参数

    poi_type: str = Field(
        default=...,
        description="地点类型: 饭店、酒店、咖啡店、美食、书店、公园、游乐场、停车场等等",
    )

    city: str | None = Field(default=None, description="搜索城市名称，可选")

    address: str | None = Field(
        default=None,
        description="具体的结构化地址，比如: 上海市平金中心, 上海市南京路1000号",
    )

    criteria: list[str] | None = Field(
        default=None,
        description="地点搜索条件列表，每条是一个自然语言约束。例如: 位置在xxx附近, 价格人均yyy, 风格适合小孩等",
    )


class PoiItem(BaseModel):
    """地点项"""

    model_config = ConfigDict(frozen=True)

    # 以下字段不允许为空
    type: str = Field(..., title="类型", description="类型")

    name: str = Field(..., title="名称", description="名称")

    address: str = Field(..., title="详细地址", description="详细地址")

    # 以下字段可以为空
    distance: int | None = Field(
        default=None, title="离中心点距离", description="离中心点距离，单位米"
    )
    rating: str | None = Field(default=None, title="评分", description="评分")
    cost: str | None = Field(default=None, title="人均消费", description="人均消费")


class PoiSearchOutput(BaseModel):
    """POI搜索输出参数"""

    pois: list[PoiItem] = Field(
        ..., description="符合条件的地点列表.每个地点项包含类型、名称、地址。"
    )


# TODO: 还不确定是否有必要支持str。先加上至少对于开发和调试非常方便。
type PoiSearchOutputLike = PoiSearchOutput | str
type PoiSearchWorker = TaskAWorker[PoiSearchOutputLike]
# type PoiSearchStreamWorker = TaskAStreamWorker[str, PoiSearchOutputLike, [str, str|None, str|None, list[str]|None]]
type PoiSearchStreamWorker = TaskAStreamWorker[str, PoiSearchOutputLike, ...]


def create_poi_search_tool(
    worker: PoiSearchWorker | PoiSearchStreamWorker,
    with_clarify: bool = False,
    # ) -> ToolType[PoiSearchInput, PoiSearchOutputLike, str, [str,str|None, str|None, list[str]|None]]:
) -> TaskToolType[PoiSearchInput, PoiSearchOutputLike, str, ...]:
    """通用的POI信息搜索工具。"""

    if with_clarify:
        description = """基于用户表达的需求，生成地点搜索所需的信息: 城市、地点类型、搜索条件等，并执行搜索，返回符合条件的地点。
如缺少关键信息，无法执行搜索，该工具会返回向用户的提问。如果返回了提问，意味着信息不足，不要再继续调用该工具，必须要想用户提问以获得新信息。
注意，只有当缺乏关键细节，或者用户表达过于模糊时，才需要向用户提问。尽量避免。"""
    else:
        description = "搜索符合criteria字段中所有条件的地点。"

    return create_tool(
        name="通用地点搜索工具",
        description=description,
        args_schema=PoiSearchInput,
        worker=worker,
        with_clarify=with_clarify,
    )


###################### 测试


async def _poi_search_dummy(
    poi_type: str,
    city: str | None = None,
    address: str | None = None,
    criteria: list[str] | None = None,
) -> PoiSearchOutput:
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    # if random.random() < 0.5:
    #    raise ValueError("poi search failed")

    item = PoiItem(type="酒店", name="丽晶大酒店", address="香港九龙")

    return PoiSearchOutput(pois=[item])


async def _poi_search_dummy_stream(
    poi_type: str,
    city: str | None = None,
    address: str | None = None,
    criteria: list[str] | None = None,
):
    # 函数签名必须和PoiSearchStreamWorker的签名一致。否则会有type check error
    yield TaskProgress[str](progress="开始POI搜索")
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    yield TaskProgress[str](progress="POI搜索结果不符合条件，开始web search")
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    # if random.random() < 0.5:
    #    raise ValueError("poi search failed")

    item = PoiItem(type="酒店", name="丽晶大酒店", address="香港九龙")

    # 注意这里的输出类型必须使用PoiSearchOutputLike，即使真实的输出是PoiSearchOutput。否则和PoiSearchStreamWorker不兼容。
    yield TaskSuccess[PoiSearchOutputLike](result=PoiSearchOutput(pois=[item]))


async def test_poi_search_tool_basic():
    print("\ntest_poi_search_tool_basic")
    tool = create_poi_search_tool(worker=_poi_search_dummy, with_clarify=False)
    runner = TaskToolRunner()
    runner.add_tool(tool, {"poi_type": "酒店", "city": "香港", "criteria": ["有名的"]})
    async for event in runner.run():
        print(event.output)


async def test_poi_search_stream_tool_basic():
    print("\ntest_poi_search_stream_tool_basic")
    tool = create_poi_search_tool(worker=_poi_search_dummy_stream, with_clarify=False)

    runner = StreamTaskToolRunner()
    runner.add_tool(
        tool,
        {"poi_type": "酒店", "city": "香港", "address": None, "criteria": ["有名的"]},
    )

    async for event in runner.run():
        print(event)


if __name__ == "__main__":
    asyncio.run(test_poi_search_tool_basic())
    asyncio.run(test_poi_search_stream_tool_basic())
