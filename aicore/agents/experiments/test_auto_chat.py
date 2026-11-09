import asyncio
from datetime import datetime
import json
import os
import random
from jinja2 import Template
from rich import print

from aicore.agents.events import ReActEventPrinter
from aicore.agents.experiments.base import AgentBase, RunParams, SystemPrompt
from aicore.agents.experiments.user_profile import UserProfile
from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, AsyncArk
from aicore.models.chat import (
    ChatParams,
    astream,
)
from aicore.models.responses.params import ResponseParams
from aicore.utils.nl_repr import nl_repr

from projects.mind.test_backend.service.agent.react import get_tool_map


HINTS_PROMPT = """
你是一个智能对话助手。根据用户提供的人设信息、对话场景及对话历史，预测用户接下来最可能说的下一句话。

请分析对话的上下文和逻辑走向，生成3-5个最合理的用户下一句可能的发言（hints）。

要求：
1. 每个hint必须是用户（human）可能说的话
2. hints要符合对话逻辑和自然语言习惯
3. hints要有一定的多样性（可以是不同表达方式，或不同方向）
4. 输出格式必须是标准的JSON数组格式

输出示例：
[
  { "role": "human", "content": "北京天气怎么样？" },
  { "role": "human", "content": "上海" },
  { "role": "human", "content": "查一下广州的天气" }
]

注意：只输出JSON数组，不要有其他文字说明。
"""

query_template = Template(
    """
人设信息：
{{ persona }}

对话场景：
{{ scene }}

对话记录：
{{ history }}
"""
)


async def create_agent(user_profile: UserProfile | None) -> AgentBase:
    """
    创建一个Agent实例，包含工具和运行参数。
    """

    tool_map = get_tool_map()
    tools = [tool_map[name] for name in tool_map]

    _, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    params = ResponseParams(thinking={"type": "disabled"})

    run_params = RunParams(
        model=model,
        params=params,
        max_turns=8,
    )

    system_prompt = SystemPrompt(
        role="你是友好的用户智能助手",
        guidelines=[
            "打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。",
            "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节。",
        ],
    )

    return AgentBase(
        system_prompt, run_params=run_params, tools=tools, user_profile=user_profile
    )


async def generate_hints(query: str) -> None:
    """
    根据用户的查询，生成3-5个最合理的用户下一句可能的发言（hints）。
    """

    params = ChatParams(thinking={"type": "disabled"})

    client, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    print("hints:", end="", flush=True)

    stream_res = await astream(
        query,
        HINTS_PROMPT,
        show_reasoning=False,
        client=client,
        model=model,
        params=params,
    )
    async for chunk in stream_res:
        print(chunk, end="", flush=True)

    return json.loads(stream_res.output)


def get_agent_message_history(agent: AgentBase) -> list:
    """
    获取agent的消息历史，并将其转换为字典列表格式。
    """

    return [
        message.model_dump()
        for message_tuple in agent.state.run_result.response.message_history
        for message in message_tuple
    ]


async def get_hint_query(persona: str, scene: str, messages: list) -> str:
    """
    随机生成一个合理的用户下一句可能的发言（query），用于驱动agent进行多轮对话。
      - persona: 用户画像的自然语言描述
      - scene: 对话场景描述
      - messages: 当前对话历史消息列表
    """
    hints_query = query_template.render(
        persona=persona,
        scene=scene,
        history=messages,
    )
    hints = await generate_hints(hints_query)

    return random.choice(hints)["content"]


async def auto_chat(
    agent: AgentBase,
    query: str,
    persona: str,
    scene: str,
    turns: int = 5,
    writer_to_file: bool = True,
) -> None:
    """
    自动对话函数，模拟用户与智能助手的多轮对话。
    """

    # 如果用户没有提供初始query，则通过get_hint_query生成一个合理的初始query
    if not query:
        query = await get_hint_query(persona, scene, [])

    print(f"\n============================ Turn {6 - turns} =========================")
    print(f"\nuser: {query}")
    print("\nassistant: ", end="")
    async for _ in agent.astream(query, event_listeners=[ReActEventPrinter(print)]):
        ...

    messages = get_agent_message_history(agent)

    if turns <= 1:
        print("[✅ 对话结束]")
        if writer_to_file:
            writer_messages_to_file(messages)
        return

    query = await get_hint_query(persona, scene, messages)

    await auto_chat(
        agent, query, persona, scene, turns=turns - 1, writer_to_file=writer_to_file
    )


def writer_messages_to_file(messages: list) -> None:
    """
    将消息列表写入文件，文件名包含当前时间戳。
    """
    file_name = f"auto_chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    file_path = os.path.join(os.path.dirname(__file__), file_name)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=4)


async def test_auto_chat() -> None:
    user_profile = {
        "user_type": "单身职场女性",
        "personal_status": ["单身", "可能有稳定伴侣但未同居", "无子女"],
        "residence": "上海市浦东新区陆家嘴滨江住宅区（高端公寓）",
        "career_identity": [
            "互联网公司产品设计师/UI设计师",
            "工作地点：浦东新区世纪大道1000号",
        ],
        "daily_behavior": [
            "通勤时间：07:00-09:00",
            "工作时间：09:00-18:00",
            "健身时间：18:00-20:00",
            "社交时间：20:00-24:00",
            "夜生活活跃",
        ],
        "personality_traits": [
            "外向开放",
            "注重自我投资",
            "追求品质生活",
            "社交活跃",
            "文艺气质",
            "独立自主",
        ],
        "interests_hobbies": [
            "独立音乐/民谣（网易云音乐）",
            "健身/瑜伽",
            "社交/夜生活",
            "购物/时尚",
            "旅行/摄影",
            "可能有宠物",
        ],
        "travel_pattern": [
            "通勤占约25%",
            "社交购物娱乐占约75%",
            "以个人享受为中心的都市生活方式",
        ],
        "vehicle_usage": [
            "空调温度均值25.2℃",
            "风量2.8档",
            "车控依赖度28%",
            "对舒适度较敏感",
        ],
        "media_preference": [
            "网易云音乐占比32%",
            "流行音乐、独立音乐",
            "常听艺人：陈粒、苏打绿、告五人、田馥甄、房东的猫",
        ],
    }

    user_profile_model = UserProfile.model_validate(user_profile)

    persona = nl_repr(user_profile)  # 将用户画像转换为自然语言描述

    # 对话场景
    scene_list = [
        "你正在和车机助手对话，你想过几天去北京旅游，想了解下最近几天的天气情况，北京的景点推荐及住宿和美食信息，你需要在5轮对话内完成这些信息的获取。",
        "你正在和车机助手对话，你想了解一下明天的天气情况，以及根据你的兴趣爱好推荐一些适合周末出行的活动和地点。你希望在5轮对话内获取这些信息。",
        "你正在和车机助手对话，你想调整一下车内的空调设置，让它更适合你的喜好。同时，你也想听一些符合你音乐口味的歌曲。你希望在5轮对话内完成这些操作。",
        "你正在和车机助手对话，你想了解一下附近的餐厅和娱乐活动，并根据你的兴趣爱好推荐一些适合的选择。你希望在5轮对话内获取这些信息。",
        "你正在和车机助手对话，你想了解一下最近的新闻和热点话题，并根据你的兴趣爱好推荐一些相关的文章和视频。你希望在5轮对话内获取这些信息。",
    ]

    # 用户的初始query
    query_list = [
        "明天天气怎么样？",
        "周末适合去哪里玩？",
        "帮我把空调调到我喜欢的设置，并放一些我喜欢的音乐。",
        "附近有什么好吃的餐厅和有趣的活动吗？",
        "最近有什么新闻和热点话题吗？",
    ]

    for scene, query in zip(scene_list, query_list):
        agent = await create_agent(user_profile_model)
        await auto_chat(
            agent=agent,  # Agent实例
            query=query,  # 用户的初始query，如果为空则由系统根据对话历史自动生成
            persona=persona,  # 用户画像的自然语言描述
            scene=scene,  # 对话场景描述
            turns=5,  # 自动对话的轮数
            writer_to_file=True,  # 是否将对话历史写入文件
        )


if __name__ == "__main__":
    asyncio.run(test_auto_chat())

# python -m aicore.agents.experiments.test_auto_chat
