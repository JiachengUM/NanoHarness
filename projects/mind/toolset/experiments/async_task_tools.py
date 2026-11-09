"""业务 TaskTool 定义及 v2 asyncable 包装入口。

``get_task_tools`` 返回未包装的原始 TaskTool；``get_async_task_tools``
和各 ``*_v2_tool`` 保留历史行为，在同一份原始定义上增加
``AsyncableTaskTool``。
"""
from aicore.runtime.task import TaskManager
from aicore.tools.factory import create_tool as create_raw_tool
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.tools.async_task import Asyncable, AsyncableTaskTool

from projects.mind.toolset.car_control import CarControlInput, VolcCarControlWorker
from projects.mind.toolset.media import MediaInput, VolcMediaWorker
from projects.mind.toolset.navigate import NavigateInput, VolcNavigateWorker
from projects.mind.toolset.music_search import (
    MusicSearchInput,
    SGMMusicWorker,
    SongSearchOutput,
    PlaylistSearchOutput,
    AlbumSearchOutput,
    search_song,
    search_playlist,
    search_album,
)
from projects.mind.toolset.poi_search import PoiSearchInput, SGMPoiWorker
from projects.mind.toolset.weather import WeatherInput, VolcWeatherWorker
from projects.mind.toolset.web_search import WebsearchInput, _websearch_worker


def _as_asyncable_tool(
    tool: TaskToolProtocolGeneral,
    *,
    task_manager: TaskManager | None,
    asyncable: Asyncable,
) -> TaskToolProtocolGeneral:
    return AsyncableTaskTool(
        tool,
        asyncable=asyncable,
        task_manager=task_manager,
    )


def _car_control_tool(chat_id: str) -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="car_control",
        description="车控指令执行",
        args_schema=CarControlInput,
        worker=VolcCarControlWorker(chat_id),
    )


def car_control_v2_tool(
    chat_id: str,
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _car_control_tool(chat_id),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _media_tool(chat_id: str) -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="media",
        description="音乐控制和执行，当搜出多首歌曲均满足筛选条件时，必须先通过媒体控制整理成歌单，然后执行歌单播放",
        args_schema=MediaInput,
        worker=VolcMediaWorker(chat_id),
    )


def media_v2_tool(
    chat_id: str,
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _media_tool(chat_id),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _navigate_tool(chat_id: str) -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="navigation",
        description="通过导航指令执行导航任务，指定目的地导航、添加途径点、路线偏好",
        args_schema=NavigateInput,
        worker=VolcNavigateWorker(chat_id),
    )


def navigate_v2_tool(
    chat_id: str,
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _navigate_tool(chat_id),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _qq_music_song_search_tool() -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="QQ音乐单曲搜索",
        description="单曲搜索工具，支持按歌曲名搜索歌曲信息；必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。",
        args_schema=MusicSearchInput,
        worker=SGMMusicWorker(search_func=search_song, output_cls=SongSearchOutput),
    )


def qq_music_song_search_v2_tool(
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _qq_music_song_search_tool(),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _qq_music_playlist_search_tool() -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="QQ音乐歌单搜索",
        description="歌单搜索工具，支持按主题、歌单名搜索歌单信息；必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。",
        args_schema=MusicSearchInput,
        worker=SGMMusicWorker(
            search_func=search_playlist,
            output_cls=PlaylistSearchOutput,
        ),
    )


def qq_music_playlist_search_v2_tool(
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _qq_music_playlist_search_tool(),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _qq_music_album_search_tool() -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="QQ音乐专辑搜索",
        description="专辑搜索工具，支持按专辑名、歌手名搜索专辑信息；必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。",
        args_schema=MusicSearchInput,
        worker=SGMMusicWorker(search_func=search_album, output_cls=AlbumSearchOutput),
    )


def qq_music_album_search_v2_tool(
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _qq_music_album_search_tool(),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _poi_search_tool() -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="地点搜索工具",
        description="完全遵循用户要求搜索poi，必须按criteria筛选，criteria是除了query之外的任何其它信息；business：poi所属商圈、营业时间、联系电话、特色内容、停车场类型、评分和人均消费；indoor：楼层索引、所在楼层；navi：导航引导点坐标包括各类poi出入口；返回的结果列表默认按距离从近到远排序。",
        args_schema=PoiSearchInput,
        worker=SGMPoiWorker(),
    )


def poi_search_v2_tool(
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _poi_search_tool(),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _websearch_tool() -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="websearch",
        description="通用联网搜索",
        args_schema=WebsearchInput,
        worker=_websearch_worker,
    )


def websearch_v2_tool(
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _websearch_tool(),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def _weather_tool(chat_id: str) -> TaskToolProtocolGeneral:
    return create_raw_tool(
        name="weather_agent",
        description="根据位置查询气候",
        args_schema=WeatherInput,
        worker=VolcWeatherWorker(chat_id),
    )


def weather_v2_tool(
    chat_id: str,
    *,
    task_manager: TaskManager | None = None,
    asyncable: Asyncable = "async",
):
    return _as_asyncable_tool(
        _weather_tool(chat_id),
        task_manager=task_manager,
        asyncable=asyncable,
    )


def get_task_tools(chat_id: str) -> list[TaskToolProtocolGeneral]:
    """返回 Duplex/StreamTask 可直接执行的 7 个未包装业务工具。"""

    return [
        _car_control_tool(chat_id),
        _navigate_tool(chat_id),
        _qq_music_song_search_tool(),
        _qq_music_playlist_search_tool(),
        _qq_music_album_search_tool(),
        _poi_search_tool(),
        _websearch_tool(),
    ]


def get_async_task_tools(
    chat_id: str,
    task_manager: TaskManager | None = None,
    *,
    asyncable: Asyncable = "async",
) -> list[TaskToolProtocolGeneral]:
    """按 asyncable 模式返回工具列表。chat_id 用于需请求火山的工具。"""
    if asyncable != "sync" and task_manager is None:
        raise ValueError(f"asyncable={asyncable} requires task_manager")
    return [
        _as_asyncable_tool(
            tool,
            task_manager=task_manager,
            asyncable=asyncable,
        )
        for tool in get_task_tools(chat_id)
    ]
