from __future__ import annotations

from typing import Any, AsyncGenerator, Self

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from aicore.core.event import EventCapturer, EventGenerator

from aicore.events.react import is_react_event, ReActEventPrinter
from aicore.events.task import TaskEvent, is_task_event, TaskEventPrinter
from aicore.events.explicit_tool_call import (
    ExplicitEvent,
    ExplicitEventPrinter,
    ExplicitFinishEvent,
    is_explicit_event,
)

from aicore.agents import ContextBase, StateBase
from aicore.agents.react import ReActEvent, ReActFinishEvent, react_with_stream_tools
from aicore.agents.explicit_tool_call import explicit_tool_call_with_stream_tools
from aicore.agents.experiments.memory import (
    MemoryProducer,
    MemoryConsumer,
    MemoryEvent,
    MemoryProducerConfig,
    MemoryConsumerConfig,
    UserInfoMetadata,
    MemoryEventPrinter,
    ProfileMemoryResponse,
    EventMemoryResponse,
)
from aicore.agents.experiments.user_profile import UserProfile

from aicore.models.messages import HumanMessage, AIMessage
from aicore.models.model_api import (
    ModelAPI,
    ModelAPIBackend,
    ModelCallParams,
    ModelParams,
    ModelResponse as APIModelResponse,
    create_model_api,
)
from aicore.tools import TaskToolTypeGeneral

from aicore.tools.experiments.event_search_tool import event_search_tool
from aicore.tools.experiments.profile_search_tool import profile_search_tool
from aicore.tools.experiments.skill_search_tool import skill_search_tool
from aicore.tools.experiments.load_skill_tool import load_skill_tool
from aicore.tools.experiments.create_new_skill_tool import create_new_skill_tool
from aicore.tools.experiments.update_skill_tool import update_skill_tool

from aicore.utils.nl_repr import nl_repr

type AgentEvent = ReActEvent | ExplicitEvent | TaskEvent | MemoryEvent
type ToolsType = list[TaskToolTypeGeneral]

SKILL_TOOL_USAGE_GUIDANCE_PROMPT = (
    "多数时候你都可以先搜索一下skill，看看是否已有可复用方法或者过往的经验可以参考着使用。"
    "当你需要解决复杂或可复用任务时，请优先使用 skill 相关工具形成“先检索、再加载、再执行、再沉淀”的闭环："
    "先用 skill搜索工具 查询是否已有可复用方法；若命中候选，再用 load_skill工具 加载完整方法并严格按步骤执行；"
    "若现有 skill 不足以覆盖场景，但你最终成功完成了任务且过程有复用价值，请使用 create_new_skill工具 沉淀新经验；"
    "若你在实践中发现已有 skill 可以优化，请使用 update_skill工具 更新内容。"
    "除非任务非常简单且无复用价值，否则不要跳过这套流程。"
)


__all__ = [
    "Agent",
    "AgentContext",
    "AgentState",
    "AgentEvent",
    "SystemPrompt",
    "ReActTaskMemoryEventPrinter",
]


class AgentContext(ContextBase[TaskToolTypeGeneral]):
    """在基础 context 上挂 memory/profile 配置。"""

    system_prompt: SystemPrompt | str = Field(..., description="系统提示词")

    enable_tool_intent: bool = Field(default=False, description="是否启用工具意图识别")

    tool_intent_model_params: ModelParams | None = Field(
        default=None, description="工具意图识别使用的模型配置；为空时复用 model_params"
    )

    memory_user_info: UserInfoMetadata | None = Field(
        default=None, description="记忆共用用户信息"
    )

    memory_producer_config: MemoryProducerConfig | None = Field(
        default=None, description="记忆生产配置"
    )
    memory_producer_session_size: int = Field(
        default=1, description="记忆生产缓冲区大小"
    )

    memory_consumer_config: MemoryConsumerConfig | None = Field(
        default=None, description="记忆消费配置"
    )
    user_profile: UserProfile | BaseModel | None = Field(
        default=None, description="用户画像"
    )

    # TODO：有依赖关系。如构建producer和consumer时都依赖memory_user_info.且producer依赖session_size。
    @model_validator(mode="after")
    def check_memory_dependencies(self) -> Self:
        """
        校验记忆模块的依赖关系：
        1. 构建 producer → 必须有 user_info + session_size
        2. 构建 consumer → 必须有 user_info
        """
        # 校验记忆生产者依赖
        if self.memory_producer_config is not None:
            if self.memory_user_info is None:
                raise ValueError(
                    "启用 memory_producer_config 必须配置 memory_user_info"
                )
            if self.memory_producer_session_size < 1:
                raise ValueError("memory_producer_session_size 必须大于 0")

        # 校验记忆消费者依赖
        if self.memory_consumer_config is not None:
            if self.memory_user_info is None:
                raise ValueError(
                    "启用 memory_consumer_config 必须配置 memory_user_info"
                )

        return self

    _tool_intent_model_api: ModelAPI[Any] | None = PrivateAttr(default=None)

    @property
    def tool_intent_model_api(self) -> ModelAPI[Any]:
        if not self.tool_intent_model_params:
            return self.model_api

        if self._tool_intent_model_api is None:
            self._tool_intent_model_api = create_model_api(
                backend=self.model_api_backend,
                model=self.tool_intent_model_params.model,
            )
        return self._tool_intent_model_api


class AgentState(StateBase[AgentEvent]):
    """扩展状态：当前保持与基类一致，便于后续扩展。"""


class SystemPrompt(BaseModel):
    """系统提示词模板。它过于简单和死板，显然只是一个toy example，供参考而已。"""

    role: str = Field(
        default=..., title="系统提示词的角色", description="系统提示词的角色"
    )

    guidelines: list[str] | None = Field(
        default=None, title="系统提示词的指令", description="系统提示词的指令"
    )

    def __nl_repr__(self) -> str:
        """返回系统提示词的字符串表示。演示nl_repr的用法。"""

        sys_prompt = self.role

        if self.guidelines:
            sys_prompt += f"\n请严格地遵循以下指令:\n{nl_repr(self.guidelines)}"

        return sys_prompt


class Agent(EventGenerator[AgentEvent]):
    """基于 context/state 扩展 memory/profile。"""

    def __init__(
        self,
        context: AgentContext,
        /,
        *,
        state: AgentState | None = None,
    ) -> None:
        self._context = context
        self._state = state or AgentState()
        if (
            self._state.model_api_state is None
            and self._state.model_api_state_dump is not None
        ):
            self._state.model_api_state = context.model_api.restore_state(
                self._state.model_api_state_dump
            )
            self._state.model_api_state_dump = None

        self.internal_tools: ToolsType = []
        self.memory_producer, self.memory_consumer = self._build_memory_clients()
        self._refresh_internal_tools()

    @property
    def context(self) -> AgentContext:
        return self._context

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    async def system_prompt(self) -> str:
        """系统提示词：画像优先，其次记忆召回。"""
        base_prompt = nl_repr(self.context.system_prompt)
        if self.context.user_profile:
            profile_str = nl_repr(self.context.user_profile)
            if profile_str:
                return f"{base_prompt}\n\n{profile_str}"

        if self.memory_consumer:
            # 增加 skill 工具使用指引
            if self.memory_consumer.has_skill_profile_type:
                base_prompt = f"{base_prompt}\n\n{SKILL_TOOL_USAGE_GUIDANCE_PROMPT}"

            # 记忆注入
            memory_rsp = await self.memory_consumer.retrieve_profiles()
            # TODO:缺少一个转化函数，把memory_rsp转化为字符串，先临时使用nl_repr
            memory_str = nl_repr(memory_rsp.data.result_list)
            if memory_str:
                return f"{base_prompt}\n\n{memory_str}"

        return base_prompt

    def _build_memory_clients(
        self,
    ) -> tuple[MemoryProducer | None, MemoryConsumer | None]:
        """构建记忆客户端。"""
        user_info = self.context.memory_user_info
        if user_info is None:
            # TODO：按理说就是不用memory，有点奇怪。没有用户信息，不构建记忆模块
            return None, None

        # 构建记忆生产客户端
        producer: MemoryProducer | None = None
        consumer: MemoryConsumer | None = None
        if self.context.memory_producer_config:
            producer = MemoryProducer(
                self.context.memory_producer_config,
                user_info,
                session_size=self.context.memory_producer_session_size,
            )

        # 构建记忆消费客户端
        if self.context.memory_consumer_config:
            consumer = MemoryConsumer(
                self.context.memory_consumer_config,
                user_info,
            )
        return producer, consumer

    def _refresh_internal_tools(self) -> None:
        """刷新内部工具（目前包括记忆事件检索、画像检索、skill工具等）。"""
        internal: ToolsType = []

        if self.memory_consumer:
            # 增加记忆事件检索工具
            if self.memory_consumer.config.event_types:
                event_worker = self.memory_consumer.create_event_search_worker()
                internal.append(event_search_tool(event_worker))
            # 增加画像检索工具
            if self.memory_consumer.non_skill_search_profile_types:
                profile_worker = self.memory_consumer.create_profile_search_worker()
                internal.append(profile_search_tool(profile_worker))
            # 增加 skill 工具
            if self.memory_consumer.has_skill_profile_type:
                skill_worker = self.memory_consumer.create_skill_search_worker()
                internal.append(skill_search_tool(skill_worker))
                load_skill_worker = self.memory_consumer.create_load_skill_worker()
                internal.append(load_skill_tool(load_skill_worker))
                create_skill_worker = self.memory_consumer.create_new_skill_worker()
                internal.append(create_new_skill_tool(create_skill_worker))
                update_skill_worker = self.memory_consumer.update_skill_worker()
                internal.append(update_skill_tool(update_skill_worker))

        self.internal_tools = internal

    @property
    def tools(self) -> ToolsType:
        """推理时使用的工具，包括外部工具和内部工具。"""
        # TODO：过滤，去重
        external_tools = self.context.tools or []
        return [*external_tools, *self.internal_tools]

    async def new_session(self) -> None:
        """开始新会话，清空运行状态并刷出记忆缓冲。"""
        if self.memory_producer:
            await self.memory_producer.flush()
        self._state = AgentState()

    async def astream(
        self, query: str, /, **kwargs: Any
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式执行：支持状态继承、工具调用、记忆写入。"""

        event_capturer = EventCapturer[AgentEvent]()

        try:
            if self.context.enable_tool_intent:
                # explicit 是 ReAct 前的快速工具意图通道：
                # 先用轻量模型判断当前 query 是否能唯一命中某个工具。
                # 如果命中，_explicit 会产出 ExplicitFinishEvent，并完成 工具执行 -> 最终回答。
                # 如果没命中，后面继续走完整 ReAct。
                explicit_finished = False
                async for event in self._explicit(query, event_capturer, **kwargs):
                    if isinstance(event, ExplicitFinishEvent):
                        explicit_finished = True
                    yield event

                if explicit_finished:
                    # ExplicitFinishEvent 是 explicit 成功的明确承诺。
                    # explicit 是一次性快速通道，不推进主会话 model_api_state。
                    return

            async for event in self._react(query, event_capturer, **kwargs):
                yield event
        finally:
            self.state.extend_trace(event_capturer.events)

    async def _react(
        self,
        query: str,
        event_capturer: EventCapturer[AgentEvent],
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行完整 ReAct，并在最终回答完成后写入 history/memory。"""

        model_state = self.state.model_api_state
        if model_state is None:
            model_state = self.context.model_api.initial_state(
                system_prompt=await self.system_prompt
            )

        response: APIModelResponse[Any] | None = None
        async for event in react_with_stream_tools(
            query,
            model_api=self.context.model_api,
            state=model_state,
            tools=self.tools,
            max_turns=self.context.react_max_turns,
            params=self.context.model_params.params,
            **kwargs,
        ):
            if isinstance(event, ReActFinishEvent):
                # TODO: 这里的type check error是有些逻辑问题的。ReActEvent的定义中，ReActFinishEvent的类型参数为Any，这就意味着不可能有response属性。
                # 需要让ReActEvent自带类型参数，这需要修改所有的react代码，太麻烦。暂时先不处理。
                response = event.response  # type: ignore

            event_capturer(event)

            yield event

        assert isinstance(response, APIModelResponse), "流式执行后，response 不应为空"
        self.state.model_api_state = response.state
        query_message = HumanMessage(content=query)
        answer_message = AIMessage(content=response.text or "")
        self.state.append_message_history(query_message, answer_message)

        async for event in self._astream_add_memory(query_message, answer_message):
            yield event

    async def _astream_add_memory(
        self, query: HumanMessage, answer: AIMessage
    ) -> AsyncGenerator[MemoryEvent, None]:
        """Persist a user-visible agent response to long-term memory."""

        if self.memory_producer is None:
            return

        volc_sp = await self.system_prompt
        async for event in self.memory_producer.add_memory(
            (query, answer),
            system_context_for_volc=volc_sp,
        ):
            yield event

    # TODO: 这个函数和base.py中的_explicit函数基本一致，只是多了event_capturer参数
    async def _explicit(
        self,
        query: str,
        event_capturer: EventCapturer[AgentEvent],
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        """先用轻量模型做显式工具意图识别，命中后直接完成工具调用。"""

        model_params = (
            self.context.tool_intent_model_params or self.context.model_params
        )
        model_api = self.context.tool_intent_model_api
        memory_messages: tuple[HumanMessage, AIMessage] | None = None
        async for event in explicit_tool_call_with_stream_tools(
            query,
            model_api=model_api,
            state=self.context.model_api.initial_state(
                system_prompt=await self.system_prompt
            ),
            tools=self.tools,
            params=model_params.params,
            **kwargs,
        ):
            if isinstance(event, ExplicitFinishEvent):
                response = event.response
                assert isinstance(response, APIModelResponse)
                query_message = HumanMessage(content=query)
                answer_message = AIMessage(content=response.text or "")
                self.state.append_message_history(query_message, answer_message)
                memory_messages = (query_message, answer_message)

            event_capturer(event)
            yield event

        if memory_messages is not None:
            query_message, answer_message = memory_messages
            async for event in self._astream_add_memory(query_message, answer_message):
                yield event

    async def dump(self) -> tuple[AgentContext, AgentState]:
        """序列化当前 agent 的 context/state。"""
        if self.state.model_api_state is not None:
            self.state.model_api_state_dump = await self.context.model_api.dump_state(
                self.state.model_api_state
            )
        return self.context, self.state

    async def retrieve_profiles(self) -> ProfileMemoryResponse:
        """召回画像记忆。需要配置 memory_consumer。"""
        assert self.memory_consumer, "memory_consumer 未配置"

        return await self.memory_consumer.retrieve_profiles()

    async def retrieve_events(self) -> EventMemoryResponse:
        """召回事件记忆。需要配置 memory_consumer。"""
        assert self.memory_consumer, "memory_consumer 未配置"

        return await self.memory_consumer.retrieve_events()


def create_agent(
    *,
    model: str,
    tools: ToolsType,
    react_max_turns: int = 5,
    system_prompt: SystemPrompt | str | None = None,
    model_call_params: ModelCallParams | None = None,
    enable_tool_intent: bool = False,
    tool_intent_model: str | None = None,
    model_api_backend: ModelAPIBackend = "chat",
) -> Agent:
    """使用标准 V1 配置创建 Agent。"""
    model_params = ModelParams(
        model=model,
        params=model_call_params or ModelCallParams(),
    )

    if system_prompt is None:
        default_system_prompt = SystemPrompt(
            role="你是友好的用户智能助手",
            guidelines=[
                "打算调用工具前，一定要简要地回复用户打算做什么，再执行工具调用。否则干死你！！！",
                "回复简明扼要，避免长篇大论",
            ],
        )
        system_prompt = default_system_prompt

    context = AgentContext(
        system_prompt=system_prompt,
        model_params=model_params,
        model_api_backend=model_api_backend,
        tool_intent_model_params=(
            ModelParams(model=tool_intent_model) if tool_intent_model else None
        ),
        enable_tool_intent=enable_tool_intent,
        react_max_turns=react_max_turns,
        tools=tools,
    )
    return Agent(context)


class ReActTaskMemoryEventPrinter:
    def __init__(self):
        self.react_event_printer = ReActEventPrinter()
        self.explicit_event_printer = ExplicitEventPrinter()
        self.task_event_printer = TaskEventPrinter()
        self.memory_event_printer = MemoryEventPrinter()

    def __call__(self, event: AgentEvent):
        if is_react_event(event):
            self.react_event_printer(event)
        elif is_explicit_event(event):
            self.explicit_event_printer(event)
        elif is_task_event(event):
            self.task_event_printer(event)
        else:
            assert isinstance(event, MemoryEvent)
            self.memory_event_printer(event)
