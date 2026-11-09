from enum import StrEnum

from typing import Literal, Any, Union, TypeIs, assert_never

from rich import print
from rich.text import Text

from pydantic import Field

from aicore.core.event import EventBase, EventListener
from aicore.core.types import SafeResult

__all__ = [
    "ReActStartEvent",
    "ToolCallStartEvent",
    "ReActTextStartEvent",
    "ReActTextDeltaEvent",
    "ReActTextDoneEvent",
    "TaskToolDoneEvent",
    "ToolCallsDoneEvent",
    "ReActErrorEvent",
    "ReActFinishEvent",
    "ReActEvent",
    "ReActEventListener",
    "ReActEventPrinter",
]

class ReActStartEvent(EventBase):
    """会话开始：Agent 开始推理，只发一次"""
    type: Literal["react.start"] = Field(default="react.start", init=False)  # type: ignore
    
class ReActTextStartEvent(EventBase):
    """文本流式开始：模型即将开始输出文本"""
    type: Literal["react.text.start"] = Field(default="react.text.start", init=False)  # type: ignore
    

class ReActTextDeltaEvent(EventBase):
    """文本流式增量：模型输出文本的一小段"""
    type: Literal["react.text.delta"] = Field(default="react.text.delta", init=False)  # type: ignore
    delta: str
    
class ReActTextDoneEvent(EventBase):
    """文本流式结束：当前段文本输出完毕"""
    type: Literal["react.text.done"] = Field(default="react.text.done", init=False)  # type: ignore
    text: str
    
class ToolCallStartEvent(EventBase):
    """工具调用开始：模型请求调用工具，外部需执行"""
    type: Literal["react.tool_call.start"] = Field(default="react.tool_call.start", init=False)  # type: ignore
    name: str
    arguments: dict[str, object]
    round: int = Field(..., description="轮次")

class TaskToolDoneEvent[OT](EventBase):
    type: Literal["task_tool.done"] = Field(default="task_tool.done", init=False)  # type: ignore
    output: SafeResult[OT]
    
class ToolCallsDoneEvent(EventBase):
    """工具调用结束：工具执行完成，结果返回给模型"""
    type: Literal["react.tool_results.done"] = Field(default="react.tool_results.done", init=False)  # type: ignore
    tool_results: list[str]
    round: int = Field(..., description="轮次")

# 完成：Agent 给出最终答案（成功）
class ReActFinishEvent[R](EventBase):
    """完成：Agent 给出最终答案（成功）"""
    type: Literal["react.finish"] = Field(default="react.finish", init=False)  # type: ignore
    response: R
    round: int = Field(..., description="轮次")
    forced: bool = Field(default=False, description="是否强制完成对话。")
    reason: str | None = Field(default=None, description="完成原因")

class ReActErrorEvent(EventBase):
    """失败：未完成或超轮次等"""
    type: Literal["react.error"] = Field(default="react.error", init=False)  # type: ignore
    reason: str | None = Field(default=None, description="失败原因")


# 总事件类型：不包括responses 事件，只有自定义事件
# 不能加泛型参数，否则不能用于isinstance
ReActEvent = Union[
    ReActStartEvent,
    ReActTextStartEvent,
    ToolCallStartEvent,
    ReActTextDeltaEvent,
    ReActTextDoneEvent,
    TaskToolDoneEvent[Any],
    ToolCallsDoneEvent,
    ReActErrorEvent,
    ReActFinishEvent[Any],
]

def is_react_event(event: Any) -> TypeIs[ReActEvent]:
    # ReActEvent 包含泛型参数，不能直接用于 isinstance
    return isinstance(event, (ReActStartEvent, ReActTextStartEvent, ToolCallStartEvent, ReActTextDeltaEvent, ReActTextDoneEvent, TaskToolDoneEvent, ToolCallsDoneEvent, ReActErrorEvent, ReActFinishEvent))

ReActEventListener = EventListener[ReActEvent]


class ReActColorMap(StrEnum):
    START = "bright_blue"
    TEXT_HINT = "cyan"
    TEXT = "bright_white"
    TOOL = "yellow"
    TOOL_RESULT = "bright_green"
    DONE = "green"
    WARNING = "orange"
    ERROR = "red"


class ReActEventPrinter:
    """print事件。"""

    def __init__(self) -> None:
        # 缺省使用rich print
        self.print = print

    def __call__(self, event: ReActEvent) -> None:
        match event:
            # 用 Text+style，避免模型输出里的 [] 破坏Rich标记
            case ReActStartEvent():
                self.print(Text("\n") + Text("🚀 ReAct 开始", style=ReActColorMap.START))

            case ReActTextStartEvent():
                self.print(Text("\n") + Text("📝 ReAct 文本开始", style=ReActColorMap.TEXT_HINT))

            case ReActTextDeltaEvent():
                # 流式文本增量
                self.print(Text(event.delta, style=ReActColorMap.TEXT), end="", flush=True)

            case ReActTextDoneEvent():

                self.print(Text("\n") + Text("📝 文本段结束", style=ReActColorMap.TEXT_HINT))

            case ToolCallStartEvent():
                self.print(Text("\n") + Text(f"🛠 开始调用工具 | round={event.round} | 名称: {event.name} | 参数: {event.arguments}", style=ReActColorMap.TOOL))

            case TaskToolDoneEvent():
                # TODO：先不使用output.nl_repr，如果内容过多，控制台会显示不全。
                self.print(Text("\n") + Text(f"📤 工具调用结果 | 输出: {event.output}", style=ReActColorMap.TOOL_RESULT))

            case ToolCallsDoneEvent():
                self.print(Text("\n") + Text(f"📦 全部工具调用结果 | round={event.round} | 输出: {event.tool_results}", style=ReActColorMap.TOOL_RESULT))

            case ReActFinishEvent():
                if event.forced:
                    self.print(Text("\n") + Text(f"⚠️ ReAct 超过最大循环次数，强制回复 | round={event.round}", style=ReActColorMap.WARNING))
                else:
                    self.print(Text("\n") + Text(f"✅ ReAct 完成 | round={event.round}", style=ReActColorMap.DONE))

            case ReActErrorEvent():
                self.print(Text("\n") + Text(f"❌ ReAct 失败 | 原因: {event.reason}", style=ReActColorMap.ERROR))

            case _:
                 assert_never(event)
