from __future__ import annotations

from typing import Any, AsyncGenerator

from pydantic import BaseModel, Field

from aicore.agents import StateBase
from aicore.core.event import EventCapturer, EventListener as EventListenerRaw

from aicore.runtime.task import TaskManager

from aicore.models.messages import HumanMessage, AIMessage
from aicore.models.model_api import (
    ModelAPIBackend,
    ModelParams,
    ModelResponse as APIModelResponse,
    ModelStateDump,
    create_model_api,
)

from aicore.agents.react import ReActEvent, ReActFinishEvent, react_with_stream_tools

from aicore.events import ReActTaskEventPrinter

from aicore.tools import TaskToolType

from aicore.events.task import TaskEvent, is_task_event

from aicore.utils.nl_repr import nl_repr

type AgentEvent = ReActEvent | TaskEvent

EventListener = EventListenerRaw[AgentEvent]

EventPrinter = ReActTaskEventPrinter

# 为了方便，省略写工具的类型参数
type ToolsType = list[TaskToolType[Any, Any, Any, ...]]


__all__ = [
    "AgentEvent",
    "EventListener",
    "EventPrinter",
    "MasterAgentBase",
    "create_agent",
]

class AgentDumpPayload(BaseModel):
    """Agent 持久化结构。"""

    # 模型参数
    system_prompt: Any = Field(..., description="系统提示词")
    model_params: ModelParams = Field(..., description="运行参数（dump 时不含 client）")
    model_api_backend: ModelAPIBackend = Field(
        default="chat",
        description="模型 API 适配器后端",
    )
    # react 相关
    max_turns: int = Field(..., description="最大回合数")
    # TODO：工具相关，需要重写
    tools_names: list[str] = Field(default_factory=list, description="工具名称列表")

    message_history: list[tuple[HumanMessage, AIMessage]] = Field(
        default_factory=list,
        description="agent 可读对话历史",
    )
    state_dump: ModelStateDump | None = Field(
        default=None,
        description="模型 provider 可持久化续接状态",
    )

# TODO: 改名为Trace。
class RunResult(BaseModel):
    """agent单轮的运行结果"""

    response: APIModelResponse[Any]
    """当前 provider-neutral 模型响应，用于保存 state 和最终文本。
    agent 可读历史由 AgentState.message_history 维护，不再挂在 response 上。
    """

    events: list[AgentEvent]
    """运行过程的的中间结果，也就是trajectory。在最简单的react情况下就是events，但完全可以任意扩展。"""


class AgentState(StateBase[AgentEvent]):
    """Agent 状态定义"""

    run_result: RunResult | None = Field(default=None, exclude=True)
    """当前运行结果。"""

    task_manager: TaskManager = Field(default_factory=TaskManager, description="任务管理器")

    dump_payload: AgentDumpPayload | None = Field(default=None, description="持久化数据")


class MasterAgentBase:
    """通用master agent。还远不成熟。刚开始。"""

    def __init__(
        self,
        system_prompt: Any,
        /,
        *,
        model_params: ModelParams,
        model_api_backend: ModelAPIBackend = "chat",
        tools: ToolsType | None = None,
        max_turns: int = 5,
        state: AgentState | None = None,
    ) -> None:
        """初始化agent，可接收已从持久化 payload 恢复出的 state。"""

        self._system_prompt = system_prompt
        self.model_params = model_params
        self.model_api_backend = (
            state.dump_payload.model_api_backend
            if state is not None and state.dump_payload is not None
            else model_api_backend
        )
        self._tools = tools or []

        self._state = state or AgentState()
        self.max_turns = max_turns

    @property
    def state(self) -> AgentState:
        """获取当前状态。"""
        return self._state

    @property
    def tools(self) -> ToolsType:
        """推理时使用的工具，包括外部工具和内部工具。"""
        return self._tools

    @property
    async def system_prompt(self) -> str:
        """系统提示词属性。目前的实现虽然简单，但它不仅仅是个wrapper，而是可扩展的。例如
        - 可以根据self.state定制化
        - 派生类可以重载
        """
        return nl_repr(self._system_prompt)

    async def astream(
        self,
        query: str,
        /,
        **kwargs: Any
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式执行。"""

        await self._restore_run_result_from_dump()
        previous_response: APIModelResponse[Any] | None = (
            self.state.run_result.response
            if self.state.run_result is not None
            else None
        )

        # TODO: 在这里写if else
        # 如果tools都是StreamTaskTool, 调用 astream_react_with_stream_tools, 并用self.state.task_manager消费其输出的event，并再次yield
        # 否则，调用下面的创通astream_react

        # 内置事件捕获器
        event_capturer = EventCapturer[AgentEvent]()

        response: APIModelResponse[Any] | None = None
        model_api = create_model_api(
            backend=self.model_api_backend,
            model=self.model_params.model,
        )
        model_state = (
            previous_response.state
            if previous_response is not None
            else model_api.initial_state(system_prompt=await self.system_prompt)
        )
        async for event in react_with_stream_tools(
            query,
            model_api=model_api,
            state=model_state,
            tools=self.tools,
            max_turns=self.max_turns,
            params=self.model_params.params,
            **kwargs,
        ):
            if isinstance(event, ReActFinishEvent):
                response = event.response

            if is_task_event(event):
                # TODO：先内部消费，再yield给外部,不确定怎么写。
                self.state.task_manager.handle_event(event)

            event_capturer(event)

            yield event

        assert isinstance(response, APIModelResponse)

        self.state.run_result = RunResult(response=response, events=event_capturer.events)
        self.state.extend_trace(event_capturer.events)
        self.state.append_message_history(
            HumanMessage(content=query),
            AIMessage(content=response.text or ""),
        )


    async def _restore_run_result_from_dump(self) -> None:
        """Restore runtime model state from the current dump payload if needed."""

        if self.state.run_result is not None:
            return

        payload = self.state.dump_payload
        if payload is None or payload.state_dump is None:
            return

        model_api = create_model_api(
            backend=self.model_api_backend,
            model=self.model_params.model,
        )
        restored_state = model_api.restore_state(payload.state_dump)
        response = APIModelResponse(
            state=restored_state,
            metadata={"restored_from_dump": True},
        )
        self.state.run_result = RunResult(response=response, events=[])
        for query_message, answer_message in payload.message_history:
            self.state.append_message_history(query_message, answer_message)

    async def dump(self) -> AgentDumpPayload:
        """Build a serializable payload with agent history and provider dump."""

        state_dump: ModelStateDump | None = None
        if self.state.run_result is not None:
            model_api = create_model_api(
                backend=self.model_api_backend,
                model=self.model_params.model,
            )
            state_dump = await model_api.dump_state(
                self.state.run_result.response.state
            )
        elif self.state.dump_payload is not None:
            state_dump = self.state.dump_payload.state_dump

        payload = AgentDumpPayload(
            system_prompt=self._system_prompt,
            model_params=self.model_params,
            model_api_backend=self.model_api_backend,
            max_turns=self.max_turns,
            tools_names=[tool.name for tool in self.tools],
            message_history=list(self.state.message_history),
            state_dump=state_dump,
        )
        self.state.dump_payload = payload
        return payload


def create_agent(
        model: str,
        tools: ToolsType | None = None,
        max_turns: int = 5,
        system_prompt: str = "你是友好的用户智能助手",
        model_api_backend: ModelAPIBackend = "chat",
        state: AgentState | None = None,
        ) -> MasterAgentBase:

    model_params = ModelParams(model=model)

    return MasterAgentBase(
        system_prompt,
        model_params=model_params,
        model_api_backend=model_api_backend,
        tools=tools,
        max_turns=max_turns,
        state=state,
    )
