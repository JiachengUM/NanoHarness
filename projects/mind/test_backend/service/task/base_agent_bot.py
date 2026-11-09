from typing import Any
from jinja2 import Template
from asgiref.sync import async_to_sync
import asyncio

from pydantic import BaseModel, Field
from aicore.utils.nl_repr.core import nl_repr_safe

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AnyBotToTest,
)
from projects.mind.test_backend.service.agent.react import get_tool_map

import asyncio
from aicore.agents.experiments.base import AgentBase, AgentDumpPayload
from aicore.agents.experiments.volc_memory_store import (
    SKILL_PROFILE_MEMORY_TYPE,
    abatch_clear_volc_memory_for_users,
)
from projects.mind.mem.volc_api import CollectionID
from projects.mind.mem.auto_test_script.auto_test_constants import (
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    MEMORY_TYPES,
    TEST_ASSISTANT_ID,
)

SKILL_PROFILE_TYPE = "skills"


class AgentDumpTrace(BaseModel):
    system_prompt: str | None
    session_id: str | None
    query: str | None
    answer: str | None
    traces: list[dict[str, Any]] | None = Field(default_factory=list)
    metadata: dict[str, Any] | None = Field(default_factory=dict)


def build_agent_config(context_config: dict[str, Any]):
    config_dict: dict[str, Any] = dict(context_config.get("task_config", {}))

    tool_name = context_config.get("tool_name") if context_config else None
    if tool_name:
        config_dict["tools_names"] = tool_name

    collection_name = context_config.get("collection_name") if context_config else None
    profile_types = context_config.get("profile_types") if context_config else None
    system_prompt_profile_types = (
        context_config.get("system_prompt_profile_types") if context_config else None
    )
    search_profile_types = (
        context_config.get("search_profile_types") if context_config else None
    )
    resolved_system_prompt_profile_types = (
        system_prompt_profile_types
        if system_prompt_profile_types is not None
        else profile_types
    )
    resolved_search_profile_types = (
        search_profile_types
        if search_profile_types is not None
        else [SKILL_PROFILE_TYPE]
    )
    profile_limit = context_config.get("profile_limit") if context_config else None
    user_id = context_config.get("user_id") if context_config else None
    assistant_id = context_config.get("assistant_id") if context_config else None

    try:
        if collection_name:
            config_dict["memory"]["consumer"]["config"]["collection_id"][
                "collection_name"
            ] = collection_name
            config_dict["memory"]["producer"]["config"]["collection_id"][
                "collection_name"
            ] = collection_name
        if resolved_system_prompt_profile_types is not None:
            config_dict["memory"]["consumer"]["config"][
                "system_prompt_profile_types"
            ] = resolved_system_prompt_profile_types
        if resolved_search_profile_types is not None:
            config_dict["memory"]["consumer"]["config"][
                "search_profile_types"
            ] = resolved_search_profile_types
        if profile_limit:
            config_dict["memory"]["consumer"]["config"]["profile_limit"] = profile_limit
        if user_id:
            config_dict["memory"]["user_info"]["user_id"] = user_id
        if assistant_id:
            config_dict["memory"]["user_info"]["assistant_id"] = assistant_id

    except Exception as e:
        print(f"更新memory collection_name失败: {e}")

    if isinstance(config_dict.get("system_prompt"), str):
        if not context_config.get("user_profile") and config_dict.get("user_profile"):
            context_config["user_profile"] = nl_repr_safe(config_dict["user_profile"])
        template = Template(config_dict["system_prompt"])
        system_prompt = template.render(**context_config)
        config_dict["system_prompt"] = system_prompt
        print(f"system_prompt: {system_prompt}")

    tool_map = get_tool_map()
    tools_names: list[str] = config_dict.get("tools_names", [])
    tools = {name: tool_map[name] for name in tools_names if name in tool_map}
    config_dict["tools_names"] = [name for name in tools_names if name in tools]

    return config_dict, tools


async def get_system_prompt_from_agent(agent: AgentBase) -> str | None:
    if agent is None or agent.state.run_result is None:
        return None

    history = await agent.state.run_result.response.ahistory(
        client=agent.run_params.client
    )

    system_prompt = None

    for item in history:
        d = item.model_dump()
        item_type = d.get("type")
        role = d.get("role")
        if item_type == "message" and role == "system":
            content_list = d.get("content", [])
            text = content_list[0].get("text", "") if content_list else ""
            system_prompt = text

    return system_prompt


class BaseAgentBot(AnyBotToTest):

    def __init__(self, context_config: dict[str, Any]):
        """初始化封装一个待测智能体"""
        self._context_config: dict[str, Any] = dict(context_config)
        self._system_prompt_template: str | None = None
        task_config = self._context_config.get("task_config", {})
        if isinstance(task_config, dict):
            system_prompt = task_config.get("system_prompt")
            if isinstance(system_prompt, str):
                self._system_prompt_template = system_prompt

        # 先构建 dict，全部修改完毕后再实例化 AgentDumpPayload
        config_dict, tools = build_agent_config(self._context_config)

        agent_config = AgentDumpPayload(**config_dict)
        self.agent = AgentBase.create(agent_config, tool_registry=tools)
        self.session_id = None
        self.query = None
        self.current_session_mock_time: str | None = None
        self.next_session_mock_time: str | None = None
        self._base_user_info = (
            self.agent.memory_producer.user_info if self.agent.memory_producer else None
        )

    def _refresh_system_prompt(self) -> None:
        """
        每轮按最新 context 重新渲染 system_prompt，确保 mock_info 生效。
        """
        if not self._system_prompt_template:
            return
        rendered = Template(self._system_prompt_template).render(**self._context_config)
        self.agent._system_prompt = rendered

    def _apply_mock_time_to_memory(self, mock_time: str | None) -> None:
        """
        通过 UserInfoMetadata 注入会话时间，不侵入 MemoryProducer 内部实现。
        """
        if not self._base_user_info or not self.agent.memory_producer:
            return
        user_info = self._base_user_info.with_mock_time(mock_time)
        self.agent.memory_producer.user_info = user_info
        if self.agent.memory_consumer:
            self.agent.memory_consumer.user_info = user_info

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        """
        更新每次多轮对话上下文：
        1) mock_time 用于下一次 new_session flush；
        2) 其他 mock_info 通过重渲染 system_prompt 生效。
        """
        self._context_config.update(context_config)
        self.next_session_mock_time = context_config.get("mock_time")
        self._refresh_system_prompt()

    async def achat(self, query: str, session_id: str) -> str:
        self.query = query
        is_first_session = self.session_id is None
        is_session_switch = (
            self.session_id is not None and self.session_id != session_id
        )
        if is_first_session or is_session_switch:
            if is_first_session:
                self.current_session_mock_time = self.next_session_mock_time
                self._apply_mock_time_to_memory(self.current_session_mock_time)
            if is_session_switch:
                # 先按上一个会话的 mock_time 刷盘，再切到新会话
                self._apply_mock_time_to_memory(self.current_session_mock_time)
                await self.agent.new_session()
                self.current_session_mock_time = self.next_session_mock_time
                self._apply_mock_time_to_memory(self.current_session_mock_time)
            self.session_id = session_id

        assert self.agent is not None

        # 内部异步函数不需要传 self
        async def run_agent() -> str:
            async for _ in self.agent.astream(query, event_listeners=[]):
                pass
            assert self.agent.state.run_result is not None, "run_result不能为None"
            return self.agent.state.run_result.response.raw_text

        # 统一用 async_to_sync，永不嵌套报错
        result = await run_agent()
        return result

    def chat(self, query: str, session_id: str) -> str:
        self.query = query
        return asyncio.run(self.achat(query, session_id))

    def dump_history(self) -> list[dict[str, str]]:
        return async_to_sync(self.adump_history)()

    async def adump_history(self) -> list[dict[str, str]]:
        assert self.agent is not None, "agent不能为None"
        assert self.agent.state.run_result is not None, "run_result不能为None"
        history = await self.agent.state.run_result.response.ahistory(
            client=self.agent.run_params.client
        )
        result: list[dict[str, str]] = []
        # TODO： 这里需要重新写下！用行业标准输出格式，先这样
        for item in history:
            d = item.model_dump()
            item_type = d.get("type")
            role = d.get("role")

            # message 类型：取 user/assistant
            if item_type == "message" and role in ("user", "assistant"):
                content_list = d.get("content", [])
                text = content_list[0].get("text", "") if content_list else ""
                result.append({"role": role, "content": text})

            # function_call 类型

            elif item_type == "function_call":
                result.append(
                    {
                        "role": "function_call",
                        "name": d.get("name", ""),
                        "arguments": d.get("arguments", ""),
                    }
                )
            elif item_type == "function_call_output":
                result.append(
                    {"role": "function_call_output", "content": d.get("output", "")}
                )

        return result

    @classmethod
    def create(cls, context_config: dict[str, Any]) -> "BaseAgentBot":
        return cls(context_config=context_config)

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        cfg = context_config or {}
        collection_name = cfg.get("collection_name", MEMORY_COLLECTION_NAME)
        assistant_id = cfg.get("assistant_id", TEST_ASSISTANT_ID)
        if not user_ids:
            return
        collection_id = CollectionID(collection_name=collection_name)
        if except_skills:
            profile_types_to_delete: list[str] = list(MEMORY_TYPES)
            for key in ("profile_types", "system_prompt_profile_types", "search_profile_types"):
                v = cfg.get(key)
                if isinstance(v, str):
                    profile_types_to_delete.append(v)
                elif isinstance(v, list):
                    profile_types_to_delete.extend(str(x) for x in v)
            seen: set[str] = set()
            deduped: list[str] = []
            for t in profile_types_to_delete:
                if t == SKILL_PROFILE_MEMORY_TYPE:
                    continue
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            cp_flag = bool(deduped)
            await abatch_clear_volc_memory_for_users(
                collection_id,
                user_ids,
                assistant_id,
                mode="by_type",
                clear_events=True,
                clear_profiles=cp_flag,
                event_types=None,
                profile_types=deduped if deduped else [],
            )
        else:
            await abatch_clear_volc_memory_for_users(
                collection_id,
                user_ids,
                assistant_id,
                mode="all",
            )
        await asyncio.sleep(1)

    async def adump_state_trace(self) -> dict:
        assert self.agent is not None, "agent不能为None"
        assert self.agent.state.run_result is not None, "run_result不能为None"
        events = [
            event.model_dump()
            for event in self.agent.state.run_result.events
            if event.type != "react.text.delta"
        ]  # 过滤掉增量事件，保持输出简洁
        session_id = self.session_id or ""
        system_prompt = await get_system_prompt_from_agent(self.agent)
        query = self.query or ""
        answer = "\n".join(
            [
                event.text
                for event in self.agent.state.run_result.events
                if event.type == "react.text.done"
            ]
        )

        trace = AgentDumpTrace(
            system_prompt=system_prompt,
            session_id=session_id,
            query=query,
            answer=answer,
            traces=events,
        )

        return trace.model_dump()
