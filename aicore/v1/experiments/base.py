from __future__ import annotations

from typing import Any, AsyncGenerator

from pydantic import Field

from aicore.agents import ContextBase, StateBase

from aicore.core.event import EventCapturer, EventGenerator

from aicore.models.messages import HumanMessage, AIMessage
from aicore.models.model_api import (
    ModelAPIBackend,
    ModelParams,
    ModelResponse as APIModelResponse,
)

from aicore.agents.react import ReActEvent, ReActFinishEvent, react_with_stream_tools
from aicore.agents.explicit_tool_call import explicit_tool_call_with_stream_tools

from aicore.tools import TaskToolTypeGeneral

from aicore.events.task import TaskEvent
from aicore.events.explicit_tool_call import ExplicitEvent, ExplicitFinishEvent
from aicore.events import ReActTaskEventPrinter as EventPrinter

from aicore.utils.nl_repr import nl_repr

type AgentEvent = ReActEvent | ExplicitEvent | TaskEvent

__all__ = [
    "AgentEvent",
    "EventPrinter",
    "AgentBase",
    "create_agent",
]

# 只能用于静态类型检查。不是动态类型。
# type AgentContext = ContextBase[TaskToolTypeGeneral]
# type AgentState = StateBase[AgentEvent]

class AgentState(StateBase[AgentEvent]):
    """Provider-neutral v1 demo agent state with persisted model state."""


# 1. 演示如何继承Context。2. 增加使用的意图识别功能。
class AgentContext(ContextBase[TaskToolTypeGeneral]):
    enable_tool_intent: bool = Field(
        default=False, description="是否启用工具意图识别。"
    )


class AgentBase(EventGenerator[AgentEvent]):
    """
    通用agent基类。还远不成熟。刚开始。
    不能用于生产环境。
    """

    def __init__(
        self,
        context: AgentContext,
        /,
        *,
        state: AgentState | None = None,
    ) -> None:
        """初始化agent。"""
        self._context = context
        self._state = state or AgentState()
        if self._state.model_api_state is None and self._state.model_api_state_dump is not None:
            self._state.model_api_state = context.model_api.restore_state(self._state.model_api_state_dump)
            self._state.model_api_state_dump = None

        # 内置事件捕获器
        self.event_capturer = EventCapturer[AgentEvent]()

    @property
    def context(self) -> AgentContext:
        """获取当前上下文。"""
        return self._context

    @property
    def state(self) -> AgentState:
        """获取当前状态。"""
        return self._state

    @property
    def system_prompt(self) -> str:
        """系统提示词属性。目前的实现虽然简单，但它不仅仅是个wrapper，而是可扩展的。例如
        - 可以根据self.state定制化
        - 派生类可以重载
        """
        return nl_repr(self.context.system_prompt)

    async def astream(
        self,
        query: str,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        """启用 enable_tool_intent 时先跑 explicit primitive
        根据 ExplicitFinishEvent 判断 explicit 是否生成了最终回答; 没有则继续跑 react.
        """
        self.event_capturer = EventCapturer[AgentEvent]()

        try:
            if self.context.enable_tool_intent:
                explicit_finished = False
                async for event in self._explicit(query, **kwargs):
                    if isinstance(event, ExplicitFinishEvent):
                        explicit_finished = True
                    yield event
                if explicit_finished:
                    # ExplicitFinishEvent 是 explicit 成功的明确承诺。
                    # explicit 是一次性快速通道，不推进主会话 model_api_state。
                    return

            async for event in self._react(query, **kwargs):
                yield event
        finally:
            self.state.extend_trace(self.event_capturer.events)

    async def _explicit(
        self,
        query: str,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式调用 explicit tool call primitive."""
        model_api = self.context.model_api
        async for event in explicit_tool_call_with_stream_tools(
            query,
            model_api=model_api,
            state=model_api.initial_state(system_prompt=self.system_prompt),
            tools=self.context.tools,
            params=self.context.model_params.params,
            **kwargs,
        ):
            self.event_capturer(event)
            if isinstance(event, ExplicitFinishEvent):
                response = event.response
                assert isinstance(response, APIModelResponse)
                query_message = HumanMessage(content=query)
                answer_message = AIMessage(content=response.text or "")
                self.state.append_message_history(query_message, answer_message)
            yield event

    async def _react(
        self,
        query: str,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式调用 react primitive."""
        
        model_api = self.context.model_api
        model_state = self.state.model_api_state
        if model_state is None:
            model_state = model_api.initial_state(system_prompt=self.system_prompt)
            
        async for event in react_with_stream_tools(
            query,
            model_api=model_api,
            state=model_state,
            tools=self.context.tools,
            max_turns=self.context.react_max_turns,
            params=self.context.model_params.params,
            **kwargs,
        ):
            self.event_capturer(event)
            if isinstance(event, ReActFinishEvent):
                # TODO: ReActFinishEvent 的类型参数为 Any, .response 会有 type
                # check 噪音; 等 ReActEvent 带回真实类型参数再清理.
                response = event.response
                assert isinstance(response, APIModelResponse)
                self.state.model_api_state = response.state
                query_message = HumanMessage(content=query)
                answer_message = AIMessage(content=response.text or "")
                self.state.append_message_history(query_message, answer_message)
            yield event

    async def dump(self) -> tuple[AgentContext, AgentState]:
        """序列化当前agent上下文和状态"""
        if self.state.model_api_state is not None:
            self.state.model_api_state_dump = await self.context.model_api.dump_state(
                self.state.model_api_state
            )
        return self.context, self.state


def create_agent(
    model: str,
    tools: list[TaskToolTypeGeneral] | None = None,
    react_max_turns: int = 5,
    system_prompt: str = "你是友好的用户智能助手",
    enable_tool_intent: bool = False,
    model_api_backend: ModelAPIBackend = "chat",
) -> AgentBase:

    model_params = ModelParams(model=model)
    # 令人崩溃的错误：context的tools类型居然跟传入的tools类型不一样。无论怎么改都不行。
    # 只有写成ContextBase才对。只要是用AgentContext，即使是最简单的继承自ContextBase，也会出错。完全无法理解。
    context = AgentContext(
        # context = ContextBase(
        system_prompt=system_prompt,
        model_params=model_params,
        model_api_backend=model_api_backend,
        react_max_turns=react_max_turns,
        tools=tools,
        enable_tool_intent=enable_tool_intent,
    )

    agent = AgentBase(context)
    return agent
