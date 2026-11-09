"""CaseRunner：自动测试主调度器。

设计（见 CONTEXT.md）：
- 调度器主动回调模式：EventScheduler 跑主循环，事件就绪时回调 _execute_event
- Runner 只负责初始化、事件分发、结果收集
- 简单直白的命名（§0.9）

时间模型（自然时间流逝，ARCHITECTURE §7.5）：
- 虚拟时间与真实时间 1:1 连续流逝（TimelineEngine 锚点对实时计算）
- 唯一跳跃方式是快进 accelerate_to（配合 WorldTick 锚点停靠定时任务）
- 假人/助手的话语记录为时间区间（开口时刻 → 说完时刻），时间戳如实反映
- 助手回复期间时间照常流逝 → 工具拿到实时时间，无需任何偏移修正

中立观察者模型（2026-08-25 定稿，框架不打断被测助手）：
- 框架是中立的记录者：绝不主动打断被测助手的推理/输出，如实记录双方事件流
- 假人话语流式投喂（2026-08-26）：假人说出第一个字就把文本流实时推给助手
  （模拟流式 ASR）——第一个 chunk = 用户开口（插话打断时机信号），说完 = EOF。
  助手支不支持打断是它自己的事：支持则中断旧流（旧流记为半截话）；不支持则
  多流并行——框架把助手实际产生的每一条流都如实记入 trace
- 助手可同时有多条活跃流（并发流），每条流一个后台消费任务；多条助手话语
  区间可能重叠，区间化渲染如实呈现
- 时间快进/WorldTick 推进前先等所有活跃流收完：时间跳跃不能穿过进行中的话语，
  否则话语时间戳语义会被扭曲
- is_partial 出现于：回复超时被截断（测试基建兜底）或助手自己插话打断中断旧流

执行流程：
1. 初始化 session（假人、虚拟车、trace、timeline、assistant）
2. 构造 ScheduledEvent 列表（script_events + state_check）
3. 启动 scheduler，事件就绪时回调 _execute_event
4. _execute_event 根据事件类型分发：
   - FakePersonScriptEvent → 假人说话（记 trace）→ 第一个字即流式投喂（spawn 流任务）
   - VirtualCarPerformScriptEvent → 虚拟车 set_state → 记 trace
   - VirtualCarStateCheckScriptEvent → 虚拟车 state_check → 记 trace
   - WorldTickScriptEvent → 锚点停靠 → 触发锚定的定时任务
5. 流任务：achat_stream(输入流) → 后台消费事件流记 trace → 收尾 aupdate_context
6. 锚点事件到达前若距当前虚拟时间 > 阈值，触发快进：
   - 先等活跃流全部收完，再 aupdate_context(car_info, current_time=target)
   - 助手若返回主动话语，记入 trace（主动智能）
   - TimelineEngine.accelerate_to(target) 记录快进
7. 所有事件完成后，等活跃流全部收完，返回 RunResult（含 trace 摘要）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Optional

from projects.experiments.time_travel_auto_test.case_schema import TestCase
from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    AssistantEventType,
    AssistantProtocol,
    ContextUpdateResult,
    StreamingReply,
    is_assistant,
)
from projects.experiments.time_travel_auto_test.case_runner.scheduler import (
    EventScheduler,
    ScheduledEvent,
)
from projects.experiments.time_travel_auto_test.case_runner.timeline import (
    TimelineEngine,
)
from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    StateCheckRecord,
    TraceRecorder,
)
from projects.experiments.time_travel_auto_test.case_runner.fake_person_driver import (
    FakePersonDriver,
)
from projects.experiments.time_travel_auto_test.case_runner.virtual_car_driver import (
    VirtualCarDriver,
)
from projects.experiments.time_travel_auto_test.fake_person.event import (
    deliver_fake_person_speech_stream,
)
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePerson,
    FakePersonSpeakArgs,
    FakePersonSpeakPerformAction,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarStateCheckScriptEvent,
    WorldTickScriptEvent,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import (
    CAR_INFO_GROUPS,
    VirtualCar,
    VirtualCarSetStateOutcome,
    VirtualCarStateCheckOutcome,
)
from projects.experiments.time_travel_auto_test.visualizer.event_bus import EventBus


# 快进阈值：距下一锚点 > 此值且无活动时快进（CONTEXT §2.6.26）
ACCELERATION_THRESHOLD: timedelta = timedelta(seconds=60)


async def _queue_to_aiter(queue: asyncio.Queue) -> AsyncIterator[str]:
    """把 asyncio.Queue[Optional[str]] 包装为输入文本流（None = EOF）。"""
    while True:
        item = await queue.get()
        if item is None:
            return
        yield item


async def _list_to_aiter(items: list[str]) -> AsyncIterator[str]:
    """把已收集的字列表包装为输入文本流（fast_mode 同步投喂用）。"""
    for item in items:
        yield item


@dataclass
class RunnerConfig:
    """Runner 配置。"""
    # 假人 LLM 调用超时（秒）
    fake_person_timeout: float = 30.0
    # 助手回复超时（秒）
    # 多工具并行/顺序执行的 case（网页搜索+POI+音乐+导航）需要等所有异步工具
    # 结果依次回灌并流式生成回复，真实耗时可达 40s+（多工具串行回灌与流式生成），
    # 60s 会过早截断为「半截话」，故放宽到 180s 兜底（超时仅用于检测流卡死）。
    assistant_timeout: float = 180.0
    # 是否使用流式回复（chunk 级时间戳，支撑重叠说话渲染）
    use_streaming: bool = True
    # 外部 API 重试次数
    external_api_max_retries: int = 2
    # 测试模式：跳过锚点事件的真实时间等待（立即执行所有事件）
    # 仅用于单元测试，生产环境不要开
    fast_mode: bool = False
    # 假人说话逐字延迟（秒），模拟真实说话节奏
    chunk_delay: float = 0.05
    # 是否启用时间加速（CONTEXT §2.6）
    # True：锚点事件距当前 mock_time > ACCELERATION_THRESHOLD 时快进
    # False：不快进，锚点事件按 anchor_time 顺序执行但不跳时间
    enable_acceleration: bool = True
    # 快进阈值（覆盖默认 60s，主要供测试用）
    acceleration_threshold: Optional[timedelta] = None
    # 后台排水泵轮询间隔（秒）：case 运行期间持续把助手的异步工具
    # 调用/结果与回灌主动话语归集落盘并实时推送到前端
    backfill_poll_interval: float = 0.05


@dataclass
class RunResult:
    """单次 case 运行的结果。"""
    case_id: str
    case_name: str
    started_at: datetime
    finished_at: datetime
    trace_summary: dict[str, Any]
    must_pass_assertions: list[str]
    bonus_assertions: list[str]
    state_check_passed: bool
    error: Optional[str] = None


class CaseRunner:
    """自动测试主调度器。

    用法：
        runner = CaseRunner(assistant=my_assistant)
        result = await runner.run(case)
    """

    def __init__(
        self,
        assistant: AssistantProtocol,
        config: Optional[RunnerConfig] = None,
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        assert is_assistant(assistant), "assistant 必须实现 AssistantProtocol"
        self.assistant: AssistantProtocol = assistant
        self.config: RunnerConfig = config or RunnerConfig()
        # 旁路事件总线（可视化）：层2过程事件由 Runner 发射，层1由 TraceRecorder 发射。
        # 不注入则零开销，行为与旧版完全一致。
        self._bus = event_bus

        # 运行时状态（每次 run 重置）
        self._fp_drivers: dict[str, FakePersonDriver] = {}
        self._vc_driver: Optional[VirtualCarDriver] = None
        self._car: Optional[VirtualCar] = None
        self._trace: TraceRecorder = TraceRecorder()
        self._timeline: Optional[TimelineEngine] = None
        self._scheduler: EventScheduler = EventScheduler()
        self._case: Optional[TestCase] = None
        self._session_id: str = ""
        # 活跃流任务集合（流式投喂）：每路输入流对应一个后台流任务，
        # 任务完成即移除；助手可同时有多条流并行（如实记录）
        self._active_stream_tasks: set[asyncio.Task] = set()
        self._stream_error: Optional[str] = None

    def _emit(self, kind: str, payload: dict, mock_time=None) -> None:
        """层2过程事件发射（旁路，无总线时零开销）。"""
        if self._bus is not None:
            self._bus.emit(kind, payload, mock_time)

    @property
    def trace(self) -> TraceRecorder:
        """暴露 trace recorder，供外部（如 Judge）构造评判输入。"""
        return self._trace

    def _share_virtual_car_with_assistant(self) -> None:
        """让助手和 Runner 共享同一个 VirtualCar 实例。

        这样剧本 set_state 和车控工具操作的是同一份状态。
        """
        # TestedAssistant 等实现通常持有一个 VirtualCar 用于车控工具
        # Runner 也需要一个 VirtualCar 用于剧本事件
        # 统一用 Runner 的实例，同步给助手
        if hasattr(self.assistant, "virtual_car") and self._car is not None:
            self.assistant.virtual_car = self._car

    async def run(
        self,
        case: TestCase,
        t0: Optional[datetime] = None,
    ) -> RunResult:
        """运行一个 case，返回结果。"""
        started_at = datetime.now()
        actual_t0 = t0 or case.t0 or started_at

        self._emit(
            "case_started",
            {
                "case_id": case.id,
                "case_name": case.case_name,
                "case_description": case.case_description,
                "t0": actual_t0.isoformat(),
                "session_id": f"{case.id}-{actual_t0.isoformat()}",
                # 初始车态快照：前端"虚拟车状态观察窗"按虚拟时间重建车态的初值
                # （car_set_state 事件是增量，必须配合初值才能重建任意时刻全量状态）
                # 取 devices 派生的全量视图（含分组字段默认值），而非仅 case 指定的键
                "initial_car_info": VirtualCar(car_info=dict(case.virtual_car.car_info)).car_info,
                # car_info key 的展示分组（有序）：前端虚拟车状态面板分层分组展示
                "car_state_groups": CAR_INFO_GROUPS,
                # 剧本时间表（锚点驱动事件）：前端时间线"未来区"的预设事件竖线——
                # 轴线右侧展示即将发生的剧本事件（劲舞团式预览）
                "script_plan": self._build_script_plan(case, actual_t0),
            },
            actual_t0,
        )

        # 初始化 session
        await self._init_session(case, actual_t0)

        # 构造调度事件列表
        events = self._build_scheduled_events(case, actual_t0)

        if not events:
            # 空事件，直接返回
            result = self._build_result(case, started_at, error=None)
            self._emit_case_finished(result)
            return result

        # 配置调度器
        # 时间加速：enable_acceleration=True 时传阈值给 scheduler，
        # scheduler 跳过远期锚点的真实等待，Runner._maybe_accelerate 处理快进逻辑
        accel_threshold = (
            self.config.acceleration_threshold or ACCELERATION_THRESHOLD
            if self.config.enable_acceleration and not self.config.fast_mode
            else None
        )
        self._scheduler = EventScheduler(
            fast_mode=self.config.fast_mode,
            acceleration_threshold=accel_threshold,
            # 锚点等待基于虚拟时间：快进后虚拟时间领先真实时间，
            # "距下一锚点的距离"必须按虚拟时钟计算
            get_now=lambda: self._timeline.mock_time if self._timeline is not None else datetime.now(),
        )
        self._scheduler.set_on_execute(self._execute_event)
        self._scheduler.schedule_batch(events)

        # 启动调度器，并并发启动后台排水泵：case 运行期间以固定小间隔持续
        # 把助手的异步工具调用/结果与回灌主动话语及时归集落盘（→实时推送前端），
        # 避免这几类旁路事件攒到快进/收尾才一次性出现在对话流/时间线。
        self._pump_stop = asyncio.Event()
        pump_task = asyncio.create_task(self._backfill_pump(self._pump_stop))
        try:
            try:
                await self._scheduler.run()
                error = None
            except Exception as e:
                error = f"Runner 执行出错: {e!r}"
            finally:
                self._scheduler.shutdown()

            # 调度器结束后，等所有活跃流收完（中立观察者：
            # 已投喂的话语必须收完回复并记录，不能因事件跑完而丢弃）
            # 与等异步工具回灌期间排水泵必须保持运行：异步工具的串行回灌链
            # （websearch→POI→音乐→导航）与回灌主动发言都延续到调度器结束后，
            # 若在此前停泵，这些事件只能靠收尾兜底 drain 一次性落盘（回放才可见）。
            await self._wait_assistant_idle()
            # 等异步工具（POI/音乐等）真实结果回灌完成，并记录回灌回复到 trace
            await self._wait_backfill_idle()
        finally:
            # 所有异步事件（工具调用/结果/回灌主动话语）归集完毕后再停泵
            self._pump_stop.set()
            await pump_task

        self._drain_backfill_utterances()
        self._drain_backfill_tool_calls()
        self._drain_backfill_tool_results()
        if error is None and self._stream_error:
            error = self._stream_error

        result = self._build_result(case, started_at, error=error)
        self._emit_case_finished(result)
        return result

    def _emit_case_finished(self, result: RunResult) -> None:
        """发射 case_finished 事件（层2，含结果摘要）。"""
        self._emit(
            "case_finished",
            {
                "case_id": result.case_id,
                "error": result.error,
                "state_check_passed": result.state_check_passed,
                "total_utterances": result.trace_summary.get("total_utterances", 0),
                "state_checks_passed": result.trace_summary.get("state_checks_passed", 0),
                "state_checks_failed": result.trace_summary.get("state_checks_failed", 0),
                "duration_seconds": (result.finished_at - result.started_at).total_seconds(),
            },
            self._timeline.mock_time if self._timeline is not None else None,
        )

    # ---------------- 初始化 ----------------

    async def _init_session(self, case: TestCase, t0: datetime) -> None:
        """初始化运行时状态。"""
        self._case = case
        self._session_id = f"{case.id}-{t0.isoformat()}"
        self._trace = TraceRecorder(event_bus=self._bus)
        self._timeline = TimelineEngine(t0)
        self._active_stream_tasks = set()
        self._stream_error = None

        # 初始化假人 + 驱动器
        self._fp_drivers = {}
        for info in case.fake_persons:
            person = FakePerson(
                role_id=info.role_id,
                profile=info.profile,
                event_memory=list(info.event_memory or []),
                state=info.state,
                intent=info.intent,
            )
            self._fp_drivers[info.role_id] = FakePersonDriver(
                person,
                external_api_max_retries=self.config.external_api_max_retries,
            )

        # 初始化虚拟车 + 驱动器
        self._car = VirtualCar(car_info=dict(case.virtual_car.car_info))
        # 车态变更钩子：助手车控工具直接 set_field 改车态时也发 car_set_state 事件
        # （此前只有剧本 set_state 有记录，助手的车控操作对可视化不可见）。
        # 事件时间 = 当前虚拟时刻，回放时车态变化时点与助手操作时序一致。
        self._car.on_field_change = self._on_car_field_change
        self._vc_driver = VirtualCarDriver(self._car)

        # 让助手共享同一个 VirtualCar 实例（车控工具和剧本事件操作同一份状态）
        self._share_virtual_car_with_assistant()

        # 初始化助手
        self.assistant.create(self._session_id)
        # 注入实时时间源：助手在回复期间调 set_reminder 等工具时
        # 拿到的是自然流逝的虚拟时间（trigger_time 天然包含回复耗时，无需偏移修正）
        if hasattr(self.assistant, "set_time_source"):
            self.assistant.set_time_source(lambda: self._timeline.mock_time)
        # 注入初始时间上下文，让助手从 T0 就感知到当前时间
        ctx_result = await self.assistant.aupdate_context(
            self._car.car_info,
            current_time=t0,
        )
        await self._handle_context_update(ctx_result, t0)

    def _build_scheduled_events(
        self,
        case: TestCase,
        t0: datetime,
    ) -> list[ScheduledEvent]:
        """合并 script_events + state_check，构造 ScheduledEvent 列表。"""
        events: list[ScheduledEvent] = []
        idx = 0

        for ev in case.script_events:
            events.append(ScheduledEvent.from_event(ev, t0, idx))
            idx += 1

        for ev in case.virtual_car_state_check_assertions:
            events.append(ScheduledEvent.from_event(ev, t0, idx))
            idx += 1

        return events

    @staticmethod
    def _build_script_plan(case: TestCase, t0: datetime) -> list[dict[str, Any]]:
        """构造剧本时间表（case_started 载荷）：锚点驱动事件的预览清单。

        前端时间线以"当前时刻轴线"居中：右侧未来区把这些预设事件渲染为
        半透明竖线 + 无框文字（劲舞团式：事件随时间推进从右向左飞向轴线）。
        边界驱动事件（无锚点时刻）无法定位，不进入时间表。
        """
        plan: list[dict[str, Any]] = []

        def _fields_text(fields: dict[str, Any]) -> str:
            return "，".join(f"{key}={value}" for key, value in fields.items())

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

    # ---------------- 事件执行（调度器回调） ----------------

    async def _execute_event(self, scheduled: ScheduledEvent) -> None:
        """调度器回调：执行单个事件。"""
        event = scheduled.event

        # 时间加速判定（CONTEXT §2.6.26）：
        # 锚点事件到达前若距当前虚拟时间 > 阈值，快进到 anchor_time
        # 快进前先通过 aupdate_context(current_time=target) 通知助手时间推进
        if (
            self.config.enable_acceleration
            and scheduled.anchor_time is not None
            and not self.config.fast_mode  # fast_mode 下时间已自动跳过，无需快进
        ):
            await self._maybe_accelerate(scheduled.anchor_time)

        # 锚点对齐：虚拟时间自然流逝，事件就绪时对齐到精确锚点时刻
        # - fast_mode：无真实等待，直接跟随锚点（jump_to）
        # - 正常模式：调度器按真实时间等待触发，误差在 PIN_TOLERANCE 内
        #   则对齐（时间戳干净）；被前序执行拖晚超过容差则保持自然时刻
        if scheduled.anchor_time is not None:
            if self.config.fast_mode:
                self._timeline.jump_to(scheduled.anchor_time)
            else:
                self._timeline.pin_to(scheduled.anchor_time)

        if isinstance(event, FakePersonScriptEvent):
            await self._execute_fake_person_event(event, scheduled)
        elif isinstance(event, VirtualCarPerformScriptEvent):
            self._execute_virtual_car_perform(event, self._timeline.mock_time)
        elif isinstance(event, VirtualCarStateCheckScriptEvent):
            self._execute_virtual_car_state_check(event, self._timeline.mock_time)
        elif isinstance(event, WorldTickScriptEvent):
            await self._execute_world_tick(event)
        else:
            raise ValueError(f"未支持的事件类型: {type(event).__name__}")

    async def _execute_world_tick(self, event: WorldTickScriptEvent) -> None:
        """执行 WorldTick 时间锚点事件。

        锚点的使命（ARCHITECTURE §7.4）：助手注入的锚点停在 trigger_time - 5s
        （提前 5 秒抵达），先记录锚点到达，再推进到锚定的定时任务触发时间并触发。
        trace 上呈现为"锚点到达 → 5 秒后助手主动说话"；
        低于加速阈值的小步推进（如 5 秒缓冲）不记为快进事件。

        中立观察者：若锚点到达时助手正在回复，先等回复说完再推进时间——
        时间快进不能穿过进行中的话语，否则话语时间戳语义被扭曲。

        迟到锚点静默跳过：注入型锚点可能被调度器串行回调拖晚——后续事件的
        多步快进中间停靠已先行触发了其锚定的任务（两级保障的另一级先到）。
        此时锚点已无意义：附近无待触发任务则直接返回，不记录"锚点到达"，
        避免 trace 尾部出现排在任务触发之后的系统事件噪音
        （任务的如实记录是它实际被触发的时刻，由先到的那一级完成）。
        """
        # 0. 等助手通道空闲（锚点可能落在回复窗口内；等待期间流任务
        #    的收尾 aupdate 也可能把到期任务触发掉——之后的检查能看到）
        await self._wait_assistant_idle()

        # 1. 迟到锚点检查：附近无待触发任务 → 静默跳过
        if not self._has_tasks_near_now():
            return

        # 2. 锚点到达（先记录，保证排在任务触发话语之前）
        self._trace.record_system_event(
            at=self._timeline.mock_time,
            kind="world_tick",
            description="WorldTick 锚点到达",
        )

        # 3. 推进并触发本锚点锚定的定时任务
        await self._drain_pending_tasks_near_anchor()

    def _has_tasks_near_now(self) -> bool:
        """当前虚拟时间的加速阈值内是否有待触发的定时任务。

        筛选口径与 _drain_pending_tasks_near_anchor 一致（含已过期任务）：
        锚点只对"附近"的任务有意义；更远的任务由各自的锚点或
        后续快进的中间停靠负责，不归本锚点管。
        """
        assert self._timeline is not None
        if not hasattr(self.assistant, "get_pending_scheduled_tasks"):
            return False
        try:
            pending = self.assistant.get_pending_scheduled_tasks()
        except Exception:
            return False
        threshold = self.config.acceleration_threshold or ACCELERATION_THRESHOLD
        now = self._timeline.mock_time
        return any(trigger_time - now <= threshold for trigger_time, _ in pending)

    async def _drain_pending_tasks_near_anchor(self) -> None:
        """推进到锚点附近的 pending 定时任务触发时间并触发。

        只处理距当前 mock_time 不超过加速阈值的任务（即本锚点锚定的任务，
        通常在 5 秒缓冲之后）；更远的任务由各自的锚点或后续事件的
        中间停靠机制处理，不会在此被提前触发。

        过期任务（gap <= 0，锚点被助手回复拖晚到 trigger_time 之后）立即触发：
        如实记录实际触发时刻，不静默跳过——测试平台的任务是如实记录和如实评价。
        """
        assert self._car is not None
        assert self._timeline is not None
        threshold = self.config.acceleration_threshold or ACCELERATION_THRESHOLD

        if not hasattr(self.assistant, "get_pending_scheduled_tasks"):
            return

        while True:
            try:
                pending = self.assistant.get_pending_scheduled_tasks()
            except Exception:
                return
            if not pending:
                return
            trigger_time = min(t for t, _ in pending)
            gap = trigger_time - self._timeline.mock_time
            if gap > threshold:
                return  # 不是本锚点锚定的任务

            # 过期任务（gap <= 0）照常触发；话语时刻用实际触发时刻（不倒填过去）
            fire_at = trigger_time if gap > timedelta(0) else self._timeline.mock_time
            from_time = self._timeline.mock_time
            ctx_result, gen_elapsed = await self._aupdate_context_timed(trigger_time)
            self._timeline.accelerate_to(trigger_time)

            # 低于加速阈值的小步推进不记为快进事件（如锚点的 5 秒缓冲）
            if trigger_time - from_time > threshold:
                self._trace.record_acceleration(from_time, trigger_time)

            await self._handle_context_update(
                ctx_result,
                fire_at,
                ttft=gen_elapsed if ctx_result.proactive_text else None,
            )

    async def _aupdate_context_timed(
        self, current_time: datetime
    ) -> tuple[ContextUpdateResult, float]:
        """调用 aupdate_context 并测量真实耗时。

        耗时用于主动话语的触发延迟标注（从定时任务到期到助手开口的真实秒数）。
        """
        assert self._car is not None
        wall_start = datetime.now()
        ctx_result = await self.assistant.aupdate_context(
            self._car.car_info,
            current_time=current_time,
        )
        elapsed = (datetime.now() - wall_start).total_seconds()
        return ctx_result, elapsed

    async def _maybe_accelerate(self, target_time: datetime) -> None:
        """快进到 target_time：通知助手时间推进 + 记 trace + 更新 mock_time。

        CONTEXT §2.5.23 + §2.6.26：
        - 快进前必须先 aupdate_context(car_info, current_time=target) 同步助手时间
        - 助手内部定时任务到期时可自主触发行为，返回值即主动话语
        - 主动话语记入 trace（RecordKind.ASSISTANT_REPLY，标志主动智能）
        - 快进事件记入 trace（RecordKind.ACCELERATION）

        多步快进（2026-08-25）：
        - 若助手在 [current, target] 区间内有 pending 定时任务，先快进到每个触发时间
        - 每个中间停靠点触发一次 aupdate_context，记录主动话语
        - 避免一步跳过定时任务触发时间，确保 Trace 时间戳正确
        """
        assert self._car is not None
        assert self._timeline is not None

        current = self._timeline.mock_time
        gap = target_time - current
        threshold = self.config.acceleration_threshold or ACCELERATION_THRESHOLD

        if gap <= threshold:
            # 距离不够远，不快进
            return

        # 中立观察者：时间快进不能穿过进行中的助手话语（否则话语时间戳语义
        # 被扭曲），先把已排队的用户话语全部投喂完、回复收完，再推进时间
        await self._wait_assistant_idle()
        # 时间快进也不能穿过执行中的异步工具（POI/音乐等）：TOOL_CALL 已甩出、
        # 真实结果尚未回灌前不得快进，否则工具结果的时间戳被扭曲甚至丢失。
        # 等回灌完成后，把工具结果与回灌回复及时落到 trace（此刻 wall→mock
        # 仍基于快进前的时间线，时间戳正确）。
        await self._wait_backfill_idle()
        self._drain_backfill_tool_calls()
        self._drain_backfill_tool_results()
        self._drain_backfill_utterances()

        # 查询助手 pending 定时任务，作为中间停靠点
        intermediates: list[datetime] = []
        if hasattr(self.assistant, "get_pending_scheduled_tasks"):
            try:
                pending = self.assistant.get_pending_scheduled_tasks()
                intermediates = sorted(
                    trigger_time
                    for trigger_time, _ in pending
                    if current < trigger_time <= target_time
                )
            except Exception:
                pass

        # 多步快进：当前 → 中间停靠点1 → 中间停靠点2 → ... → target
        for trigger_time in intermediates:
            from_time = self._timeline.mock_time
            ctx_result, gen_elapsed = await self._aupdate_context_timed(trigger_time)
            self._timeline.accelerate_to(trigger_time)

            # 低于加速阈值的小步推进不记为快进事件
            if trigger_time - from_time > threshold:
                self._trace.record_acceleration(from_time, trigger_time)

            # 处理 ContextUpdateResult：主动话语 + 注入事件
            await self._handle_context_update(
                ctx_result,
                trigger_time,
                ttft=gen_elapsed if ctx_result.proactive_text else None,
            )

        # 最终快进到 target_time
        from_time = self._timeline.mock_time
        ctx_result, gen_elapsed = await self._aupdate_context_timed(target_time)
        self._timeline.accelerate_to(target_time)

        # 记录快进事件（低于阈值的小步推进不记）
        if target_time - from_time > threshold:
            self._trace.record_acceleration(from_time, target_time)

        # 处理 ContextUpdateResult：主动话语 + 注入事件
        await self._handle_context_update(
            ctx_result,
            target_time,
            ttft=gen_elapsed if ctx_result.proactive_text else None,
        )

    async def _handle_context_update(
        self,
        ctx_result: ContextUpdateResult,
        at: datetime,
        ttft: Optional[float] = None,
    ) -> None:
        """处理 ContextUpdateResult：记录主动话语 + 调度注入事件。

        - proactive_text: 助手主动说话 → 记入 trace（ASSISTANT_REPLY，is_proactive=True）
        - at: 定时任务触发时刻（快进停靠点 / WorldTick drain 的 fire_at）
        - ttft: 主动话语的触发延迟（从任务到期到助手开口的真实耗时）；
          话语时间戳 = at + ttft（任务到期后 ttft 秒才开口），保证时间戳
          与"触发后 Xs 开口"标注自洽，而非把开口记在到期瞬间
        - injected_events: WorldTick 事件 → 加入事件队列（scheduler.schedule_one）
        """
        # 记录主动话语
        if ctx_result.proactive_text:
            segments = ctx_result.proactive_segments
            if segments:
                # 基于流式分段重建区间：首字偏移 = 开口延迟（ttft），末字偏移 = 说完时刻，
                # 与普通话语一样呈现为区间而非瞬时点
                first_offset = segments[0][0]
                last_offset = segments[-1][0]
                started = at + timedelta(seconds=first_offset)
                ended = at + timedelta(seconds=max(last_offset, first_offset))
                actual_ttft = first_offset
                mock_segments = [
                    (at + timedelta(seconds=off), d) for off, d in segments
                ]
            else:
                # 无分段信息（如 MockAssistant）回退旧行为：开口 = at + ttft（点事件）
                started = at + timedelta(seconds=ttft) if ttft else at
                ended = started
                actual_ttft = ttft
                mock_segments = []
            self._trace.record_utterance(
                role="assistant",
                content=ctx_result.proactive_text,
                kind=RecordKind.ASSISTANT_REPLY,
                started_at=started,
                ended_at=ended,
                ttft=actual_ttft,
                is_proactive=True,
                segments=mock_segments,
            )

        # 调度注入的 WorldTick 事件
        for wt in ctx_result.injected_events:
            # 注入事件的偏移量是相对 aupdate_context 时刻（= at）计算的，
            # 因此锚点基准也用 at，保证 WorldTick 落在 trigger_time - 5s
            injected = ScheduledEvent.from_event(
                wt,
                t0=at,
                original_index=-1,  # 注入事件，无原始序号
            )
            self._scheduler.schedule_one(injected, immediate=True)

    async def _execute_fake_person_event(
        self,
        event: FakePersonScriptEvent,
        scheduled: ScheduledEvent,
    ) -> None:
        """执行假人说话事件：假人说（事件流）→ 记 trace → 流式投喂助手。

        中立观察者模型：
        - 假人侧只负责"说"——话语按真实说话节奏交付（区间 + chunk 级 segments），
          锚点到达即开口，不等助手空闲（插话与助手回复在时间上如实重叠）
        - 流式投喂（模拟流式 ASR）：假人说出第一个字就启动投喂，后续每个字
          实时推入输入流；说完 = EOF。助手支不支持打断是它自己的事：
          支持打断的助手在第一个 chunk（用户开口）即中断旧流；不支持的
          多流并行——框架如实记录它的实际行为
        - fast_mode（单元测试）：说完后同步投喂，保持事件严格顺序
        """
        driver = self._fp_drivers.get(event.target)
        if driver is None:
            raise ValueError(f"找不到 target={event.target!r} 的假人驱动器")

        assert isinstance(event.action, FakePersonSpeakPerformAction)
        content = event.action.args.content

        if content is not None:
            user_text = content
        else:
            user_text = await self._fake_person_llm_speak(event.target)

        # ---- 假人侧：事件流交付（话语区间 + chunk 级 segments）----
        # 同时把 text_delta 实时推入输入队列（流式投喂给助手）
        speech_start_wall: Optional[datetime] = None
        speech_end_wall: Optional[datetime] = None
        segments: list[tuple[datetime, str]] = []
        input_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        deltas: list[str] = []  # fast_mode 用：收集完整话语后同步投喂
        stream_spawned = False

        async for fp_event in deliver_fake_person_speech_stream(
            user_text, event.target, chunk_delay=self.config.chunk_delay,
        ):
            if fp_event.type == "speak_start":
                speech_start_wall = fp_event.wall_time
            elif fp_event.type == "text_delta":
                segments.append((fp_event.wall_time, fp_event.delta))
                deltas.append(fp_event.delta)
                self._emit(
                    "fake_person_delta",
                    {"target": event.target, "delta": fp_event.delta},
                    self._timeline.wall_to_mock(fp_event.wall_time),
                )
                if not self.config.fast_mode:
                    if not stream_spawned:
                        # 第一个字即投喂：立即启动后台流任务（不等说完）
                        stream_spawned = True
                        self._spawn_stream(_queue_to_aiter(input_queue))
                    await input_queue.put(fp_event.delta)
            elif fp_event.type == "speak_done":
                speech_end_wall = fp_event.wall_time
                if not self.config.fast_mode and stream_spawned:
                    await input_queue.put(None)  # 输入流 EOF（用户说完）

        speech_start = self._timeline.wall_to_mock(speech_start_wall) if speech_start_wall else self._timeline.mock_time
        speech_end = self._timeline.wall_to_mock(speech_end_wall) if speech_end_wall else self._timeline.mock_time
        speech_duration = (speech_end_wall - speech_start_wall).total_seconds() if (speech_start_wall and speech_end_wall) else None
        self._trace.record_utterance(
            role=f"fake_person:{event.target}",
            content=user_text,
            kind=RecordKind.FAKE_PERSON_SPEAK,
            started_at=speech_start,
            ended_at=speech_end,
            speech_duration=speech_duration,
            segments=[(self._timeline.wall_to_mock(w), d) for w, d in segments],
        )

        # ---- 投喂助手（fast_mode：说完后同步投喂，保持事件严格顺序）----
        if self.config.fast_mode and deltas:
            await self._feed_one(_list_to_aiter(deltas))

    # ---------------- 流任务管理（中立观察者核心） ----------------

    def _spawn_stream(self, chunks: AsyncIterator[str]) -> None:
        """为一路输入流启动后台流任务（流式投喂）。

        不等助手空闲、不排队。助手可同时有多条活跃流
        （被测助手不支持打断时并行跑，框架如实记录每条流的输出）。
        """
        task = asyncio.create_task(self._stream_task(chunks))
        self._active_stream_tasks.add(task)
        task.add_done_callback(self._active_stream_tasks.discard)

    async def _stream_task(self, chunks: AsyncIterator[str]) -> None:
        """单条流任务：消费输入流 → 消费助手事件流记 trace → 收尾 aupdate_context。"""
        try:
            await self._feed_one(chunks)
        except Exception as e:
            self._stream_error = f"投喂助手出错: {e!r}"

    async def _feed_one(self, chunks: AsyncIterator[str]) -> None:
        """投喂一路输入流：助手回复（记 trace）→ aupdate_context（主动智能/锚点）。

        流式投喂模型下这是单条流任务的基本单元，可与其它流任务并发执行。
        """
        if self.config.use_streaming:
            await self._assistant_chat_streaming(chunks)
        else:
            # 非流式输出：聚合完整输入（说完）再调 achat
            full_text = "".join([c async for c in chunks])
            wall_start = datetime.now()
            reply_text = await self._assistant_chat(full_text)
            wall_end = datetime.now()
            self._trace.record_utterance(
                role="assistant",
                content=reply_text,
                kind=RecordKind.ASSISTANT_REPLY,
                started_at=self._timeline.wall_to_mock(wall_start),
                ended_at=self._timeline.wall_to_mock(wall_end),
            )

        # 助手回复结束后立即把本轮流出的异步工具调用（TaskCreatedEvent 排队）
        # 补记为 TOOL_CALL——实时推给前端工具泳道，避免拖到快进/收尾才一次性落盘。
        # 此刻 wall→mock 仍是本轮自然流逝时间线，时间戳正确。
        self._drain_backfill_tool_calls()

        # 更新助手上下文（车态 + 当前虚拟时间）：
        # - 收集回复期间新建定时任务的 WorldTick 锚点
        # - 触发回复窗口内已到期的定时任务（主动智能）
        # 注意：aupdate_context 与 _handle_context_update 用同一时刻，
        # 保证注入的 WorldTick 锚点精确落在 trigger_time - 5s
        now = self._timeline.mock_time
        ctx_result, gen_elapsed = await self._aupdate_context_timed(now)
        await self._handle_context_update(
            ctx_result,
            now,
            ttft=gen_elapsed if ctx_result.proactive_text else None,
        )

    async def _wait_assistant_idle(self) -> None:
        """等所有活跃流任务收完（助手通道空闲）。

        供时间快进 / WorldTick 推进前调用——时间跳跃不能穿过进行中的话语。
        调用方（调度器回调）被阻塞期间不会再有新话语投喂，必然收敛。
        """
        while self._active_stream_tasks:
            await asyncio.wait(set(self._active_stream_tasks))
            if self._stream_error:
                return  # 出错后不再等待

    async def _wait_backfill_idle(self) -> None:
        """等助手内部所有进行中活动结束（统一权威忙碌信号）。

        优先调用 await_idle（回复流 + 后台异步任务 + 回灌回复生成统一覆盖），
        回退 await_async_idle（旧实现）；不实现这些可选钩子的助手
        （如 MockAssistant）静默跳过。
        """
        if hasattr(self.assistant, "await_idle"):
            await self.assistant.await_idle(
                timeout=self.config.assistant_timeout,
            )
        elif hasattr(self.assistant, "await_async_idle"):
            await self.assistant.await_async_idle(
                timeout=self.config.assistant_timeout,
            )

    async def _backfill_pump(self, stop: asyncio.Event) -> None:
        """后台排水泵：case 运行期间持续把助手旁路事件及时归集落盘。

        v2 真实 agent 的异步工具调用/结果（TaskCreatedEvent/TaskSuccessEvent）
        与工具结果回灌后的主动话语（BackfillUtterance）都不经过 reply.stream()
        主流，而是走 TaskManager 旁路、由助手侧排队。此前只靠 _consume_stream
        顶点 / _feed_one 尾 / 快进 / 收尾等少数稀疏时机 drain，导致实时模式下
        工具与主动话语延迟出现甚至缺失，直到结束回放才补齐。

        这里用一个与调度器并发的小间隔循环持续 drain 三个 backfill 队列——
        产生即落盘即推送。drain 为同步原子清空（get_nowait），与既有 drain 点
        幂等并发安全；用 wait_for(stop.wait()) 而非裸 sleep，停止时立即退出。
        """
        interval = self.config.backfill_poll_interval
        while not stop.is_set():
            self._drain_backfill_tool_calls()
            self._drain_backfill_tool_results()
            self._drain_backfill_deltas()
            self._drain_backfill_utterances()
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _drain_backfill_utterances(self) -> None:
        """把助手产出的回灌回复记录为主动话语（ASSISTANT_REPLY, is_proactive）。

        回灌回复是助手在异步工具真实结果到达后自发开口的后续解答，
        与定时提醒触发的主动话语同属"主动智能"。回复是流式生成的：
        按 started/ended wall→mock 换算起止区间，并携带 chunk 级 segments，
        与普通话语一样在时间线/对话流里呈现为区间而非瞬时点。
        """
        if not hasattr(self.assistant, "drain_backfill_utterances"):
            return
        for bu in self.assistant.drain_backfill_utterances():
            self._trace.record_utterance(
                role="assistant",
                content=bu.text,
                kind=RecordKind.ASSISTANT_REPLY,
                started_at=self._timeline.wall_to_mock(bu.started_wall),
                ended_at=self._timeline.wall_to_mock(bu.ended_wall),
                is_proactive=True,
                segments=[
                    (self._timeline.wall_to_mock(w), d) for w, d in bu.segments
                ],
            )

    def _drain_backfill_deltas(self) -> None:
        """把回灌回复的流式增量实时发射为 assistant_delta 事件。

        回灌回复（异步工具结果到达后助手自发产出的后续解答）是慢速逐 token
        生成的——若不实时发射 delta，前端只能在整段回复生成完后看到一条完整
        utterance "瞬间出现"，实时模式无打字机过程。这里按产出顺序把增量
        发射为 assistant_delta，前端靠 liveAssistant 打字机缓冲逐字渲染。
        mock_time 已在助手侧生成当下取好（规避快进重锚定漂移）。
        """
        if not hasattr(self.assistant, "drain_backfill_deltas"):
            return
        for mock_time, text in self.assistant.drain_backfill_deltas():
            self._emit("assistant_delta", {"delta": text}, mock_time)

    def _drain_backfill_tool_calls(self) -> None:
        """把异步工具调用记录为 TOOL_CALL 事件（配对到工具泳道）。

        异步工具（POI/音乐等）的 TOOL_CALL 不经过 agent.astream 主流——v2 agent
        的工具调用只经 TaskManager 的 TaskCreatedEvent 外抛，由助手侧
        _consume_task_events 排队；这里把排队中的工具调用补记为 TOOL_CALL。
        助手侧已在事件产生时取到虚拟时刻（mock），直接使用，不再 wall_to_mock
        （wall_to_mock 在快进后重锚定会导致时间漂移）。
        """
        if not hasattr(self.assistant, "drain_backfill_tool_calls"):
            return
        for mock_time, task_id, tool_name, tool_args in self.assistant.drain_backfill_tool_calls():
            self._trace.record_tool_call(
                at=mock_time,
                tool_name=tool_name,
                tool_args=tool_args,
                task_id=task_id,
            )

    def _drain_backfill_tool_results(self) -> None:
        """把异步工具真实结果记录为 TOOL_RESULT 事件（配对到工具泳道）。

        异步工具（POI/音乐等）的真正结果经 TaskManager 后台执行后回灌——
        这里把回灌结果补记为 TOOL_RESULT。助手侧已取到虚拟时刻（mock）、
        task_id 与真实耗时（duration_ms），直接落盘，前端按 task_id 精确配对。
        """
        if not hasattr(self.assistant, "drain_backfill_tool_results"):
            return
        for mock_time, task_id, tool_name, result, duration_ms in self.assistant.drain_backfill_tool_results():
            self._trace.record_tool_result(
                at=mock_time,
                tool_name=tool_name,
                result=result,
                duration_ms=duration_ms,
                task_id=task_id,
            )

    def _on_car_field_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """助手车控 set_field 的旁路记录：发 car_set_state 事件（单字段增量）。

        剧本 set_state 路径不走这里（_execute_virtual_car_perform 抑制通知，
        保持"多字段一条"的既有 trace 格式不变）。
        """
        assert self._car is not None
        at = self._timeline.mock_time if self._timeline is not None else datetime.now()
        self._trace.record_set_state(at, {key: new_value}, source="assistant")

    def _execute_virtual_car_perform(
        self,
        event: VirtualCarPerformScriptEvent,
        at: datetime,
    ) -> None:
        """执行虚拟车 set_state 事件。

        suppress 钩子通知：剧本路径由下方 record_set_state 以"多字段一条"
        记录（既有 trace 格式），避免钩子逐字段拆分导致双记录。
        """
        assert self._vc_driver is not None
        assert self._car is not None
        self._car.notify_enabled = False
        try:
            result = self._vc_driver.drive(event, event_at=at)
        finally:
            self._car.notify_enabled = True
        assert isinstance(result.outcome, VirtualCarSetStateOutcome)
        self._trace.record_set_state(at, result.outcome.updated_fields, source="script")

    def _execute_virtual_car_state_check(
        self,
        event: VirtualCarStateCheckScriptEvent,
        at: datetime,
    ) -> None:
        """执行虚拟车 state_check 事件。"""
        assert self._vc_driver is not None
        result = self._vc_driver.drive(event, event_at=at)
        assert isinstance(result.outcome, VirtualCarStateCheckOutcome)
        record = StateCheckRecord(
            expected_fields=result.outcome.expected_fields,
            actual_fields=result.outcome.car_info,
            passed=result.outcome.passed,
            mismatches=result.outcome.mismatches,
        )
        self._trace.record_state_check(at, record)

    # ---------------- 助手调用 ----------------

    async def _assistant_chat(self, user_text: str) -> str:
        """非流式调用助手。"""
        try:
            return await asyncio.wait_for(
                self.assistant.achat(user_text),
                timeout=self.config.assistant_timeout,
            )
        except asyncio.TimeoutError:
            return "[助手回复超时]"

    async def _assistant_chat_streaming(self, chunks: AsyncIterator[str]) -> str:
        """流式调用助手：投喂输入流，消费 AssistantEvent 流并记录话语区间。

        中立观察者（2026-08-25）：框架绝不因锚点/插话打断这条流——
        回复从头到尾完整消费，如实记录。假人插话由调度器并发执行，
        与本回复在时间上重叠的部分由 trace.get_overlaps() 检测并渲染。

        输入 chunks 是假人话语的实时文本流（模拟流式 ASR）：
        第一个 chunk = 用户开口（插话打断时机），EOF = 用户说完。
        助手若支持打断，会在第一个 chunk 时中断自己旧的输出流——
        旧流提前结束（is_partial=True 如实记录，插话打断能力可测）。

        从 AssistantEvent 流中提取：
        - TEXT_DELTA → 拼接为完整回复文本 + chunk 级 segments（供重叠切片）
        - TOOL_CALL / TOOL_RESULT → 记入 trace（时间戳换算为虚拟时间）
        - 文本流内相邻 TEXT_DELTA 间隔 > 阈值 → 记录 LONG_PAUSE
          （工具边界间隙不算——工具执行+LLM 围绕工具的思考是正常节奏，
          工具区间已单独可见）

        话语记录（自然时间流逝）：
        - 正常完成：ASSISTANT_REPLY，区间 = [首字时刻, 流结束时刻]
        - 半截话：超时截断（测试基建兜底）或助手自己插话打断中断旧流
          （is_interrupted），区间 = [首字时刻, 结束时刻]，内容为已说部分

        返回值：完整回复文本
        """
        wall_start = datetime.now()         # 助手回复开始的 wall_time
        ttft: Optional[float] = None  # 首字延迟（Time To First Token）

        try:
            reply = await asyncio.wait_for(
                self.assistant.achat_stream(chunks),
                timeout=self.config.assistant_timeout,
            )
        except asyncio.TimeoutError:
            self._trace.record_utterance(
                role="assistant",
                content="[助手回复超时]",
                kind=RecordKind.ASSISTANT_REPLY,
                started_at=self._timeline.wall_to_mock(wall_start),
                ended_at=self._timeline.mock_time,
            )
            return "[助手回复超时]"

        # 消费事件流：收集文本 + 记录工具调用 + 检测停顿（中立观察：不打断）
        collected_text: list[str] = []
        segments: list[tuple[datetime, str]] = []
        first_token_time: Optional[datetime] = None
        was_timed_out = False

        consume_task = asyncio.create_task(self._consume_stream(reply, collected_text, segments))

        try:
            await asyncio.wait_for(consume_task, timeout=self.config.assistant_timeout)
        except asyncio.TimeoutError:
            # 消费超时（流卡死）：打断并保存已说出的部分为半截话
            was_timed_out = True
            reply.interrupt()
            try:
                await asyncio.wait_for(consume_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # 首字时刻从事件流时间戳取（wall_time 由助手侧填充）
        for ev in reply.events:
            if ev.type == AssistantEventType.TEXT_DELTA and ev.delta:
                first_token_time = ev.wall_time
                break
        stream_end_time = datetime.now()

        def _record_reply(*, is_partial: bool, interrupted_by_barge_in: bool, ended_wall: datetime, content: str) -> None:
            """把本次助手话语按时间区间记入 trace。"""
            nonlocal ttft
            if first_token_time:
                ttft = (first_token_time - wall_start).total_seconds()
                started_mock = self._timeline.wall_to_mock(first_token_time)
            else:
                # 尚未开口就超时：话语时刻 = 结束时刻，零长度区间
                # （没说过话就不显示"说了 Xs"）
                started_mock = self._timeline.wall_to_mock(ended_wall)
            self._trace.record_utterance(
                role="assistant",
                content=content,
                kind=RecordKind.ASSISTANT_REPLY,
                started_at=started_mock,
                ended_at=self._timeline.wall_to_mock(ended_wall),
                is_partial=is_partial,
                interrupted_by_barge_in=interrupted_by_barge_in,
                ttft=ttft,
                segments=[(self._timeline.wall_to_mock(w), d) for w, d in segments],
            )

        result = "".join(collected_text) or reply.collected_text
        _record_reply(
            is_partial=was_timed_out or reply.is_interrupted,
            interrupted_by_barge_in=reply.is_interrupted and not was_timed_out,
            ended_wall=stream_end_time,
            content=result if result else "[助手无输出]",
        )
        return result

    async def _consume_stream(
        self,
        reply: StreamingReply,
        collected_text: list[str],
        segments: list[tuple[datetime, str]],
    ) -> None:
        """消费 AssistantEvent 流：文本/工具事件/停顿检测写入共享容器。"""
        PAUSE_THRESHOLD = 2.0  # 超过 2 秒的间隔视为异常停顿
        last_event_time: Optional[datetime] = None
        last_event_type: Optional[AssistantEventType] = None
        async for event in reply.stream():
            # 实时落盘异步工具调用/结果：v2 agent 的工具调用不经过 astream 主流，
            # 而是经 TaskManager 外抛、由助手侧 _consume_task_events 排队进
            # _backfill_tool_calls/_backfill_tool_results。这里在流事件到达间隙即时
            # drain，让工具区间在助手回复文本出现之前/同时就推到前端工具泳道
            # （否则要等整条回复流消费完才在 _feed_one 收尾落盘，工具信息晚于文本）。
            self._drain_backfill_tool_calls()
            self._drain_backfill_tool_results()

            now = datetime.now()
            # 停顿检测语义（2026-08-26 修订）：只测"文本流内"的停顿
            # （TEXT_DELTA → TEXT_DELTA 间隔 > 2s，反映流式流畅度）。
            # 工具边界间隙（任一侧是 TOOL_CALL/TOOL_RESULT）不算停顿：
            # 工具执行 + LLM 围绕工具的思考是 agent 正常节奏，
            # 且工具执行区间已在 trace/时间线以工具区间可见，不再重复记停顿
            if last_event_time is not None:
                gap = (now - last_event_time).total_seconds()
                is_tool_boundary = (
                    last_event_type in (AssistantEventType.TOOL_CALL, AssistantEventType.TOOL_RESULT)
                    or event.type in (AssistantEventType.TOOL_CALL, AssistantEventType.TOOL_RESULT)
                )
                if gap > PAUSE_THRESHOLD and not is_tool_boundary:
                    self._trace.record_long_pause(
                        at=self._timeline.wall_to_mock(now), pause_seconds=gap,
                    )
            last_event_time = now
            last_event_type = event.type

            if event.type == AssistantEventType.TEXT_DELTA and event.delta:
                collected_text.append(event.delta)
                segments.append((now, event.delta))
                self._emit("assistant_delta", {"delta": event.delta}, self._timeline.wall_to_mock(now))
            elif event.type == AssistantEventType.TOOL_CALL:
                self._trace.record_tool_call(
                    at=self._timeline.wall_to_mock(now),
                    tool_name=event.tool_name,
                    tool_args=event.tool_args,
                )
            elif event.type == AssistantEventType.TOOL_RESULT:
                self._trace.record_tool_result(
                    at=self._timeline.wall_to_mock(now),
                    tool_name=event.tool_name,
                    result=event.tool_result,
                    duration_ms=event.tool_duration_ms,
                )

    async def _fake_person_llm_speak(self, target: str) -> str:
        """假人自主发挥：调 LLM 生成台词。"""
        assert self._case is not None
        assert self._car is not None

        driver = self._fp_drivers.get(target)
        if driver is None:
            raise ValueError(f"找不到 target={target!r} 的假人驱动器")

        # 取助手上一句回复作为输入
        utterances = self._trace.get_utterances()
        assistant_last = ""
        for u in reversed(utterances):
            if u.role == "assistant":
                assistant_last = u.content
                break

        trigger_event = FakePersonScriptEvent(
            event_t0_plus_timedelta=None,
            target=target,
            action=FakePersonSpeakPerformAction(
                args=FakePersonSpeakArgs(content=None),
            ),
        )

        try:
            outcome = await asyncio.wait_for(
                driver.drive(
                    trigger_event,
                    session_id=self._session_id,
                    assistant_last=assistant_last,
                    car_info=self._car.car_info_text(),
                    start_query="",
                    text_script=self._case.text_script,
                    case_description=self._case.case_description,
                    max_round=self._case.max_round,
                ),
                timeout=self.config.fake_person_timeout,
            )
            return outcome.utterance
        except asyncio.TimeoutError:
            return "[假人 LLM 超时]"

    # ---------------- 结果构建 ----------------

    def _build_result(
        self,
        case: TestCase,
        started_at: datetime,
        error: Optional[str],
    ) -> RunResult:
        finished_at = datetime.now()
        trace_summary = self._trace.summary()

        # 判断 state_check 是否全通过
        state_checks = self._trace.get_state_checks()
        state_check_passed = all(sc.passed for _, sc in state_checks) if state_checks else True

        return RunResult(
            case_id=case.id,
            case_name=case.case_name,
            started_at=started_at,
            finished_at=finished_at,
            trace_summary=trace_summary,
            must_pass_assertions=list(case.must_pass_assertions),
            bonus_assertions=list(case.bonus_assertions),
            state_check_passed=state_check_passed,
            error=error,
        )
