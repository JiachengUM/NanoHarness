from __future__ import annotations

from typing import Any

from aicore.v2.tools.async_task import AsyncableTaskTool
from projects.mind.toolset.car_control import CarControlInput, VolcCarControlWorker
from projects.mind.toolset.media import MediaInput
from projects.mind.toolset.music_search import (
    AlbumSearchOutput,
    MusicSearchInput,
    PlaylistSearchOutput,
    SGMMusicWorker,
    SongSearchOutput,
    search_album,
    search_playlist,
    search_song,
)
from projects.mind.toolset.navigate import NavigateInput, VolcNavigateWorker
from projects.mind.toolset.poi_search import PoiSearchInput, SGMPoiWorker
from projects.mind.toolset.weather import WeatherInput
from projects.mind.toolset.web_search import WebsearchInput, _websearch_worker
from projects.mind.toolset.experiments.async_task_tools import (
    car_control_v2_tool,
    get_async_task_tools,
    get_task_tools,
    media_v2_tool,
    navigate_v2_tool,
    poi_search_v2_tool,
    qq_music_album_search_v2_tool,
    qq_music_playlist_search_v2_tool,
    qq_music_song_search_v2_tool,
    weather_v2_tool,
    websearch_v2_tool,
)


EXPECTED_BUSINESS_SURFACE = [
    ("car_control", "车控指令执行", CarControlInput),
    (
        "navigation",
        "通过导航指令执行导航任务，指定目的地导航、添加途径点、路线偏好",
        NavigateInput,
    ),
    (
        "QQ音乐单曲搜索",
        "单曲搜索工具，支持按歌曲名搜索歌曲信息；必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。",
        MusicSearchInput,
    ),
    (
        "QQ音乐歌单搜索",
        "歌单搜索工具，支持按主题、歌单名搜索歌单信息；必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。",
        MusicSearchInput,
    ),
    (
        "QQ音乐专辑搜索",
        "专辑搜索工具，支持按专辑名、歌手名搜索专辑信息；必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。",
        MusicSearchInput,
    ),
    (
        "地点搜索工具",
        "完全遵循用户要求搜索poi，必须按criteria筛选，criteria是除了query之外的任何其它信息；business：poi所属商圈、营业时间、联系电话、特色内容、停车场类型、评分和人均消费；indoor：楼层索引、所在楼层；navi：导航引导点坐标包括各类poi出入口；返回的结果列表默认按距离从近到远排序。",
        PoiSearchInput,
    ),
    ("websearch", "通用联网搜索", WebsearchInput),
]


def tool_surface(tools: list[Any]) -> list[tuple[str, str, type]]:
    return [(tool.name, tool.description, tool.args_schema) for tool in tools]


def test_get_task_tools_returns_exact_unwrapped_business_tools() -> None:
    tools = get_task_tools("chat-1")

    assert tool_surface(tools) == EXPECTED_BUSINESS_SURFACE
    assert not any(isinstance(tool, AsyncableTaskTool) for tool in tools)

    car_worker = tools[0].actual_worker  # type: ignore[attr-defined]
    assert isinstance(car_worker, VolcCarControlWorker)
    assert car_worker.chat_id == "chat-1"

    navigate_worker = tools[1].actual_worker  # type: ignore[attr-defined]
    assert isinstance(navigate_worker, VolcNavigateWorker)
    assert navigate_worker.chat_id == "chat-1"

    music_workers = [
        tool.actual_worker  # type: ignore[attr-defined]
        for tool in tools[2:5]
    ]
    for worker in music_workers:
        assert isinstance(worker, SGMMusicWorker)
    assert [worker.search_func for worker in music_workers] == [
        search_song,
        search_playlist,
        search_album,
    ]
    assert [worker.output_cls for worker in music_workers] == [
        SongSearchOutput,
        PlaylistSearchOutput,
        AlbumSearchOutput,
    ]

    assert isinstance(
        tools[5].actual_worker,  # type: ignore[attr-defined]
        SGMPoiWorker,
    )
    assert tools[6].actual_worker is _websearch_worker  # type: ignore[attr-defined]


def test_get_async_task_tools_wraps_the_same_public_surface() -> None:
    tools = get_async_task_tools("chat-1", asyncable="sync")

    assert tool_surface(tools) == EXPECTED_BUSINESS_SURFACE
    assert all(isinstance(tool, AsyncableTaskTool) for tool in tools)
    assert all(tool.asyncable == "sync" for tool in tools)


def test_existing_single_tool_factories_keep_their_surface() -> None:
    tools = [
        car_control_v2_tool("chat-1", asyncable="sync"),
        navigate_v2_tool("chat-1", asyncable="sync"),
        qq_music_song_search_v2_tool(asyncable="sync"),
        qq_music_playlist_search_v2_tool(asyncable="sync"),
        qq_music_album_search_v2_tool(asyncable="sync"),
        poi_search_v2_tool(asyncable="sync"),
        websearch_v2_tool(asyncable="sync"),
    ]

    assert tool_surface(tools) == EXPECTED_BUSINESS_SURFACE
    assert media_v2_tool("chat-1", asyncable="sync").args_schema is MediaInput
    assert weather_v2_tool("chat-1", asyncable="sync").args_schema is WeatherInput
