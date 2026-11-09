import asyncio

from rich import print

import pathlib
import json

from aicore.tools.experiments.weather import create_weather_search_tool, _weather_dummy
from aicore.tools.experiments.poi_search import (
    create_poi_search_tool,
    _poi_search_dummy_stream,
)
from aicore.tools.experiments.music_search import music_search_tool, _music_search_dummy

from aicore.models.credentials import ModelName

from aicore.v1.experiments.base import (
    AgentContext,
    AgentState,
    AgentBase,
    create_agent,
    EventPrinter,
)

from aicore.events.explicit_tool_call import ExplicitFinishEvent, SelectionMissedEvent
from aicore.events.react import ReActFinishEvent

from aicore.tools import TaskToolImpl, create_tools
from projects.mind.toolset.experiments import structured_poi_search_tool, structured_music_search_tool

WEATHER_TOOL = create_weather_search_tool(_weather_dummy, with_clarify=True)
# POI_STREAM_TOOL = create_poi_search_tool(_poi_search_dummy_stream, with_clarify=True)
POI_TOOL = structured_poi_search_tool()
# MUSIC_TOOL = music_search_tool(_music_search_dummy, with_clarify=True)
MUSIC_TOOL = structured_music_search_tool(with_clarify=False)

TOOLS = [WEATHER_TOOL, POI_TOOL, MUSIC_TOOL]

# WORKERS = { # TODO: 看下 clarify 改装饰器后如何处理
#     t.name: TaskToolImpl(
#         args_schema=t.args_schema,
#         worker=t.worker,
#     )
#     for t in TOOLS
# }


async def test_agent_with_tools():
    agent = create_agent(
        model=ModelName.SEED_1_8_251228, tools=TOOLS, enable_tool_intent=False, react_max_turns=2
    )

    query = "北京今天天气怎么样？"  # 能有效调用weather_tool
    # query = "天气怎么样？"  # 模糊意图，需要clarify

    # query = "我正在香港旅游，想参观一个有名的酒店"  # 能有效的调用poi_tool
    # query = "我想参观一个酒店"  # 模糊意图，需要clarify

    # query = "请推荐张学友的有名歌曲。"  # 能有效调用music_tool
    # query = "帮我找个歌。"  # 模糊意图，需要clarify

    # query = "我正在香港旅游，想帮我找个有名的酒店去参观。请推荐张学友的有名歌曲。顺便帮我查下明天的天气。"  # 意图明确的多任务
    # query = "我正在旅游，想找个地方玩，请推荐。想听歌，请推荐。顺便帮我查下天气。"  # 意图模糊的多任务
    
    # music
    # query = "搜一下周杰伦的歌, 标题中带有雨天, 歌词中带有晴天, 发布时间在 2020~2024 之间"

    # poi
    # query = "我在平金中心，找附近 3km 内评分 4 分以上的火锅店"
    # query = "查找西岸凤巢附近有水果店的商场" # contains relation
    # query = "帮我找上海徐汇区附近有停车场的商场，优先商场附近 500 米内有停车场" # nearby relation

    print(f"user: {query}")

    await agent.run_astream(query, event_listeners=[EventPrinter()])

    assert agent.state.model_api_state is not None, "流式执行后，状态中应该有模型续接状态"
    print(f"\nassistant(完整): {agent.state.message_history[-1][1].content or ''}")


async def test_dump_and_create():
    print("测试dump")

    agent = create_agent(model=ModelName.SEED_1_8_251228, tools=TOOLS)
    await agent.run_astream(
        "你好，上海天气怎么样，再帮我推荐一个香港的酒店",
        event_listeners=[EventPrinter()],
    )

    context, state = await agent.dump()
    print(context)
    print(state)

    context_json = context.model_dump_json()
    state_json = state.model_dump_json()

    context_restored = AgentContext.model_validate_json(context_json)
    state_restored = AgentState.model_validate_json(state_json)
    if context_restored.tool_defs:
        context_restored.tools = create_tools(context_restored.tool_defs, WORKERS)

    print("开始测试create")
    restored = AgentBase(context_restored, state=state_restored)
    await restored.run_astream("复述下我之前都说了啥", event_listeners=[EventPrinter()])
    assert restored.state.model_api_state is not None, "create测试失败"
    print("create测试成功")


async def test_loop_dump_create(rounds: int = 3):
    """反复 dump → create，验证每轮恢复后能继续对话且再次 dump 可被下一次 create 正常反序列化。"""

    agent = create_agent(model=ModelName.SEED_1_8_251228, tools=TOOLS)

    await agent.run_astream(
        "你好，上海天气怎么样，再帮我推荐一个香港的酒店",
        event_listeners=[EventPrinter()],
    )
    context, state = await agent.dump()

    for i in range(rounds):
        print("*" * 60 + f" 第 {i + 1}/{rounds} 轮 create ")
        restored = AgentBase(context, state=state)
        await restored.run_astream(
            f"记住当前是第{i + 1}轮对话", event_listeners=[EventPrinter()]
        )
        context, state = await restored.dump()
        pathlib.Path(f"tests/v1/agent_loop_{i + 1}.json").write_text(
            json.dumps(
                {
                    "context": context.model_dump(mode="json"),
                    "state": state.model_dump(mode="json"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    print("*" * 60 + " 最后一轮仅 create + 提问，校验最终 payload 可恢复 ")
    final = AgentBase(context, state=state)
    await final.run_astream("复述下我之前都说了啥", event_listeners=[EventPrinter()])
    print("循环 dump/create 测试通过。")


async def test_explicit_hit_returns_directly():
    """Explicit 命中: query 唯一指向某个 tool, 由 explicit primitive 直接给出最终回答,
    dispatcher 不再落到 react.

    断言:
    - 事件流里出现 ExplicitFinishEvent (explicit 已承诺)
    - 事件流里不出现 ReActFinishEvent (react 未被触发)
    - model_api_state 不被 explicit 推进
    - message_history 写入本轮回答
    """
    agent = create_agent(
        model=ModelName.SEED_1_8_251228, tools=TOOLS, enable_tool_intent=True
    )

    query = "请推荐张学友的有名歌曲。"  # 唯一指向 music_tool
    print(f"user: {query}")

    printer = EventPrinter()
    explicit_finished = False
    react_finished = False
    async for event in agent.astream(query):
        printer(event)
        if isinstance(event, ExplicitFinishEvent):
            explicit_finished = True
        if isinstance(event, ReActFinishEvent):
            react_finished = True

    assert explicit_finished, "explicit 应命中并产出 ExplicitFinishEvent"
    assert not react_finished, "explicit 命中后不应再走 react"
    assert agent.state.model_api_state is None, "explicit 不应推进主会话 model_api_state"
    assert agent.state.message_history, "explicit 应写入 message_history"
    print(f"\nassistant: {agent.state.message_history[-1][1].content or ''}")


async def test_explicit_miss_falls_through_to_react():
    """Explicit 未命中: 多意图 / 模糊 query 触发 SelectionMissedEvent,
    dispatcher 落到 react 完成回答.

    断言:
    - 事件流里出现 SelectionMissedEvent
    - 事件流里不出现 ExplicitFinishEvent (未承诺)
    - 事件流里出现 ReActFinishEvent (回退路径生效)
    - model_api_state 被推进 (由 react 写入)
    """
    agent = create_agent(
        model=ModelName.SEED_1_8_251228, tools=TOOLS, enable_tool_intent=True
    )

    query = "我正在旅游，想找个地方玩，请推荐。想听歌，请推荐。顺便帮我查下天气。"  # 多意图, explicit 无法唯一命中
    print(f"user: {query}")

    printer = EventPrinter()
    saw_miss = False
    explicit_finished = False
    react_finished = False
    async for event in agent.astream(query):
        printer(event)
        if isinstance(event, SelectionMissedEvent):
            saw_miss = True
        if isinstance(event, ExplicitFinishEvent):
            explicit_finished = True
        if isinstance(event, ReActFinishEvent):
            react_finished = True

    assert saw_miss, "多意图 query 应导致 explicit 未命中 (SelectionMissedEvent)"
    assert not explicit_finished, "未命中不应产出 ExplicitFinishEvent"
    assert react_finished, "未命中后应落到 react 并产出 ReActFinishEvent"
    assert agent.state.model_api_state is not None, "model_api_state 应被 react 推进"
    print(f"\nassistant: {agent.state.message_history[-1][1].content or ''}")


async def main():
    await test_agent_with_tools()
    # await test_dump_and_create()
    # await test_loop_dump_create()
    # await test_explicit_hit_returns_directly()
    # await test_explicit_miss_falls_through_to_react()


if __name__ == "__main__":
    asyncio.run(main())
