from typing import AsyncGenerator

from pydantic import BaseModel, Field, ConfigDict

from aicore.utils.nl_repr import nl_repr

from aicore.tools import BaseTool
from aicore.models.responses import AsyncArk, ResponseParams, Response

from aicore.agents.events import (
    ReActEvent, 
    ReActCompletedEvent, 
    ReActEventListener, 
    EventCapturer,
)

from aicore.agents.react import _astream_react_naive

AgentEvent = ReActEvent

class RunParams(BaseModel):
    """通用master agent。"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str = Field(..., description="模型名称")
    client: AsyncArk = Field(..., description="AsyncArk 客户端", repr=False, exclude=True)
    params: ResponseParams | None = Field(default=None, description="模型参数")
    max_turns: int = Field(default=5, description="最大轮数")


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


class AgentBase:
    """通用master agent。还远不成熟。刚开始。"""
    def __init__(
        self, 
        system_prompt: str | SystemPrompt | BaseModel,
        /,
        *,
        run_params: RunParams,
        tools: list[BaseTool] = Field(..., description="工具列表"),
    ) -> None:
        """初始化agent。
        TODO: 增加AgentState参数，用于反序列化。
        """
        
        self._system_prompt = system_prompt
        self.run_params = run_params
        self.tools = tools

        self.state = AgentState()
        # 初始时state.run_result为None

    @property
    def system_prompt(self) -> str:
        """系统提示词属性。目前的实现虽然简单，但它不仅仅是个wrapper，而是可扩展的。例如
        - 可以根据self.state定制化
        - 派生类可以重载
        """
        return nl_repr(self._system_prompt)

    async def astream(
        self, 
        query: str,
        /, 
        *,
        event_listeners: list[ReActEventListener],
        **kwargs
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式执行。和ReActAgentBase不同，它不再是astream_react的wrapper，而是需要维护自己的状态。"""

        # 内置事件捕获器
        event_capturer = EventCapturer()
        event_listeners.append(event_capturer)

        # 如果state.run_result不为空，则使用state.run_result.response
        if self.state.run_result:
            previous_response_or_system_prompt = self.state.run_result.response
        else:
            # 初始时state.run_result为None，也就是第一轮对话时，传入system_prompt
            previous_response_or_system_prompt = self.system_prompt

        async for event in _astream_react_naive(
            query,
            previous_response_or_system_prompt,
            client=self.run_params.client,
            model=self.run_params.model,
            tools=self.tools,
            max_turns=self.run_params.max_turns,
            params=self.run_params.params,
            **kwargs,
        ):
            if isinstance(event, ReActCompletedEvent):
                response = event.response

            # 调用事件监听器
            for event_listener in event_listeners:
                event_listener(event)
                            
            yield event

        assert isinstance(response, Response)

        self.state.run_result = RunResult(response=response, events=event_capturer.events)