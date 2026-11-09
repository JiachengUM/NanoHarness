from __future__ import annotations

import os
from typing import AsyncGenerator

import anyio

from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskManager
from aicore.simulation.user_env.data_source import UserDataMocked, UserDataSourceBase
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.agent_runner import AgentRunner
from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT
from aicore.v2.experiments.react_agent_with_task_runner import (
    AgentTaskEventPrinter,
    create_react_agent_with_task_runner,
)
from aicore.v2.experiments.music_search_v2 import qq_music_song_search_v2_tool
from aicore.v2.experiments.poi_search_v2 import poi_search_v2_tool
from aicore.v2.experiments.sgm_tools_v2 import build_sgm_v2_tools
from aicore.v2.experiments.weather_v2 import weather_search_v2_tool

from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
from projects.mind.toolset.car_control import CarControlTool
from projects.mind.toolset.media import MediaTool
from projects.mind.toolset.navigate import NavigateTool

CHAT_ID = os.getenv("V2_REACT_TEST_CHAT_ID", "v2-react-real-tool-test")

TASK_MANAGER = TaskManager()
TOOLS: list[TaskToolProtocolGeneral] = [
    weather_search_v2_tool(chat_id=CHAT_ID, task_manager=TASK_MANAGER),
    poi_search_v2_tool(task_manager=TASK_MANAGER),
    qq_music_song_search_v2_tool(task_manager=TASK_MANAGER),
    CarControlTool(chat_id=CHAT_ID),
    MediaTool(chat_id=CHAT_ID, task_manager=TASK_MANAGER),
    NavigateTool(chat_id=CHAT_ID, task_manager=TASK_MANAGER),
    create_task_cancel_tool(task_manager=TASK_MANAGER),
]

class UserDataDelayed(UserDataSourceBase):
    """多轮用户输入：每条 query 在 yield 之前先 sleep 指定秒数。

    用于模拟“用户看完上一轮回答之后过了 N 秒再追问”的真实节奏，
    给 react_agent_with_task_runner 留出足够时间走完前一个 query 的所有 ReAct 轮 + 异步工具回灌。
    """

    def __init__(self, turns: list[tuple[str, float]]):
        # turns: [(query, delay_before_seconds), ...]
        self.turns = turns

    async def __call__(self) -> AsyncGenerator[str, None]:
        for query, delay in self.turns:
            if delay > 0:
                await anyio.sleep(delay)
            print(f"👨>>>>>>>> delay query {query}")
            yield query


# ============================================================
# 多轮测试用例
# 每个 case 是一组 (query, delay_before) 元组列表；
# 第一条的 delay 通常为 0，后续条目的 delay 给 agent 留出处理上一轮的时间。
# ============================================================

MULTI_TURN_CASES: dict[str, list[tuple[str, float]]] = {
    # ---------------- 多轮 + 单工具 ----------------
    # 同一工具被多次问，验证 chain id / 工具回灌不会串台
    "weather_followup": [
        ("请查一下香港今天的天气", 0.0),
        ("那明天呢？", 8.0),
        ("后天的怎么样", 8.0),
    ],
    "music_followup": [
        ("推荐一首张学友的经典歌曲", 0.0),
        ("再来一首王菲的", 6.0),
        ("帮我换一首适合下雨天听的", 6.0),
        ("哪首歌适合下雨天听？", 6.0),      # 这里应该怎么回复？？，这是同一个意图，属于多轮交互，应该直接按最新的回复即可，v1/v2没区别？
    ],
    "poi_followup": [
        ("帮我在香港找一家适合入住的酒店", 0.0),
        ("换成上海的", 8.0),
    ],

    # ---------------- 多轮 + 多工具 ----------------
    # 每轮都触发并发的多工具，验证多轮叠加下的占位/回灌时序
    "multi_tool_followup": [
        ("请查香港今天的天气，再找一家酒店", 0.0),
        ("换成上海的天气，再推荐一家上海的酒店", 10.0),
    ],
    "three_tools_then_one": [
        ("请查香港今天的天气，找一家上海徐汇区西岸附近的酒店，再推荐一首张学友的歌", 0.0),
        ("再换一首王菲的歌就行", 1.0),
    ],

    # ---------------- 多轮 + 单/多工具 混合 ----------------
    "mixed_single_then_multi": [
        ("你好，简单介绍一下你能做什么", 0.0),
        ("请查香港今天的天气", 3.0),
        ("再帮我找一家上海平金中心附近的酒店，并推荐一首张学友的歌", 3.1),    # 模型会claim需要特定的城市，也能理解时序，【刚刚的任务没有完成】
    ],
    "mixed_multi_then_single": [
        ("查一下香港今天的天气，再推荐一首适合雨天听的张学友歌曲", 0.0),
        ("再推荐一家可以听这首歌喝下午茶的咖啡馆", 10.0),
    ],

    # ---------------- 异步任务 pending 期间的用户插话 ----------------
    # 用户在上一个任务真实结果尚未回灌时提出新的无关需求：
    # 期望旧任务继续执行，新任务也能创建，最终两个结果分别回复且不串台。
    "pending_unrelated_request": [
        ("请查一下香港今天的天气", 0.0),
        ("顺便推荐一首张学友的歌", 0.5),
    ],
    # 用户基于未完成结果追问：
    # 期望 agent 不把占位回执当真实天气，也不凭空回答是否带伞。
    "pending_dependent_followup": [
        ("请查一下香港今天的天气", 0.0),
        ("那我需要带伞吗？", 2),
    ],
    # 用户已经换话题后，旧任务结果才回来：
    # 期望结果回复能带上原任务上下文，避免像无关插话。
    # !!!是一个异步的好case
    "result_after_topic_shift": [
        ("请查一下香港今天的天气", 0.0),
        ("你知道 NanoAI 是什么吗？", 0.5),
    ],

    # ---------------- 重复请求 / 澄清型多轮 ----------------
    # 当前阶段允许创建 3 个任务；观察是否会额外重复创建或状态串台。
    "duplicate_weather_requests": [
        ("请查一下香港今天的天气", 0.0),
        ("请再一下香港今天的天气", 1.0),
        ("再再再查一次香港今天的天气", 1.0),    # TODO 如果间隔时间比较短，5s内连续发送任务，agent会不生成task。。。
    ],
    # 参数不足时先澄清，用户补充地点后再创建 POI 任务。延迟要短，如果长和v1+多轮没有区别！！
    "clarify_nearby_place_then_city": [
        ("帮我在附近找一个很好吃的中餐厅", 0.0),
        ("附近是上海平金中心", 3.0),
    ],

    # ---------------- 长对话 + 占位污染压力 ----------------
    # 8-15 轮长链路：混合 pending 插话、基于未完成结果追问、换话题、
    # 超级长的对话，足够的时延，应该要和v1阻塞版本能力一致 —— 完美通过！！
    "long_dialogue_vs_v1": [
        ("请查一下香港今天的天气", 0.0),
        ("那我需要带伞吗？", 10),
        ("先不管这个，推荐一首张学友的经典歌", 20),
        ("这首歌适合下雨天听吗？", 10.0),
        ("再查一次香港今天的天气", 20),
        ("你刚才查天气了吗，查完了吗？", 20),
        ("换个话题，你简单介绍一下你能做什么", 20),
        ("明天上海天气怎么样？", 20),
        ("再推荐一家上海平金中心附近可以边听歌边喝下午茶的咖啡馆", 20),
        ("最后总结一下刚才总结的所有事情", 40.0),
    ],
    # 极短的时延，尽量接近用户真的输入，看是否会有错乱的回答
    # 测试结果：稳定工具调用，没有乱序（只是比较啰嗦），并且有上下文工具结果指代的消息时，也不会额外调用工具；并且，能正确区分完成/未完成
    "long_dialogue_placeholder_pollution": [
        ("再推荐一家上海平金中心附近可以边听歌边喝下午茶的咖啡馆", 0),
        ("取消任务", 10),
        ("推荐一首张学友的经典歌", 3),
        ("这首歌适合下雨天听吗？", 10.0),
        ("明天上海天气怎么样？", 5),
        ("再查一次香港今天的天气", 3),
        ("你刚才查天气了吗，查完了吗？", 10),           # 回复了2个城市天气
        ("刚刚查的上海天气是啥？", 5),                  # 没有调用工具，直接用结果回复
        ("换个话题，你简单介绍一下你能做什么", 5.0),
        ("再推荐一家上海平金中心附近可以边听歌边喝下午茶的咖啡馆", 10),
        ("最后总结一下刚才总结的所有事情", 5.0),        # 上个任务没有执行完，回复正确，就是待办事项！
    ],
    "car_control": [
        ("打开车窗", 0.0),
        ("播放周杰伦的晴天", 8.0),
        ("取消导航", 8.0),
    ],
}

CASES = [
    # 单工具
    "请查一下香港今天的天气",
    "帮我在香港找一家适合入住的酒店",
    "推荐一首张学友的经典歌曲",

    # 双工具
    "请帮我查询香港今天的天气，再找一家适合入住的酒店",
    "查一下香港今天的天气，再推荐一首适合雨天听的张学友歌曲",
    "在香港找一家酒店，再推荐一首张学友的歌",

    # 三工具
    "请查香港今天的天气，找一家酒店，再推荐一首张学友的歌",
    "明天上海天气怎么样，找一家平金中心附近适合晚餐的餐厅，再推荐一首适合路上听的歌",

    # 非工具/澄清
    "你好，简单介绍一下你能做什么",
    "帮我找个附近不错的地方",
    "放一首我会喜欢的歌",
]


async def test_run() -> None:
    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_1_8_251228, # 实测SEED_1_6_FLASH_250828 不够稳定，可能会报错，但速度快
        tools=TOOLS,
        system_prompt=ASYNC_REACT_SYSTEM_PROMPT,
        max_turns=5,
    )

    runner = AgentRunner(
        user_data=UserDataMocked(
            [
                # "请帮我查询香港今天的天气，再找一家适合入住的酒店",
                # "在香港找一家酒店，再推荐一首张学友的歌",
                "请查香港今天的天气，找一家酒店，再推荐一首张学友的歌",
            ]
        ),
        agent=agent,
        task_manager=TASK_MANAGER,
        client=AgentTaskEventPrinter(),
    )
    await runner.run()


async def test_run_multi_turn() -> None:
    """多轮 query 测试入口。

    通过环境变量 V2_REACT_MULTI_TURN_CASE 选择 MULTI_TURN_CASES 中的一组用例；
    默认跑 "multi_tool_followup"。
    """
    case_name = "car_control"

    turns = MULTI_TURN_CASES[case_name]
    print(f"\n[multi-turn case] {case_name}")
    for i, (q, d) in enumerate(turns):
        print(f"  turn {i}: delay={d}s query={q!r}")

    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_1_8_251228,
        tools=TOOLS,
        system_prompt=ASYNC_REACT_SYSTEM_PROMPT,
        max_turns=5,
    )

    runner = AgentRunner(
        user_data=UserDataDelayed(turns),
        agent=agent,
        task_manager=TASK_MANAGER,
        client=AgentTaskEventPrinter(),
    )
    await runner.run()


def run_single_turn_tui() -> None:
    """单轮 + TUI 演示入口"""
    from aicore.v2.experiments.tui import ReActTUIApp, TUIEventClient
    case_name = "car_control"

    turns = MULTI_TURN_CASES[case_name]
    print(f"\n[multi-turn case] {case_name}")
    for i, (q, d) in enumerate(turns):
        print(f"  turn {i}: delay={d}s query={q!r}")

    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_1_8_251228,
        tools=TOOLS,
        system_prompt=ASYNC_REACT_SYSTEM_PROMPT,
        max_turns=5,
    )

    app = ReActTUIApp()
    runner = AgentRunner(
        user_data=UserDataDelayed(turns),
        agent=agent,
        task_manager=TASK_MANAGER,
        client=TUIEventClient(app),
    )
    app.set_runner(runner.run)
    app.run()


if __name__ == "__main__":
    # 跑单轮 test_run
    # anyio.run(test_run)

    # run_single_turn_tui()

    # 多轮 test_run_multi_turn
    anyio.run(test_run_multi_turn)
    
