import random
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import json

from jinja2 import Template
from pydantic import BaseModel
from aicore.agents.experiments.memory import (
    MemoryConsumer,
    MemoryProducer,
)
from aicore.models.chat.params import ChatParams
from aicore.models.chat.streaming import astream
from aicore.models.credentials import create_client, AsyncArk, ModelName
from aicore.models.model_api import ModelParams, ModelCallParams
from aicore.v1.experiments.agent import Agent, AgentContext, AgentState
from projects.mind.complex_reasoning.task_data.chat_history import (
    AgentChatSession,
    AgentHumanChatMessage,
    AgentAIChatMessage,
    AgentV1DumpPayload,
    ErrorEvent,
    HumanMessageEvent,
)
from projects.mind.complex_reasoning.task_mdb_models.chat_history import (
    AgentChatSessionDBSchema,
)
from projects.mind.complex_reasoning.task_schemas.chat_history import (
    AgentChatSessionCreate,
)
from projects.mind.toolset import get_default_tools, get_prompt
from projects.mind.intent.repositories import mdb_api
from projects.mind.test_backend.schemas.agent.react import (
    AgentMemoryResponse,
    MemoryConfig,
    ReActAgentAutoChatRequest,
    ReActAgentConfig,
    ReActAgentRequest,
)
from aicore.agents.experiments.base import (
    AgentBase,
    AgentDumpPayload,
    RunParams,
    SystemPrompt,
)

_SESSION_TTL = 3600  # 1小时无访问则销毁

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

HINTS_QUERY_TEMPLATE = Template(
    """
人设信息：
{{ user_profile }}

对话场景：
{{ chat_scene }}

对话记录：
{{ history }}
"""
)


@dataclass
class _SessionEntry:
    agent: Agent | AgentBase
    last_access: float = field(default_factory=time.time)


_base_agent_sessions: dict[str, _SessionEntry] = {}


def _cleanup_expired_sessions() -> None:
    """清理超过 TTL 的过期 session"""
    now = time.time()
    expired = [
        sid
        for sid, entry in _base_agent_sessions.items()
        if now - entry.last_access > _SESSION_TTL
    ]
    for sid in expired:
        del _base_agent_sessions[sid]


__all__ = ["get_tool_map"]


def get_tool_map():
    """获取所有Tools的map映射"""
    tools = get_default_tools(chat_id="")

    return {tool.name: tool for tool in tools}


def get_system_prompt() -> SystemPrompt:
    return get_prompt()


def format_step(
    step: Any,
) -> dict:
    """
    格式化Agent执行步骤，区分模型响应、工具调用和工具结果
    """

    if step is None:
        return {"type": "none", "content": ""}

    elif isinstance(step, BaseModel):
        type = getattr(step, "type", "unknown model")

        try:
            return {"type": type, "content": step.model_dump()}
        except:
            return {"type": type, "content": str(step)}
    else:
        return {"type": "unknown", "content": str(step)}


def new_format_step(
    step: Any,
) -> dict:
    """
    格式化Agent执行步骤，区分模型响应、工具调用和工具结果
    """

    if step is None:
        return {"type": "none", "content": ""}

    elif isinstance(step, BaseModel):
        type = getattr(step, "type", "unknown model")

        try:
            return {"type": type, "content": step.model_dump()}
        except:
            return {"type": type, "content": str(step)}
    else:
        return {"type": "unknown", "content": str(step)}


def generate_memory(
    memory_config: MemoryConfig | None,
) -> tuple[MemoryProducer | None, MemoryConsumer | None]:
    if not memory_config:
        return None, None

    memory_producer = MemoryProducer(
        memory_config.producer_config,
        memory_config.user_info,
        session_size=memory_config.session_size,
    )

    memory_consumer = MemoryConsumer(
        memory_config.consumer_config, memory_config.user_info
    )

    return memory_producer, memory_consumer


def resolve_model_name(model_input: str) -> ModelName:
    """支持枚举 key 或 value"""
    # 1. 尝试作为 key
    try:
        return ModelName[model_input]
    except KeyError:
        pass

    # 2. 尝试作为 value
    try:
        return ModelName(model_input)
    except ValueError:
        pass

    # 3. 都不匹配，抛出清晰的错误
    raise ValueError(
        f"Invalid model name: '{model_input}'. "
        f"Valid keys: {list(ModelName.__members__.keys())}, "
        f"Valid values: {[m.value for m in ModelName]}"
    )


def generate_base_agent(
    config: ReActAgentConfig, chat_session: AgentChatSession | None = None
) -> AgentBase:
    """根据配置动态生成或复用 AgentBase 实例。

    若传入 session_id，则优先复用已存在会话的 agent；
    超过 TTL（1小时未访问）的 session 会在每次调用时被清理。
    """
    _cleanup_expired_sessions()

    # 优先复用已有会话的 agent 实例
    if (
        chat_session
        and chat_session.session_id
        and chat_session.session_id in _base_agent_sessions
    ):
        entry = _base_agent_sessions[chat_session.session_id]
        if isinstance(entry.agent, AgentBase):
            entry.last_access = time.time()
            print(f"Reusing existing agent for session {chat_session.session_id}")
            return entry.agent

    agent = None

    if (
        chat_session
        and chat_session.agent_instance_dump
        and isinstance(chat_session.agent_instance_dump, AgentDumpPayload)
    ):
        # 从会话的 agent_instance_dump 中恢复 agent 实例
        try:
            tools_names = chat_session.agent_instance_dump.tools_names
            tools = {name: get_tool_map()[name] for name in tools_names}
            agent = AgentBase.create(
                chat_session.agent_instance_dump, tool_registry=tools
            )
            print(f"Restored agent from dump for session {chat_session.session_id}")
        except Exception as e:
            print(f"Failed to restore agent from dump: {e}")

    if not agent:
        # 根据配置创建新agent实例
        memory_producer, memory_consumer = generate_memory(config.memory_config)
        model_name = resolve_model_name(config.model)
        client, model = create_client(model_name, AsyncArk)
        tool_map = get_tool_map()
        tools = [tool_map[name] for name in config.tools if name in tool_map]
        run_params = RunParams(
            model=model,
            params=config.params,
            max_turns=config.max_turns,
        )

        agent = AgentBase(
            config.system_prompt or get_system_prompt(),
            run_params=run_params,
            tools=tools,
            memory_producer=memory_producer,
            memory_consumer=memory_consumer,
            user_profile=config.user_profile,
        )
        session_label = (
            chat_session.session_id
            if chat_session and chat_session.session_id
            else "N/A"
        )
        print(f"Created new agent for session {session_label}")

    if chat_session and chat_session.session_id:
        # 保存agent实例到会话映射
        _base_agent_sessions[chat_session.session_id] = _SessionEntry(agent=agent)

    return agent


def generate_agent_v1(
    config: ReActAgentConfig,
    chat_session: AgentChatSession | None = None,
    session_id: str | None = None,
) -> Agent:
    """根据配置动态生成或复用 v1 Agent 实例。"""
    _cleanup_expired_sessions()

    sid = (
        chat_session.session_id
        if (chat_session and chat_session.session_id)
        else session_id
    )

    if sid and sid in _base_agent_sessions:
        entry = _base_agent_sessions[sid]
        if isinstance(entry.agent, Agent):
            entry.last_access = time.time()
            print(f"Reusing existing v1 agent for session {sid}")
            return entry.agent

    agent: Agent | None = None
    tool_map = get_tool_map()

    if chat_session and chat_session.agent_instance_dump:
        try:
            dump_obj = chat_session.agent_instance_dump
            dump_data: Any
            if isinstance(dump_obj, BaseModel):
                dump_data = dump_obj.model_dump(mode="json")
            else:
                dump_data = dump_obj

            if (
                isinstance(dump_data, dict)
                and "context" in dump_data
                and "state" in dump_data
            ):
                context = AgentContext.model_validate(dump_data["context"])
                state = AgentState.model_validate(dump_data["state"])
                if context.tool_defs:
                    context.tools = [
                        tool_map[t.name]
                        for t in context.tool_defs
                        if t.name in tool_map
                    ]
                agent = Agent(context, state=state)
                print(
                    f"Restored v1 agent from dump for session {chat_session.session_id}"
                )
        except Exception as e:
            print(f"Failed to restore v1 agent from dump: {e}")

    if not agent:
        model_name = resolve_model_name(config.model)
        _, model = create_client(model_name, AsyncArk)
        tools = [tool_map[name] for name in config.tools if name in tool_map]

        model_params_kwargs: dict[str, Any] = {"model": model}
        if config.params is not None:
            cp = config.params
            model_params_kwargs["params"] = ModelCallParams(
                temperature=cp.temperature,
                top_p=cp.top_p,
                max_output_tokens=cp.max_output_tokens,
                thinking=cp.thinking,
            )

        memory_user_info = None
        memory_producer_config = None
        memory_consumer_config = None
        memory_producer_session_size = 1
        if config.memory_config:
            memory_user_info = config.memory_config.user_info
            memory_producer_config = config.memory_config.producer_config
            memory_consumer_config = config.memory_config.consumer_config
            memory_producer_session_size = config.memory_config.session_size

        system_prompt_text: str
        if isinstance(config.system_prompt, str):
            system_prompt_text = config.system_prompt
        elif config.system_prompt is None:
            system_prompt_text = "你是友好的用户智能助手"
        else:
            system_prompt_text = str(config.system_prompt)

        context = AgentContext(
            system_prompt=system_prompt_text,
            model_params=ModelParams(**model_params_kwargs),
            react_max_turns=config.max_turns,
            tools=tools,
            memory_user_info=memory_user_info,
            memory_producer_config=memory_producer_config,
            memory_producer_session_size=memory_producer_session_size,
            memory_consumer_config=memory_consumer_config,
            user_profile=config.user_profile,
        )
        agent = Agent(context)
        print(
            f"Created new v1 agent for session {chat_session.session_id if chat_session and chat_session.session_id else 'N/A'}"
        )

    if sid:
        _base_agent_sessions[sid] = _SessionEntry(agent=agent)

    return agent


async def run_base_agent_stream(
    payload: ReActAgentRequest,
) -> AsyncGenerator[str, None]:
    """SSE流式返回Base Agent执行步骤"""

    session_id = payload.session_id  # 当前会话Id
    save_to_db = payload.save_to_db

    current_session = None
    if save_to_db:
        docs = await mdb_api.get_list(
            AgentChatSessionDBSchema, query={"session_id": session_id}
        )

        current_session = docs[0] if docs else None

        if not current_session:  # 第一轮会话，创建会话记录
            session_title = (
                payload.query[:20] + "..." if len(payload.query) > 20 else payload.query
            )
            current_session_create = AgentChatSessionCreate(
                title=session_title,
                session_id=session_id,
                agent_instance_dump=None,
                creator=payload.creator,
            )

            current_session = await mdb_api.create(
                AgentChatSessionDBSchema, current_session_create
            )

        human_msg = AgentHumanChatMessage(content=payload.query)
        current_session.messages.append(human_msg)

    agent = generate_agent_v1(
        payload.config, chat_session=current_session, session_id=session_id
    )

    ai_msg = AgentAIChatMessage(content="", events=[], human_evaluation=None)
    if ai_msg.events is None:
        ai_msg.events = []

    try:
        async for step in agent.astream(payload.query):
            event_str = f"data: {json.dumps(step.model_dump(mode='json') if isinstance(step, BaseModel) else step, ensure_ascii=False)}\n\n"

            if step.type != "react.text.delta":
                ai_msg.events.append(step)

            if step.type == "react.text.done":
                ai_msg.content = step.text

            yield event_str

    except Exception as e:
        print(f"Error during agent execution: {e}")
        event = ErrorEvent(type="error", reason=f"Error during agent execution: {e}")
        ai_msg.events.append(event)
        yield f"data: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"

    if save_to_db:
        try:
            context, state = await agent.dump()

            current_session.agent_instance_dump = AgentV1DumpPayload(
                context=context,
                state=state,
            )
        except Exception as e:
            print(f"Failed to dump agent: {e}")
            event = ErrorEvent(type="error", reason=f"Failed to dump agent: {e}")
            ai_msg.events.append(event)
            yield f"data: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"

        try:
            # 最终保存完整的会话历史
            current_session.messages.append(ai_msg)
            await mdb_api.update(AgentChatSessionDBSchema, current_session)
        except Exception as e:
            print(f"Failed to save session: {e}")
            event = ErrorEvent(type="error", reason=f"Failed to save session: {e}")
            yield f"data: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"


async def run_base_agent_stream_auto_chat(
    payload: ReActAgentAutoChatRequest,
) -> AsyncGenerator[str, None]:
    """SSE流式返回Base Agent执行步骤(自动对话)"""

    auto_chat_config = payload.auto_chat_config
    chat_turns = auto_chat_config.chat_turns

    while True:
        async for chunk in run_base_agent_stream(payload):
            yield chunk

        chat_turns -= 1
        if chat_turns <= 0:
            return

        entry = _base_agent_sessions[payload.session_id]

        if not entry:
            return

        hints_query = HINTS_QUERY_TEMPLATE.render(
            user_profile=auto_chat_config.user_profile,
            chat_scene=auto_chat_config.chat_scene,
            history=get_agent_message_history(entry.agent),
        )

        hints = await generate_hints(hints_query)

        if not hints:
            return

        query = random.choice(hints).get("content", "")
        if not query:
            return
        payload.query = query

        event = HumanMessageEvent(content=query)
        yield f"data: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"


def get_agent_message_history(agent: Agent | AgentBase) -> list:
    """
    获取agent的消息历史，并将其转换为字典列表格式。
    """

    if not agent:
        return []

    if isinstance(agent, Agent):
        if agent.state.response is None:
            return []
        return [
            message.model_dump()
            for message_tuple in agent.state.response.message_history
            for message in message_tuple
        ]

    if agent.state.run_result is None:
        return []
    return [
        message.model_dump()
        for message_tuple in agent.state.run_result.response.message_history
        for message in message_tuple
    ]


async def generate_hints(query: str) -> list[dict[str, Any]]:
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


async def retrieve_memory(session_id: str) -> AgentMemoryResponse:
    """Agent记忆召回结果"""

    docs = await mdb_api.get_list(
        AgentChatSessionDBSchema, query={"session_id": session_id}
    )

    current_session = docs[0] if docs else None

    if not current_session:
        return AgentMemoryResponse(profiles=None, events=None)

    dump_obj = current_session.agent_instance_dump or {}
    dump: dict[str, Any]
    if isinstance(dump_obj, BaseModel):
        dump = dump_obj.model_dump(mode="json")
    elif isinstance(dump_obj, dict):
        dump = dump_obj
    else:
        dump = {}

    # v1 dump: {"context": ..., "state": ...}
    if "context" in dump:
        context_raw = dump.get("context", {})
        model_params_raw = context_raw.get("model_params", {})
        tool_defs = context_raw.get("tool_defs", []) or []

        memory_user_info = context_raw.get("memory_user_info")
        memory_producer_config = context_raw.get("memory_producer_config")
        memory_consumer_config = context_raw.get("memory_consumer_config")
        memory_session_size = context_raw.get("memory_producer_session_size", 5)

        if not memory_consumer_config or not memory_user_info:
            return AgentMemoryResponse(profiles=None, events=None)

        config = ReActAgentConfig(
            model=model_params_raw.get("model"),
            params=model_params_raw.get("params"),
            tools=[t.get("name") for t in tool_defs if t.get("name")],
            max_turns=context_raw.get("react_max_turns", 5),
            system_prompt=context_raw.get("system_prompt"),
            memory_config=MemoryConfig(
                user_info=memory_user_info,
                producer_config=memory_producer_config,
                consumer_config=memory_consumer_config,
                session_size=memory_session_size,
            ),
            user_profile=context_raw.get("user_profile"),
        )

        agent = generate_agent_v1(config, chat_session=current_session)
        if not agent.memory_consumer:
            return AgentMemoryResponse(profiles=None, events=None)
        profiles = await agent.memory_consumer.retrieve_profiles()
        events_response = await agent.memory_consumer.retrieve_events()
        return AgentMemoryResponse(profiles=profiles, events=events_response)

    run_params_raw = dump.get("run_params", {})
    producer_raw = dump.get("memory_producer")
    consumer_raw = dump.get("memory_consumer")

    memory_config = None
    if producer_raw or consumer_raw:
        user_info = (
            dump.get("memory", {}).get("user_info")
            if isinstance(dump.get("memory"), dict)
            else None
        )
        producer_config = (
            producer_raw.get("config") if isinstance(producer_raw, dict) else None
        )
        consumer_config = (
            consumer_raw.get("config") if isinstance(consumer_raw, dict) else None
        )
        session_size = (
            producer_raw.get("session_size", 5) if isinstance(producer_raw, dict) else 5
        )
        if not user_info or not producer_config or not consumer_config:
            return AgentMemoryResponse(profiles=None, events=None)
        memory_config = MemoryConfig(
            user_info=user_info,
            producer_config=producer_config,
            consumer_config=consumer_config,
            session_size=session_size,
        )

    config = ReActAgentConfig(
        model=run_params_raw.get("model"),
        params=run_params_raw.get("params"),
        tools=dump.get("tools_names") or [],
        max_turns=run_params_raw.get("max_turns", 5),
        system_prompt=dump.get("system_prompt"),
        memory_config=memory_config,
        user_profile=dump.get("user_profile"),
    )

    if not consumer_raw:
        return AgentMemoryResponse(profiles=None, events=None)

    agent = generate_base_agent(config, chat_session=current_session)

    profiles = await agent.retrieve_profiles()
    events_response = await agent.retrieve_events()

    return AgentMemoryResponse(profiles=profiles, events=events_response)


if __name__ == "__main__":
    # test run_base_agent_stream
    from aicore.models.responses.params import ResponseParams
    import asyncio

    payload = ReActAgentRequest(
        config=ReActAgentConfig(
            model="SEED_1_8_251228",
            tools=["weather_agent"],
            params=None,
            system_prompt="你是友好的用户智能助手",
            memory_config=None,
            user_profile=None,
        ),
        session_id="test",
        query="北京今天天气怎么样",
    )

    # 异步调用run_base_agent_stream
    async def test_run_base_agent_stream():
        async for chunk in run_base_agent_stream(payload):
            print(chunk)

    asyncio.run(test_run_base_agent_stream())
