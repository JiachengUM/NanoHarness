import asyncio

from rich import print

from aicore.models.credentials import  ModelName

from aicore.agents.react import ReActEventPrinter
from aicore.agents.experiments.base import _create_agent, AgentBase

from projects.mind.toolset import get_default_tools


TOOL_QUERY_CASES = [
  "打开空调",  # CarControlTool
  "暂停播放",  # MediaTool
  "导航去东方明珠",  # NavigateTool
  "搜一首周杰伦的歌",  # QQMusicSongSearchTool
  "搜个跑步歌单",  # QQMusicPlaylistSearchTool
  "搜周杰伦的专辑",  # QQMusicAlbumSearchTool
  "平金中心附近有什么咖啡店",  # PoiSearchTool
  "北京今天天气怎么样",  # WeatherTool
  "网上查一下最近的热点新闻",  # WebsearchTool
]



async def test_agent_with_tools(agent: AgentBase):
    # 测试react 的超过循环的case。假设max_turns=2

    for i, query in enumerate(TOOL_QUERY_CASES[:]):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)

        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            pass

        print("="*80)
    

async def main():
    TOOLS = get_default_tools(chat_id="test_chat")

    MODEL = ModelName.SEED_1_8_251228

    agent = _create_agent(model=MODEL, tools=TOOLS)

    await test_agent_with_tools(agent)

if __name__ == "__main__":
    asyncio.run(main())