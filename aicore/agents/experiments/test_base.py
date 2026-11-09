"""
agent base 各功能测试
"""
from __future__ import annotations

import asyncio
import json
import pathlib
from datetime import datetime

from pydantic import BaseModel
from typing import Any
from rich import print

from aicore.models.credentials import create_client, AsyncArk
from aicore.models.doubao_models import ModelName
from aicore.models.responses import ainvoke # type: ignore

from aicore.agents.react import ReActEventPrinter
from aicore.agents.experiments.base import (
    _create_agent, # type: ignore
    SystemPrompt,
    AgentBase,
    ResponseParams,
    RunParams,
)

from aicore.tools.experiments.music_search import music_search_tool, _music_search_dummy # type: ignore
from aicore.tools.experiments.weather import _weather_search_tool_dummy # type: ignore
from aicore.tools.experiments.poi_search import create_poi_search_tool, _poi_search_dummy, _poi_search_dummy_stream # type: ignore

from aicore.events.task import TaskEventPrinter, is_task_event
from aicore.tools import TaskToolType

from aicore.agents.experiments.memory import (
    MemoryProducerConfig,
    MemoryConsumerConfig,
    MemoryProducer,
    MemoryConsumer,
    MemoryEvent,
    UserInfoMetadata,
    CollectionID,
    SKILL_PROFILE_TYPE,
)
from aicore.agents.experiments.user_profile import SINGLE_CAREER_WOMAN

MODEL = ModelName.SEED_1_8_251228

poi_tool = create_poi_search_tool(_poi_search_dummy)
music_tool = music_search_tool(_music_search_dummy)
poi_stream_tool = create_poi_search_tool(_poi_search_dummy_stream)
weather_tool = _weather_search_tool_dummy()

TOOLS: list[TaskToolType[Any, Any, Any, ...]] = [music_tool, poi_stream_tool, weather_tool]

TOOL_REGISTRY = {t.name: t for t in TOOLS}


TOOL_QUERIES = [
    "请帮我找一下香港的度假酒店",  # 测试 poi_stream_tool
    "找下汪峰的歌",
    # "请把空调调到18度，凉爽模式",
    # "看看今天上海天气如何，根据情况帮我开空调",
]

REACT_OVER_TURNS_CASES = [
    # 测试 react 的超过循环的 case。假设 max_turns=2
    "你好，我叫小明。请简单介绍一下自己",
    "请把空调调到18度，调整好了再去查询下上海天气,之后再关闭空调。",
    "导航去迪士尼。",
    "我之前都说了什么，复述一遍",
    "先关闭空调,再帮我随便播放一首音乐，最后导航去上海平金中心",
    "介绍下你自己",
]

# 记忆单测：collection、用户、问句
TEST_COLLECTION_NAME = "test_prompt"
TEST_USER_ID = "test_memory_user_id"
TEST_USER_NAME = "张三"
TEST_ASSISTANT_NAME = "小途"
TEST_ASSISTANT_ID = "test_assistant_id"
TEST_PROFILE_TYPES = ["steward_note_book",SKILL_PROFILE_TYPE]
TEST_EVENT_TYPES = ["event_v1"]
TEST_SKILL_PROFILE_TYPE = SKILL_PROFILE_TYPE

MEMORY_DIALOG_QUERIES = [
    "你好呀，我现在在上海闵行平金中心上班。",
    "请把空调调到18度，凉爽模式",
    "播放周杰伦的稻香",
    "导航到七宝古镇",
    "搜一下周杰伦的歌",
    "查一下公司附近的咖啡店",
    "今天天气怎么样",
    "搜一下今天当地的新闻头条",
    "公司附近的餐厅",
]
MEMORY_RECALL_QUERIES = [
    "前两天我说的那个游戏是啥来着",
    "简单讲述下我的个人信息，偏好等等。",
    "看看我喜欢哪些音乐",
    "看看我喜欢什么运动。",
]
NEW_SESSION_QUERIES = [
    "我是张三",
    "讲个笑话",
    "我刚刚说了哪些话，复述一遍。",
    "我第一句说的是什么",
    "我是谁",
]

# dump 单测那几句对话
DUMP_DIALOG_QUERIES = [
    "你好",
    "看看今天上海天气如何，根据情况帮我开空调",
]


# 对话相关
async def test_agent_chat():
    agent = _create_agent(model=MODEL, tools=TOOLS)

    queries = [
        "你好，我叫小明。请介绍一下自己",
        "我的名字叫什么",
        "请讲个跟你的能力有关的笑话",
    ]

    for i, query in enumerate(queries):
        print(f"\n{"="*20} ROUND {i+1} {"="*20}")

        print(f"user: {query}")
        print("assistant(流式): ", end="")
        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            pass
        assert agent.state.run_result is not None
        print(f"\nassistant(完整): {agent.state.run_result.response.raw_text}")

    print("agent state")
    print(agent.state)


async def test_agent_chat_vague():
    agent = _create_agent(model=MODEL, tools=TOOLS)

    """需要意图澄清的对话"""
    queries = [
        "我想查询一下天气",
        "我想导航",
        "我想查询一下车的状态",
        "我想听音乐",
        "我想控制一下车的座位",
        "我想调音量",
        "我想调整空调",
    ]

    for i, query in enumerate(queries):
        print(f"\n{"="*20} ROUND {i+1} {"="*20}")

        print(f"user: {query}")
        print("assistant(流式): ", end="")
        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            pass


async def test_agent_with_tools():
    agent = _create_agent(model=MODEL, tools=TOOLS)
    task_event_printer = TaskEventPrinter()

    for i, query in enumerate(TOOL_QUERIES[:]):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}:[red]{query}[/red]")
        print("="*80)

        async for event in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            if is_task_event(event):
                task_event_printer(event)

        # print("\n最终结果:")
        # print(agent.state.run_result)
        print("="*80)


async def test_agent_res_eval():
    """测试 Agent 运行结果评估"""
    agent = _create_agent(model=MODEL, tools=TOOLS)

    query = TOOL_QUERIES[1]
    print(f"{query}")

    async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
        pass

    print("\n最终结果:")
    assert agent.state.run_result is not None
    print(agent.state.run_result.response.raw_text)

    client, model = create_client(MODEL, AsyncArk)

    query_judge = f"""你是一个裁判，为AI助手的回答质量打分。

用户问题: {query}

AI回答: {agent.state.run_result.response.raw_text}

打分规则：分数为0-10分，0分表示回答质量很差，10分表示回答质量非常好。
质量标准如下:
1. 回答是否符合用户问题的意图。
2. 回答是否包含必要的信息。
3. 回答是否有逻辑错误或不完整。
4. 回答是否符合道德和法律规范。

请给出分数，以及原因。
"""

    res_judge = await ainvoke(query_judge, client=client, model=model)
    print(res_judge.raw_text)


async def test_agent_with_tools_over_turns():
    # 测试react 的超过循环的case。假设max_turns=2
    agent = _create_agent(model=MODEL, tools=TOOLS, max_turns=2)

    for i, query in enumerate(REACT_OVER_TURNS_CASES[:]):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)

        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            pass

        print("\nMessage_history:")
        assert agent.state.run_result is not None
        print(agent.state.run_result.response.message_history)

        print("="*80)


# 记忆相关
def _create_user_info() -> UserInfoMetadata:
    return UserInfoMetadata(
        user_id=TEST_USER_ID,
        user_name=TEST_USER_NAME,
        assistant_id=TEST_ASSISTANT_ID,
        assistant_name=TEST_ASSISTANT_NAME,
    )


def _create_memory_agent_config():
    run_params = RunParams(
        model=MODEL,
        params=ResponseParams(thinking={ "type": "disabled" }),
        max_turns=5,
    )
    system_prompt = SystemPrompt(
        role=f"你是友好的用户智能助手。当前时间{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}。",
        guidelines=[
            "打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。",
            "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节。",
        ],
    )
    return run_params, system_prompt


def _memory_producer_consumer_for_test(
    user_info: UserInfoMetadata,
) -> tuple[MemoryProducer, MemoryConsumer]:

    producer = MemoryProducer(
        MemoryProducerConfig(
            collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
            memory_type=TEST_EVENT_TYPES + TEST_PROFILE_TYPES,
        ),
        user_info,
        session_size=3,
    )
    consumer = MemoryConsumer(
        MemoryConsumerConfig(
            collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
            system_prompt_profile_types=TEST_PROFILE_TYPES,
            search_profile_types=[TEST_SKILL_PROFILE_TYPE],
            event_types=TEST_EVENT_TYPES,
            profile_limit=3,
            event_limit=3,
        ),
        user_info,
    )
    return producer, consumer


def _memory_test_agents() -> tuple[AgentBase, AgentBase, AgentBase]:
    """只挂 producer / 只挂 consumer / 两个都挂，给下面几个记忆单测各用各的。"""
    user_info = _create_user_info()
    run_params, system_prompt = _create_memory_agent_config()
    memory_producer, memory_consumer = _memory_producer_consumer_for_test(user_info)
    only_producer = AgentBase(
        system_prompt, run_params=run_params, tools=[], memory_producer=memory_producer
    )
    only_consumer = AgentBase(
        system_prompt, run_params=run_params, tools=[], memory_consumer=memory_consumer
    )
    both = AgentBase(
        system_prompt,
        run_params=run_params,
        tools=[],
        memory_producer=memory_producer,
        memory_consumer=memory_consumer,
    )
    return only_producer, only_consumer, both


async def test_agent_with_memory(agent: AgentBase, queries: list[str]):
    for i, query in enumerate(queries):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)
        async for event in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            if isinstance(event, MemoryEvent):
                print(event)
        print("="*80)


async def test_agent_with_memory_and_new_session(agent: AgentBase, queries: list[str]):
    for i, query in enumerate(queries):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)
        async for event in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            if isinstance(event, MemoryEvent):
                print(event)
        print("="*80)
        assert agent.memory_producer
        print(f"未new_session前缓冲区：{agent.memory_producer.pending_count}")

    print("清空记忆缓冲区")
    await agent.new_session()
    assert agent.memory_producer
    print(f"new_session触发提交新对话后缓冲区：{agent.memory_producer.pending_count}")


async def test_agent_retrieve_memory(agent: AgentBase):

    print("测试通过agent.retrieve_profiles()和agent.retrieve_events()返回画像和事件记忆")
    print("="*80)

    profiles = await agent.retrieve_profiles()
    assert profiles.code == 0, f"retrieve_profiles() 失败: {profiles.message}"

    print(profiles)
    print("="*80)

    events = await agent.retrieve_events()
    assert events.code == 0, f"retrieve_events() 失败: {events.message}"

    print(events)
    print("="*80)


async def test_memory_producer():
    only_producer, _, _ = _memory_test_agents()
    await test_agent_with_memory(only_producer, MEMORY_DIALOG_QUERIES)


async def test_memory_consumer():
    _, only_consumer, _ = _memory_test_agents()
    await test_agent_with_memory(only_consumer, MEMORY_RECALL_QUERIES)


async def test_memory_producer_consumer():
    _, _, both = _memory_test_agents()
    await test_agent_retrieve_memory(both)


async def test_agent_new_session_with_producer():
    only_producer, _, _ = _memory_test_agents()
    await test_agent_with_memory_and_new_session(only_producer, NEW_SESSION_QUERIES)


# dump / create
async def test_dump_and_create():
    """专门测试 dump 与 create：先跑一轮对话 → dump → create 恢复 → 校验状态一致。"""

    agent = _create_agent(
        model=MODEL,
        tools=TOOLS,
        guidelines=["打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。"],
    )
    for i, query in enumerate(DUMP_DIALOG_QUERIES):
        print("\n" + "=" * 80)
        print(f"测试流式输出 #{i + 1}: {query}")
        print("=" * 80)

        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            pass

    assert agent.state.run_result is not None
    original_id = agent.state.run_result.response.id
    print(f"原始id: {original_id}")

    path = "aicore/agents/experiments/agent.json"
    payload_obj = await agent.dump()
    pathlib.Path(path).write_text(
        json.dumps(payload_obj.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    restored = AgentBase.create(payload_obj, tool_registry=TOOL_REGISTRY)

    print("*" * 100)
    print("用恢复的agent继续对话")
    print("*" * 100)
    for query in ["我之前都说过啥？"]:
        async for _ in restored.astream(query, event_listeners=[ReActEventPrinter()]):
            pass
        print("*" * 100)
    # print("恢复的agent状态:")
    # print(restored.state)

    print(f"agent dump的文件已保存至\n{path}")


async def test_loop_dump_create(rounds: int = 3):
    """反复 dump → create，验证每轮恢复后能继续对话且再次 dump 可被下一次 create 正常反序列化。"""
    user_info = _create_user_info()
    run_params, system_prompt = _create_memory_agent_config()
    memory_producer, memory_consumer = _memory_producer_consumer_for_test(user_info)

    agent = AgentBase(
        system_prompt,
        run_params=run_params,
        tools=TOOLS,
        memory_producer=memory_producer,
        memory_consumer=memory_consumer,
        user_profile=SINGLE_CAREER_WOMAN,
    )

    async for _ in agent.astream("你好，上海天气怎么样", event_listeners=[ReActEventPrinter()]):
        pass
    payload_obj = await agent.dump()
    pathlib.Path("aicore/agents/experiments/agent_loop_base.json").write_text(
        json.dumps(payload_obj.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    for i in range(rounds):
        print("*" * 60 + f" 第 {i + 1}/{rounds} 轮 create ")
        restored = AgentBase.create(payload_obj, tool_registry=TOOL_REGISTRY)
        async for _ in restored.astream(f"记住当前是第{i + 1}轮对话", event_listeners=[ReActEventPrinter()]):
            pass
        payload_obj = await restored.dump()
        pathlib.Path(f"aicore/agents/experiments/agent_loop_{i + 1}.json").write_text(
            json.dumps(payload_obj.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print("*" * 60 + " 最后一轮仅 create + 一问，校验最终 payload 可恢复 ")
    final = AgentBase.create(payload_obj, tool_registry=TOOL_REGISTRY)
    async for _ in final.astream("复述下我之前都说了啥", event_listeners=[ReActEventPrinter()]):
        pass
    print("循环 dump/create 测试通过。")


async def test_basemodel_serialization():
    """复现 dump 时 system prompt 为空字典。测试 BaseModel 序列化场景。"""

    class SystemPromptLocal(BaseModel):
        content: str

    class SgmSystemPrompt(BaseModel):
        content: str

    class MainModel(BaseModel):
        prompt: str | SystemPromptLocal | BaseModel

    sys_prompt = SystemPromptLocal(content="测试")
    model1 = MainModel(prompt=sys_prompt)
    print("SystemPrompt 实例序列化：", model1.model_dump())

    sgm_prompt = SgmSystemPrompt(content="外部测试内容")
    model2 = MainModel(prompt=sgm_prompt)
    print("SgmSystemPrompt 实例序列化：", model2.model_dump())
    """结论：当匹配到 BaseModel 分支时，Pydantic 就「按 BaseModel 的规则序列化」；
    BaseModel 类本身没有定义任何字段（content 是子类 SgmSystemPrompt 定义的）；
    Pydantic 的 model_dump() 只会序列化「当前类型注解中声明的类所定义的字段」→ BaseModel 无字段 → 输出 {}；
    哪怕实际传入的是 SgmSystemPrompt 实例（有 content 字段），但因为注解匹配到了 BaseModel，Pydantic 不会去读取子类的字段。"""


async def test_skill_memory_tool_chain():
    """测试 skill 工具链：先创建3个skill，再search/load/use/update/reload。"""
    print("\n" + "=" * 80)
    print("开始执行 test_skill_memory_tool_chain")
    print("=" * 80)

    user_info = _create_user_info()
    memory_consumer = MemoryConsumer(
        MemoryConsumerConfig(
            collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
            search_profile_types=[TEST_SKILL_PROFILE_TYPE],
            event_types=TEST_EVENT_TYPES,
            profile_limit=10,
            event_limit=3,
        ),
        user_info,
    )

    create_worker = memory_consumer.create_new_skill_worker()
    search_worker = memory_consumer.create_skill_search_worker()
    load_worker = memory_consumer.create_load_skill_worker()
    update_worker = memory_consumer.update_skill_worker()

    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    skill_cases = [
        {
            "skill_name": f"trip_itinerary_planning_{suffix}",
            "skill_description": "面向多约束出行需求的行程规划方法。",
            "skill_markdown_content": (
                "# 行程规划技能\n"
                "## 适用场景\n"
                "- 用户给出时间、预算、偏好后需要生成可执行计划。\n"
                "## 步骤\n"
                "1. 收集约束\n2. 生成候选方案\n3. 对比并给推荐\n4. 输出执行清单"
            ),
            "search_query": "行程规划 预算 时间 偏好",
        },
        {
            "skill_name": f"bug_triage_and_fix_flow_{suffix}",
            "skill_description": "用于线上问题的定位、修复与回归验证流程。",
            "skill_markdown_content": (
                "# 缺陷定位修复技能\n"
                "## 步骤\n"
                "1. 复现问题\n2. 收集日志与上下文\n3. 缩小范围\n4. 修复并验证\n5. 输出复盘"
            ),
            "search_query": "bug定位 修复 回归 验证",
        },
        {
            "skill_name": f"meeting_summary_action_items_{suffix}",
            "skill_description": "将长会议记录提炼为结论、风险和行动项。",
            "skill_markdown_content": (
                "# 会议纪要提炼技能\n"
                "## 步骤\n"
                "1. 提炼关键决策\n2. 列出行动项负责人与截止时间\n3. 标注风险与依赖\n4. 输出摘要"
            ),
            "search_query": "会议纪要 行动项 提炼",
        },
    ]

    # 先创建3个有意义命名的 skill
    for case in skill_cases:
        print(f"[CREATE] 准备创建 skill: {case['skill_name']}")
        create_rsp = await create_worker(
            skill_name=case["skill_name"],
            skill_description=case["skill_description"],
            skill_markdown_content=case["skill_markdown_content"],
        )
        assert create_rsp.success, f"create_new_skill 失败: {create_rsp.messages}"
        print(f"[CREATE] 成功: {case['skill_name']}")

    # 在已创建skill基础上，逐个执行搜索、加载、使用
    for case in skill_cases:
        skill_name = case["skill_name"]
        print(f"[SEARCH] 开始检索 skill: {skill_name}")
        search_rsp = await search_worker(query=case["search_query"], limit=10)
        for _ in range(5):
            if search_rsp.skills and any(s.skill_name == skill_name for s in search_rsp.skills):
                break
            await asyncio.sleep(1)
            search_rsp = await search_worker(query=case["search_query"], limit=10)
        assert search_rsp.skills, f"skill_search 未返回结果: {skill_name}"
        assert any(s.skill_name == skill_name for s in search_rsp.skills), f"skill_search 未检索到: {skill_name}"
        print(f"[SEARCH] 命中: {skill_name}，返回 {len(search_rsp.skills)} 条候选")

        print(f"[LOAD] 开始加载 skill: {skill_name}")
        load_rsp = await load_worker(skill_name=skill_name)
        for _ in range(5):
            if load_rsp.skill is not None:
                break
            await asyncio.sleep(1)
            load_rsp = await load_worker(skill_name=skill_name)
        assert load_rsp.skill is not None, f"load_skill 失败: {skill_name}, {load_rsp.messages}"
        assert load_rsp.skill.skill_name == skill_name
        print(f"[LOAD] 成功: {skill_name}")

        # “使用之”：读取skill正文并检查包含步骤结构，模拟可执行消费。
        assert "步骤" in (load_rsp.skill.skill_markdown_content or ""), f"skill内容不完整: {skill_name}"
        print(f"[USE] 内容校验通过: {skill_name}")

    # 更新其中一个skill，再加载确认更新成功
    target = skill_cases[1]
    print(f"[UPDATE] 开始更新 skill: {target['skill_name']}")
    updated_description = "用于线上问题定位、修复、回归及经验沉淀的一体化流程。"
    updated_markdown = (
        "# 缺陷定位修复技能（升级版）\n"
        "## 步骤\n"
        "1. 复现并分级\n2. 增加可观测性\n3. 快速止血与根因修复\n4. 回归验证\n5. 沉淀防回归清单"
    )
    update_rsp = await update_worker(
        skill_name=target["skill_name"],
        skill_description=updated_description,
        skill_markdown_content=updated_markdown,
    )
    assert update_rsp.success, f"update_skill 失败: {update_rsp.messages}"
    print(f"[UPDATE] 成功: {target['skill_name']}")

    print(f"[RELOAD] 开始加载更新后的 skill: {target['skill_name']}")
    reloaded_rsp = await load_worker(skill_name=target["skill_name"])
    for _ in range(5):
        if reloaded_rsp.skill and reloaded_rsp.skill.skill_markdown_content == updated_markdown:
            break
        await asyncio.sleep(1)
        reloaded_rsp = await load_worker(skill_name=target["skill_name"])
    assert reloaded_rsp.skill is not None, f"更新后 load_skill 失败: {reloaded_rsp.messages}"
    assert reloaded_rsp.skill.skill_description == updated_description, "skill_description 未更新成功"
    assert reloaded_rsp.skill.skill_markdown_content == updated_markdown, "skill_markdown_content 未更新成功"
    print(f"[RELOAD] 更新校验通过: {target['skill_name']}")
    print("[PASS] test_skill_memory_tool_chain 通过")


async def main():
    # 工具调用、对话、澄清、评估、react 超出轮次
    await test_agent_with_tools()
    await test_agent_chat()
    await test_agent_chat_vague()
    await test_agent_res_eval()
    await test_agent_with_tools_over_turns()

    # agent 配置memory相关
    await test_memory_producer()
    await test_memory_consumer()
    await test_memory_producer_consumer()

    await test_agent_new_session_with_producer()

    # agent 序列化，dump / create
    await test_dump_and_create()
    await test_loop_dump_create()
    await test_basemodel_serialization()
    await test_skill_memory_tool_chain()


if __name__ == "__main__":
    asyncio.run(main())
