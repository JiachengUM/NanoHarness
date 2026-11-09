"""
复杂推理默认工具集：对应原 complex_reasoning_agent subagent 的 Tool 形态。
需火山 call_fc 的工具（车控、媒体、导航、天气）需传入 chat_id。
"""
from projects.mind.complex_reasoning.tools.CarControl import CarControlTool
from projects.mind.complex_reasoning.tools.Media import MediaTool
from projects.mind.complex_reasoning.tools.MusicSearch import MusicSearchTool
from projects.mind.complex_reasoning.tools.Navigate import NavigateTool
from projects.mind.complex_reasoning.tools.PoiSearch import PoiSearchTool
from projects.mind.complex_reasoning.tools.Weather import WeatherTool
from projects.mind.complex_reasoning.tools.Websearch import WebsearchTool

__all__ = [
    "CarControlTool",
    "MediaTool",
    "MusicSearchTool",
    "NavigateTool",
    "PoiSearchTool",
    "WeatherTool",
    "WebsearchTool",
    "get_default_tools",
]


def get_default_tools(chat_id: str):
    """返回默认工具列表。chat_id 用于需请求火山的工具（车控、媒体、导航）。"""
    return [
        CarControlTool(chat_id=chat_id),
        MediaTool(chat_id=chat_id),
        NavigateTool(chat_id=chat_id),
        MusicSearchTool(),
        PoiSearchTool(),
        WeatherTool(chat_id=chat_id),
        WebsearchTool(),
    ]
