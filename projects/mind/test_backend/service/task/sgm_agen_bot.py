from typing import Any
from jinja2 import Template
import asyncio
import uuid
from tqdm import tqdm
from aicore.agents.experiments.memory import (
    MemoryConsumer,
    MemoryConsumerConfig,
    MemoryProducer,
    MemoryProducerConfig,
    UserInfoMetadata,
)
from aicore.utils.nl_repr.core import nl_repr_safe
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import AnyBotToTest
from projects.mind.test_backend.service.task.base_agent_bot import get_system_prompt_from_agent
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
from projects.sgm_prod.core import AgentDoStreamRequest, SGMAgent, StreamChunk

SKILL_PROFILE_TYPE = "skills"


def build_agent_config(context_config: dict[str, Any]):
    config_dict = context_config.get("task_config", {})

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

    memory_consumer = None
    memory_producer = None

    try:
        if collection_name:
            config_dict["memory"]["consumer"]["config"]["collection_id"][
                "collection_name"
            ] = collection_name
            config_dict["memory"]["producer"]["config"]["collection_id"][
                "collection_name"
            ] = collection_name
        if resolved_system_prompt_profile_types is not None:
            config_dict["memory"]["consumer"]["config"]["system_prompt_profile_types"] = resolved_system_prompt_profile_types
        if resolved_search_profile_types is not None:
            config_dict["memory"]["consumer"]["config"]["search_profile_types"] = resolved_search_profile_types
        if profile_limit:
            config_dict["memory"]["consumer"]["config"]["profile_limit"] = profile_limit
        if user_id:
            config_dict["memory"]["user_info"]["user_id"] = user_id
        if assistant_id:
            config_dict["memory"]["user_info"]["assistant_id"] = assistant_id

        memory_producer = MemoryProducer(
            config=MemoryProducerConfig(**config_dict["memory"]["producer"]["config"]),
            user_info=UserInfoMetadata(**config_dict["memory"]["user_info"]),
            session_size=config_dict["memory"]["producer"]["session_size"]
        )

        memory_consumer = MemoryConsumer(
            config=MemoryConsumerConfig(**config_dict["memory"]["consumer"]["config"]),
            user_info=UserInfoMetadata(**config_dict["memory"]["user_info"]),
        )

        print(f"memory_producer: {memory_producer.config.model_dump()}")
        print(f"memory_consumer: {memory_consumer.config.model_dump()}")

    except Exception as e:
        print(f"更新memory collection_name失败: {e}")

    # 渲染 system_prompt（task_config.system_prompt 是 Jinja2 模板字符串）
    system_prompt: str | None = config_dict.get("system_prompt")
    if isinstance(system_prompt, str):
        user_profile = config_dict.get("user_profile")
        car_info = config_dict.get("car_info")
        if not context_config.get("user_profile") and user_profile:
            context_config["user_profile"] = nl_repr_safe(user_profile)
        if not context_config.get("car_info") and car_info:
            context_config["car_info"] = nl_repr_safe(car_info)
        system_prompt = Template(system_prompt).render(**context_config)
        print(f"system_prompt: {system_prompt}")

    chat_id = f"sgm_test_{uuid.uuid4().hex[:8]}"

    return {
        "chat_id": chat_id,
        "system_prompt": system_prompt,
        "memory_producer": memory_producer,
        "memory_consumer": memory_consumer,
    }


class SGMAgentBot(AnyBotToTest):

    def __init__(self, context_config: dict[str, Any]):
        """初始化封装一个待测 SGM 智能体"""
        self._context_config: dict[str, Any] = dict(context_config)
        self._system_prompt_template: str | None = None
        task_config = self._context_config.get("task_config", {})
        if isinstance(task_config, dict):
            system_prompt = task_config.get("system_prompt")
            if isinstance(system_prompt, str):
                self._system_prompt_template = system_prompt

        config = build_agent_config(self._context_config)
        print(f"sgm_agent chat_id:{config["chat_id"]}")
        self.agent = SGMAgent.build(**config)
        self._chat_id = config["chat_id"]
        # self._context_config = context_config
        self.session_id: str | None = None
        self.current_session_mock_time: str | None = None
        self.next_session_mock_time: str | None = None
        self._base_user_info = (
            self.agent.memory_producer.user_info if self.agent.memory_producer else None
        )
        self._last_chunks: list[StreamChunk] = []

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
        is_first_session = self.session_id is None
        is_session_switch = (
            self.session_id is not None and self.session_id != session_id
        )
        if is_first_session or is_session_switch:
            if is_first_session:
                self.current_session_mock_time = self.next_session_mock_time
                self._apply_mock_time_to_memory(self.current_session_mock_time)
            if is_session_switch:
                self._apply_mock_time_to_memory(self.current_session_mock_time)
                await self.agent.new_session()
                self.current_session_mock_time = self.next_session_mock_time
                self._apply_mock_time_to_memory(self.current_session_mock_time)
                wait_seconds = 15
                print(f"多次多轮对话之间间隔...{wait_seconds}秒")
                # 异步等待记忆抽取生效，增加异步tqdm进度条
                for _ in tqdm(range(wait_seconds), desc="倒计时", unit="秒", ncols=75):
                    await asyncio.sleep(1)
                print("等待间隔时间到！")
            self.session_id = session_id

        assert self.agent is not None

        req = AgentDoStreamRequest(
            chat_id=self._chat_id,
            question_id=session_id,
            query=query,
            intent_type="复杂推理"
        )

        chunks: list[StreamChunk] = []
        content = ""
        async for chunk in self.agent.astream_chunks(req):
            if chunk.content:
                print(chunk.content, end="")
            if chunk.observation or chunk.debug_info:
                print(f"observation: {chunk}")

            chunks.append(chunk)
            if chunk.content:
                content += chunk.content

        self._last_chunks.extend(chunks)
        return content

    def chat(self, query: str, session_id: str) -> str:
        return asyncio.run(self.achat(query, session_id))

    async def adump_history(self) -> list[dict[str, str]]:
        assert self.agent is not None, "agent不能为None"
        assert self.agent.state.run_result is not None, "run_result不能为None"
        history = await self.agent.state.run_result.response.ahistory(
            client=self.agent.run_params.client
        )
        result: list[dict[str, str]] = []
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

    def dump_history(self) -> list[dict[str, str]]:
        return asyncio.run(self.adump_history())

    @classmethod
    def create(cls, context_config: dict[str, Any]) -> "SGMAgentBot":
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
        trace = self.agent.state.run_result
        trace.events = [event for event in trace.events if event.type != "react.text.delta"] # 过滤掉增量事件，保持输出简洁
        trace = trace.model_dump()
        trace["system_prompt"] = await get_system_prompt_from_agent(self.agent)

        return trace
