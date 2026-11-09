from typing import Any
from jinja2 import Template
from asgiref.sync import async_to_sync
import asyncio
import json
from collections import defaultdict

from tqdm.asyncio import tqdm
from aicore.utils.nl_repr.core import nl_repr_safe
from aicore.utils.nl_repr import nl_repr

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AnyBotToTest,
    is_auto_test_bot_console_suppressed,
)
from projects.mind.test_backend.service.agent.react import get_tool_map

from aicore.v1.experiments.agent import Agent, AgentContext
from aicore.models.model_api import ModelCallParams, ModelParams
from aicore.models.model_api.types import SystemMessage
from projects.mind.test_backend.service.task.base_agent_bot import AgentDumpTrace
from aicore.agents.experiments.volc_memory_store import (
    SKILL_PROFILE_MEMORY_TYPE,
    abatch_clear_volc_memory_for_users,
)
from projects.voice_test.schemas.browser_schemas import CountdownWaitEvent
from projects.mind.mem.volc_api import CollectionID
from projects.mind.mem.auto_test_script.agent_v1_eval_context import (
    canonicalize_v1_context_config,
)
from projects.mind.toolset import get_prompt
from projects.mind.mem.auto_test_script.auto_test_constants import (
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    MEMORY_TYPES,
    TEST_ASSISTANT_ID,
)

SKILL_PROFILE_TYPE = "skills"
_MEMORY_EXTRACTION_WAIT_SEC = 25


def _render_v1_system_prompt(template_str: str, context_config: dict[str, Any]) -> str:
    rendered = Template(template_str).render(**context_config)
    base = get_prompt()
    if base.guidelines:
        rendered = f"{rendered.rstrip()}\n\n请严格地遵循以下指令:\n{nl_repr(base.guidelines)}\n最后，你的回复极简极简极简极简极简，绝对不允许有emoji表情！！！"
    return rendered


def _run_params_to_model_params(run_params_dict: dict[str, Any]) -> ModelParams:
    """将 task_config.run_params 转为 v1 Agent 使用的 ModelParams。"""
    model_params_kwargs: dict[str, Any] = {"model": run_params_dict["model"]}
    raw_params = run_params_dict.get("params")
    if raw_params is None:
        return ModelParams(**model_params_kwargs)

    if isinstance(raw_params, ModelCallParams):
        model_params_kwargs["params"] = raw_params
        return ModelParams(**model_params_kwargs)

    if not isinstance(raw_params, dict):
        model_params_kwargs["params"] = raw_params
        return ModelParams(**model_params_kwargs)

    thinking_raw = raw_params.get("thinking")
    thinking_type = None
    if isinstance(thinking_raw, dict):
        thinking_type = thinking_raw.get("type")
    elif isinstance(thinking_raw, str):
        thinking_type = thinking_raw

    call_kwargs: dict[str, Any] = {}
    for key in ("temperature", "top_p", "max_output_tokens"):
        if raw_params.get(key) is not None:
            call_kwargs[key] = raw_params[key]
    if thinking_type is not None:
        call_kwargs["thinking"] = thinking_type

    model_params_kwargs["params"] = ModelCallParams(**call_kwargs)
    return ModelParams(**model_params_kwargs)


def _get_last_answer_from_agent(agent: Agent) -> str:
    """从 trace 或 message_history 取本轮最终回复。"""
    for event in reversed(agent.state.trace):
        if event.type == "react.text.done":
            return event.text
    if agent.state.message_history:
        _, last_ai = agent.state.message_history[-1]
        return last_ai.content or ""
    return ""


def _tool_output_text(output: Any) -> str:
    nl_repr = getattr(output, "nl_repr", None)
    if callable(nl_repr):
        return nl_repr()
    return str(output)


def _split_trace_by_react_start(trace: list[Any]) -> list[list[Any]]:
    """按每次 achat 的 react.start 切分 trace（与 message_history 条目一一对应）。"""
    segments: list[list[Any]] = []
    current: list[Any] = []
    for event in trace:
        event_type = getattr(event, "type", None)
        if event_type == "react.start":
            if current:
                segments.append(current)
            current = [event]
            continue
        if current:
            current.append(event)
    if current:
        segments.append(current)
    return segments


def _tool_records_from_trace_segment(segment: list[Any]) -> list[dict[str, str]]:
    """从单轮 trace 提取 function_call / function_call_output（对齐 BaseAgentBot）。"""
    records: list[dict[str, str]] = []
    saw_task_tool_done = False
    for event in segment:
        event_type = getattr(event, "type", None)
        if event_type == "react.tool_call.start":
            args = getattr(event, "arguments", None)
            if isinstance(args, dict):
                args_text = json.dumps(args, ensure_ascii=False)
            else:
                args_text = str(args)
            records.append(
                {
                    "role": "function_call",
                    "name": getattr(event, "name", "") or "",
                    "arguments": args_text,
                }
            )
        elif event_type == "task_tool.done":
            saw_task_tool_done = True
            records.append(
                {
                    "role": "function_call_output",
                    "content": _tool_output_text(getattr(event, "output", None)),
                }
            )
        elif event_type == "react.tool_results.done" and not saw_task_tool_done:
            tool_results = getattr(event, "tool_results", None) or []
            for item in tool_results:
                records.append(
                    {"role": "function_call_output", "content": str(item)}
                )
    return records


def _agent_state_to_dump_history(agent: Agent) -> list[dict[str, str]]:
    """
    将 v1 Agent 的 message_history + trace 转为评测侧可读格式。

    message_history 只有 user/assistant 最终 QA；工具调用在 trace 的
    react.tool_call.start / task_tool.done 等事件里，需合并后给 Judge。
    """
    history = agent.state.message_history or ()
    trace_segments = _split_trace_by_react_start(list(agent.state.trace or []))
    result: list[dict[str, str]] = []
    for index, (query_msg, answer_msg) in enumerate(history):
        result.append({"role": "user", "content": query_msg.content or ""})
        if index < len(trace_segments):
            result.extend(_tool_records_from_trace_segment(trace_segments[index]))
        result.append({"role": "assistant", "content": answer_msg.content or ""})
    return result


def build_agent_context(context_config: dict[str, Any]) -> tuple[AgentContext, dict]:
    """从配置字典构建 AgentContext 和工具映射。"""
    context_config = canonicalize_v1_context_config(context_config)
    config_dict: dict[str, Any] = dict(context_config.get("task_config", {}))

    if isinstance(config_dict.get("system_prompt"), str):
        if not context_config.get("user_profile") and config_dict.get("user_profile"):
            context_config["user_profile"] = nl_repr_safe(config_dict["user_profile"])
        rendered_prompt = _render_v1_system_prompt(
            config_dict["system_prompt"],
            context_config,
        )
        config_dict["system_prompt"] = rendered_prompt
        # print(f"system_prompt: {system_prompt}")

    tool_map = get_tool_map()
    tools_names: list[str] = config_dict.get("tools_names", [])
    tools_dict = {name: tool_map[name] for name in tools_names if name in tool_map}
    tools_list = [tools_dict[name] for name in tools_names if name in tools_dict]

    # 构建 AgentContext（run_params → model_params + react_max_turns，memory 结构展开）
    run_params_dict: dict[str, Any] = config_dict.get("run_params", {})
    memory_dict: dict[str, Any] = config_dict.get("memory") or {}
    producer_dict: dict[str, Any] = memory_dict.get("producer") or {}
    consumer_dict: dict[str, Any] = memory_dict.get("consumer") or {}

    context = AgentContext(
        system_prompt=config_dict.get("system_prompt", ""),
        model_params=_run_params_to_model_params(run_params_dict),
        react_max_turns=run_params_dict.get("max_turns", 5),
        tools=tools_list or None,
        memory_user_info=memory_dict.get("user_info"),
        memory_producer_config=producer_dict.get("config"),
        memory_producer_session_size=producer_dict.get("session_size", 1),
        memory_consumer_config=consumer_dict.get("config"),
        user_profile=config_dict.get("user_profile"),
    )

    return context, tools_dict


async def get_system_prompt_from_agent(agent: Agent) -> str | None:
    """从 model_api.history 取首轮注入的 SystemMessage，与模型实际所见一致。"""
    if agent is None:
        return None
    model_state = agent.state.model_api_state
    if model_state is None:
        return None
    messages = await agent.context.model_api.history(model_state)
    for msg in messages:
        if isinstance(msg, SystemMessage):
            return msg.text
    return None


class AgentV1Bot(AnyBotToTest):

    def __init__(self, context_config: dict[str, Any]):
        """初始化封装一个待测智能体"""
        self._context_config: dict[str, Any] = dict(context_config)
        self._system_prompt_template: str | None = None
        task_config = self._context_config.get("task_config", {})
        if isinstance(task_config, dict):
            system_prompt = task_config.get("system_prompt")
            if isinstance(system_prompt, str):
                self._system_prompt_template = system_prompt

        context, _ = build_agent_context(self._context_config)

        self.agent: Agent = Agent(context)
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
        rendered = _render_v1_system_prompt(
            self._system_prompt_template,
            self._context_config,
        )
        self.agent.context.system_prompt = rendered

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

    async def _await_volc_memory_extraction(
        self, *, after_substantial_flush_ok: bool
    ) -> None:
        """在确有对话缓冲已提交火山后，短时等待服务端抽取落库。"""
        if not after_substantial_flush_ok:
            return
        w = _MEMORY_EXTRACTION_WAIT_SEC
        adapter = self._context_config.get("voice_test_adapter")
        if adapter is not None:
            await adapter.push_event(CountdownWaitEvent(label="等待记忆提取", seconds=w))
        suppress = bool(
            self._context_config.get("auto_test_suppress_bot_console", False)
        ) or is_auto_test_bot_console_suppressed()
        if suppress:
            for _ in range(w):
                await asyncio.sleep(1)
        else:
            for _ in tqdm(
                range(w),
                desc="等待记忆提取，倒计时",
                unit="秒",
                ncols=75,
            ):
                await asyncio.sleep(1)
            print("等待记忆生成时间到！")
        if adapter is not None:
            await adapter.push_event(CountdownWaitEvent(label="等待记忆提取", seconds=0))

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
                self._apply_mock_time_to_memory(self.current_session_mock_time)
                await self.agent.new_session()
                self.current_session_mock_time = self.next_session_mock_time
                self._apply_mock_time_to_memory(self.current_session_mock_time)
            self.session_id = session_id

        assert self.agent is not None

        # 内部异步函数不需要传 self
        async def run_agent() -> str:
            async for _ in self.agent.astream(query):
                pass
            return _get_last_answer_from_agent(self.agent)

        result = await run_agent()
        return result

    def chat(self, query: str, session_id: str) -> str:
        self.query = query
        return asyncio.run(self.achat(query, session_id))

    def dump_history(self) -> list[dict[str, str]]:
        return async_to_sync(self.adump_history)()

    async def adump_history(self) -> list[dict[str, str]]:
        """导出当前会话可追溯消息；评测里每次「单次多轮」结束都会调用至此。

        在拉取助手侧原始 history 之后，对已启用的 MemoryProducer 执行 ``flush()``，使未及
        ``session_size`` 阈值的缓冲也能落库——与 ``achat`` 里 ``session_id`` 切换时的
        ``new_session()`` 互补（避免仅一段对话、或未再切会话时缓冲区被丢弃）。

        若本次 ``flush`` 前缓冲非空且提交成功，则在此等待服务端记忆抽取（与原先在 ``session``
        切换处等待等价，但更贴合「先有上传再起算」）。
        """
        assert self.agent is not None, "agent不能为None"
        result = _agent_state_to_dump_history(self.agent)

        prod = self.agent.memory_producer
        if prod is not None:
            had_pending = prod.pending_count > 0
            try:
                ok = await prod.flush()
                if not ok and not is_auto_test_bot_console_suppressed():
                    print(
                        "[AgentV1Bot.adump_history] memory_producer.flush() 返回 "
                        "False，火山侧可能未写入。"
                    )
                await self._await_volc_memory_extraction(
                    after_substantial_flush_ok=had_pending and ok,
                )
            except asyncio.CancelledError:
                raise

        return result

    @classmethod
    def create(cls, context_config: dict[str, Any]) -> "AgentV1Bot":
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
        events = self.agent.state.trace or []
        filtered_events = [
            e for e in events if e.type != "react.text.delta"
        ]  # 过滤掉增量事件，保持输出简洁

        session_id = self.session_id or ""
        system_prompt = await get_system_prompt_from_agent(self.agent)
        query = self.query or ""
        answer = _get_last_answer_from_agent(self.agent)

        trace = AgentDumpTrace(
            system_prompt=system_prompt,
            session_id=session_id,
            query=query,
            answer=answer,
            traces=[e.model_dump() for e in filtered_events],
        )

        return trace.model_dump()
