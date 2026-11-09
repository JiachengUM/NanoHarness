"""adapter_v2：新接入协议（事件源适配器模式）的独立验证目录。

与旧 case_runner/assistant_protocol.py 完全独立，不动现有代码；
仅复用与协议无关的基础设施（TimelineEngine / TraceRecorder / VirtualCar）。
"""

from projects.experiments.time_travel_auto_test.adapter_v2.protocol import (
    AdapterEnv,
    AssistantAdapter,
    AssistantEvent,
    Capabilities,
    EventType,
    SourcedEvent,
    Turn,
    TurnKind,
    WorldUpdate,
    is_adapter,
)
from projects.experiments.time_travel_auto_test.adapter_v2.turn_muxer import (
    TurnMuxer,
    run_turn,
)

__all__ = [
    "AdapterEnv",
    "AssistantAdapter",
    "AssistantEvent",
    "Capabilities",
    "EventType",
    "SourcedEvent",
    "Turn",
    "TurnKind",
    "TurnMuxer",
    "WorldUpdate",
    "is_adapter",
    "run_turn",
]