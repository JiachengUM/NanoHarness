"""AdapterRunner：新协议（事件源适配器模式）的薄调度器。

对照旧 CaseRunner（case_runner/runner.py），它把「异步工具回灌、空闲判定、
时间换算、hasattr 散落钩子」这些脏活全部甩给了框架——新协议里这些已由
TurnMuxer 统一承担，因此本调度器只需做三件事：

1. 复用与协议无关的基础设施：
   - TimelineEngine    （虚拟时间 + wall→mock 换算）
   - TraceRecorder     （轨迹落盘）+ RecordKind / StateCheckRecord
   - VirtualCar + VirtualCarDriver （车态 + 剧本 set_state / state_check）
   - deliver_fake_person_speech_stream （假人说话节奏，产出 chunk 级 segments）
   - EventScheduler    （锚点/边界事件的 heapq 调度）
2. 把「假人说话」包装成一个 USER Turn，交给 TurnMuxer 消费成统一事件流，
   再按「话语段」落盘到 TraceRecorder（工具事件把流切段）。
3. 打断：新 USER 输入到来、旧回合未耗尽时，框架只做「并发发起新回合 +
   标记旧回合为被插话」，真正中断由被测助手自驱（Capabilities.supports_barge_in）。

彻底中立：本模块不认识任何被测助手的实现，只通过 protocol.AssistantAdapter
接口驱动；也不 import 旧 assistant_protocol。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from projects.experiments.time_travel_auto_test.case_runner.scheduler import (
    EventScheduler,
    ScheduledEvent,
)
from projects.experiments.time_travel_auto_test.case_runner.timeline import TimelineEngine
from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    StateCheckRecord,
    TraceRecorder,
)
from projects.experiments.time_travel_auto_test.case_runner.virtual_car_driver import (
    VirtualCarDriver,
)
from projects.experiments.time_travel_auto_test.case_schema import TestCase
from projects.experiments.time_travel_auto_test.fake_person.event import (
    deliver_fake_person_speech_stream,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarStateCheckScriptEvent,
    WorldTickScriptEvent,
)
from projects.experiments.time_travel_auto_test.visualizer.event_bus import EventBus
from projects.experiments.time_travel_auto_test.virtual_car.models import (
    CAR_INFO_GROUPS,
    VirtualCar,
    VirtualCarSetStateOutcome,
    VirtualCarStateCheckOutcome,
)

from projects.experiments.time_travel_auto_test.adapter_v2.protocol import (
    AdapterEnv,
    AssistantAdapter,
    EventType,
    Turn,
    TurnKind,
    WorldUpdate,
)
from projects.experiments.time_travel_auto_test.adapter_v2.turn_muxer import TurnMuxer


@dataclass
class RunResult:
    """AdapterRunner.run 的结果（对齐裁判/前端所需字段）。"""
    case_id: str
    case_name: str
    trace_summary: dict[str, Any]
    must_pass_assertions: list[str]
    bonus_assertions: list[str]
    state_check_passed: bool
    error: Optional[str] = None


class _TurnHandle:
    """一个进行中的助手回合（供并发跟踪 + 打断标记）。"""
    __slots__ = ("muxer", "turn", "barged_in")

    def __init__(self, muxer: TurnMuxer, turn: Turn) -> None:
        self.muxer = muxer
        self.turn = turn
        # 是否被标记为"被新用户输入插话"（中性观察：只记录事实，不主动中断）
        self.barged_in = False


class AdapterRunner:
    """薄调度器：把新协议的 TurnMuxer 接入脚本事件链路。

    用法：
        runner = AdapterRunner(adapter)
        result = await runner.run(case)          # 完整脚本驱动
        # 或动作级（demo 复用）：
        runner.setup(case)
        await runner.speak("开空调")
        await runner.accelerate_to(t0 + timedelta(seconds=1800))
        await runner.wait_idle()
    """

    def __init__(
        self,
        adapter: AssistantAdapter,
        *,
        chunk_delay: float = 0.02,
        acceleration_threshold: timedelta = timedelta(minutes=1),
        fast_mode: bool = False,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._adapter = adapter
        self._chunk_delay = chunk_delay
        self._acceleration_threshold = acceleration_threshold
        self._fast_mode = fast_mode
        # 旁路事件总线（可视化）：层1由 TraceRecorder 发射、层2由本类发射。
        # 不注入则零开销，行为与 demo/verify 完全一致。
        self._bus = event_bus

        self._timeline: Optional[TimelineEngine] = None
        self._trace: TraceRecorder = TraceRecorder()
        self._car: Optional[VirtualCar] = None
        self._vc_driver: Optional[VirtualCarDriver] = None
        self._scheduler: Optional[EventScheduler] = None
        self._handles: set[_TurnHandle] = set()
        self._turn_tasks: set[asyncio.Task] = set()
        self._last_error: Optional[str] = None

    def _emit(self, kind: str, payload: dict, mock_time: Optional[datetime] = None) -> None:
        """层2过程事件发射（旁路，无总线时零开销）。"""
        if self._bus is not None:
            self._bus.emit(kind, payload, mock_time)

    # ---------------- 只读访问 ----------------

    @property
    def trace(self) -> TraceRecorder:
        return self._trace

    @property
    def virtual_car(self) -> Optional[VirtualCar]:
        return self._car

    @property
    def mock_time(self) -> Optional[datetime]:
        """当前虚拟时间（未 setup 时为 None）。"""
        return self._timeline.mock_time if self._timeline is not None else None

    # ---------------- 会话初始化 ----------------

    def setup(self, case: TestCase, t0: Optional[datetime] = None) -> None:
        """建立会话：时间线 + 轨迹 + 虚拟车（含 on_field_change 钩子）+ 助手 setup。"""
        actual_t0 = t0 or case.t0 or datetime.now().replace(microsecond=0)
        self._timeline = TimelineEngine(actual_t0)
        # 轨迹记录器接 event_bus：record_* 落盘的同时自动发射层1事件（零新增埋点）
        self._trace = TraceRecorder(event_bus=self._bus)
        self._car = VirtualCar(car_info=dict(case.virtual_car.car_info))
        # 助手车控 set_field 的旁路记录（三色区分的 assistant 来源）
        self._car.on_field_change = self._on_car_field_change
        self._vc_driver = VirtualCarDriver(self._car)

        self._adapter.setup(
            AdapterEnv(
                session_id=case.id,
                virtual_car=self._car,
                get_virtual_time=lambda: self._timeline.mock_time,
            )
        )
        self._handles = set()
        self._turn_tasks = set()
        self._last_error = None

        # 层2：case_started（前端重建运行态 + 车态时间机初值 + 时间线未来区）
        self._emit(
            "case_started",
            {
                "case_id": case.id,
                "case_name": case.case_name,
                "case_description": case.case_description,
                "t0": actual_t0.isoformat(),
                "session_id": f"{case.id}-{actual_t0.isoformat()}",
                "initial_car_info": self._car.car_info,
                "car_state_groups": CAR_INFO_GROUPS,
                "script_plan": self._build_script_plan(case, actual_t0),
            },
            actual_t0,
        )

    # ---------------- 完整脚本驱动（复用 EventScheduler） ----------------

    async def run(self, case: TestCase) -> RunResult:
        """跑一个完整 case：遍历脚本事件 + 状态断言，直到调度器清空。"""
        started_at = datetime.now()
        self.setup(case)

        events = self._build_scheduled_events(case, self._timeline.t0)
        self._scheduler = EventScheduler(
            fast_mode=self._fast_mode,
            acceleration_threshold=self._acceleration_threshold,
            get_now=lambda: self._timeline.mock_time,
        )
        self._scheduler.set_on_execute(self._execute_event)
        self._scheduler.schedule_batch(events)

        try:
            await self._scheduler.run()
        except Exception as exc:  # noqa: BLE001 — 调度错误兜底，向上如实上报
            self._last_error = f"{exc!r}"
        finally:
            self._scheduler.shutdown()

        # 等所有助手回合（含被打断的旧回合）自然耗尽
        await self.wait_idle()

        trace_summary = self._trace.summary()
        state_checks = self._trace.get_state_checks()
        state_check_passed = (
            all(sc.passed for _, sc in state_checks) if state_checks else True
        )

        # 层2：case_finished（前端激活回放 + 终局统计）
        self._emit(
            "case_finished",
            {
                "case_id": case.id,
                "error": self._last_error,
                "state_check_passed": state_check_passed,
                "total_utterances": trace_summary.get("total_utterances", 0),
                "state_checks_passed": trace_summary.get("state_checks_passed", 0),
                "state_checks_failed": trace_summary.get("state_checks_failed", 0),
                "duration_seconds": (datetime.now() - started_at).total_seconds(),
            },
            self._timeline.mock_time if self._timeline is not None else None,
        )

        return RunResult(
            case_id=case.id,
            case_name=case.case_name,
            trace_summary=trace_summary,
            must_pass_assertions=list(case.must_pass_assertions),
            bonus_assertions=list(case.bonus_assertions),
            state_check_passed=state_check_passed,
            error=self._last_error,
        )

    @staticmethod
    def _build_script_plan(case: TestCase, t0: datetime) -> list[dict[str, Any]]:
        """构造剧本时间表（case_started 载荷）：锚点驱动事件的预览清单。

        前端时间线以"当前时刻轴线"居中：右侧未来区把这些预设事件渲染为
        半透明竖线 + 无框文字（事件随时间推进从右向左飞向轴线）。
        边界驱动事件（无锚点时刻）与主动话语（无预设时刻）无法定位，不进入时间表。
        """

        def _fields_text(fields: dict[str, Any]) -> str:
            return "，".join(f"{key}={value}" for key, value in fields.items())

        plan: list[dict[str, Any]] = []
        for ev in case.script_events:
            if ev.event_t0_plus_timedelta is None:
                continue  # 边界驱动：无预设时刻
            at = (t0 + ev.event_t0_plus_timedelta).isoformat()
            if isinstance(ev, FakePersonScriptEvent):
                content = ev.action.args.content
                label = f"{ev.target}：{content}" if content else f"{ev.target}：自主发挥"
                plan.append({"kind": "fake_person_speak", "at": at, "target": ev.target, "label": label})
            elif isinstance(ev, VirtualCarPerformScriptEvent):
                fields = ev.action.args.fields
                plan.append({
                    "kind": "car_set_state",
                    "at": at,
                    "target": "car",
                    "label": f"剧本改车态：{_fields_text(fields)}",
                })

        for ev in case.virtual_car_state_check_assertions:
            if ev.event_t0_plus_timedelta is None:
                continue
            at = (t0 + ev.event_t0_plus_timedelta).isoformat()
            plan.append({
                "kind": "state_check",
                "at": at,
                "target": "car",
                "label": f"状态检查：{_fields_text(ev.action.args.expected_fields)}",
            })

        plan.sort(key=lambda item: item["at"])
        return plan

    def _build_scheduled_events(
        self,
        case: TestCase,
        t0: datetime,
    ) -> list[ScheduledEvent]:
        events: list[ScheduledEvent] = []
        for idx, ev in enumerate(case.script_events):
            events.append(ScheduledEvent.from_event(ev, t0, idx))
        offset = len(case.script_events)
        for jdx, ev in enumerate(case.virtual_car_state_check_assertions):
            events.append(ScheduledEvent.from_event(ev, t0, offset + jdx))
        return events

    async def _execute_event(self, scheduled: ScheduledEvent) -> None:
        event = scheduled.event
        if isinstance(event, FakePersonScriptEvent):
            await self._execute_fake_person_event(event)
        elif isinstance(event, VirtualCarPerformScriptEvent):
            self._execute_virtual_car_perform(event)
        elif isinstance(event, VirtualCarStateCheckScriptEvent):
            self._execute_virtual_car_state_check(event)
        elif isinstance(event, WorldTickScriptEvent):
            self._execute_world_tick(event)

    # ---------------- 假人说话 ----------------

    async def _execute_fake_person_event(self, event: FakePersonScriptEvent) -> None:
        content = event.action.args.content
        if content is None:
            raise NotImplementedError(
                "新协议 demo 仅支持固定台词；假人 LLM 自主发挥是执行细节，"
                "不在事件源适配器范围内（可复用旧 FakePersonDriver 补接）"
            )
        await self.speak(content, role_id=event.target)

    async def speak(self, text: str, role_id: str = "driver") -> None:
        """假人说出 text（chunk 级 segments）→ 落盘 → 发起一个 USER 回合。"""
        assert self._timeline is not None

        speech_start_wall: Optional[datetime] = None
        speech_end_wall: Optional[datetime] = None
        segments: list[tuple[datetime, str]] = []
        async for fp in deliver_fake_person_speech_stream(
            text, role_id, chunk_delay=self._chunk_delay
        ):
            if fp.type == "speak_start":
                speech_start_wall = fp.wall_time
            elif fp.type == "text_delta":
                segments.append((fp.wall_time, fp.delta))
                # 层2：假人逐字增量（前端实时打字机，避免整句"瞬间出现"）
                self._emit(
                    "fake_person_delta",
                    {"target": role_id, "delta": fp.delta},
                    self._timeline.wall_to_mock(fp.wall_time),
                )
            elif fp.type == "speak_done":
                speech_end_wall = fp.wall_time

        start = self._timeline.wall_to_mock(speech_start_wall) if speech_start_wall else self._timeline.mock_time
        end = self._timeline.wall_to_mock(speech_end_wall) if speech_end_wall else self._timeline.mock_time
        duration = (
            (speech_end_wall - speech_start_wall).total_seconds()
            if (speech_start_wall and speech_end_wall) else None
        )
        self._trace.record_utterance(
            role=f"fake_person:{role_id}",
            content=text,
            kind=RecordKind.FAKE_PERSON_SPEAK,
            started_at=start,
            ended_at=end,
            speech_duration=duration,
            segments=[(self._timeline.wall_to_mock(w), d) for w, d in segments],
        )

        # 发起助手回合（并发，不在此等待——中立观察者：假人说完即继续）
        self._start_turn(Turn(kind=TurnKind.USER, text=text, at=self._timeline.mock_time))

    # ---------------- 助手回合（TurnMuxer → TraceRecorder） ----------------

    def _start_turn(self, turn: Turn) -> None:
        """发起一个回合：标记旧 USER 回合为被插话 + 起后台消费任务。"""
        if turn.kind is TurnKind.USER and self._adapter.capabilities.supports_barge_in:
            for handle in list(self._handles):
                if handle.turn.kind is TurnKind.USER:
                    handle.barged_in = True  # 只记录事实，真正中断由助手自驱

        assert self._timeline is not None
        handle = _TurnHandle(TurnMuxer(self._adapter, turn, self._timeline), turn)
        self._handles.add(handle)
        task = asyncio.create_task(self._consume_turn(handle))
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)

    async def _consume_turn(self, handle: _TurnHandle) -> None:
        """消费一个回合：按「话语段」落盘，工具事件把连续 TEXT_DELTA 切段。"""

        def flush(
            segments: list[tuple[datetime, str]],
            text: list[str],
            first: Optional[datetime],
            last: Optional[datetime],
        ) -> None:
            if not segments:
                return
            self._trace.record_utterance(
                role="assistant",
                content="".join(text),
                kind=RecordKind.ASSISTANT_REPLY,
                started_at=first,
                ended_at=last,
                is_partial=handle.barged_in,
                interrupted_by_barge_in=handle.barged_in,
                is_proactive=(handle.turn.kind is TurnKind.PROACTIVE),
                segments=segments,
            )

        try:
            segments: list[tuple[datetime, str]] = []
            text: list[str] = []
            first: Optional[datetime] = None
            last: Optional[datetime] = None
            async for sourced in handle.muxer.stream():
                ev = sourced.event
                if ev.type is EventType.TEXT_DELTA:
                    if first is None:
                        first = sourced.mock_time
                    last = sourced.mock_time
                    segments.append((sourced.mock_time, ev.delta))
                    text.append(ev.delta)
                    # 层2：助手逐字增量（前端实时打字机，与整段 utterance 落盘不冲突）
                    self._emit("assistant_delta", {"delta": ev.delta}, sourced.mock_time)
                elif ev.type is EventType.TOOL_CALL:
                    flush(segments, text, first, last)
                    segments, text, first, last = [], [], None, None
                    self._trace.record_tool_call(
                        sourced.mock_time, ev.tool_name, ev.tool_args, ev.task_id
                    )
                elif ev.type is EventType.TOOL_RESULT:
                    flush(segments, text, first, last)
                    segments, text, first, last = [], [], None, None
                    # duration_ms 由展示层用 task_id 配对按 mock 时间差计算，此处传 0
                    self._trace.record_tool_result(
                        sourced.mock_time, ev.tool_name, ev.tool_result, 0.0, ev.task_id
                    )
            flush(segments, text, first, last)
        finally:
            self._handles.discard(handle)

    # ---------------- 车态（剧本 set_state / state_check） ----------------

    def _on_car_field_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """助手车控 set_field 的旁路记录（source="assistant"）。"""
        at = self._timeline.mock_time if self._timeline is not None else datetime.now()
        self._trace.record_set_state(at, {key: new_value}, source="assistant")

    def _execute_virtual_car_perform(self, event: VirtualCarPerformScriptEvent) -> None:
        assert self._vc_driver is not None
        assert self._car is not None
        self._car.notify_enabled = False  # 剧本路径抑制钩子，避免逐字段双记录
        try:
            result = self._vc_driver.drive(event, event_at=self._timeline.mock_time)
        finally:
            self._car.notify_enabled = True
        assert isinstance(result.outcome, VirtualCarSetStateOutcome)
        self._trace.record_set_state(
            self._timeline.mock_time, result.outcome.updated_fields, source="script"
        )

    def _execute_virtual_car_state_check(self, event: VirtualCarStateCheckScriptEvent) -> None:
        assert self._vc_driver is not None
        result = self._vc_driver.drive(event, event_at=self._timeline.mock_time)
        assert isinstance(result.outcome, VirtualCarStateCheckOutcome)
        self._trace.record_state_check(
            self._timeline.mock_time,
            StateCheckRecord(
                expected_fields=result.outcome.expected_fields,
                actual_fields=result.outcome.car_info,
                passed=result.outcome.passed,
                mismatches=result.outcome.mismatches,
            ),
        )

    def _execute_world_tick(self, event: WorldTickScriptEvent) -> None:
        self._trace.record_system_event(
            self._timeline.mock_time, "world_tick", "时间演进锚点（WorldTick）"
        )

    # ---------------- 快进 + 主动话语 + 收尾 ----------------

    async def accelerate_to(self, target: datetime) -> list[datetime]:
        """快进虚拟时间到 target，并通知助手世界更新，返回未来停靠点。"""
        assert self._timeline is not None
        assert self._car is not None
        from_time = self._timeline.mock_time
        self._timeline.accelerate_to(target)
        self._trace.record_acceleration(from_time, target)
        return await self._adapter.apply_world_update(
            WorldUpdate(car_info=dict(self._car.car_info), current_time=target)
        )

    async def proactive(self, reason: str = "") -> None:
        """发起一个主动话语回合（定时提醒到期等，无用户输入）。"""
        assert self._timeline is not None
        self._start_turn(
            Turn(kind=TurnKind.PROACTIVE, text=reason, at=self._timeline.mock_time)
        )

    async def wait_idle(self) -> None:
        """等所有助手回合任务自然耗尽（含被打断的旧回合）。"""
        while self._turn_tasks:
            await asyncio.gather(*list(self._turn_tasks), return_exceptions=True)