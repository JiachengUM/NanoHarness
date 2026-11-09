"""
Agent V1 车载评测上下文构建（对齐原 ``demo_auto_test.create_params_payload`` 管线）。

此处为 **libraries** 层级代码：可被 ``auto_test_and_rl_data_generator`` / 服务端 task / demos 共用；
切勿从 ``auto_test_demos`` 反向 import——示例脚本只能依赖这里，不能反过来。
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from jinja2 import Template
from pydantic import BaseModel, Field

from aicore.agents.experiments.memory import (
    MemoryConsumerConfig,
    MemoryProducerConfig,
    UserInfoMetadata,
)
from aicore.models.credentials import ModelName
from projects.mind.mem.volc_api import CollectionID
from projects.mind.toolset import get_default_tools

from projects.mind.mem.auto_test_script.auto_test_constants import (
    DEFAULT_MEMORY_USER_ID,
    EVENT_MEMORY_LIMIT,
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    MEMORY_LIMIT,
    TEST_ASSISTANT_ID,
)
from projects.mind.mem.auto_test_script.default_jarvis_system_prompt_template import (
    DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
)

SKILL_PROFILE_TYPE = "skills"
DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES = ["steward_note_book"]

USER_PROFILE = """
40岁的非常有耐心的一个大哥。
"""

VEHICLE_STATE_PROMPT = """
        '当前系统时间': {{current_time}},
        '当前位置': '上海平金中心，经度121.357°，纬度31.134°',
        '车辆当前档位': 'P档（驻车档）',
        '车辆当前行驶速度': '0 km/h（静止状态）',
        '车内温度': '24摄氏度（舒适模式）',
        '车外温度': '20摄氏度',
        '车辆动力模式（新能源车/混动车专用）': '纯电模式',
        '动力电池电量百分比（新能源车必需）': '70%',
        '剩余续航里程（新能源车）': '510 km',
        '天窗状态': '已打开',
        '遮阳帘状态': '关闭',
        '空调开启状态及模式': '关闭中',
        '车内空气质量（智能车功能）': 'PM2.5 15μg/m³（优）',
        '中控屏幕状态（智能车重点）': '演示模式 - 智能座舱功能展示页面',
        '语音助手唤醒词': '唤醒词"你好小涂"',
        '四轮胎压监测': '左前2.3bar，右前2.3bar，左后2.2bar，右后2.2bar（正常）',
        '总里程数': '15 km（展车测试里程）',
        '车辆告警/故障信息': '无告警',
        '车辆展示模式（车展专用）': '演示模式已开启'"""


class create_params_payload(BaseModel):
    """车载评测默认 Bot 配置（与原 AgentWithMemoryToTest.create 对齐）。"""

    model_config = {"extra": "allow"}

    tool_name: list[str] = Field(default_factory=list)
    model_name: str = Field(default=ModelName.SEED_2_1_PRO_260628)
    system_prompt_template: str = Field(default=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE)
    thinking: bool = Field(default=True)
    user_profile: str = Field(default=USER_PROFILE)
    car_info: str = Field(default=VEHICLE_STATE_PROMPT)
    collection_name: str = Field(default=MEMORY_COLLECTION_NAME)
    profile_types: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES)
    )
    system_prompt_profile_types: list[str] | None = Field(
        default=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES
    )
    search_profile_types: list[str] | None = Field(default=None)
    event_types: list[str] | None = Field(default=[EVENT_MEMORY_TYPES])
    event_limit: int = Field(default=EVENT_MEMORY_LIMIT)
    profile_limit: int = Field(default=MEMORY_LIMIT)
    user_id: str = Field(default=DEFAULT_MEMORY_USER_ID)
    assistant_id: str = Field(default=TEST_ASSISTANT_ID)


def default_demo_bot_params() -> create_params_payload:
    """评测用 AgentV1Bot 默认参数（全量默认工具集 + steward_note_book + skills 检索画像）。"""
    chat_id = "auto_test_" + uuid.uuid4().hex
    return create_params_payload(
        tool_name=[tool.name for tool in get_default_tools(chat_id)],
        model_name=ModelName.SEED_2_1_PRO_260628,
        system_prompt_template=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
        user_profile=USER_PROFILE,
        car_info=VEHICLE_STATE_PROMPT,
        collection_name=MEMORY_COLLECTION_NAME,
        profile_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
        system_prompt_profile_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
        search_profile_types=[SKILL_PROFILE_TYPE],
        event_types=[EVENT_MEMORY_TYPES],
        event_limit=EVENT_MEMORY_LIMIT,
        profile_limit=MEMORY_LIMIT,
        user_id=DEFAULT_MEMORY_USER_ID,
        assistant_id=TEST_ASSISTANT_ID,
    )


def default_voice_test_bot_params() -> create_params_payload:
    """voice-test Agent V1 默认参数（贾维斯模板 + 默认工具，不含 skills 检索）。"""
    chat_id = "voice_test_default"
    return create_params_payload(
        tool_name=[tool.name for tool in get_default_tools(chat_id)],
        model_name=ModelName.SEED_2_1_PRO_260628,
        system_prompt_template=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
        thinking=False,
        user_profile="",
        car_info=VEHICLE_STATE_PROMPT,
        collection_name=MEMORY_COLLECTION_NAME,
        profile_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
        system_prompt_profile_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
        search_profile_types=list(DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES),
        event_types=[EVENT_MEMORY_TYPES],
        event_limit=EVENT_MEMORY_LIMIT,
        profile_limit=MEMORY_LIMIT,
        user_id=DEFAULT_MEMORY_USER_ID,
        assistant_id=TEST_ASSISTANT_ID,
    )


def build_voice_test_agent_v1_context(
    case_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """voice-test：构建 AgentV1 context_config；case 可覆盖 car_info / user_profile / mock_time。"""
    params = default_voice_test_bot_params()
    ctx = _build_agent_v1_task_context(params.model_dump(exclude_none=True), params)
    task_config = ctx["task_config"]
    task_config["run_params"]["max_turns"] = 5
    task_config["memory"]["producer"]["session_size"] = 5

    merged = dict(case_context or {})
    for key in ("user_profile", "car_info", "mock_time", "thinking", "user_id", "collection_name"):
        if merged.get(key) is not None:
            ctx[key] = merged[key]
    return canonicalize_v1_context_config(ctx)


def _resolve_tool_names(params: create_params_payload) -> list[str]:
    tool_map = {tool.name: tool for tool in get_default_tools("")}
    if params.tool_name:
        for name in params.tool_name:
            if name not in tool_map:
                raise ValueError(f"工具 {name} 不存在")
        return list(params.tool_name)
    return list(tool_map.keys())


def _build_agent_v1_task_context(
    merged: dict[str, Any],
    params: create_params_payload,
) -> dict[str, Any]:
    """
    将扁平 ``create_params_payload`` 转成 ``AgentV1Bot.build_agent_context`` 所需的
    ``context_config`` 形状（顶层字段 + ``task_config`` 树）。
    """
    event_types = list(params.event_types or [EVENT_MEMORY_TYPES])
    system_prompt_profile_types = (
        params.system_prompt_profile_types
        if params.system_prompt_profile_types is not None
        else list(params.profile_types)
    )
    search_profile_types = (
        list(params.search_profile_types)
        if params.search_profile_types is not None
        else [SKILL_PROFILE_TYPE]
    )
    user_info = UserInfoMetadata(
        user_id=params.user_id,
        assistant_id=params.assistant_id,
    )
    producer_config = MemoryProducerConfig(
        collection_id=CollectionID(collection_name=params.collection_name),
        memory_type=event_types + system_prompt_profile_types,
    )
    consumer_config = MemoryConsumerConfig(
        collection_id=CollectionID(collection_name=params.collection_name),
        system_prompt_profile_types=system_prompt_profile_types,
        search_profile_types=search_profile_types,
        event_types=event_types,
        profile_limit=params.profile_limit,
        event_limit=params.event_limit,
    )
    thinking_type = "enabled" if params.thinking else "disabled"
    car_info_rendered = Template(params.car_info).render(
        current_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    tool_names = _resolve_tool_names(params)
    task_config: dict[str, Any] = {
        "system_prompt": params.system_prompt_template,
        "run_params": {
            "model": params.model_name,
            "params": {"thinking": {"type": thinking_type}},
            "max_turns": 15,
        },
        "memory": {
            "user_info": user_info.model_dump(mode="json"),
            "producer": {
                "config": producer_config.model_dump(mode="json"),
                "session_size": 100,
            },
            "consumer": {
                "config": consumer_config.model_dump(mode="json"),
            },
        },
        "tools_names": tool_names,
    }
    flat_merged = {k: v for k, v in merged.items() if k != "task_config"}
    return {
        **flat_merged,
        "task_config": task_config,
        "tool_name": tool_names,
        "collection_name": params.collection_name,
        "profile_types": params.profile_types,
        "system_prompt_profile_types": system_prompt_profile_types,
        "search_profile_types": search_profile_types,
        "profile_limit": params.profile_limit,
        "user_id": params.user_id,
        "assistant_id": params.assistant_id,
        "user_profile": params.user_profile,
        "car_info": car_info_rendered,
        "thinking": params.thinking,
        "system_prompt_template": params.system_prompt_template,
    }


def canonicalize_v1_context_config(context_config: dict[str, Any]) -> dict[str, Any]:
    """把顶层 memory / tool 字段写入 task_config，统一为 AgentV1Bot 可读的一棵树。

    场景字段（user_profile / car_info / mock_time 等）保留在顶层，供 Jinja 渲染 system_prompt。
    Task 跑批、AutoTest、voice-test 等入口仍可能在顶层带 collection_name 等字段，在此归一化。
    """
    if not context_config:
        return {}
    ctx = dict(context_config)
    task_config = dict(ctx.get("task_config") or {})
    ctx["task_config"] = task_config

    tool_name = ctx.get("tool_name")
    if tool_name:
        task_config["tools_names"] = tool_name

    memory = task_config.get("memory")
    if not isinstance(memory, dict):
        return ctx

    consumer = memory.get("consumer")
    producer = memory.get("producer")
    if not isinstance(consumer, dict) or not isinstance(producer, dict):
        return ctx

    consumer_config = consumer.get("config")
    producer_config = producer.get("config")
    if not isinstance(consumer_config, dict) or not isinstance(producer_config, dict):
        return ctx

    collection_name = ctx.get("collection_name")
    if collection_name:
        for cfg in (consumer_config, producer_config):
            collection_id = cfg.setdefault("collection_id", {})
            if isinstance(collection_id, dict):
                collection_id["collection_name"] = collection_name

    profile_types = ctx.get("profile_types")
    system_prompt_profile_types = ctx.get("system_prompt_profile_types")
    search_profile_types = ctx.get("search_profile_types")

    if system_prompt_profile_types is not None:
        consumer_config["system_prompt_profile_types"] = system_prompt_profile_types
    elif profile_types is not None and "system_prompt_profile_types" not in consumer_config:
        consumer_config["system_prompt_profile_types"] = profile_types

    if search_profile_types is not None:
        consumer_config["search_profile_types"] = search_profile_types
    elif "search_profile_types" not in consumer_config:
        consumer_config["search_profile_types"] = [SKILL_PROFILE_TYPE]

    profile_limit = ctx.get("profile_limit")
    if profile_limit:
        consumer_config["profile_limit"] = profile_limit

    user_info = memory.get("user_info")
    if not isinstance(user_info, dict):
        user_info = {}
        memory["user_info"] = user_info

    user_id = ctx.get("user_id")
    if user_id:
        user_info["user_id"] = user_id
    assistant_id = ctx.get("assistant_id")
    if assistant_id:
        user_info["assistant_id"] = assistant_id

    return ctx
