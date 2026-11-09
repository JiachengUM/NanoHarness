from .react import ReActEventPrinter, ReActEvent, is_react_event
from .task import TaskEventPrinter, TaskEvent, is_task_event
from .explicit_tool_call import (
    ExplicitEvent,
    ExplicitEventPrinter,
    is_explicit_event,
)

__all__ = [
    "ReActTaskEventPrinter",
]


class ReActTaskEventPrinter:
    def __init__(self):
        self.react_event_printer = ReActEventPrinter()
        self.task_event_printer = TaskEventPrinter()
        self.explicit_event_printer = ExplicitEventPrinter()

    def __call__(self, event: ReActEvent | TaskEvent | ExplicitEvent):
        if is_react_event(event):
            self.react_event_printer(event)
        elif is_task_event(event):
            self.task_event_printer(event)
        else:
            assert is_explicit_event(event)
            self.explicit_event_printer(event)
