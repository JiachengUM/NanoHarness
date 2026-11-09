"""测试复杂推理 ReAct Agent：验证能通过 ReAct 调用车控工具。写法仿照 tests/agents/test_react.py。"""
import asyncio
import uuid

from rich import print

from aicore.agents.react import ReActAgentBase

from projects.mind.complex_reasoning.agent.agent import create_agent
from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.complex_reasoning.tools import get_default_tools
from projects.mind.complex_reasoning.utils.http_client import HttpClient

from aicore.agents.events import ReActEventPrinter, EventCapturer


def make_chat_id() -> str:
    """生成 chat_id，用于需火山的工具（车控、媒体、导航）。"""
    return "chatbox_" + uuid.uuid4().hex


BASIC_QUERIES = [
    # 基础功能测试
    # "请把空调调到18度，凉爽模式",       # 车控 火山fc
    # "播放周杰伦的稻香",                 # 媒体 火山fc
    # "导航到北京故宫",                   # 导航 火山fc
    # # "搜一下周杰伦的歌",                 # 音乐检索
    # # "查一下北京市朝阳区望京的咖啡店",   # POI
    "北京今天天气怎么样",               # 天气 火山fc
    # "搜一下今天的新闻头条",             # 联网检索
    # "徐家汇附近的餐厅",
]

COMPLEX_QUERIES = [
    # 复杂组合测试
    # "检查车辆电池和油量状态，如果油量足够，导航到北京故宫，路上播放轻松的音乐",
    # "获取上海明后天的天气，如果温度超过25度，打开空调到凉爽模式24度，并播放上海交通广播",
    # "导航到最近的加油站，路上播放节奏感强的音乐，同时查一下沿途附近评分高的咖啡店",
    # "查一下深圳南山区科技园附近的健身房，选一个后导航过去，并播放运动歌单",
    # "查询杭州最近三天天气，再搜索今天国际新闻头条，最后播放一首轻音乐",
]

QUERIES = BASIC_QUERIES + COMPLEX_QUERIES


async def run_all(agent: ReActAgentBase) -> None:
    """顺序执行所有 QUERIES，打印每轮结果；结束时关闭 HttpClient。"""
    try:
        for i, query in enumerate(QUERIES):
            print("\n" + "=" * 80)
            print(f"测试 #{i + 1}: {query}")
            print("=" * 80)
            try:
                res = await agent.ainvoke(query)
                print(f"final response: {res}")
            except Exception as e:
                print(f"测试失败: {e}")
            print("=" * 80)
    finally:
        await HttpClient.close_for_current_loop()


async def run_stream_all(agent: ReActAgentBase) -> None:
    """流式输出所有 query 的步骤。"""
    try:
        for i, query in enumerate(QUERIES):
            print("\n" + "=" * 80)
            print(f"测试流式输出 #{i + 1}: {query}")
            print("=" * 80)
            capturer = EventCapturer()
            
            res = await agent.astream_run(query, event_listeners=[ReActEventPrinter(print), capturer])

            print("以下为事件统计信息:")
            capturer.dump(print=print)
            print(f"\n最终响应: \n{res}")
            print("=" * 80)
    finally:
        await HttpClient.close_for_current_loop()


if __name__ == "__main__":
    # 确认使用的 config（应为 mind 仓库内 projects.mind.complex_reasoning.configs.config）
    cfg = get_app_config()
    config_module = get_app_config.__module__
    print("[config] 当前加载:", config_module)
    print("[config] AMAP_API_KEY 已配置:", bool(cfg.AMAP_API_KEY))
    print("[config] WEBSEARCH_BOT_MODEL 已配置:", bool(getattr(cfg, "WEBSEARCH_BOT_MODEL", "")))
    print()

    chat_id = make_chat_id()
    print("chat_id =", chat_id)
    tools = get_default_tools(chat_id)
    agent = create_agent(tools=tools, max_turns=5)

    print(agent)
    print(agent.model_dump())

    # asyncio.run(run_all(agent))
    asyncio.run(run_stream_all(agent))
