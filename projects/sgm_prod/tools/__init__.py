from aicore.tools import TaskToolType, create_tool

from projects.sgm_prod.tools.CarControl import (
    CarControlInput,
    CarControlWorker,
    create_car_control_tool,
)
from projects.sgm_prod.tools.Media import (
    MediaInput,
    MediaWorker,
    create_media_tool,
)
from projects.mind.toolset.music_search import (
    qq_music_album_search_tool,
    qq_music_playlist_search_tool,
    qq_music_song_search_tool,
)
from projects.mind.toolset.poi_search import SGMPoiWorker, poi_search_tool
from projects.sgm_prod.tools.Navigation import (
    NavigationInput,
    NavigationWorker,
    create_navigation_tool,
)
from projects.sgm_prod.tools.WebSearch import (
    WebsearchInput,
    WebsearchWorker,
    create_websearch_tool,
)

__all__ = [
    "create_car_control_tool",
    "create_media_tool",
    "qq_music_song_search_tool",
    "qq_music_playlist_search_tool",
    "qq_music_album_search_tool",
    "create_navigation_tool",
    "poi_search_tool",
    "create_websearch_tool",
    "build_tools",
]


def build_tools(chat_id: str) -> list[TaskToolType]:
    """构建 SGM Agent 可用的工具列表。

    统一通过 aicore.tools.factory.create_tool 创建，隔离具体 Tool 实现类型。
    """
    return [
        create_tool(
            name="car_control",
            description=(
                "执行车载设备控制，包括：空调（温度、风量、模式）、座椅（位置、按摩、加热、通风）、"
                "车窗/天窗/车门、灯光（氛围灯、阅读灯、远近光）等。输入为自然语言车控指令。"
            ),
            args_schema=CarControlInput,
            worker=CarControlWorker(chat_id),
        ),
        create_tool(
            name="media",
            description="控制车载多媒体，如播放/暂停/切歌、播放指定歌曲或歌单。输入为自然语言控制指令。",
            args_schema=MediaInput,
            worker=MediaWorker(chat_id),
        ),
        create_tool(
            name="navigation",
            description="执行导航相关任务，如开始导航、取消导航、添加途经点、调整路线偏好。",
            args_schema=NavigationInput,
            worker=NavigationWorker(chat_id),
        ),
        poi_search_tool(SGMPoiWorker()),
        qq_music_song_search_tool(),
        qq_music_playlist_search_tool(),
        qq_music_album_search_tool(),
        create_tool(
            name="websearch",
            description="通用联网搜索，获取网络上的基础信息",
            args_schema=WebsearchInput,
            worker=WebsearchWorker(),
        ),
    ]
