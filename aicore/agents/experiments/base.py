from __future__ import annotations

from typing import AsyncGenerator, Any
from functools import cached_property

from pydantic import BaseModel, Field, ConfigDict

from aicore.utils.nl_repr import nl_repr

from aicore.models.credentials import create_client, AsyncArk, ModelName
from aicore.models.responses import ResponseParams, Response, ResponseItemSimple, convert_items_to_input_params

from aicore.tools import TaskToolType
from aicore.agents.react import ReActEvent, ReActFinishEvent, react_with_stream_tools
from aicore.events.react import ReActEventListener

from aicore.core.event import EventCapturer
from aicore.events.task import TaskEvent, is_task_event

from aicore.agents.experiments.memory import (
    MemoryProducer, 
    MemoryConsumer, 
    MemoryEvent, 
    ProfileMemoryResponse, 
    EventMemoryResponse,
    MemoryProducerConfig,
    MemoryConsumerConfig,
    UserInfoMetadata,
)
from aicore.tools.experiments.event_search_tool import event_search_tool
from aicore.tools.experiments.profile_search_tool import profile_search_tool
from aicore.tools.experiments.skill_search_tool import skill_search_tool
from aicore.tools.experiments.load_skill_tool import load_skill_tool
from aicore.tools.experiments.create_new_skill_tool import create_new_skill_tool
from aicore.tools.experiments.update_skill_tool import update_skill_tool
from aicore.agents.experiments.user_profile import UserProfile
from aicore.models.messages import HumanMessage, AIMessage

AgentEvent = ReActEvent | TaskEvent | MemoryEvent

# 为了方便，省略写工具的类型参数
type ToolsType = list[TaskToolType[Any, Any, Any, ...]]

SKILL_TOOL_USAGE_GUIDANCE_PROMPT = (
    "多数时候你都可以先搜索一下skill，看看是否已有可复用方法或者过往的经验可以参考着使用。"
    "当你需要解决复杂或可复用任务时，请优先使用 skill 相关工具形成“先检索、再加载、再执行、再沉淀”的闭环："
    "先用 skill搜索工具 查询是否已有可复用方法；若命中候选，再用 load_skill工具 加载完整方法并严格按步骤执行；"
    "若现有 skill 不足以覆盖场景，但你最终成功完成了任务且过程有复用价值，请使用 create_new_skill工具 沉淀新经验；"
    "若你在实践中发现已有 skill 可以优化，请使用 update_skill工具 更新内容。"
    "除非任务非常简单且无复用价值，否则不要跳过这套流程。"
)


class MemoryProducerDump(BaseModel):
    """记忆生产配置"""
    config: MemoryProducerConfig = Field(..., description="记忆生产配置")
    session_size: int = Field(..., description="缓冲区大小")


class MemoryConsumerDump(BaseModel):
    """记忆消费配置"""
    config: MemoryConsumerConfig = Field(..., description="记忆消费配置")


class MemoryDump(BaseModel):
    # 虽然两个模块中的user_info是单独传的，但在agent 内部应当是同一个。
    user_info: UserInfoMetadata = Field(..., description="共用的用户信息。")

    producer: MemoryProducerDump | None = Field(default=None, description="记忆生产配置项")
    consumer: MemoryConsumerDump | None = Field(default=None, description="记忆消费配置项")


class AgentDumpPayload(BaseModel):
    """Agent 持久化结构。与 AgentBase 入参类型对齐。"""
    # 按说有用，以后再说
    # version: int = Field(default=1, description="格式版本")
    system_prompt: str | SystemPrompt | BaseModel = Field(..., description="系统提示词")
    run_params: RunParams = Field(..., description="运行参数（dump 时不含 client）")
    # 暂时没用上
    # state: AgentState = Field(..., description="Agent 状态")
    tools_names: list[str] = Field(default_factory=list, description="工具名称列表")
    history: list[ResponseItemSimple] = Field(default_factory=list, description="历史对话")
    inherited_message_history: list[tuple[HumanMessage, AIMessage]] = Field(default_factory=list, description="需要继承的对话历史")

    memory: MemoryDump | None = Field(default=None, description="记忆相关配置，包含生产和消费配置")
    user_profile: UserProfile | BaseModel | None = Field(default=None, description="用户画像")


class RunParams(BaseModel):
    """通用master agent。"""
    model_config = ConfigDict(frozen=True)
    model: str = Field(..., description="模型名称")
    params: ResponseParams | None = Field(default=None, description="模型参数")
    max_turns: int = Field(default=5, description="最大轮数")

    @cached_property
    def client(self) -> AsyncArk:
        """创建 AsyncArk 客户端。"""
        model = ModelName(self.model)
        client, _= create_client(model, AsyncArk)
        return client
        

class SystemPrompt(BaseModel):
    """系统提示词模板。它过于简单和死板，显然只是一个toy example，供参考而已。"""

    role: str = Field(default=..., title="系统提示词的角色", description="系统提示词的角色")

    guidelines : list[str] | None = Field(default=None, title="系统提示词的指令", description="系统提示词的指令")

    def __nl_repr__(self) -> str:
        """返回系统提示词的字符串表示。演示nl_repr的用法。"""

        sys_prompt = self.role

        if self.guidelines:
            sys_prompt += f"\n请严格地遵循以下指令:\n{nl_repr(self.guidelines)}"

        return sys_prompt


class RunResult(BaseModel):
    """agent单轮的运行结果"""

    response: Response
    """当前模型的响应，以及对话历史。参见Response中message_history的描述。
    TODO: Response的语义过于底层，基本都是模型层的信息，大量细节信息并没有必要返回。应该有必要抽象出一个更高级的语义，比如AgentResponse。
    TODO: 可能值得增加一个从模型层response到agent层response的转换函数? 拿不准。
    """

    events: list[AgentEvent]
    """运行过程的的中间结果，也就是trajectory。在最简单的react情况下就是events，但完全可以任意扩展。"""


class AgentState(BaseModel):
    """Agent 状态定义"""

    run_result: RunResult | None = None
    """当前运行结果。"""
    history: list[ResponseItemSimple] = Field(default_factory=list, description="历史对话")
    """从 dump 恢复时的历史对话首轮 query 时与 query 组成 input 后清空。"""
    inherited_message_history: list[tuple[HumanMessage, AIMessage]] = Field(default_factory=list, description="继承的历史对话")
    """用于从dump恢复时，message_history不丢失该记录"""


class AgentBase:
    """通用master agent。还远不成熟。刚开始。"""
    def __init__(
        self, 
        system_prompt: str | SystemPrompt | BaseModel,
        /,
        *,
        run_params: RunParams,
        tools: ToolsType = Field(..., description="工具列表"),
        state: AgentState | None = None,
        memory_producer: MemoryProducer | None = None,
        memory_consumer: MemoryConsumer | None = None,
        user_profile: UserProfile | BaseModel | None = None,
    ) -> None:
        """初始化agent。
        TODO: 增加AgentState参数，用于反序列化。
        """
        
        self._system_prompt = system_prompt
        self.run_params = run_params
        self._external_tools = list(tools)
        self._internal_tools: ToolsType = []
        self._state = state if state is not None else AgentState()
        self.memory_producer = memory_producer
        self.memory_consumer = memory_consumer
        self.user_profile = user_profile

        # 刷新内部工具,目前有self.memory_consumer的依赖
        self._refresh_internal_tools

    @property
    def state(self) -> AgentState:
        """获取当前状态。"""
        return self._state

    async def new_session(self) -> None:
        """开始新对话，清空当前状态和记忆缓冲区。"""
        # 记忆需要管理，提交缓冲区内的对话历史并清空缓冲区
        if self.memory_producer:
            # TODO：记忆提交有可能失败，不清楚怎么处理
            await self.memory_producer.flush()
            # assert result, "强制提交缓冲区失败"

        # TODO: 其他配置先保持现状
        # 清空状态
        self._state = AgentState()

    @property
    async def system_prompt(self) -> str:
        """系统提示词属性。目前的实现虽然简单，但它不仅仅是个wrapper，而是可扩展的。例如
        - 可以根据self.state定制化
        - 派生类可以重载
        """
        base_prompt = nl_repr(self._system_prompt)
        # TODO：传入自定义画像，画像优先,跳过记忆召回。暂时先这么处理
        if self.user_profile:
            # 直接用nl_repr
            profile_str = nl_repr(self.user_profile)
            if profile_str:
                return f"{base_prompt}\n\n{profile_str}"
        
        if self.memory_consumer:
            if self.memory_consumer.has_skill_profile_type:
                base_prompt = f"{base_prompt}\n\n{SKILL_TOOL_USAGE_GUIDANCE_PROMPT}"
            # 记忆注入
            memory_rsp = await self.memory_consumer.retrieve_profiles()
            # TODO:缺少一个转化函数，把memory_rsp转化为字符串，先临时使用nl_repr
            memory_str = nl_repr(memory_rsp.data.result_list)
            if memory_str:
                return f"{base_prompt}\n\n{memory_str}"
        
        return base_prompt

    @property
    def _refresh_internal_tools(self) -> None:
        # 统一管理内部工具,避免外部工具和内部工具混淆
        internal: ToolsType = []

        if self.memory_consumer:
            if self.memory_consumer.config.event_types:
                event_worker = self.memory_consumer.create_event_search_worker()
                internal.append(event_search_tool(event_worker))
            if self.memory_consumer.non_skill_search_profile_types:
                profile_worker = self.memory_consumer.create_profile_search_worker()
                internal.append(profile_search_tool(profile_worker))
            if self.memory_consumer.has_skill_profile_type:
                skill_worker = self.memory_consumer.create_skill_search_worker()
                internal.append(skill_search_tool(skill_worker))
                load_skill_worker = self.memory_consumer.create_load_skill_worker()
                internal.append(load_skill_tool(load_skill_worker))
                create_skill_worker = self.memory_consumer.create_new_skill_worker()
                internal.append(create_new_skill_tool(create_skill_worker))
                update_skill_worker = self.memory_consumer.update_skill_worker()
                internal.append(update_skill_tool(update_skill_worker))

        self._internal_tools = internal

    @property
    def tools(self) -> ToolsType:
        """推理时使用的工具，包括外部工具和内部工具。"""
        # TODO：去重
        return [*self._external_tools, *self._internal_tools]  

    async def astream(
        self, 
        query: str,
        /, 
        *,
        event_listeners: list[ReActEventListener],
        **kwargs: Any
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式执行。和ReActAgentBase不同，它不再是astream_react的wrapper，而是需要维护自己的状态。"""

        # 内置事件捕获器
        event_capturer = EventCapturer[AgentEvent]()
        event_listeners.append(event_capturer)

        # 三种情况只有一种成立
        assert sum([bool(self.state.run_result), bool(self.state.history), not (self.state.run_result or self.state.history)]) == 1, "三种输入场景仅能有一个成立"
        inherited_message_history: list[tuple[HumanMessage, AIMessage]] | None = None
        # 如果state.run_result不为空，则使用state.run_result.response
        if self.state.run_result:
            previous_response_or_system_prompt = self.state.run_result.response

        # 如果history不为空，则使用history
        elif self.state.history:
            # 从 dump 恢复后首轮：history 作为参数及query进入底层模型构建为一个input
            previous_response_or_system_prompt = convert_items_to_input_params(self.state.history)
            if self.state.inherited_message_history:
                inherited_message_history = self.state.inherited_message_history
                # 用完后清空
                self.state.inherited_message_history = []
            # 用完后清空
            self.state.history = []
            
        else:
            # 初始时state.run_result为None，history为空，也就是第一轮对话时，传入system_prompt
            previous_response_or_system_prompt = await self.system_prompt
            
        response: Response | None = None
        async for event in react_with_stream_tools(
            query,
            previous_response_or_system_prompt,  # type: ignore
            client=self.run_params.client,
            model=self.run_params.model,
            tools=self.tools,
            max_turns=self.run_params.max_turns,
            params=self.run_params.params,
            inherited_message_history=inherited_message_history,
            **kwargs,
        ):
            if isinstance(event, ReActFinishEvent):
                response = event.response

            if is_task_event(event):
                # TODO：需要处理TaskEvent，目前暂时不处理，统一yield给外部
                pass
            else:
                # TODO：调用事件监听器。TaskEvent 不透传给 ReActEventListener。
                for event_listener in event_listeners:
                    event_listener(event)

            yield event

        assert isinstance(response, Response)

        self.state.run_result = RunResult(response=response, events=event_capturer.events)
        # 结束后触发记忆更新,每次传入增量的message_history,取最后一项。
        if self.memory_producer:
            # 触发逻辑由memory_producer内部处理。
            volc_sp = await self.system_prompt
            async for event in self.memory_producer.add_memory(
                response.message_history[-1],
                system_context_for_volc=volc_sp,
            ):
                yield event

    async def astream_run(
        self, 
        query: str,
        /, 
        *,
        event_listeners: list[ReActEventListener],
        **kwargs:dict[str, Any]
    ) -> RunResult:
        """流式执行的wrapper。仅仅为了方便。"""
        async for _ in self.astream(query, event_listeners=event_listeners, **kwargs):
            pass

        assert self.state.run_result, "流式执行后，状态中应该有运行结果"

        return self.state.run_result

    async def dump(self) -> AgentDumpPayload:
        """将当前 agent 状态转为 AgentDumpPayload。"""
        # 如果state.run_result不为空，则获取历史对话
        if self.state.run_result:
            history = await self.state.run_result.response.ahistory(client=self.run_params.client)
            inherited_message_history = self.state.run_result.response.message_history
        else:
            history = []
            inherited_message_history = []

        memory_dump = None
        if self.memory_producer or self.memory_consumer:
            user_info = None
            producer_dump = None
            consumer_dump = None
            
            if self.memory_producer:
                user_info = self.memory_producer.user_info
                producer_dump = MemoryProducerDump(
                    config=self.memory_producer.config,
                    session_size=self.memory_producer.session_size,
                )
            
            if self.memory_consumer:
                user_info = user_info or self.memory_consumer.user_info
                consumer_dump = MemoryConsumerDump(
                    config=self.memory_consumer.config,
                )
            
            assert user_info, "记忆生产和消费配置中肯定包含用户信息"
            memory_dump = MemoryDump(
                user_info=user_info,
                producer=producer_dump,
                consumer=consumer_dump,
            )
        
        # 画像
        user_profile_dump = None
        if self.user_profile:
            user_profile_dump = self.user_profile

        return AgentDumpPayload(
            system_prompt=self._system_prompt,
            run_params=self.run_params, # 不包含 client
            tools_names = [tool.name for tool in self._external_tools],
            history = history,
            inherited_message_history=inherited_message_history,
            memory=memory_dump,
            user_profile=user_profile_dump,
        )

    @classmethod
    def create(
        cls,
        payload_obj: AgentDumpPayload,
        *,
        tool_registry: dict[str, TaskToolType[Any, Any, Any, ...]],
    ) -> AgentBase:
        """从 AgentDumpPayload 恢复。tools 按 tools_names 的 name 从 tool_registry 映射。"""

        # 已经重建好，无需重新model_dump
        run_params = payload_obj.run_params
        # 这里history是list[ResponseItemSimple]
        history = payload_obj.history
        inherited_message_history = payload_obj.inherited_message_history

        state = AgentState(history=history, inherited_message_history=inherited_message_history)

        # tools_snapshot 只是「工具描述」，还原不出可执行的 tool 对象, 需自行映射。
        tools: ToolsType = []
       
        for name in payload_obj.tools_names:
            if name not in tool_registry:
                raise KeyError(f"tool_registry 未注册 name={name}")
            tools.append(tool_registry[name])

        memory_producer = None
        memory_consumer = None
        if payload_obj.memory:
            mem = payload_obj.memory
            user_info = mem.user_info
            
            if mem.producer:
                memory_producer = MemoryProducer(
                    mem.producer.config,
                    user_info,
                    session_size=mem.producer.session_size,
                )
            
            if mem.consumer:
                memory_consumer = MemoryConsumer(
                    mem.consumer.config,
                    user_info,
                )

        # 画像
        user_profile = None
        if payload_obj.user_profile:
            user_profile = payload_obj.user_profile

        return cls(
            payload_obj.system_prompt,
            run_params=run_params,
            tools=tools,
            state=state,
            memory_producer=memory_producer,
            memory_consumer=memory_consumer,
            user_profile=user_profile,
        )

    async def retrieve_profiles(self) -> ProfileMemoryResponse:
        """召回画像记忆。需要配置 memory_consumer。"""
        assert self.memory_consumer, "memory_consumer 未配置"

        return await self.memory_consumer.retrieve_profiles()

    async def retrieve_events(self) -> EventMemoryResponse:
        """召回事件记忆。需要配置 memory_consumer。"""
        assert self.memory_consumer, "memory_consumer 未配置"

        return await self.memory_consumer.retrieve_events()


def _create_agent(
    *,
    model: str, 
    tools: ToolsType,
    max_turns: int = 5,
    guidelines: list[str] | None = None,
    ) -> AgentBase:
    """a simple helper function just for test. do not use in production."""

    params = ResponseParams(thinking = {"type": "disabled"})

    run_params = RunParams(
        model=model,
        params=params,
        max_turns=max_turns,
    )

    guidelines = guidelines or []
    guidelines.extend([
            #"打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。",
            "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节。",
            "回复简明扼要，避免长篇大论",
        ])

    system_prompt = SystemPrompt(
        role="你是友好的用户智能助手",
        guidelines=guidelines,
    )

    agent = AgentBase(system_prompt, run_params=run_params, tools=tools)
    return agent
