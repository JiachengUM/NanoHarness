from __future__ import annotations
import os

from projects.mind.toolset import get_default_tools, get_prompt
from aicore.v1.experiments.agent import SystemPrompt

from projects.mind.toolset.web_search import WebsearchTool
from projects.mind.toolset.car_control import CarControlTool
from projects.mind.toolset.media import MediaTool
from projects.mind.toolset.navigate import NavigateTool
from projects.mind.toolset.music_search import qq_music_song_search_tool, qq_music_playlist_search_tool, qq_music_album_search_tool
from projects.mind.toolset.poi_search import poi_search_tool, SGMPoiWorker
from projects.mind.toolset.weather import WeatherTool


CHAT_ID = os.getenv("V2_REACT_TEST_CHAT_ID", "v2-react-real-tool-test")


# TOOLS = [
#     weather_search_v2_tool(chat_id=CHAT_ID),
#     poi_search_v2_tool(),
#     qq_music_song_search_v2_tool(),
# ]

TOOLS = get_default_tools(chat_id="test_chat")


def build_v2_s2s_system_prompt() -> str:
    return (
    "你是友好的用户语音智能助手。用户请求天气、音乐、地点信息时，"
    "你在上海市徐汇区西岸滨江"
    "必须调用对应工具，不要凭空回答工具可以查询的问题。\n"
    "【语音回复规范】你的回复会被转换为语音播放，因此：\n"
    "- 每次回复控制在30字以内，最多不超过60字；\n"
    "- 语言口语化、自然流畅，避免列表、符号、Markdown格式；\n"
    "- 直接给出结论，不重复用户的问题，不作冗余解释。\n"
    "重要约定：\n"
    "1) 当某个 function_call_output 以 \"[占位回执]\" 开头时，"
    "代表该工具调用的真实结果尚未到达、工具仍在异步执行中。"
    "你必须只对用户简短说明正在查询/执行，不得再次调用同一工具，"
    "也不得再调用其它工具去补救。\n"
    "2) 如果用户后续追问依赖某个正在异步执行中的工具真实结果，"
    "例如天气尚未返回时询问是否带伞、歌曲尚未返回时询问是否适合雨天、"
    "地点尚未返回时询问怎么过去，这类追问只能等待已有 pending 工具结果。"
    "你不得为了回答该追问重复调用同一工具，也不得调用其它工具替代回答；"
    "请简短告知用户需要等该工具真实结果返回后才能判断。\n"
    "3) 只有当用户提出的是与 pending 工具无关的新需求，"
    "或者明确改变了工具查询目标/参数导致已有 pending 工具结果无法回答时，"
    "才可以创建新的工具调用。\n"
    "4) 之后你会收到以 \"[工具结果回灌]\" 开头的用户消息，"
    "代表某个 pending 工具的真实返回结果。请把它当作真实工具结果，"
    "结合此前等待该结果的连续追问回复用户；只围绕该工具结果及其相关追问回复，"
    "不要额外调用工具。\n"
    "5) 如果 \"[工具结果回灌]\" 中包含 \"用户意图不清晰\"、\"需要向用户提问\" "
    "或类似澄清文本，说明该工具没有执行真实查询，而是在要求补充参数。"
    "如果后续对话中用户尚未补充该参数，请直接向用户提出这个澄清问题，"
    "不要说正在查询，也不要再次调用工具。"
    "如果后续对话中用户已经补充了该参数，或者已经基于补充信息创建了新的同类工具调用，"
    "则这个澄清结果已经过期，必须忽略它，不要再向用户重复提问，也不要输出额外回复。\n"
    "6) 多个工具结果可能分批到达，按到达顺序逐个回复，"
    "已回复过的内容**无需重复**；如果存在更新的同类工具结果，以最新结果回复用户即可。\n"
    "7) 如果用户明确要求取消尚未返回结果的任务，根据对应占位回执找到 task_id，"
    "调用 cancel_task。"
    "无法唯一确定目标时先询问用户，不要调用取消工具。"
    "取消多个任务必须由用户明确要求取消全部，或明确逐一指出多个目标。"
    "cancel_task 会返回以 \"[已取消]\"、\"[无需取消]\" 或 \"[取消失败]\" 开头的 observation，"
    "请基于 observation 用一句话简短回复用户。"
)

def build_v2_tools():
    return TOOLS


def build_v1_tools_with_timeout(chat_id: str, timeout = 20):
    """为了演示场景，给每个工具设置随机超时时间。"""
    
    return [
        CarControlTool(chat_id=chat_id,timeout=timeout),
        MediaTool(chat_id=chat_id,timeout=timeout),
        NavigateTool(chat_id=chat_id,timeout=timeout),
        qq_music_song_search_tool(timeout=timeout),
        qq_music_playlist_search_tool(timeout=timeout),
        qq_music_album_search_tool(timeout=timeout),
        # QQMusicMVSearchTool(),
        # QQMusicRadioSearchTool(),
        poi_search_tool(SGMPoiWorker(),timeout=timeout),
        WeatherTool(chat_id=chat_id,timeout=timeout),
        WebsearchTool(timeout=0.1), # 固定为0.1s。for demo
    ]


def build_v1_s2s_system_prompt() -> SystemPrompt:
    from datetime import datetime
    raw_prompt = get_prompt()

    return SystemPrompt(
        role=f"你是车载助手，完全遵循用户要求。当前时间：{datetime.now().strftime('%Y年%m月%d日 %H时%M分%S秒')}。",
        guidelines=[
            "调用工具前先向用户简要说明意图，再执行工具调用，禁止静默调用。否则干死你！！"  ,
            "最终回复时需保持极简极简极简极简。",
        ] 
        + (raw_prompt.guidelines or []),
    )
