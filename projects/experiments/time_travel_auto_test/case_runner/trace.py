"""TraceRecorder：记录测试过程的完整轨迹。

职责：
- 按时间顺序记录每个事件（假人说话、助手回复、车态变更、状态检查、快进）
- 话语以时间区间记录（started_at → ended_at），时间戳来自自然流逝的虚拟时间
- 中立观察者模型（框架不打断被测助手）：is_partial 出现于回复超时被截断（基建兜底）
  或助手响应插话打断自中断旧流（interrupted_by_barge_in=True 区分成因）；
  假人与助手同时说话按各自区间如实记录，get_overlaps() 检测重叠窗口
- 提供 Judge 评判所需的完整 trace

设计原则（见 CONTEXT.md §0.2）：
- 简单的数据结构，不做过度抽象
- 用 Pydantic BaseModel 规范结构（§0.10）
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from projects.experiments.time_travel_auto_test.visualizer.event_bus import (
    EventBus,
    serialize_segments,
    to_jsonable,
)


class RecordKind(str, Enum):
    """Trace 记录类型。"""
    FAKE_PERSON_SPEAK = "fake_person_speak"
    ASSISTANT_REPLY = "assistant_reply"
    VIRTUAL_CAR_SET_STATE = "virtual_car_set_state"
    VIRTUAL_CAR_STATE_CHECK = "virtual_car_state_check"
    ACCELERATION = "acceleration"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"           # 助手工具调用
    TOOL_RESULT = "tool_result"       # 助手工具返回
    TOOL_MERGED = "tool_merged"       # 渲染层配对合并后的工具区间（不落盘，仅 Judge 视图）
    LONG_PAUSE = "long_pause"         # 流式回复中的异常停顿


class UtteranceRecord(BaseModel):
    """一次发言记录（假人或助手）。

    话语是耗时说出来的：started_at 为开口时刻，ended_at 为说完时刻，
    两者都落在自然流逝的虚拟时间线上。
    """
    role: str                          # "fake_person:driver" / "assistant"
    content: str                       # 完整内容（被打断时为已说出的部分）
    started_at: datetime               # 开口时刻（虚拟时间）
    ended_at: datetime                 # 说完时刻（虚拟时间）
    is_partial: bool = False           # 是否半截话（被打断，只说了一部分）
    interrupted_by_barge_in: bool = False  # 半截话成因：助手响应用户插话打断自中断旧流（区别于超时截断）
    # 时序信息（事件流协议 v2）
    speech_duration: Optional[float] = None   # 说话耗时（秒），假人侧
    ttft: Optional[float] = None              # 首字延迟（秒），助手侧
    is_proactive: bool = False                # 是否助手主动开口（如定时提醒触发）
    # chunk 级时间戳（事件流协议 v3）：[(时刻, 文本增量), ...]
    # 假人侧来自 text_delta 事件，助手侧来自 TEXT_DELTA 事件，时刻为虚拟时间。
    # 支撑重叠说话渲染：按 chunk 时刻切出任意时间窗内的文字内容。
    segments: list[tuple[datetime, str]] = Field(default_factory=list)


class StateCheckRecord(BaseModel):
    """状态检查结果记录。"""
    expected_fields: dict[str, Any]
    actual_fields: dict[str, Any]
    passed: bool
    mismatches: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TraceSlice(BaseModel):
    """时间切片：同一时间点发生的所有事件。"""
    at: datetime
    records: list[UtteranceRecord | StateCheckRecord] = Field(default_factory=list)


class TraceRecorder:
    """轨迹记录器。

    可选注入 event_bus（旁路事件总线）：每次 record_* 落盘的同时向前端
    发射层1事件（零新增埋点）。不注入则行为与旧版完全一致。
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._records: list[tuple[datetime, RecordKind, Any]] = []
        self._bus = event_bus

    def _emit(self, kind: str, payload: dict[str, Any], mock_time: Optional[datetime]) -> None:
        """层1事件发射（旁路，无订阅者时零开销）。"""
        if self._bus is not None:
            self._bus.emit(kind, payload, mock_time)

    def record_utterance(
        self,
        role: str,
        content: str,
        *,
        kind: RecordKind,
        started_at: datetime,
        ended_at: datetime,
        is_partial: bool = False,
        interrupted_by_barge_in: bool = False,
        speech_duration: Optional[float] = None,
        ttft: Optional[float] = None,
        is_proactive: bool = False,
        segments: Optional[list[tuple[datetime, str]]] = None,
    ) -> None:
        """记录一次发言（区间化：started_at 开口 → ended_at 说完）。

        排序时间戳用 started_at（开口时刻），保证时间线按"谁先开口"阅读。
        segments 为 chunk 级时间戳（虚拟时间），供重叠说话渲染切片用。
        事件信封 mock_time 用 ended_at（落盘时刻）——话语进行中的 delta 事件
        已携带更晚的虚拟时间，落盘事件若回填 started_at 会造成信封流时间倒退。
        """
        ts = started_at or ended_at
        record = UtteranceRecord(
            role=role,
            content=content,
            started_at=started_at,
            ended_at=ended_at,
            is_partial=is_partial,
            interrupted_by_barge_in=interrupted_by_barge_in,
            speech_duration=speech_duration,
            ttft=ttft,
            is_proactive=is_proactive,
            segments=segments or [],
        )
        self._records.append((ts, kind, record))
        self._emit(
            "utterance",
            {
                "speaker_kind": kind.value,
                "role": role,
                "content": content,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "is_partial": is_partial,
                "interrupted_by_barge_in": interrupted_by_barge_in,
                "speech_duration": speech_duration,
                "ttft": ttft,
                "is_proactive": is_proactive,
                "segments": serialize_segments(record.segments),
            },
            ended_at,
        )

    def record_state_check(
        self,
        at: datetime,
        result: StateCheckRecord,
    ) -> None:
        """记录一次状态检查。"""
        self._records.append((at, RecordKind.VIRTUAL_CAR_STATE_CHECK, result))
        self._emit("state_check", result.model_dump(mode="json"), at)

    def record_set_state(
        self,
        at: datetime,
        updated_fields: dict[str, Any],
        source: Optional[str] = None,
    ) -> None:
        """记录一次车态 set_state。

        source 标注变更来源（可视化三色区分）：
        - "script"：上帝视角剧本 set_state
        - "assistant"：被测助手车控工具
        - "fake_person"：假人直接操作（预留）
        None = 旧调用方（未知来源，前端按中性处理）
        """
        self._records.append(
            (at, RecordKind.VIRTUAL_CAR_SET_STATE, {"updated_fields": updated_fields, "source": source})
        )
        self._emit(
            "car_set_state",
            {"updated_fields": to_jsonable(updated_fields), "source": source},
            at,
        )

    def record_acceleration(
        self,
        from_time: datetime,
        to_time: datetime,
    ) -> None:
        """记录一次快进。

        使用模拟目标时间 to_time 排序，确保快进事件在 trace 中出现在
        正确的逻辑时间位置（而非 wall-clock 时间）。
        """
        self._records.append((to_time, RecordKind.ACCELERATION, {"from": from_time, "to": to_time}))
        self._emit(
            "acceleration",
            {"from": from_time.isoformat(), "to": to_time.isoformat()},
            to_time,
        )

    def record_system_event(
        self,
        at: datetime,
        kind: str,
        description: str,
    ) -> None:
        """记录一个系统级事件（如 WorldTick 锚点到达）。"""
        self._records.append((at, RecordKind.SYSTEM, {"kind": kind, "description": description}))
        self._emit("system", {"kind": kind, "description": description}, at)

    def record_tool_call(
        self,
        at: datetime,
        tool_name: str,
        tool_args: dict[str, Any],
        task_id: Optional[str] = None,
    ) -> None:
        """记录一次助手工具调用。

        task_id 用于与对应 TOOL_RESULT 精确配对（并行同名工具不误配）；
        非 v2 异步路径（无 task_id）传 None，前端回退 tool_name FIFO 配对。
        """
        self._records.append((at, RecordKind.TOOL_CALL, {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "task_id": task_id,
        }))
        self._emit(
            "tool_call",
            {"tool_name": tool_name, "tool_args": to_jsonable(tool_args), "task_id": task_id},
            at,
        )

    def record_tool_result(
        self,
        at: datetime,
        tool_name: str,
        result: Any,
        duration_ms: float,
        task_id: Optional[str] = None,
    ) -> None:
        """记录一次工具调用返回。"""
        self._records.append((at, RecordKind.TOOL_RESULT, {
            "tool_name": tool_name,
            "result": result,
            "duration_ms": duration_ms,
            "task_id": task_id,
        }))
        self._emit(
            "tool_result",
            {
                "tool_name": tool_name,
                "result": to_jsonable(result),
                "duration_ms": duration_ms,
                "task_id": task_id,
            },
            at,
        )

    def record_long_pause(
        self,
        at: datetime,
        pause_seconds: float,
    ) -> None:
        """记录一次流式回复中的异常停顿。"""
        self._records.append((at, RecordKind.LONG_PAUSE, {
            "pause_seconds": round(pause_seconds, 3),
            "description": f"流式停顿 {pause_seconds:.1f}s",
        }))
        self._emit("long_pause", {"pause_seconds": round(pause_seconds, 3)}, at)

    # ---------------- 导出 ----------------

    @property
    def records(self) -> list[tuple[datetime, RecordKind, Any]]:
        return list(self._records)

    def get_slices(self) -> list[TraceSlice]:
        """按时间分组为时间切片。"""
        if not self._records:
            return []
        # 按时间排序
        sorted_records = sorted(self._records, key=lambda x: x[0])
        slices: list[TraceSlice] = []
        current_at: Optional[datetime] = None
        current_records: list = []
        for ts, kind, record in sorted_records:
            if current_at is None or ts != current_at:
                if current_records:
                    slices.append(TraceSlice(at=current_at, records=current_records))
                current_at = ts
                current_records = [record]
            else:
                current_records.append(record)
        if current_records:
            slices.append(TraceSlice(at=current_at, records=current_records))
        return slices

    def get_utterances(self) -> list[UtteranceRecord]:
        """获取所有发言记录（按开口时刻排序）。"""
        return [
            r for _, kind, r in sorted(self._records, key=lambda x: x[0])
            if kind in (RecordKind.FAKE_PERSON_SPEAK, RecordKind.ASSISTANT_REPLY)
            and isinstance(r, UtteranceRecord)
        ]

    def get_state_checks(self) -> list[tuple[datetime, StateCheckRecord]]:
        """获取所有状态检查记录。"""
        return [
            (ts, r) for ts, kind, r in sorted(self._records, key=lambda x: x[0])
            if kind == RecordKind.VIRTUAL_CAR_STATE_CHECK and isinstance(r, StateCheckRecord)
        ]

    def get_overlaps(self) -> list[tuple[datetime, datetime, UtteranceRecord, UtteranceRecord]]:
        """检测假人与助手话语的时间重叠窗口。

        返回 [(窗口起点, 窗口终点, 假人话语, 助手话语), ...]，按窗口起点排序。
        假人侧与助手侧各自的话语在框架内天然串行（同一时刻只有一个人在说），
        因此任意重叠窗口 = 某句假人话语与某句助手话语的区间交集。
        """
        utterances = self.get_utterances()
        fps = [u for u in utterances if u.role.startswith("fake_person:")]
        assts = [u for u in utterances if u.role == "assistant"]
        overlaps: list[tuple[datetime, datetime, UtteranceRecord, UtteranceRecord]] = []
        for fp in fps:
            for asst in assts:
                ws = max(fp.started_at, asst.started_at)
                we = min(fp.ended_at, asst.ended_at)
                if ws < we:
                    overlaps.append((ws, we, fp, asst))
        overlaps.sort(key=lambda x: x[0])
        return overlaps

    def summary(self) -> dict[str, Any]:
        """生成 trace 摘要供 Judge 使用。"""
        utterances = self.get_utterances()
        state_checks = self.get_state_checks()
        overlaps = self.get_overlaps()
        return {
            "total_utterances": len(utterances),
            "total_state_checks": len(state_checks),
            "state_checks_passed": sum(1 for _, sc in state_checks if sc.passed),
            "state_checks_failed": sum(1 for _, sc in state_checks if not sc.passed),
            "has_partial_utterance": any(u.is_partial for u in utterances),
            "has_overlapping_speech": bool(overlaps),
            "overlap_count": len(overlaps),
            "dialogue_text": "\n".join(
                f"[{u.role}]{'(半截话，被用户插话打断)' if u.interrupted_by_barge_in else ('(半截话，超时截断)' if u.is_partial else '')}: {u.content}"
                for u in utterances
            ),
            "state_check_details": [
                {
                    "at": ts.isoformat(),
                    "passed": sc.passed,
                    "expected": sc.expected_fields,
                    "actual": sc.actual_fields,
                    "mismatches": sc.mismatches,
                }
                for ts, sc in state_checks
            ],
        }
