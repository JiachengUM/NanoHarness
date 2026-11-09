"""
复杂推理注入记忆内容的测试模块
"""
import asyncio
from datetime import datetime
from typing import Any

from rich import print
from jinja2 import Template
import time

from projects.mind.mem.benchi_demo.prompt import PLANNER_PROMPT, VEHICLE_STATE_PROMPT
from nanoai.model.llm import allm, AsyncOpenAI
from nanoai.model.config import ModelName, create_client
from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.async_utils import amap, with_param_parse_async
from projects.mind.mem.volc_api import (
    Message,
    add_session,
    SessionCreate,
    SessionMetadata,
    SearchMemory,
    MemoryFilter,
    search_memory,
    msg_to_volc_format,
)


MODEL_NAME = ModelName.DOUBAO_SEED_1_8_PREVIEW
# 模型默认配置
DEFAULT_LLM_PARAMS: dict[str, Any] = {
    "stream": False,
    "temperature": 0.01,
    "max_tokens": 8192,
}

# 记忆检索配置
MEMORY_COLLECTION_NAME = "SGM"
# MEMORY_TYPES = ["profile_v1", "profile_device_v1", "profile_location_v1", "profile_music_v1", "steward_note_book"]
MEMORY_TYPES = ["steward_note_book"]
MEMORY_USER_ID = "user_889"
MEMORY_LIMIT = 10

# mock的
FAKE_RESTURANT_INFO_LIST_1 = [
    {"name": "甬府", "type": "餐厅", "location": "前滩","rating": "4.5星", "price_per_person": "800"},
    {"name": "弄堂排骨年糕", "type": "餐厅", "location": "前滩","rating": "4.0星", "price_per_person": "15"},
]

FAKE_RESTURANT_INFO_LIST_2 = [
    {"name": "大志烤肉", "type": "餐厅", "location": "外滩","rating": "4.5星", "price_per_person": "200"},
    {"name": "兰州拉面", "type": "餐厅", "location": "外滩","rating": "4.0星", "price_per_person": "20"},
]

CASE1 ={
    "query": "回家",
    # 该id已经有记忆
    "user_id": "user_01",
}

CASE2 ={
    "query": "回家",
    "background_conversation": [
        Message(role="user", content="我搬家了，搬到了前滩。"),
        Message(role="assistant", content="好的主人，我记下了。"),
    ],
    "user_id": "user_01",
}

CASE3 ={
    "query": "饿了，给我推荐一个附近的餐厅",
    "background_conversation": [
        Message(role="user", content="饿了，给我推荐一个附近的餐厅"),
        Message(role="assistant", content="好的稍等我找一下。"),
        # Message(role="tool", content=str(FAKE_RESTURANT_INFO_LIST_1)),
        Message(role="assistant", content="给你推荐一家评价很高的餐厅甬府，是精品宁波菜，人均800，怎么样？"),
        Message(role="user", content="妈呀你当我是富二代啊？这么贵！"),
        Message(role="assistant", content="好的明白了，那我推荐附近一家弄堂排骨年糕，15块就能填饱肚子。"),
        Message(role="user", content="好的"),
    ],
    "user_id": MEMORY_USER_ID,
}

CASE4 ={
    "query": "帮我放上次我放的那首歌",
    # 该id有音乐偏好记忆
    "user_id": "user_01",
}


async def add_to_memory(
    conversation: list[Message],
    /,
    *,
    collection_name: str = MEMORY_COLLECTION_NAME,
    user_id: str,
    default_assistant_id: str = "小途助手",
    session_id: str | None = None,
    ) -> None:
    """将对话添加到记忆库"""

    msgs = msg_to_volc_format(conversation)
    
    session=SessionCreate(
        collection_name=collection_name,
        session_id=session_id,
        messages=msgs,
        metadata=SessionMetadata(
            default_user_id=user_id,
            default_assistant_id=default_assistant_id,
            time=int(time.time() * 1000),
        )
    )
    
    # 将同步的 add_session 调用放到线程池中执行，避免阻塞事件循环
    await asyncio.to_thread(add_session, session=session)

# async def test_steward(
#     query: str,
#     user_id: str,
#     use_memory: bool = True,
#     model: str = MODEL_NAME,
#     llm_params: dict[str, Any] | None = None
# ) -> str:

async def test_complex_reasoning_memory(
    query: str,
    user_id: str,
    use_memory: bool = True,
    model: str = MODEL_NAME,
    llm_params: dict[str, Any] | None = None
) -> str:
    """
    测试复杂推理注入记忆内容函数，返回复杂推理结果。

    Args:
        query: 用户查询语句（位置参数，强制前置）
        user_id: 根据用户ID检索记忆
        use_memory: 是否使用用户记忆，默认True
        model: 调用的LLM模型名称/枚举
        llm_params: LLM调用参数，默认使用DEFAULT_LLM_PARAMS

    Returns:
        str: LLM返回的复杂推理结果
    """

    # 渲染车辆状态
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vehicle_state = Template(VEHICLE_STATE_PROMPT).render(current_time=current_time)

    memory_str: str = ""
    if use_memory:
        # 构建并执行记忆检索
        search_request = SearchMemory(
            collection_name=MEMORY_COLLECTION_NAME,
            query=query,
            limit=MEMORY_LIMIT,
            filter=MemoryFilter(memory_type=MEMORY_TYPES, user_id=user_id)
        )
        # 将同步的 search_memory 调用放到线程池中执行，避免阻塞事件循环
        memory = await asyncio.to_thread(search_memory, search_request)
        print("*" * 80)
        print(f"用户原始记忆\n{memory}")
        
        memory_str = nl_repr([item.memory_info for item in memory.data.result_list])
    else:
        memory_str = "无记忆"

    prompt = Template(PLANNER_PROMPT).render(
        memory=memory_str,
        car_state=vehicle_state,
    )
    
    client, model = create_client(model, client_class=AsyncOpenAI)
    llm_params = llm_params or {}

    response = await allm(
        query,
        prompt,
        model=model,
        client=client,
        **llm_params
    )
    return response.output


async def test_complex_reasoning_memory_compare(case: dict[str, Any]) -> None:
    """
    同时对一个query，一个开启记忆，一个不开启记忆，进行对比
    """
    query = case["query"]
    user_id = case["user_id"]
    # 如果有背景对话，则添加记忆，否则直接去调用模型
    if "background_conversation" in case:
        background_conversation = case["background_conversation"]
        # 等待 add_to_memory 完成
        # 本质上此处的memory是模拟过往对话生成的长时记忆，因为短时记忆是可以通过将对话历史直接塞入模型即可实现
        await add_to_memory(background_conversation, user_id=user_id)
        print(f"[记忆] 背景对话添加记忆成功，等待20秒生效")
        # 使用异步 sleep，避免阻塞事件循环，但保证等待20秒
        await asyncio.sleep(20)
    else:
        print(f"[记忆] 没有背景对话，直接调用模型")
    print("*" * 80)
    wrapped_func = with_param_parse_async(test_complex_reasoning_memory)
    params = [
        (query, user_id, True),
        (query, user_id, False)
    ]
    responses, _ = await amap(wrapped_func, params)
    print("*" * 80)
    print(f"查询语句\n[red]{query}[/red]")
    print("*" * 80)
    print(f"开启记忆的输出结果\n{responses[0]}")
    print("*" * 80)
    print(f"不开启记忆的输出结果\n{responses[1]}")

async def main() -> None:

    # await test_complex_reasoning_memory_compare(CASE1)
    await test_complex_reasoning_memory_compare(CASE2)
    # await test_complex_reasoning_memory_compare(CASE3)
    # await test_complex_reasoning_memory_compare(CASE4)

if __name__ == "__main__":
    asyncio.run(main())