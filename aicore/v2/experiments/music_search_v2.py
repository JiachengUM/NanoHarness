from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager, TaskProgress, TaskSuccess
from aicore.tools import TaskAStreamWorker
from aicore.v2.tools.factory import create_tool
from projects.mind.toolset.music_search import SongItem, search_song


class MusicSearchInput(BaseModel):
    query: str = Field(..., description="单曲搜索关键词，例如歌手名、歌曲名、风格或用户想听的内容")
    criteria: list[str] = Field(default_factory=list, description="歌曲筛选条件，例如发行时间、风格、语言、适合场景")
    limit: int = Field(default=5, ge=1, le=10, description="返回歌曲数量")


class SongSearchOutput(BaseModel):
    items: list[SongItem] = Field(default_factory=list, description="单曲搜索结果")
    message: str = Field(default="", description="结果说明")


MusicSearchWorker = Callable[..., Awaitable[SongSearchOutput | str]]
MusicSearchStreamWorker = TaskAStreamWorker[str, SongSearchOutput | str, ...]


class QQMusicSongSearchV2Worker:
    async def __call__(
        self,
        query: str,
        criteria: list[str] | None = None,
        limit: int = 5,
    ) -> SongSearchOutput:
        items = await search_song(query, num=limit)
        return SongSearchOutput(items=items[:limit])


class QQMusicSongSearchV2StreamWorker:
    def __init__(self, worker: MusicSearchWorker):
        self.worker = worker

    async def __call__(
        self,
        query: str,
        criteria: list[str] | None = None,
        limit: int = 5,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[SongSearchOutput | str], None]:
        yield TaskProgress(progress="开始QQ音乐单曲搜索")
        yield TaskProgress(progress=f"搜索关键词: {query}")
        if criteria:
            yield TaskProgress(progress="包含筛选条件: " + "；".join(criteria))
        result = await self.worker(query=query, criteria=criteria or [], limit=limit)
        yield TaskSuccess(result=result)


def qq_music_song_search_v2_tool(
    worker: MusicSearchWorker | MusicSearchStreamWorker | None = None,
    *,
    timeout: float | None = 15,
    task_manager: TaskManager,
):
    worker = worker or QQMusicSongSearchV2StreamWorker(QQMusicSongSearchV2Worker())
    return create_tool(
        name="QQ音乐单曲搜索工具",
        description=(
            "搜索QQ音乐单曲。用户要求找歌、推荐歌曲、查询某位歌手的歌曲、根据风格找单曲时使用。"
            "不要用于搜索歌单或专辑。"
        ),
        args_schema=MusicSearchInput,
        worker=worker,
        timeout=timeout,
        asyncable="async",
        with_clarify=True,
        task_manager=task_manager,
    )


__all__ = [
    "MusicSearchInput",
    "SongSearchOutput",
    "MusicSearchWorker",
    "QQMusicSongSearchV2Worker",
    "QQMusicSongSearchV2StreamWorker",
    "qq_music_song_search_v2_tool",
]
