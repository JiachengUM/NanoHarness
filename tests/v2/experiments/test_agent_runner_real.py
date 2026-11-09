from __future__ import annotations

import anyio
import pytest

from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskManager
from aicore.simulation.user_env.data_source import UserDataMocked
from aicore.tools.experiments.music_search import music_search_tool, _music_search_dummy
from aicore.tools.experiments.poi_search import create_poi_search_tool, _poi_search_dummy_stream
from aicore.tools.experiments.weather import create_weather_search_tool, _weather_dummy
from aicore.v2.agent_runner import AgentRunner
from aicore.v2.experiments.react_agent_with_task_runner import (
    AgentTaskEventPrinter,
    create_react_agent_with_task_runner,
)

MUSIC_TOOL = music_search_tool(_music_search_dummy)
WEATHER_TOOL = create_weather_search_tool(_weather_dummy)
POI_STREAM_TOOL = create_poi_search_tool(_poi_search_dummy_stream, with_clarify=True)

TOOLS = [MUSIC_TOOL, WEATHER_TOOL, POI_STREAM_TOOL]


async def test_run_react():
    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_1_8_251228,
        tools=TOOLS,
        system_prompt=(
            "你是友好的用户智能助手。用户请求天气、音乐、地点信息时，"
            "必须调用对应工具，不要凭空回答工具可以查询的问题。\n"
            "重要约定：\n"
            "1) 当某个 function_call_output 以 \"[占位回执]\" 开头时，"
            "代表该 call_id 的真实结果尚未到达、工具仍在异步执行中。"
            "你必须只对用户简短说明'正在为您查询中'，"
            "不得再次调用同一工具，也不得再调用其它工具去补救。\n"
            "2) 之后你会收到一条以 \"[工具结果回灌]\" 开头的用户消息，"
            "里面携带 task_id 与该工具的真实返回值。请把它当作刚到的工具结果整合进对答里，"
            "围绕该结果回复用户，不要再调用同名工具。\n"
            "3) 多个工具结果可能分批到达，每条都以 \"[工具结果回灌]\" 开头，"
            "请按到达顺序逐个回复，已回复过的内容无需重复。"
        ),
        max_turns=5,
    )

    runner = AgentRunner(
        user_data=UserDataMocked(["请帮我查询香港今天的天气，放一首张学友的歌"]),
        agent=agent,
        task_manager=TaskManager(),
        client=AgentTaskEventPrinter(),
    )
    await runner.run()


if __name__ == "__main__":
    anyio.run(test_run_react)
