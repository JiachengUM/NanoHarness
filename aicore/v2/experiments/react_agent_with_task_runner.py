from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
import re
from typing import Any, AsyncGenerator

from pydantic import ConfigDict, Field
from rich import print
from rich.text import Text

from aicore.agents import ContextBase, StateBase
from aicore.events.agent import (
    AgentOutEvent,
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
    TaskCreatedEvent,
    is_agent_out_event,
)
from aicore.events.task import TaskEvent, TaskEventPrinter, TaskSuccessEvent, is_task_event, TaskProgressEvent
from aicore.events.react import (
    ReActTextStartEvent,
    ReActTextDeltaEvent,
    ReActTextDoneEvent,
)
from aicore.models.responses import ResponseInputItemParam
from aicore.models.messages import HumanMessage, AIMessage
from aicore.models.model_api import (
    ModelAPIBackend,
    ModelParams,
    ModelResponse as APIModelResponse,
    create_model_api,
)
from aicore.runtime.task import TaskManager

from aicore.agents.react import ReActEvent, ReActFinishEvent, react_with_stream_tools

from aicore.tools import TaskToolProtocolGeneral
from aicore.utils.nl_repr import nl_repr
from aicore.v2.agent_model import AgentBase, AgentInputEvent

type ToolsType = list[TaskToolProtocolGeneral]
type ReActInputData = str | list[ResponseInputItemParam]
type AmbientContextProvider = Callable[[], str]


__all__ = [
    "AmbientContextProvider",
    "ReactAgentWithTaskRunnerContext",
    "ReactAgentWithTaskRunnerState",
    "AgentOutEventPrinter",
    "AgentTaskEventPrinter",
    "ReactAgentWithTaskRunner",
    "create_react_agent_with_task_runner",
    "render_active_task_context",
]


def _render_context_arg_value(value: str, max_length: int = 80) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    normalized = normalized.replace("用户当前输入:", "用户当前输入：")
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length] + "..."


class ReactAgentWithTaskRunnerContext(ContextBase[TaskToolProtocolGeneral]):
    """v2 React agent 的长期上下文：模型、工具、系统提示词等静态配置。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # TODO(agent dump): ambient_context_provider 是运行时 callback，不能被可靠地序列化或恢复。
    # 当前先保留原字段行为；后续完善 v2 dump/restore 时，应将其排除出持久化数据，
    # 并由 Agent builder 在恢复会话时重新注入，与 ContextBase.tools 的处理保持一致。
    ambient_context_provider: AmbientContextProvider | None = Field(
        default=None,
        description="每轮用户字符串输入前注入的环境任务上下文提供器",
    )


class ReactAgentWithTaskRunnerState(StateBase[ReActEvent | TaskEvent]):
    """v2 React agent 的运行状态：模型续接状态与完整内部事件轨迹。"""


class AgentOutColorMap(StrEnum):
    TEXT_HINT = "cyan"
    TEXT = "bright_white"
    TOOL = "yellow"


class AgentOutEventPrinter:
    """打印 v2 agent 对外事件。"""

    def __init__(self) -> None:
        self.print = print

    def __call__(self, event: AgentOutEvent) -> None:
        match event:
            case AgentOutTextStartEvent():
                self.print(Text("\n") + Text("📝 Agent 文本开始", style=AgentOutColorMap.TEXT_HINT))

            case AgentOutTextDeltaEvent():
                self.print(Text(event.delta, style=AgentOutColorMap.TEXT), end="", flush=True)

            case AgentOutTextDoneEvent():
                self.print(Text("\n") + Text("📝 Agent 文本结束", style=AgentOutColorMap.TEXT_HINT))

            case TaskCreatedEvent():
                self.print(
                    Text("\n")
                    + Text(
                        f"🛠 创建任务 | id={event.task_id} | 名称: {event.name} | 参数: {event.arguments}",
                        style=AgentOutColorMap.TOOL,
                    )
                )


class AgentTaskEventPrinter:
    """同时打印 v2 agent 输出事件和 task runner 事件。"""

    def __init__(self) -> None:
        self.agent_event_printer = AgentOutEventPrinter()
        self.task_event_printer = TaskEventPrinter()

    def __call__(self, event: AgentOutEvent | TaskEvent) -> None:
        if is_agent_out_event(event):
            self.agent_event_printer(event)
        else:
            assert is_task_event(event)
            self.task_event_printer(event)


def render_active_task_context(task_manager: TaskManager) -> str:
    projections = task_manager.get_active_task_projections()
    if not projections:
        return ""

    lines = ["当前活跃任务:"]
    for projection in projections:
        string_args = [
            f"{key}={_render_context_arg_value(value)}"
            for key, value in projection.arguments.items()
            if isinstance(value, str)
        ]
        summary = (
            f"{projection.tool_name}({', '.join(string_args)})"
            if string_args
            else projection.tool_name
        )
        lines.append(f"- {summary}: {projection.status.value}")

    return "\n".join(lines)


def _react_to_agent_out_event(raw_event: ReActEvent | TaskEvent) -> AgentOutEvent | ReActFinishEvent[Any] | TaskProgressEvent[Any] | None:
    match raw_event:
        case ReActTextStartEvent():
            return AgentOutTextStartEvent()

        case ReActTextDeltaEvent():
            return AgentOutTextDeltaEvent(delta=raw_event.delta)

        case ReActTextDoneEvent():
            return AgentOutTextDoneEvent()

        case ReActFinishEvent():
            return raw_event
        
        # 目前这里的TaskProgressEvent是create_tasks_tool yield的内部事件。
        case TaskProgressEvent():
            if isinstance(raw_event.progress,TaskCreatedEvent):
                return raw_event.progress
            else:
                # 其他类型的 TaskProgress 事件先保留
                return raw_event
        
        case _:
            return None


class ReactAgentWithTaskRunner(AgentBase):
    """适配 v2 runner 的 React agent：模型流式输出，工具由异步 task runner 执行。"""

    def __init__(
        self, 
        context: ReactAgentWithTaskRunnerContext,
        /,
        *,
        state: ReactAgentWithTaskRunnerState | None = None,
    ) -> None:
        self._context = context
        self._state = state or ReactAgentWithTaskRunnerState()
        if self._state.model_api_state is None and self._state.model_api_state_dump is not None:
            self._state.model_api_state = context.model_api.restore_state(self._state.model_api_state_dump)
            self._state.model_api_state_dump = None

    @property
    def context(self) -> ReactAgentWithTaskRunnerContext:
        return self._context

    @property
    def state(self) -> ReactAgentWithTaskRunnerState:
        return self._state

    @property
    def tools(self) -> ToolsType:
        return self.context.tools or []

    @property
    async def system_prompt(self) -> str:
        return nl_repr(self.context.system_prompt)

    async def new_session(self) -> None:
        self._state = ReactAgentWithTaskRunnerState()

    async def astream(
        self,
        input: AgentInputEvent,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentOutEvent| TaskProgressEvent[Any], None]:
        response: APIModelResponse[Any] | None = None
        user_query: str | None = None
        previous_state = self.state.model_api_state

        if isinstance(input, str):
            user_query = input
            # 首轮：previous = system_prompt（str）；续轮：previous = 上一轮的 Response，
            # 利用火山方舟 previous_response_id 机制延续对话上下文。
            ambient_context = ""
            if self.context.ambient_context_provider is not None:
                ambient_context = self.context.ambient_context_provider().strip()
            input_data: ReActInputData = (
                f"{ambient_context}\n\n用户当前输入:\n{input}"
                if ambient_context
                else input
            )
        elif isinstance(input, TaskSuccessEvent):
            # 异步 task 真实结果到达：作为一条 user message 追加到链上，而不是再写一次同
            # call_id 的 function_call_output（call_id 已在占位 fc_output 里被一次性消费）。
            # 由此 previous_state 始终是上一轮 agent.astream 留下的模型状态，链路 append-only。
            assert previous_state is not None, "收到任务结果时必须已有上一轮模型状态"
            # 回灌 payload 自己实现 nl_repr 协议，agent 层不拼接具体文本格式。
            input_data = nl_repr(input.result)

        model_api = create_model_api(
            backend=self.context.model_api_backend,
            model=self.context.model_params.model,
        )
        model_state = (
            previous_state
            if previous_state is not None
            else model_api.initial_state(system_prompt=await self.system_prompt)
        )

        async for raw_event in react_with_stream_tools(
            input_data,
            model_api=model_api,
            state=model_state,
            tools=self.tools,
            max_turns=self.context.react_max_turns,
            params=self.context.model_params.params,
            **kwargs,
        ):
            # trace 保存完整内部事件；对外只透传投影后的 AgentOutEvent。
            # 逐条写入可确保 ReAct 中途失败时仍保留已经发生的轨迹。
            self.state.append_trace(raw_event)
            # ReActFinishEvent 是内部事件：截获最终 Response 用于更新 model_api_state，
            # 不向外（runner / client）转发。仿 v1 master.py 截获 ReActFinishEvent 的写法。
            event = _react_to_agent_out_event(raw_event)
            if isinstance(event, ReActFinishEvent):
                response = event.response
                break

            if event:
                yield event

        if response is not None:
            self.state.model_api_state = response.state
            if user_query is not None:
                self.state.append_message_history(
                    HumanMessage(content=user_query),
                    AIMessage(content=response.text or ""),
                )

    async def dump(self) -> tuple[ReactAgentWithTaskRunnerContext, ReactAgentWithTaskRunnerState]:
        """序列化当前 agent 的 context/state。"""
        if self.state.model_api_state is not None:
            self.state.model_api_state_dump = await self.context.model_api.dump_state(
                self.state.model_api_state
            )
        return self.context, self.state


def create_react_agent_with_task_runner(
    model: str,
    tools: ToolsType | None = None,
    max_turns: int = 5,
    system_prompt: str = "你是友好的用户智能助手",
    ambient_context_provider: AmbientContextProvider | None = None,
    model_api_backend: ModelAPIBackend = "responses",
) -> ReactAgentWithTaskRunner:
    model_params = ModelParams(model=model)
    context = ReactAgentWithTaskRunnerContext(
        system_prompt=system_prompt,
        model_params=model_params,
        model_api_backend=model_api_backend,
        react_max_turns=max_turns,
        tools=tools,
        ambient_context_provider=ambient_context_provider,
    )

    return ReactAgentWithTaskRunner(context)
