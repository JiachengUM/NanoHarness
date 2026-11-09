from typing import Literal, assert_never, Any, TypeIs
from enum import StrEnum

from rich import print
from rich.text import Text

from aicore.core.event import EventBase, Field

__all__ = [
    "TaskEventBase",
    "TaskCreatedEvent",
    "TaskStartEvent",
    "TaskProgressEvent",
    "TaskSuccessEvent",
    "TaskFailureEvent",
    "TaskCancelledEvent",
    "TaskEvent",
    "is_task_event",
    "TaskEventPrinter",
]

class TaskEventBase(EventBase):
    """所有任务事件的基类"""
    type: Literal["task.base"] = Field(default="task.base", init=False)  # type: ignore
    
    task_id: str

class TaskCreatedEvent(TaskEventBase):
    """任务创建。和任务开始执行是不同的。"""
    type: Literal["task.created"] = Field(default="task.created", init=False)  # type: ignore

    name: str

    arguments: dict[str, Any] = Field(default_factory=dict)

class TaskStartEvent(TaskEventBase):
    """任务开始执行"""
    type: Literal["task.start"] = Field(default="task.start", init=False)  # type: ignore


class TaskProgressEvent[P](TaskEventBase):
    """任务进度/中间流式数据"""
    type: Literal["task.progress"] = Field(default="task.progress", init=False)  # type: ignore

    # progress 可以是 str (LLM token), dict (步骤信息), int (百分比) 等
    progress: P

class TaskSuccessEvent[R](TaskEventBase):
    """任务成功结束"""
    type: Literal["task.success"] = Field(default="task.success", init=False)  # type: ignore

    result: R


class TaskFailureEvent[E](TaskEventBase):
    """任务失败结束"""
    type: Literal["task.failure"] = Field(default="task.failure", init=False)  # type: ignore
    
    error: E

class TaskCancelRequest(TaskEventBase):
    """任务取消请求
    TODO: 关于request类的event，不知道是否应该和普通event区分开。
    """
    type: Literal["task.cancel"] = Field(default="task.cancel", init=False)  # type: ignore

    intent: str


class TaskCancelledEvent(TaskEventBase):
    """任务取消：只需要知道原因"""
    type: Literal["task.cancelled"] = Field(default="task.cancelled", init=False)  # type: ignore
    
    reason: str | None = None

# 定义一个联合类型，方便类型提示
# 不能加泛型参数，否则不能用于isinstance
TaskEvent = TaskCreatedEvent | TaskStartEvent | TaskProgressEvent[Any] | TaskSuccessEvent[Any] | TaskFailureEvent[Any] | TaskCancelledEvent

def is_task_event(event: Any) -> TypeIs[TaskEvent]:
    # ReActEvent 包含泛型参数，不能直接用于 isinstance
    return isinstance(event, (TaskCreatedEvent, TaskStartEvent, TaskProgressEvent, TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent))


###################### 辅助功能
class TaskColorMap(StrEnum):
    CREATED = "yellow"
    START = "bright_blue"
    PROGRESS = "bright_white"
    SUCCESS = "green"
    CANCEL = "orange"
    ERROR = "red"


class TaskEventPrinter:
    """print事件。"""

    def __init__(self) -> None:
        # 缺省使用rich print
        self.print = print

    def __call__(self, event: TaskEvent) -> None:
        match event:
            # 用 Text+style，避免模型输出里的 [] 破坏Rich标记
            case TaskCreatedEvent():
                self.print(Text("\n") + Text(f"🛠 Task({event.task_id}) 创建 | 名称: {event.name}", style=TaskColorMap.CREATED))

            case TaskStartEvent():
                self.print(Text("\n") + Text(f"🚀 Task({event.task_id}) 开始", style=TaskColorMap.START))

            case TaskProgressEvent():
                self.print(Text("\n") + Text(f"📝 Task({event.task_id}) 进度: {event.progress}", style=TaskColorMap.PROGRESS))

            case TaskSuccessEvent():
                self.print(Text("\n") + Text(f"📤 Task({event.task_id}) 成功 | 输出: {event.result}", style=TaskColorMap.SUCCESS))

            case TaskFailureEvent():
                self.print(Text("\n") + Text(f"❌ Task({event.task_id}) 失败 | 错误: {event.error}", style=TaskColorMap.ERROR))

            case TaskCancelledEvent():
                self.print(Text("\n") + Text(f"⚠️ Task({event.task_id}) 取消 | 原因: {event.reason}", style=TaskColorMap.CANCEL))

            case _:
                assert_never(event)


