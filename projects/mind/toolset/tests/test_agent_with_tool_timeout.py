from rich import print

import asyncer

from aicore.tools.convert import tool
from aicore.models.credentials import create_client, AsyncArk, ModelName

from aicore.agents.events import ReActEventPrinter
from aicore.agents.experiments.base import SystemPrompt, AgentBase, ResponseParams, RunParams

from projects.mind.toolset import (
    CarControlTool,
    MediaTool,
    NavigateTool,
    WeatherTool,
    WebsearchTool,
    QQMusicMVSearchTool,
    QQMusicRadioSearchTool,
)
from projects.mind.toolset.music_search import (
    qq_music_song_search_tool_with_planning,
    qq_music_playlist_search_tool_with_planning,
    qq_music_album_search_tool_with_planning,
)
from projects.mind.toolset.poi_search import SGMPoiWorker, poi_search_tool_with_planning

def get_tools(chat_id: str,timeout: float | None = None):
    print(f"工具的timeout设置: {timeout}！")
    return [
        CarControlTool(chat_id=chat_id, timeout=timeout),
        MediaTool(chat_id=chat_id, timeout=timeout),
        NavigateTool(chat_id=chat_id, timeout=timeout),
        qq_music_song_search_tool_with_planning(timeout=timeout),
        qq_music_playlist_search_tool_with_planning(timeout=timeout),
        qq_music_album_search_tool_with_planning(timeout=timeout),
        QQMusicMVSearchTool(timeout=timeout),
        QQMusicRadioSearchTool(timeout=timeout),
        poi_search_tool_with_planning(SGMPoiWorker()),
        # WeatherTool(chat_id=chat_id, timeout=timeout),
        WebsearchTool(timeout=timeout),
    ]

# 无超时限制
@tool
def send_message(receiver: str, message: str) -> dict[str, str | int]:
    """发送消息到指定接收方"""
    return {"receiver": receiver, "message": message, "status": "success"}

# 根据工具列表，设计测试用例
QUERIES = [
    "发送消息给张三: ”你好，当前为装饰器创建的tool“",
    "打开主驾车窗",
    "播放周杰伦的歌曲<青花瓷>",
    "导航至上海虹桥国际机场",
    "搜索周杰伦的歌",
    "搜索周杰伦的经典歌单",
    "搜索周杰伦的青花瓷的专辑",
    "看看周杰伦的青花瓷的mv的时长",
    "看看上海有啥音乐电台节目",
    "搜索上海徐汇区的公园",
    "上海天气咋样",
    "看看今天的国际新闻",
]

async def test_agent_with_tools(agent: AgentBase):
    for i, query in enumerate(QUERIES[:]):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)

        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter(print)]):
            pass
        # 每个测试用例之间，重置session
        await agent.new_session()


def main():
    # 1. 初始化工具
    real_tools = get_tools(chat_id="test", timeout=0.2)
    tools =  real_tools + [send_message]
    
    _, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    params = ResponseParams(thinking = {"type": "disabled"})

    run_params = RunParams(
        model=model,
        params=params,
    )
    system_prompt = SystemPrompt(
        role="你是友好的用户智能助手",
        guidelines=[
            "打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。",
            "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节。",
            "如果工具超时，立刻告知用户！",
            "简短回复!"*5,
        ],
    )

    agent = AgentBase(system_prompt, run_params=run_params, tools=tools)
    
    asyncer.syncify(test_agent_with_tools, False)(agent)

if __name__ == "__main__":
    main()