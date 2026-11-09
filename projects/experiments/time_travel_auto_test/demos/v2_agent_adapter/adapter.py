"""V2AgentAdapter：把真实 v2_agent（ReactAgentWithTaskRunner）接入新协议。

对照旧接入（demos/v2_agent_to_test/tested_assistant.py）：
- 旧协议把「异步工具回灌、空闲判定、wall→mock 换算、hasattr 散落钩子」全部甩给接入者，
  导致 tested_assistant.py 膨胀到 780+ 行。
- 新协议（adapter_v2.AssistantAdapter）内核提供这些脏活，接入者只交：
  能力声明 / 初始源 / 翻译 / 结果续接 / 世界更新 / 历史导出，其余框架全包。

本适配器的关键映射（v2_agent 底层事件流 → 统一事件）：
1. agent.astream(input) 只往外冒文本增量 AgentOutTextDeltaEvent（异步工具调用
   不经过这条流，而是走 TaskManager.astream() —— 见 _react_to_agent_out_event
   里对 TaskSuccessEvent 的丢弃分支）。所以「回复源」= agent.astream。
2. 工具的 TaskCreatedEvent / TaskSuccessEvent（真实结果回灌）只出现在
   TaskManager.astream() 这条持久流里。适配器用一个后台排水泵持续消费它，
   按 task_id → 所属回合路由到对应回合的任务事件队列。
3. TaskSuccessEvent 携带 result=AsyncTaskResultBackfill（真实结果），
   通过 on_result 挂载「接续回复源」= agent.astream(TaskSuccessEvent)，
   生成「工具结果回来 → 接着往下说」的后续回复。
4. 定时提醒：apply_world_update 检测到期任务，PROACTIVE 回合再驱动 agent 开口。

插话打断（助手自驱）：新 USER 回合到来时，initial_sources 置位旧回合的打断信号，
旧回复源在下一个 token 间隔点自行提前结束（半截话），框架全程不 cancel 旧流——
与协议 Capabilities.supports_barge_in 语义、mock_adapter 参考实现一致。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from aicore.events.agent import AgentOutTextDeltaEvent
from aicore.events.task import (
    TaskCancelledEvent,
    TaskCreatedEvent,
    TaskFailureEvent,
    TaskSuccessEvent,
)
from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskManager
from aicore.v2.experiments.music_search_v2 import qq_music_song_search_v2_tool
from aicore.v2.experiments.poi_search_v2 import poi_search_v2_tool
from aicore.v2.experiments.react_agent_with_task_runner import (
    create_react_agent_with_task_runner,
)
from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
from aicore.v2.experiments.weather_v2 import weather_search_v2_tool
from aicore.v2.tools.async_task import AsyncTaskResultBackfill
from aicore.v2.tools.factory import create_tool as create_async_tool

from projects.mind.toolset.web_search import WebsearchInput, _websearch_worker

from projects.experiments.time_travel_auto_test.adapter_v2.protocol import (
    AdapterEnv,
    AssistantEvent,
    Capabilities,
    EventType,
    Turn,
    TurnKind,
    WorldUpdate,
)
from projects.experiments.time_travel_auto_test.demos.tools.virtual_car_control import (
    VirtualCarControlTool,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import (
    DEFAULT_SYSTEM_PROMPT,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tools.media_control import (
    MediaControlTool,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tools.navigation_control import (
    NavigationControlTool,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tools.scheduled_tasks import (
    ScheduledTaskManager,
    create_reminder_tool,
)


def _event_text(event: Any) -> str:
    """从 agent 原生事件提取文本增量（仅 AgentOutTextDeltaEvent 有内容）。"""
    delta = getattr(event, "delta", None)
    if delta:
        return delta
    text = getattr(event, "text", None)
    return text or ""


@dataclass
class _TurnCtx:
    """一个 USER 回合的任务事件上下文。

    后台排水泵把 TaskCreatedEvent / 终态事件按 task_id 路由到对应回合的队列，
    回合的任务事件源（_task_source）据此产出 TOOL_CALL / TOOL_RESULT，
    并在「回复源结束且无未决任务」时自然收尾。
    """

    key: int
    queue: asyncio.Queue
    reply_done: bool = False
    # 本回合已创建但尚未收尾的 task_id（终态事件到达时清除）
    outstanding: set[str] = field(default_factory=set)


class V2AgentAdapter:
    """真实 v2_agent 的新协议适配器（实现 adapter_v2.AssistantAdapter）。"""

    # 避免 pytest 误收集
    __test__ = False

    def __init__(
        self,
        virtual_car: Any = None,
        model: ModelName = ModelName.SEED_2_0_PRO_260215,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        chat_id: str = "time-travel-demo",
    ) -> None:
        self._initial_car = virtual_car
        self._model: ModelName = model
        self._system_prompt: str = system_prompt
        self._chat_id: str = chat_id

        self._car: Any = None
        self._get_virtual_time: Optional[Any] = None

        # 会话状态
        self._session_id = ""
        self._agent: Any = None
        self._task_manager: Optional[TaskManager] = None
        self._task_manager_task: Optional[asyncio.Task] = None
        self._pump_task: Optional[asyncio.Task] = None
        self._agent_turn_lock: asyncio.Lock = asyncio.Lock()
        self._history: list[dict[str, str]] = []

        # 定时任务
        self._scheduled_tasks = ScheduledTaskManager()
        self._pending_proactive_prompts: list[str] = []
        self._pending_time_context: Optional[str] = None
        self._current_time: Optional[datetime] = None

        # 插话打断（助手自驱）：当前可被打断的回复源的信号
        self._active_barge_signal: Optional[asyncio.Event] = None

        # 任务事件路由
        self._turn_ctxs: dict[int, _TurnCtx] = {}
        self._task_owner: dict[str, int] = {}  # task_id -> owner 回合 key
        self._current_turn_id: Optional[int] = None

    # ---------------- 能力声明 ----------------

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_barge_in=True,
            has_async_tools=True,
            can_proactive_speak=True,
            needs_time_source=True,
        )

    # ---------------- 会话初始化 ----------------

    def setup(self, env: AdapterEnv) -> None:
        self._session_id = env.session_id
        self._car = env.virtual_car if env.virtual_car is not None else self._initial_car
        self._get_virtual_time = env.get_virtual_time
        if env.system_prompt:
            self._system_prompt = env.system_prompt

        self._history = []
        self._scheduled_tasks = ScheduledTaskManager()
        self._pending_proactive_prompts = []
        self._pending_time_context = None
        self._current_time = None
        self._active_barge_signal = None
        self._turn_ctxs = {}
        self._task_owner = {}
        self._current_turn_id = None
        self._agent_turn_lock = asyncio.Lock()

        # 停止上一会话的后台任务，重置 agent（下次懒加载）
        self._stop_task_manager()
        self._agent = None
        self._task_manager = None

    # ---------------- 初始源 ----------------

    def initial_sources(self, turn: Turn) -> list[AsyncIterator[Any]]:
        if turn.kind is TurnKind.USER:
            # 插话打断（助手自驱，中立观察者）：新输入到来，置位旧回复源打断信号
            if self.capabilities.supports_barge_in and self._active_barge_signal is not None:
                self._active_barge_signal.set()

            ctx = _TurnCtx(key=id(turn), queue=asyncio.Queue())
            self._turn_ctxs[id(turn)] = ctx
            self._current_turn_id = id(turn)

            actual = self._inject_time_context(turn.text)
            self._history.append({"role": "user", "content": actual})
            return [self._reply_source(ctx, actual), self._task_source(ctx)]

        if turn.kind is TurnKind.PROACTIVE:
            return [self._proactive_source(turn)]

        return []

    # ---------------- 翻译（纯函数） ----------------

    def translate(self, raw: Any) -> Optional[AssistantEvent]:
        if isinstance(raw, AgentOutTextDeltaEvent):
            wall = getattr(raw, "timestamp", None) or datetime.now()
            return AssistantEvent(
                type=EventType.TEXT_DELTA, wall_time=wall, delta=raw.delta
            )

        if isinstance(raw, TaskCreatedEvent):
            wall = getattr(raw, "timestamp", None) or datetime.now()
            return AssistantEvent(
                type=EventType.TOOL_CALL,
                wall_time=wall,
                tool_name=raw.name,
                tool_args=raw.arguments,
                task_id=raw.task_id,
            )

        if isinstance(raw, TaskSuccessEvent):
            result = getattr(raw, "result", None)
            if isinstance(result, AsyncTaskResultBackfill):
                wall = getattr(raw, "timestamp", None) or datetime.now()
                return AssistantEvent(
                    type=EventType.TOOL_RESULT,
                    wall_time=wall,
                    tool_name=result.tool_name,
                    tool_result=result.result,
                    task_id=raw.task_id,
                )
            return None  # 非回灌结果（如同步工具）不进入统一事件流

        return None

    # ---------------- 结果续接 ----------------

    def on_result(self, raw: Any) -> Optional[AsyncIterator[Any]]:
        """异步工具真实结果回灌到达 → 挂载接续回复源（接着往下说）。"""
        if isinstance(raw, TaskSuccessEvent):
            result = getattr(raw, "result", None)
            if isinstance(result, AsyncTaskResultBackfill):
                return self._agent_stream(raw, bargeable=False)
        return None

    # ---------------- 世界更新 ----------------

    async def apply_world_update(self, update: WorldUpdate) -> list[datetime]:
        anchors: list[datetime] = []
        ct = update.current_time
        if ct is None:
            return anchors

        old = self._current_time
        self._current_time = ct
        self._pending_time_context = (
            f"[系统通知：当前时间已更新为 {ct.strftime('%Y年%m月%d日 %H:%M:%S')}]"
        )

        if old is None:
            return anchors

        # 时间锚点：定时任务触发前 WORLD_TICK_BUFFER 秒停靠，避免快进一步跳过
        for wt_abs, _desc in self._scheduled_tasks.get_pending_world_ticks():
            if wt_abs > ct:
                anchors.append(wt_abs)

        due = self._scheduled_tasks.get_due_tasks(old, ct)
        if due:
            descriptions = "; ".join(t.description for t in due)
            prompt = (
                f"[系统通知：当前时间已更新为 {ct.strftime('%Y年%m月%d日 %H:%M:%S')}。"
                f"您设置的以下提醒已到期：{descriptions}。请立即提醒用户。]"
            )
            self._history.append({"role": "user", "content": prompt})
            self._pending_proactive_prompts.append(prompt)

        return anchors

    # ---------------- 历史导出 ----------------

    def dump_history(self) -> list[dict[str, str]]:
        return list(self._history)

    # ---------------- 各条原生源 ----------------

    async def _reply_source(self, ctx: _TurnCtx, actual: str) -> AsyncIterator[Any]:
        """回复源：跑 agent.astream，产出文本增量；结束/被打断后标记回合完成。"""
        try:
            async for event in self._agent_stream(actual, bargeable=True):
                yield event
        finally:
            ctx.reply_done = True
            # 同步认领本回合仍在执行的任务（submit_task 已同步写入 _store），
            # 兜住「排水泵尚未路由 TaskCreatedEvent」的异步投影窗口
            self._claim_active_tasks(ctx)

    async def _task_source(self, ctx: _TurnCtx) -> AsyncIterator[Any]:
        """任务事件源：产出本回合的工具调用/结果，回复结束且无未决任务时收尾。"""
        idle = 0
        while True:
            while not ctx.queue.empty():
                idle = 0
                yield ctx.queue.get_nowait()

            if ctx.reply_done and not ctx.outstanding:
                idle += 1
                if idle >= 2:
                    return  # 双拍稳定判空，兜住排水泵延迟投影

            try:
                raw = await asyncio.wait_for(ctx.queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            idle = 0
            yield raw

    async def _proactive_source(self, turn: Turn) -> AsyncIterator[Any]:
        """主动话语源：到期提醒驱动 agent 自主开口（无用户输入）。"""
        if not self._pending_proactive_prompts:
            return
        prompt = self._pending_proactive_prompts.pop(0)
        async for event in self._agent_stream(prompt, bargeable=False):
            yield event

    async def _agent_stream(self, input_data: Any, *, bargeable: bool) -> AsyncIterator[Any]:
        """跑一轮 agent.astream，产出原生事件并写回历史。

        - bargeable=True 时注册打断信号：新 USER 回合置位后，本流在下一个
          token 间隔点自行提前结束（半截话，不回写模型链，即「丢弃」语义）。
        - 所有 agent.astream 调用串行化（模型链单线程），避免回灌轮与用户轮
          并发争用导致竞态/上下文倒置。
        """
        agent = self._ensure_agent()
        parts: list[str] = []
        signal = asyncio.Event()
        if bargeable:
            self._active_barge_signal = signal
        try:
            async with self._agent_turn_lock:
                async for event in agent.astream(input_data):
                    if signal.is_set():
                        break
                    text = _event_text(event)
                    if text:
                        parts.append(text)
                    yield event
        finally:
            if bargeable and self._active_barge_signal is signal:
                self._active_barge_signal = None
            content = "".join(parts)
            if content:
                self._history.append({"role": "assistant", "content": content})

    # ---------------- 内部：agent 懒加载 + 任务排水泵 ----------------

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        self._task_manager = TaskManager()
        tools = [
            VirtualCarControlTool(self._car, task_manager=self._task_manager),
            NavigationControlTool(self._car, chat_id=self._chat_id, task_manager=self._task_manager),
            MediaControlTool(self._car, task_manager=self._task_manager),
            weather_search_v2_tool(task_manager=self._task_manager, chat_id=self._chat_id),
            poi_search_v2_tool(task_manager=self._task_manager),
            qq_music_song_search_v2_tool(task_manager=self._task_manager),
            create_async_tool(
                name="websearch",
                description="通用联网搜索",
                args_schema=WebsearchInput,
                worker=_websearch_worker,
                asyncable="async",
                task_manager=self._task_manager,
            ),
            create_task_cancel_tool(task_manager=self._task_manager),
            create_reminder_tool(
                self._scheduled_tasks,
                self._current_virtual_time,
                task_manager=self._task_manager,
            ),
        ]

        self._agent = create_react_agent_with_task_runner(
            model=self._model,
            tools=tools,
            system_prompt=self._system_prompt,
            max_turns=10,
        )
        self._start_task_manager()
        return self._agent

    def _start_task_manager(self) -> None:
        if self._task_manager_task is not None and not self._task_manager_task.done():
            return
        assert self._task_manager is not None
        self._task_manager_task = asyncio.create_task(
            self._task_manager.run(), name="v2-adapter-task-manager"
        )
        self._pump_task = asyncio.create_task(
            self._pump(), name="v2-adapter-task-pump"
        )

    def _stop_task_manager(self) -> None:
        for task in (self._task_manager_task, self._pump_task):
            if task is not None and not task.done():
                task.cancel()
        self._task_manager_task = None
        self._pump_task = None

    async def _pump(self) -> None:
        """后台排水泵：消费 TaskManager 对外事件流，按 task_id 路由到回合队列。"""
        assert self._task_manager is not None
        async for event in self._task_manager.astream():
            if isinstance(event, TaskCreatedEvent):
                owner = self._current_turn_id
                if owner is None:
                    continue
                self._task_owner[event.task_id] = owner
                ctx = self._turn_ctxs.get(owner)
                if ctx is not None:
                    ctx.outstanding.add(event.task_id)
                    await ctx.queue.put(event)
            elif isinstance(event, (TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent)):
                owner = self._task_owner.pop(event.task_id, None)
                ctx = self._turn_ctxs.get(owner) if owner is not None else None
                if ctx is not None:
                    ctx.outstanding.discard(event.task_id)
                    await ctx.queue.put(event)
            # TaskStartEvent / TaskProgressEvent 不进入统一事件流

    # ---------------- 内部：辅助 ----------------

    def _claim_active_tasks(self, ctx: _TurnCtx) -> None:
        """同步认领当前仍在执行的任务归属本回合（兜底异步投影延迟）。"""
        tm = self._task_manager
        if tm is None:
            return
        for run in tm.get_active_tasks():
            self._task_owner.setdefault(run.task_id, ctx.key)
            if self._task_owner.get(run.task_id) == ctx.key:
                ctx.outstanding.add(run.task_id)

    def _current_virtual_time(self) -> datetime:
        if self._get_virtual_time is not None:
            return self._get_virtual_time()
        return self._current_time or datetime.now()

    def _inject_time_context(self, text: str) -> str:
        if self._pending_time_context is not None:
            ctx = self._pending_time_context
            self._pending_time_context = None
            return f"{ctx}\n\n{text}"
        return text