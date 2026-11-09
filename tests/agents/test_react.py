import anyio

from rich import print

from aicore.tools.experiments.poi_search import create_poi_search_tool, _poi_search_dummy
from aicore.tools.experiments.music_search import _music_search_dummy, music_search_tool
from aicore.tools.experiments.weather import create_weather_search_tool, _weather_dummy

from aicore.models.credentials import ModelName
from aicore.models.model_api import create_model_api
from aicore.agents.react import react_with_base_tools, react_with_task_tools, react_with_stream_tools

from aicore.events.react import ReActEventPrinter
from aicore.events import ReActTaskEventPrinter

from tests.tools.test_base_tool import (
    get_weather,
    ControlACTool,
    VehicleStatusTool,
    NavigationTool,
    MultimediaTool,
    SeatControlTool,
)

def get_tools():
    return [get_weather, ControlACTool(), VehicleStatusTool(), NavigationTool(), MultimediaTool(), SeatControlTool()]

model = ModelName.SEED_1_6_251015
#model_api = create_model_api(model=model, backend="chat")
model_api = create_model_api(model=model, backend="responses")

SIMPLE_QUERIES = [
    "你好", #无tool
    # 基础功能测试
    "请把空调调到18度，凉爽模式",  # 测试空调控制工具
    "看看今天天气如何，根据情况帮我开空调",  # 测试天气查询 + 空调控制
    
    # 复杂组合测试
    "检查车辆电池和油量状态，如果油量足够，导航到北京故宫，路上播放轻松的音乐，调整驾驶员座椅的按摩功能到放松模式",  # 车辆状态 + 导航 + 多媒体 + 座椅控制
    "获取上海的天气，如果温度超过25度，打开空调到凉爽模式24度，同时播放上海交通广播",  # 天气查询 + 条件空调控制 + 广播
    "帮我导航到最近的加油站，路上打开车窗通风，播放节奏感强的音乐",  # 导航 + 多媒体
    "检查车辆胎压和车门状态，然后导航到首都机场T3航站楼，设置导航模式为最快路线，避开收费路段",  # 车辆状态 + 高级导航设置
    "调整副驾驶座椅到最舒适的位置，打开按摩功能，同时播放视频教程，导航到北京大学",  # 座椅控制 + 多媒体 + 导航
    "获取当前天气，如果下雨，关闭所有车窗，打开空调到自动模式22度，播放轻音乐",  # 天气查询 + 条件操作 + 空调控制 + 多媒体
    "检查车辆电池状态，如果电池电量低于50%，提醒我充电，同时导航到最近的充电站，播放轻音乐",  # 车辆状态 + 条件导航 + 多媒体
    "帮我规划一条从当前位置到长城的导航路线，设置为经济模式，路上调整座椅按摩功能，播放长城相关的音乐",  # 导航 + 座椅控制 + 多媒体    

    # 其它
    # "我想导航去虹桥火车站。",
    # "今天几个北京的朋友过来了，帮我在附近找个适合吃川菜的餐厅"
]

async def test_react_with_base_tools():
    print("test_react_with_base_tools")

    event_printer = ReActEventPrinter()

    for query in SIMPLE_QUERIES:
        print("\n==================================")
        print(f"user: {query}")

        async for event in react_with_base_tools(
            query,
            model_api=model_api,
            state=model_api.initial_state(),
            tools=get_tools(),
            max_turns=2,
            ):
            event_printer(event)


QUERIES = [
    "我正在香港旅游，想帮我找个有名的酒店去参观",  # 意图明确的poi search任务
    "我想找个好玩的地方",  # 需要澄清的poi_search tool
    "我正在香港旅游，想帮我找个有名的酒店去参观。请推荐张学友的有名歌曲。顺便帮我查下明天的天气。",  # 意图明确的多任务
    "我正在旅游，想找个地方玩，请推荐。想听歌，请推荐。顺便帮我查下天气。", # 意图模糊的多任务
]

poi_tool = create_poi_search_tool(_poi_search_dummy, with_clarify=True)
music_tool = music_search_tool(worker=_music_search_dummy)
weather_tool = create_weather_search_tool(_weather_dummy, with_clarify=True)

TOOLS = [poi_tool, music_tool, weather_tool]

async def test_react_with_task_tools():
    print("test_react_with_task_tools")

    query = QUERIES[2]

    print(f"user: {query}")

    event_printer = ReActEventPrinter()

    async for event in react_with_task_tools(
        query,
        model_api=model_api,
        state=model_api.initial_state(),
        tools=TOOLS,
        max_turns=2,
        ):
        event_printer(event)


async def test_react_with_stream_tools():
    print("test_react_with_stream_tools")

    query = QUERIES[3]

    print(f"user: {query}")

    event_printer = ReActTaskEventPrinter()
    async for event in react_with_stream_tools(
        query,
        model_api=model_api,
        state=model_api.initial_state(),
        tools=TOOLS,
        max_turns=2,
        ):
        event_printer(event)


async def main():
    await test_react_with_base_tools()
    await test_react_with_task_tools()
    await test_react_with_stream_tools()


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")
