from enum import StrEnum
from typing import Any, Literal, TypeIs, Union, assert_never

from rich import print
from rich.text import Text

from pydantic import Field

from aicore.core.event import EventBase

__all__ = [
    "ExplicitStartEvent",
    "ExplicitTextStartEvent",
    "ExplicitTextDeltaEvent",
    "ExplicitTextDoneEvent",
    "SelectionMissedEvent",
    "ExplicitFinishEvent",
    "ExplicitEvent",
    "is_explicit_event",
    "ExplicitEventPrinter",
]


class ExplicitStartEvent(EventBase):
    """Explicit tool call 流程开始, 只发一次."""

    type: Literal["explicit.start"] = Field(default="explicit.start", init=False)  # type: ignore


class ExplicitTextStartEvent(EventBase):
    """文本流式开始: 模型即将开始输出 finalize 文本."""

    type: Literal["explicit.text.start"] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default="explicit.text.start", init=False
    )


class ExplicitTextDeltaEvent(EventBase):
    """文本流式增量: finalize 文本的一小段."""

    type: Literal["explicit.text.delta"] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default="explicit.text.delta", init=False
    )
    delta: str


class ExplicitTextDoneEvent(EventBase):
    """文本流式结束: finalize 段文本输出完毕."""

    type: Literal["explicit.text.done"] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default="explicit.text.done", init=False
    )
    text: str


class SelectionMissedEvent(EventBase):
    """Selection 层未唯一命中 EXACT 工具.

    explicit primitive 在未命中时 yield 此事件并 return; 调用方 (dispatcher)
    据 outcome 决定下一步 (回退 React / 反问用户 / 兜底文案).

    outcome 实际类型为 NoToolMatch | ClarifyNeeded | Ambiguous, 来自
    aicore.tools.experiments.planning. 字段类型用 Any 避免 pydantic 处理
    dataclass union 字段的额外配置, 调用方用 isinstance 模式匹配即可.
    """

    type: Literal["explicit.selection_missed"] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default="explicit.selection_missed", init=False
    )
    outcome: Any


class ExplicitFinishEvent[R](EventBase):
    """Explicit tool call 完成: 工具已跑完, 模型已基于结果给出最终回答.

    与 ReActFinishEvent 平行但不复用; 不带 round 字段 (explicit 不循环),
    多带一个 tool_name 字段标识本次显式调用的工具.
    """

    type: Literal["explicit.finish"] = Field(default="explicit.finish", init=False)  # pyright: ignore[reportIncompatibleVariableOverride]
    response: R
    tool_name: str = Field(..., description="本次显式调用的工具名")


# 总事件类型 (不含泛型参数, 便于 isinstance)
ExplicitEvent = Union[
    ExplicitStartEvent,
    ExplicitTextStartEvent,
    ExplicitTextDeltaEvent,
    ExplicitTextDoneEvent,
    SelectionMissedEvent,
    ExplicitFinishEvent[Any],
]


def is_explicit_event(event: Any) -> TypeIs[ExplicitEvent]:
    # ExplicitEvent 包含泛型参数, 不能直接用于 isinstance
    return isinstance(
        event,
        (
            ExplicitStartEvent,
            ExplicitTextStartEvent,
            ExplicitTextDeltaEvent,
            ExplicitTextDoneEvent,
            SelectionMissedEvent,
            ExplicitFinishEvent,
        ),
    )


###################### 辅助功能
class ExplicitColorMap(StrEnum):
    START = "bright_blue"
    TEXT_HINT = "cyan"
    TEXT = "bright_white"
    MISS = "orange3"
    DONE = "green"


class ExplicitEventPrinter:
    """print explicit 事件流. 形态与 ReActEventPrinter / TaskEventPrinter 对齐."""

    def __init__(self) -> None:
        self.print = print

    def __call__(self, event: ExplicitEvent) -> None:
        match event:
            case ExplicitStartEvent():
                self.print(
                    Text("\n") + Text("🎯 Explicit 开始", style=ExplicitColorMap.START)
                )

            case ExplicitTextStartEvent():
                self.print(
                    Text("\n")
                    + Text("📝 Explicit 文本开始", style=ExplicitColorMap.TEXT_HINT)
                )

            case ExplicitTextDeltaEvent():
                # 流式文本增量
                self.print(
                    Text(event.delta, style=ExplicitColorMap.TEXT), end="", flush=True
                )

            case ExplicitTextDoneEvent():
                self.print(
                    Text("\n") + Text("📝 文本段结束", style=ExplicitColorMap.TEXT_HINT)
                )

            case SelectionMissedEvent():
                self.print(
                    Text("\n")
                    + Text(
                        f"❓ Explicit 未命中 | outcome: {event.outcome}",
                        style=ExplicitColorMap.MISS,
                    )
                )

            case ExplicitFinishEvent():
                self.print(
                    Text("\n")
                    + Text(
                        f"✅ Explicit 完成 | 工具: {event.tool_name}",
                        style=ExplicitColorMap.DONE,
                    )
                )

            case _:
                assert_never(event)
