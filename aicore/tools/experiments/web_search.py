"""
通用的联网检索数据结构和API。和具体实现无关。
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
    "WebSearchInput",
    "WebSearchItem",
    "WebSearchOutput",
    "create_web_search_tool",
    "_web_search_dummy",
]


class WebSearchInput(BaseModel):
    # 联网检索输入参数

    query: str = Field(..., description="搜索关键词")

class WebSearchItem(BaseModel):
    """联网检索结果项"""

    model_config = ConfigDict(frozen=True)

    # 以下字段不允许为空
    title: str = Field(..., title="标题", description="网页或文章标题")

    # 以下字段可以为空
    site_name: str | None = Field(default=None, title="站点名称", description="来源网站名称")
    publish_time: str | None = Field(default=None, title="发布时间", description="内容发布时间")
    summary: str | None = Field(default=None, title="摘要", description="内容摘要或片段")


class WebSearchOutput(BaseModel):
    """联网检索输出参数"""
    query: str = Field(..., description="搜索关键词")
    references: list[WebSearchItem] = Field(
        default_factory=list,
        description="符合条件的检索结果列表。每条包含标题、站点、发布时间和摘要。",
    )
    message: str = Field(default="", description="检索结果说明或错误信息")


# TODO: 还不确定是否有必要支持str。先加上至少对于开发和调试非常方便。
type WebSearchOutputLike = WebSearchOutput | str
type WebSearchWorker = TaskAWorker[WebSearchOutputLike]
type WebSearchStreamWorker = TaskAStreamWorker[str, WebSearchOutputLike, ...]


def create_web_search_tool(
    worker: WebSearchWorker | WebSearchStreamWorker,
    with_clarify: bool = False,
) -> TaskToolType[WebSearchInput, WebSearchOutputLike, str, ...]:
    """通用的联网检索工具。"""

    if with_clarify:
        description = """基于用户表达的需求，生成联网检索所需的信息: 搜索关键词、检索条件等，并执行搜索，返回符合条件的参考结果。
如缺少关键信息，无法执行搜索，该工具会返回向用户的提问。如果返回了提问，意味着信息不足，不要再继续调用该工具，必须要向用户提问以获得新信息。
注意，只有当缺乏关键细节，或者用户表达过于模糊时，才需要向用户提问。尽量避免。"""
    else:
        description = "通用联网检索工具，根据用户需求执行联网检索，返回符合条件的检索结果。"

    return create_tool(
        name="通用联网检索工具",
        description=description,
        args_schema=WebSearchInput,
        worker=worker,
        with_clarify=with_clarify,
    )

def _dummy_web_search_output(query: str) -> WebSearchOutput:
    """测试用：根据 query 生成通用的 mock 检索输出。"""
    references = [
        WebSearchItem(
        title=f"关于「{query}」的检索结果",
        site_name="示例站点",
        publish_time="2026-05-18",
        summary=f"关于「{query}」的检索结果摘要",
    )
    ]
    return WebSearchOutput(
        query=query,
        references=references,
        message=f"共 {len(references)} 条检索结果",
    )


async def _web_search_dummy(query: str) -> WebSearchOutput:
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    if random.random() < 0.5:
       raise ValueError("web search failed")

    return _dummy_web_search_output(query)


async def _web_search_dummy_stream(query: str):

    yield TaskProgress[str](progress="开始联网检索")
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    yield TaskProgress[str](progress="联网检索结果整理中")
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    if random.random() < 0.5:
       raise ValueError("web search failed")

    yield TaskSuccess[WebSearchOutputLike](result=_dummy_web_search_output(query))


async def test_web_search_tool_basic():
    print("\ntest_web_search_tool_basic")
    tool = create_web_search_tool(worker=_web_search_dummy, with_clarify=False)
    runner = TaskToolRunner()
    runner.add_tool(tool, {"query": "AI发展趋势"})
    async for event in runner.run():
        print(event.output)


async def test_web_search_stream_tool_basic():
    print("\ntest_web_search_stream_tool_basic")
    tool = create_web_search_tool(worker=_web_search_dummy_stream, with_clarify=False)

    runner = StreamTaskToolRunner()
    runner.add_tool(tool, {"query": "AI发展趋势"})

    async for event in runner.run():
        print(event)


if __name__ == "__main__":
    asyncio.run(test_web_search_tool_basic())
    asyncio.run(test_web_search_stream_tool_basic())
