import asyncio

from rich import print

from aicore.agents.react import ReActEventPrinter
from aicore.agents.experiments.base import _create_agent
from aicore.models.credentials import ModelName
from aicore.tools.experiments.music_search import MusicSearchOutput
from aicore.tools.task import SafeResult
from projects.mind.toolset.music_search import (
    qq_music_album_search_tool,
    qq_music_playlist_search_tool,
    qq_music_song_search_tool,
    qq_music_album_search_tool_with_planning,
    qq_music_playlist_search_tool_with_planning,
    qq_music_song_search_tool_with_planning,
)


async def test_song_task_tool_basic():
    tool = qq_music_song_search_tool()
    res = await tool._arun(query="周杰伦", criteria=None)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(res, SafeResult)
    tool = qq_music_song_search_tool()
    res = await tool._arun(description="搜索周杰伦的单曲", query="周杰伦", criteria=None)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(res, SafeResult)
    assert res.is_success, f"[song] 调用失败: {res.error}"
    assert isinstance(res.data, MusicSearchOutput)
    print(f"[song] 返回数量: {len(res.data.music_items)}")
    if res.data.music_items:
        print(f"[song] 首条: {res.data.music_items[0]}")


async def test_playlist_task_tool_basic():
    tool = qq_music_playlist_search_tool()
    res = await tool._arun(query="周杰伦", criteria=None)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(res, SafeResult)
    assert res.is_success, f"[playlist] 调用失败: {res.error}"
    assert isinstance(res.data, MusicSearchOutput)
    print(f"[playlist] 返回数量: {len(res.data.music_items)}")
    if res.data.music_items:
        print(f"[playlist] 首条: {res.data.music_items[0]}")


async def test_album_task_tool_basic():
    tool = qq_music_album_search_tool()
    res = await tool._arun(query="周杰伦", criteria=None)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(res, SafeResult)
    assert res.is_success, f"[album] 调用失败: {res.error}"
    assert isinstance(res.data, MusicSearchOutput)
    print(f"[album] 返回数量: {len(res.data.music_items)}")
    if res.data.music_items:
        print(f"[album] 首条: {res.data.music_items[0]}")


async def test_agent_with_tools_with_planning():
    """Agent 带三个 planning 工具，自由决策选哪个（或反问用户）。"""
    tools = [
        qq_music_song_search_tool_with_planning(),
        qq_music_playlist_search_tool_with_planning(),
        qq_music_album_search_tool_with_planning(),
    ]
    agent = _create_agent(model=ModelName.SEED_1_8_251228, tools=tools)

    queries = [
        "帮我找几首周杰伦的歌",        # 意图明确 → 单曲搜索
        "找一个适合夜晚开车听的歌单",   # 意图明确 → 歌单搜索
        "查一查周杰伦出过哪些专辑",     # 意图明确 → 专辑搜索
        "我想听点好听的",              # 意图模糊 → 预期反问用户
    ]

    for query in queries:
        print("=" * 40)
        print(f"user: {query}")
        result = await agent.astream_run(query, event_listeners=[ReActEventPrinter(print)])
        print(f"\nassistant(完整): {result.response.raw_text}")


async def main():
    # await test_song_task_tool_basic()
    # await test_playlist_task_tool_basic()
    # await test_album_task_tool_basic()
    await test_agent_with_tools_with_planning()


if __name__ == "__main__":
    asyncio.run(main())
