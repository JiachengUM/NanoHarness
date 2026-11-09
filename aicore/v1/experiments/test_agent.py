import asyncio
from typing import Any
from rich import print
from datetime import datetime
from time import perf_counter
import pathlib
import json

from pydantic import BaseModel, Field

from aicore.models.credentials import ModelName
from aicore.models.model_api import ModelParams
from aicore.tools.experiments.poi_search import create_poi_search_tool, _poi_search_dummy, _poi_search_dummy_stream # type: ignore
from aicore.tools.experiments.music_search import _music_search_dummy, music_search_tool # type: ignore
from aicore.tools.experiments.weather import create_weather_search_tool, _weather_dummy # type: ignore
from aicore.tools.experiments.web_search import create_web_search_tool, _web_search_dummy, _web_search_dummy_stream # type: ignore
from aicore.v1.experiments.agent import Agent, AgentContext, AgentState, SystemPrompt
from aicore.tools import TaskToolImpl, create_tool, create_tools
from aicore.agents.experiments.memory import UserInfoMetadata, MemoryConsumerConfig, CollectionID, MemoryProducerConfig
from aicore.v1.experiments.agent import ReActTaskMemoryEventPrinter

from aicore.models.model_api import ModelCallParams, ModelAPIBackend


WEATHER_TOOL = create_weather_search_tool(_weather_dummy)
MUSIC_TOOL = music_search_tool(worker=_music_search_dummy)
POI_TOOL = create_poi_search_tool(_poi_search_dummy)
POI_STREAM_TOOL = create_poi_search_tool(_poi_search_dummy_stream)
WEB_SEARCH_TOOL = create_web_search_tool(worker=_web_search_dummy_stream)

class CarWindowInput(BaseModel):
    action: str = Field(..., description="车窗控制动作，例如打开、关闭")
    target: str = Field(default="全部车窗", description="要控制的车窗，例如全部车窗、主驾车窗")


class CarWindowOutput(BaseModel):
    action: str = Field(..., description="已执行的动作")
    target: str = Field(..., description="已控制的车窗")
    status: str = Field(..., description="执行状态")


async def _car_window_dummy(
    action: str,
    target: str = "全部车窗",
) -> CarWindowOutput:
    return CarWindowOutput(action=action, target=target, status="success")


CAR_WINDOW_TOOL = create_tool(
    name="车窗控制工具",
    description="控制车辆车窗，支持打开或关闭车窗。",
    args_schema=CarWindowInput,
    worker=_car_window_dummy,
)

TOOLS = [MUSIC_TOOL, WEATHER_TOOL, POI_STREAM_TOOL] 

WORKERS = {
    t.name: TaskToolImpl(
        args_schema=t.args_schema,
        worker=t.actual_worker,
    ) for t in TOOLS
}


TEST_USER_ID = "test_memory_user_id"
TEST_USER_NAME = "张三"
TEST_ASSISTANT_NAME = "小途"
TEST_ASSISTANT_ID = "test_assistant_id"

# TEST_COLLECTION_NAME = "test_memory"
# TEST_PROFILE_TYPES = ["sys_profile_v1"]
# TEST_EVENT_TYPES = ["sys_event_v1"]
# SKILL_PROFILE_TYPE = None

# TODO：skill相关的tool，需要对应的记忆库配置了skill 画像，才可正常使用。
TEST_COLLECTION_NAME = "test_prompt"
TEST_PROFILE_TYPES = ["steward_note_book"]
TEST_EVENT_TYPES = ["event_v1"]
SKILL_PROFILE_TYPE = "skills"


def create_agent(
    tools: list[Any] | None = None,
    use_memory: bool = True,
    enable_tool_intent: bool = False,
    tool_intent_model_params: ModelParams | None = None,
    react_max_turns: int = 5,
    model_api_backend: ModelAPIBackend = "chat",
) -> Agent:

    tools = tools if tools is not None else TOOLS
    system_prompt = SystemPrompt(
        role=f"你是友好的用户智能助手,当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        guidelines=[
            "打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。",
            "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节。",
        ],
    )
    # TODO: 依然会发生致命bug。context中的tools被退化为BaseTool。
    context = AgentContext(
        system_prompt=system_prompt,
        model_params=ModelParams(model=ModelName.SEED_1_8_251228,params=ModelCallParams(thinking="disabled")),
        enable_tool_intent=enable_tool_intent,
        tool_intent_model_params=tool_intent_model_params,
        react_max_turns=react_max_turns,
        tools=tools,
        model_api_backend=model_api_backend,
    )
    if use_memory:
        context.memory_user_info = UserInfoMetadata(
                                        user_id=TEST_USER_ID,
                                        user_name=TEST_USER_NAME,
                                        assistant_id=TEST_ASSISTANT_ID,
                                        assistant_name=TEST_ASSISTANT_NAME,
                                    )
        context.memory_producer_config = MemoryProducerConfig(
                                        collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
                                        memory_type=TEST_PROFILE_TYPES + TEST_EVENT_TYPES,
                                    )
        context.memory_consumer_config = MemoryConsumerConfig(
                                        collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
                                        system_prompt_profile_types=TEST_PROFILE_TYPES,
                                        search_profile_types=[SKILL_PROFILE_TYPE] if SKILL_PROFILE_TYPE else None,
                                        event_types=TEST_EVENT_TYPES,
                                        profile_limit=3,
                                        event_limit=3,
                                    )
        context.memory_producer_session_size = 1

    return Agent(context)

async def test_agent_with_tools() -> None:

    tool_query_cases =  [
    "前两天我说的那个游戏是啥来着，再帮我找下香港有哪些酒店", # search_event_tool、POI
    "我喜欢啥？说说看",
    "我正在旅游，想找个地方玩，请推荐。想听歌，请推荐。顺便帮我查下今天上海天气。看看今天国际上发生了什么大事。",

    # TODO：需要SKILL_PROFILE_TYPE = "skills"，且记忆库存在该画像，才可测试skill tool
    "看看有哪些小妙招", # skill_search_tool 
    "加载逛街小妙招，准备去逛街喽，来套连招", # load_skill_tool
    "更新下小妙招，我个人比较喜欢去商场逛逛，然后去咖啡店坐坐", # update_skill_tool
    ]
    agent = create_agent(tools=TOOLS, use_memory=True, enable_tool_intent=False)

    for i, query in enumerate(tool_query_cases, start=1):
        print("\n" + "=" * 80)
        print(f"测试流式输出 #{i}: {query}")
        print("=" * 80)
        await agent.run_astream(query, event_listeners=[ReActTaskMemoryEventPrinter()])
        # 每个测试用例之间独立测试。
        # await agent.new_session()
        print("=" * 80)


async def _run_agent_and_measure(agent: Agent, query: str) -> float:
    start = perf_counter()
    await agent.run_astream(query, event_listeners=[ReActTaskMemoryEventPrinter()])
    return perf_counter() - start


async def test_flash_tool_intent_vs_react_latency() -> None:
    query = "帮我打开车窗"

    print("\n" + "=" * 80)
    print(f"测试 flash 工具意图识别 vs 直接 ReAct 耗时: {query}")
    print("=" * 80)

    flash_intent_agent = create_agent(
        tools=[CAR_WINDOW_TOOL],
        use_memory=False,
        enable_tool_intent=True,
        tool_intent_model_params=ModelParams(
            model=ModelName.SEED_1_6_FLASH_250828,
        ),
    )
    flash_elapsed = await _run_agent_and_measure(flash_intent_agent, query)

    react_agent = create_agent(
        tools=[CAR_WINDOW_TOOL],
        use_memory=False,
        enable_tool_intent=False,
    )
    react_elapsed = await _run_agent_and_measure(react_agent, query)

    print("-" * 80)
    print(f"flash explicit 工具意图识别耗时: {flash_elapsed:.3f}s")
    print(f"直接 ReAct 耗时: {react_elapsed:.3f}s")
    print(f"差值 flash explicit - ReAct: {flash_elapsed - react_elapsed:+.3f}s")
    print("=" * 80)


async def test_dump_and_create():
    print("测试dump")
    agent = create_agent(tools=[POI_TOOL], use_memory=False)
    await agent.run_astream("你好，上海天气怎么样，再帮我推荐一个香港的酒店", event_listeners=[ReActTaskMemoryEventPrinter()])
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
    restored = Agent(context_restored, state=state_restored)
    await restored.run_astream("复述下我刚刚说了啥", event_listeners=[ReActTaskMemoryEventPrinter()])
    assert restored.state.model_api_state is not None, "create测试失败"
    print("create测试成功")
    print(await restored.dump())

async def test_loop_dump_create(rounds: int = 3):
    """反复 dump → create，验证每轮恢复后能继续对话且再次 dump 可被下一次 create 正常反序列化。"""
    agent = create_agent(tools=TOOLS, react_max_turns=1)

    await agent.run_astream("你好", event_listeners=[ReActTaskMemoryEventPrinter()])# 不会超过react最大轮次
    assert agent.state.model_api_state is not None, "model_api_state不能为None"
    print("第一轮对话后message_history:", agent.state.message_history)
    await agent.run_astream("上海天气怎么样，再帮我推荐一个香港的酒店，看看前两天我干了啥", event_listeners=[ReActTaskMemoryEventPrinter()])
    print("第二轮对话后message_history:", agent.state.message_history)
    context, state = await agent.dump()

    pathlib.Path(f"aicore/v1/experiments/agent_loop_base.json").write_text(
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

    for i in range(rounds):
        print("*" * 60 + f" 第 {i + 1}/{rounds} 轮 create ")
        restored = Agent(context, state=state)
        await restored.run_astream(f"记住当前是第{i+1}轮对话", event_listeners=[ReActTaskMemoryEventPrinter()])
        context, state = await restored.dump()
        pathlib.Path(f"aicore/v1/experiments/agent_loop_{i+1}.json").write_text(
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
    final = Agent(context, state=state)
    await final.run_astream("复述下我刚刚都说了啥", event_listeners=[ReActTaskMemoryEventPrinter()])
    print("循环 dump/create 测试通过。")

async def test_agent_retrieve_memory():
    """测试通过agent.retrieve_profiles()和agent.retrieve_events()返回画像和事件记忆"""
    agent = create_agent(tools=TOOLS, use_memory=True)
    profiles = await agent.retrieve_profiles()
    events = await agent.retrieve_events()
    print("画像记忆召回结果:")
    print(profiles)
    print("事件记忆召回结果:")
    print(events)


async def main() -> None:
    # await test_flash_tool_intent_vs_react_latency()

    # await test_agent_with_tools()

    # await test_dump_and_create()
    await test_loop_dump_create()

    # await test_agent_retrieve_memory()


if __name__ == "__main__":
    asyncio.run(main())
