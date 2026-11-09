from typing import Any

import asyncio

from rich import print

from aicore.agents.experiments.react_obsolete import ReActEventPrinter, ReActAgentBase

from aicore.core.event import EventCapturer

from aicore.models.credentials import ModelName
from aicore.models.responses import ResponseParams, ModelParams

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

model_params = ModelParams(
    #model = ModelName.SEED_1_8_251228
    model=ModelName.SEED_1_6_251015,
    params = ResponseParams(thinking = {"type": "disabled"}),
    )

QUERIES = [
    # # 基础功能测试
    "请把空调调到18度，凉爽模式",  # 测试空调控制工具
    # "看看今天天气如何，根据情况帮我开空调",  # 测试天气查询 + 空调控制
    
    # # 复杂组合测试
    # "检查车辆电池和油量状态，如果油量足够，导航到北京故宫，路上播放轻松的音乐，调整驾驶员座椅的按摩功能到放松模式",  # 车辆状态 + 导航 + 多媒体 + 座椅控制
    # "获取上海的天气，如果温度超过25度，打开空调到凉爽模式24度，同时播放上海交通广播",  # 天气查询 + 条件空调控制 + 广播
    # "帮我导航到最近的加油站，路上打开车窗通风，播放节奏感强的音乐",  # 导航 + 多媒体
    # "检查车辆胎压和车门状态，然后导航到首都机场T3航站楼，设置导航模式为最快路线，避开收费路段",  # 车辆状态 + 高级导航设置
    # "调整副驾驶座椅到最舒适的位置，打开按摩功能，同时播放视频教程，导航到北京大学",  # 座椅控制 + 多媒体 + 导航
    # "获取当前天气，如果下雨，关闭所有车窗，打开空调到自动模式22度，播放轻音乐",  # 天气查询 + 条件操作 + 空调控制 + 多媒体
    # "检查车辆电池状态，如果电池电量低于50%，提醒我充电，同时导航到最近的充电站，播放轻音乐",  # 车辆状态 + 条件导航 + 多媒体
    # "帮我规划一条从当前位置到长城的导航路线，设置为经济模式，路上调整座椅按摩功能，播放长城相关的音乐",  # 导航 + 座椅控制 + 多媒体

    # 测试新的event_filter
    "获取上海的天气同时播放交通广播", # 一次出多tool
    # "先获取上海的天气，然后根据天气情况播放适合的音乐", # 串行tool，需要等待第一个tool完成才能执行第二个tool
    #"你好" #无tool

    "我想导航去虹桥火车站。",
    # "今天几个北京的朋友过来了，帮我在附近找个适合吃川菜的餐厅"
]

async def test_react_agent():
    agent = ReActAgentBase(
        tools=get_tools(),
        model=model_params.model,
        client=model_params.client,
        params=model_params.params,
        max_turns=10,
    )

    for i, query in enumerate(QUERIES):
        print("\n" + "="*80)
        print(f"测试 #{i+1}: {query}")
        print("="*80)
        try:
            res = await agent.ainvoke(query)
            print(f"final response: {res}")
        except Exception as e:
            print(f"测试失败: {e}")
        print("="*80)


async def test_react_agent_stream():
    # 测试流式输出
    agent = ReActAgentBase(
        tools=get_tools(),
        model=model_params.model,
        client=model_params.client,
        params=model_params.params,
        max_turns=10,
    )

    for i, query in enumerate(QUERIES[:]):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)

        capturer = EventCapturer[Any]()
        system_prompt =  "打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。同一工具调用多次（超过两次）失败时，请提醒用户该任务无法完成。"
        res = await agent.astream_run(query, system_prompt, event_listeners=[ReActEventPrinter(), capturer])

        print("以下为事件统计信息:")
        capturer.dump(print=print)

        print("\n最终响应: ")
        print(res)
        print("="*80)


async def main():
    await test_react_agent()  # failed, 有bug
    await test_react_agent_stream()
    
if __name__ == "__main__":
    asyncio.run(main())