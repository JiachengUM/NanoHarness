from collections.abc import Iterable

from pydantic import BaseModel, Field, ConfigDict, PrivateAttr

from aicore.models.messages import HumanMessage, AIMessage
from aicore.models.model_api import ModelState, ModelStateDump
from aicore.core.event import EventBase

# 这里有个大坑：类型参数E如果约束为EventBase，用StateBase做model_validate_json反序列化时会用EventBase作类型检查，结果失败。
# 必须使用带真实类型参数的State class做反序列化。
class StateBase[E: EventBase](BaseModel):
    """Agent 状态，记录agent运行过程和结果。用于Agent的组件之间交换数据。"""
    # 允许任意类型，方便扩展和继承
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_api_state: ModelState | None = Field(
        default=None,
        description="接续模型调用上下文",
        exclude=True,
    )
    """provider-owned 模型续接状态，只在进程内使用，不参与持久化。"""

    model_api_state_dump: ModelStateDump | None = Field(
        default=None,
        description="模型 provider 可持久化续接状态",
    )
    """provider-owned 模型续接状态的可序列化 dump。"""

    _message_history: list[tuple[HumanMessage, AIMessage]] = PrivateAttr(
        default_factory=list
    )
    """供 memory、展示和业务状态使用的对话摘要，不是 provider transcript。"""

    @property
    def message_history(self) -> tuple[tuple[HumanMessage, AIMessage], ...]:
        """agent 可读的人类对话历史。"""

        return tuple(self._message_history)

    def append_message_history(
        self,
        query: HumanMessage,
        answer: AIMessage,
    ) -> None:
        """追加一轮用户可见对话历史。"""

        self._message_history.append((query, answer))

    _trace: list[E] = PrivateAttr(default_factory=list)
    """运行过程轨迹，供 review 和 debug。"""

    @property
    def trace(self) -> tuple[E, ...]:
        """运行过程轨迹。"""

        return tuple(self._trace)

    def append_trace(self, event: E) -> None:
        """追加一条运行轨迹事件。"""

        self._trace.append(event)

    def extend_trace(self, events: Iterable[E]) -> None:
        """批量追加运行轨迹事件。"""

        self._trace.extend(events)
