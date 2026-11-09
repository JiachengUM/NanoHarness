"""
通用的音乐搜索数据结构和API。和具体实现无关。
"""

import asyncio
import random

from pydantic import BaseModel, ConfigDict, Field

from rich import print
from aicore.tools import (
    TaskAWorker,
    TaskToolType,
    create_tool,
    TaskAStreamWorker,
    TaskProgress,
    TaskSuccess,
)
from aicore.tools.runner import StreamTaskToolRunner
from aicore.tools.runner.task_tool_runner import TaskToolRunner

__all__ = [
    "MusicSearchInput",
    "MusicItem",
    "MusicSearchOutput",
    "music_search_tool",
    "_music_search_dummy",
    "_music_search_dummy_stream",
]


class MusicSearchInput(BaseModel):
    # 音乐搜索输入参数（单曲/歌单/专辑）。

    query: str = Field(..., description="搜索关键词，例如：周杰伦、告白气球、华语流行")
    criteria: list[str] | None = Field(
        default=None,
        description="音乐搜索条件的列表，每一条是关于音乐某种属性的约束、规则或条件。例如: 流派是摇滚, 发布年份在2020年之后, 时长小于3分钟等",
    )


class MusicItem(BaseModel):
    """音乐项（统一抽象，兼容单曲/歌单/专辑）。"""

    model_config = ConfigDict(frozen=True)

    title: str = Field(..., title="标题", description="歌曲名/歌单名/专辑名")
    artist: str | None = Field(default=None, title="歌手", description="歌手名")
    album: str | None = Field(default=None, title="专辑", description="专辑名")
    genre: str | None = Field(default=None, title="流派", description="音乐流派")
    release_year: str | None = Field(
        default=None, title="发行时间", description="歌曲/专辑发行时间"
    )
    intro: str | None = Field(default=None, title="简介", description="歌单/专辑简介")
    creator: str | None = Field(default=None, title="创建者", description="歌单创建者")


class MusicSearchOutput(BaseModel):
    """音乐搜索输出参数。"""

    music_items: list[MusicItem] = Field(
        default_factory=list,
        description="符合条件的音乐列表.每个音乐项包含歌曲名称、艺术家、专辑。",
    )


# TODO: 还不确定这个类型实际中是否真的必要，但能支持str至少对于开发和调试非常方便。
type MusicSearchOutputLike = MusicSearchOutput | str
type MusicSearchWorker = TaskAWorker[MusicSearchOutputLike]
type MusicSearchStreamWorker = TaskAStreamWorker[str, MusicSearchOutputLike, ...]


def music_search_tool(
    worker: MusicSearchWorker | MusicSearchStreamWorker, with_clarify: bool = False
) -> TaskToolType[MusicSearchInput, MusicSearchOutputLike, str, ...]:
    """通用的音乐搜索工具。"""

    if with_clarify:
        description = """基于用户表达的需求，生成音乐搜索所需的信息: 搜索关键词、搜索条件等，并执行搜索，返回符合条件的音乐。
如缺少关键信息，无法执行搜索，该工具会返回向用户的提问。
注意，只有当缺乏关键细节，或者用户表达过于模糊时，才需要向用户提问。尽量避免。"""
    else:
        description = "搜索符合criteria字段中所有条件的音乐。"

    return create_tool(
        name="通用音乐搜索工具",
        description=description,
        args_schema=MusicSearchInput,
        worker=worker,
        with_clarify=with_clarify,
    )


############### 以下是测试


async def _music_search_dummy(
    query: str, description: str = "", criteria: list[str] = []
) -> MusicSearchOutput:
    sleep_time = random.uniform(0, 1)
    await asyncio.sleep(sleep_time)

    # if random.random() < 0.5:
    #    raise ValueError("music search failed")

    item = MusicItem(
        title="她来听我的演唱会",
        artist="张学友",
        album="祝福",
        release_year="1993",
        genre="流行",
    )

    return MusicSearchOutput(music_items=[item])


async def _music_search_dummy_stream(
    query: str | None = None, criteria: list[str] | None = None
):
    yield TaskProgress[str](progress="开始音乐搜索")
    await asyncio.sleep(random.uniform(0, 0.5))

    yield TaskProgress[str](progress="搜索结果处理中")
    await asyncio.sleep(random.uniform(0, 0.5))

    item = MusicItem(
        title="她来听我的演唱会",
        artist="张学友",
        album="祝福",
        release_year="1993",
        genre="流行",
    )
    yield TaskSuccess[MusicSearchOutputLike](
        result=MusicSearchOutput(music_items=[item])
    )


async def test_music_search_tool_basic():
    tool = music_search_tool(worker=_music_search_dummy)
    runner = TaskToolRunner()
    runner.add_tool(tool, {"query": "张学友", "criteria": ["流行音乐"]})
    async for event in runner.run():
        print(f"Runner event: {event.output}")


async def test_music_search_stream_tool_basic():
    tool = music_search_tool(worker=_music_search_dummy_stream)
    runner = StreamTaskToolRunner()
    runner.add_tool(tool, {"query": "张学友", "criteria": ["流行音乐"]})

    async for event in runner.run():
        print(f"Stream runner event: {event}")


if __name__ == "__main__":
    print("***** test_music_search_tool_basic *****")
    asyncio.run(test_music_search_tool_basic())

    print("##### test_music_search_stream_tool_basic ######")
    asyncio.run(test_music_search_stream_tool_basic())
