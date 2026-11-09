"""CaseRunner：自动测试主调度框架。

设计原则（见 CONTEXT.md §0）：
- 调度器主动回调：EventScheduler 跑主循环，事件就绪时回调 Runner
- 简单直白的命名：SUT → TestedAssistant（被测助手）
- 实现即测试：每个组件都有对应测试
"""

from projects.experiments.time_travel_auto_test.case_runner.scheduler import (
    EventScheduler,
    EventSource,
    ScheduledEvent,
)
from projects.experiments.time_travel_auto_test.case_runner.timeline import (
    TimelineEngine,
)
from projects.experiments.time_travel_auto_test.case_runner.trace import (
    TraceRecorder,
    TraceSlice,
    UtteranceRecord,
    StateCheckRecord,
)
from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    AssistantProtocol,
    StreamingReply,
    is_assistant,
)
from projects.experiments.time_travel_auto_test.case_runner.runner import (
    CaseRunner,
    RunResult,
    RunnerConfig,
)
from projects.experiments.time_travel_auto_test.case_runner.fake_person_driver import (
    FakePersonDriver,
)
from projects.experiments.time_travel_auto_test.case_runner.virtual_car_driver import (
    VirtualCarDriver,
)

__all__ = [
    # Scheduler
    "EventScheduler",
    "EventSource",
    "ScheduledEvent",
    # Timeline
    "TimelineEngine",
    # Trace
    "TraceRecorder",
    "TraceSlice",
    "UtteranceRecord",
    "StateCheckRecord",
    # Assistant
    "AssistantProtocol",
    "StreamingReply",
    "is_assistant",
    # Runner
    "CaseRunner",
    "RunResult",
    "RunnerConfig",
    # Drivers
    "FakePersonDriver",
    "VirtualCarDriver",
]
