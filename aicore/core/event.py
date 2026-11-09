from typing import Protocol, Type, Callable, Literal, Any, AsyncGenerator

from abc import ABC, abstractmethod

from functools import cached_property
from collections import Counter

from pydantic import BaseModel, Field, ConfigDict
import uuid
from datetime import datetime

class EventBase(BaseModel):
    """
    所有事件的基类。
    """

    # 开启严格模式，不允许额外字段。开启冻结模式，防止字段被修改。
    model_config = ConfigDict(extra='forbid', frozen=True)

    # 用default_factory确保每个示例都有唯一的ID。
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # 用default_factory确保每个示例都有当前的时间戳。
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # 用于区分运行时类型，由子类自动填充，无需手动赋值。
    type: Literal["undefined"] = Field(default="undefined", init=False)


class EventListener[E: EventBase](Protocol):
    """事件流监听器的通用定义。用于print, log等。
    1. 旁路处理，不是业务核心逻辑。
    2. 对于event只读，不修改，对事件流无影响。业务不依赖它。
    3. 可以异步和并行。
    """

    # TODO: 需要改成async
    def __call__(self, event: E) -> None:
        ...

class EventPrinter[E: EventBase]():
    """
    一种特殊的监听器，用于打印事件。用于调试。
    """

    def __init__(self, *, print: Callable[..., None] = print):
        self.print = print
        
    def __call__(self, event: E) -> None:
        self.print(event)


class EventCapturer[E: EventBase](BaseModel):
    """
    一种特殊的监听器。捕获事件并统计。
    注意必须用__call__捕获全部事件后再使用event_types和event_type_counter属性。它们只cache一次。
    """

    events: list[E] = []

    def __call__(self, event: E) -> None:
        self.events.append(event)

    @cached_property
    def event_types(self) -> list[Type[E]]:
        return [type(event) for event in self.events]

    @cached_property
    def event_type_counter(self) -> Counter[Type[E]]:
        return Counter(self.event_types)

    def dump(self, *, print: Callable[..., None] = print, print_types: bool = False):
        print(f"Captured {len(self.events)} events with {len(self.event_type_counter)} types.")
        if print_types:
            print(self.event_types)
        print(self.event_type_counter)


class EventGenerator[E: EventBase](ABC):

    @abstractmethod
    async def astream(self, input: Any, /, **kwargs: Any) -> AsyncGenerator[E, None]:
        # TODO: 这里可以加入通用的event_listener参数
        raise NotImplementedError
        yield EventBase()  # 虽然不会运行,但需要有个yield, 否则会报错：async for requires an object with __aiter__ method

    async def run_astream(
        self, 
        query: str,
        /, 
        event_listeners: list[EventListener[E]] | None = None,
        **kwargs: Any
    ) -> None:
        """简单的helper"""

        event_listeners = event_listeners or []    
        async for event in self.astream(query, **kwargs):
            # 调用事件监听器
            for event_listener in event_listeners:
                event_listener(event)
