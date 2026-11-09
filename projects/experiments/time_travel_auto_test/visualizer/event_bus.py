"""旁路事件总线：把测试执行过程实时发射给外部观察者（可视化前端）。

中立观察者原则：事件总线是纯旁路——只读观察 TraceRecorder / Runner 的
关键事实，不参与任何执行决策、不影响被测助手。trace 落盘仍是唯一判卷依据。

事件信封（双时间戳是本框架特色，支撑实时/回放两套坐标系）：
{
  "seq": 42,                      # 进程内自增序号（排序/去重）
  "wall_time": "2026-08-26T...",  # 真实墙钟（实时模式坐标系）
  "mock_time": "2026-08-26T...",  # 虚拟时间（回放模式坐标系；层1事件=记录时间戳）
  "kind": "utterance",            # 事件类型
  "payload": {...}                # 结构化原始字段（不预渲染，前端自行呈现）
}

事件分两层：
- 层1（TraceRecorder 落盘即推）：utterance / state_check / car_set_state /
  acceleration / system / tool_call / tool_result / long_pause——零新增埋点，
  record_* 每次调用即发射
- 层2（Runner 过程事件）：case_started / case_finished / fake_person_delta /
  assistant_delta 等——补过程感（chunk 逐字到达、生命周期边界）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

# 同步回调：handler(信封 dict)。订阅方（如 WS 服务器）自行放入 asyncio.Queue。
EventHandler = object  # Callable[[dict[str, Any]], None]


class EventBus:
    """进程内事件总线（单订阅者，M1 够用）。"""

    def __init__(self) -> None:
        self._seq = 0
        self._handler = None  # Optional[Callable[[dict], None]]

    @property
    def has_subscriber(self) -> bool:
        return self._handler is not None

    def subscribe(self, handler) -> None:
        """订阅事件。后订阅者覆盖先订阅者（单订阅者模型）。"""
        self._handler = handler

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        mock_time: Optional[datetime],
    ) -> int:
        """发射一个事件。无订阅者时静默丢弃（零开销旁路）。

        返回分配的 seq；无订阅者返回 -1。
        """
        if self._handler is None:
            return -1
        self._seq += 1
        envelope = {
            "seq": self._seq,
            "wall_time": datetime.now().isoformat(),
            "mock_time": mock_time.isoformat() if mock_time else None,
            "kind": kind,
            "payload": payload,
        }
        self._handler(envelope)
        return self._seq


def serialize_segments(
    segments: list[tuple[datetime, str]],
) -> list[list[str]]:
    """segments: [(datetime, 文本增量), ...] → JSON 友好的 [[iso, str], ...]。"""
    return [[ts.isoformat(), text] for ts, text in segments]


def to_jsonable(value: Any) -> Any:
    """递归转换为 JSON 可序列化值（工具参数/返回值等 Any 类型兜底）。"""
    from datetime import datetime as _dt

    from pydantic import BaseModel as _BaseModel

    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, _dt):
        return value.isoformat()
    if isinstance(value, _BaseModel):
        return value.model_dump(mode="json")
    return str(value)
