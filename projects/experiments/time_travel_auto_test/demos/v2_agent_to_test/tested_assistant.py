"""TestedAssistant：被测助手实现。

实现 AssistantProtocol（见 case_runner/assistant_protocol.py），接入 CaseRunner。

设计：
- 基于 aicore v2 ReactAgentWithTaskRunner（直接用 agent.astream，不用 AgentRunner 常驻模式）
- 一个 TestedAssistant 实例对应一次 case 运行
- create(session_id) 重置会话
- achat / achat_stream 两种调用模式
- achat_stream 用 anyio.CancelScope 支持打断（StreamingReply.interrupt 取消消费协程）
- aupdate_context 更新车态上下文（车控工具直接操作 VirtualCar 实例）
- 车控工具操作 Runner 共享的 VirtualCar 实例
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Optional

import anyio
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

from aicore.v2.tools.factory import create_tool as create_async_tool
from projects.mind.toolset.web_search import WebsearchInput, _websearch_worker

from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    AssistantEvent,
    AssistantEventType,
    ContextUpdateResult,
    StreamingReply,
)
from projects.experiments.time_travel_auto_test.demos.tools.virtual_car_control import (
    VirtualCarControlTool,
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
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tools.scheduled_tasks.manager import (
    WORLD_TICK_BUFFER,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    WorldTickScriptEvent,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar


DEFAULT_SYSTEM_PROMPT = """你是友好的车载智能助手。用户请求天气、音乐、地点信息时，必须调用对应工具，不要凭空回答工具可以查询的问题。

**重要约定**：
1) 当某个 function_call_output 以 "[占位回执]" 开头时，代表该工具调用的真实结果尚未到达、工具仍在异步执行中。你必须只对用户简短说明正在查询/执行，不得再次调用同一工具，也不得再调用其它工具去补救。

2) 如果用户后续追问依赖某个正在异步执行中的工具真实结果，例如天气尚未返回时询问是否带伞、歌曲尚未返回时询问是否适合雨天、地点尚未返回时询问怎么过去，这类追问只能等待已有 pending 工具结果。你不得为了回答该追问重复调用同一工具，也不得调用其它工具替代回答；请简短告知用户需要等该工具真实结果返回后才能判断。

3) 只有当用户提出的是与 pending 工具无关的新需求，或者明确改变了工具查询目标/参数导致已有 pending 工具结果无法回答时，才可以创建新的工具调用。

4) 之后你会收到以 "[工具结果回灌]" 开头的用户消息，代表某个 pending 工具的真实返回结果。请把它当作真实工具结果，结合此前等待该结果的连续追问回复用户；只围绕该工具结果及其相关追问回复，不要额外调用工具。

5) 如果 "[工具结果回灌]" 中包含 "用户意图不清晰"、"需要向用户提问" 或类似澄清文本，说明该工具没有执行真实查询，而是在要求补充参数。如果后续对话中用户尚未补充该参数，请直接向用户提出这个澄清问题，不要说正在查询，也不要再次调用工具。如果后续对话中用户已经补充了该参数，或者已经基于补充信息创建了新的同类工具调用，则这个澄清结果已经过期，必须忽略它，不要再向用户重复提问，也不要输出额外回复。

6) 多个工具结果可能分批到达，按到达顺序逐个回复，已回复过的内容无需重复；如果存在更新的同类工具结果，以最新结果回复用户即可。

7) 用户明确要求取消尚未返回结果的任务时，根据对应占位回执找到 task_id 并调用 cancel_task。无法唯一确定目标时先询问，不要调用取消工具。取消多个任务必须由用户明确要求取消全部，或明确逐一指出多个目标。请根据 cancel_task 返回的 "[已取消]"、"[无需取消]" 或 "[取消失败]" 简短回复。

**车控与设备指令约定**：
- 车控（car_control 工具）：空调（开关/温度16-30度/制冷制热/风量）、门窗（行驶中无法操作）、座椅、灯光等车载设备控制
- 媒体控制（media 工具，独立工具非车控）：播放/暂停/继续、播放指定歌曲或歌手（如"播放周杰伦的晴天"）、播放歌单、音量调节、音源切换（蓝牙音乐/在线音乐/收音机/USB）、查询播放状态
- 导航控制（navigation 工具，独立工具非车控）：设置目的地开始导航（如"导航到虹桥火车站"）、取消导航、查询导航状态
- 工具执行后会返回执行状态和变更的状态，请基于实际结果回复用户

如果用户的任务复杂需要对不同工具进行组合编排，则优先调用 DAG工具，否则，调用其余业务工具。
"""


@dataclass
class BackfillUtterance:
    """一条回灌回复（异步工具真实结果到达后，助手自发产出的后续解答）。

    与端到端的普通助手回复一样区间化 + 流式分段：
    - started_wall / ended_wall：首字/末字的真实墙钟时刻（回灌生成期间记录）
    - text：完整内容
    - segments：[(wall_time, delta), ...] 流式 chunk 级时间戳
    """
    started_wall: datetime
    ended_wall: datetime
    text: str
    segments: list[tuple[datetime, str]]


class TestedAssistant:
    """被测助手：实现 AssistantProtocol，接入 CaseRunner。

    用法：
        assistant = TestedAssistant(virtual_car=my_car)
        assistant.create(session_id="case-001")
        reply = await assistant.achat("开空调")

    实现：
    - 直接用 ReactAgentWithTaskRunner.astream(input) 异步生成器，不通过 AgentRunner 常驻模式
    - achat_stream 用 anyio.CancelScope 包消费协程，StreamingReply.interrupt 触发取消
    - 车控工具操作 self.virtual_car（由 Runner 共享同一实例）
    """

    # 避免 pytest 误收集（类名以 Test 开头）
    __test__ = False

    def __init__(
        self,
        virtual_car: VirtualCar | None = None,
        model: ModelName = ModelName.SEED_2_0_PRO_260215,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        chat_id: str = "time-travel-demo",
    ) -> None:
        self.virtual_car: VirtualCar = virtual_car or VirtualCar()
        self.model: ModelName = model
        self.system_prompt: str = system_prompt
        # chat_id 用于天气工具等需要外部上下文的 worker（可被 create() 覆盖）
        self._chat_id: str = chat_id

        # 会话状态
        self._session_id: str = ""
        self._agent: Any = None  # ReactAgentWithTaskRunner，懒加载
        self._task_manager: TaskManager | None = None
        self._history: list[dict[str, str]] = []
        # 当前活跃流（插话打断目标）：新输入第一个 chunk 到达时 interrupt 它
        self._active_reply: StreamingReply | None = None
        # 实时虚拟时间源（Runner 注入 TimelineEngine.mock_time）：
        # set_reminder 等工具取当前时刻时自然流逝的虚拟时间，
        # trigger_time 天然包含助手回复耗时，无需偏移修正
        self._get_now: Optional[Callable[[], datetime]] = None
        # 最近一次 aupdate_context 同步的虚拟时间（get_now 未注入时的回退）
        self._current_time: Optional[datetime] = None
        self._pending_time_context: Optional[str] = None
        # 定时任务管理器
        self._scheduled_tasks = ScheduledTaskManager()

        # 文字层异步工具结果回灌循环（POI/音乐等 async 工具的真实结果回灌）：
        # - _agent_turn_lock 串行化 agent.astream 调用，防止回灌轮与用户轮争用模型链
        # - _task_manager_task 驱动 TaskManager 的 runner 真正执行异步任务
        # - _backfill_listener_task 监听 TaskSuccessEvent，把真实结果回灌给 agent
        self._agent_turn_lock = asyncio.Lock()
        self._task_manager_task: asyncio.Task | None = None
        self._backfill_listener_task: asyncio.Task | None = None
        self._backfill_utterances: asyncio.Queue[BackfillUtterance] = asyncio.Queue()
        # 回灌回复流式增量队列（供 Runner 实时发射 assistant_delta）：
        # 每条 = (mock_time, text)。回灌回复的 LLM 生成是慢速逐 token 产出，
        # 若不实时发射 delta，前端只能在整段回复生成完后看到一条完整 utterance
        # "瞬间出现"——对话流/时间线虽最终时间戳正确，实时模式无打字机过程。
        self._backfill_deltas: asyncio.Queue[tuple[datetime, str]] = asyncio.Queue()
        # 异步工具真实结果队列（供 Runner 记录为 TOOL_RESULT 事件，落到工具泳道）
        # 每条 = (mock_time, task_id, tool_name, result, duration_ms)。
        self._backfill_tool_results: asyncio.Queue[
            tuple[datetime, Optional[str], str, Any, float]
        ] = asyncio.Queue()
        # 异步工具调用队列（供 Runner 记录为 TOOL_CALL 事件，落到工具泳道）
        # 每条 = (mock_time, task_id, tool_name, tool_args)。
        self._backfill_tool_calls: asyncio.Queue[
            tuple[datetime, str, str, dict[str, Any]]
        ] = asyncio.Queue()
        # 异步任务开始虚拟时刻索引：task_id → 工具调用甩出时的 mock 时间，
        # 供 _handle_backfill 计算真实执行耗时（duration_ms，含快进后的虚拟时长）。
        self._task_start_mock: dict[str, datetime] = {}
        # 统一权威忙碌信号：覆盖回复流生成、后台异步任务、回灌回复生成三类
        # 进行中活动（原子计数，await_idle 据此判空，供时间快进前等待）。
        self._busy_count = 0

    # ---------------- AssistantProtocol 实现 ----------------

    def create(self, session_id: str, system_prompt: str = "") -> None:
        """创建/重置对话会话。"""
        self._session_id = session_id
        self._history = []
        if system_prompt:
            self.system_prompt = system_prompt
        # 停止上一会话的 TaskManager 后台任务，避免残留跨会话执行
        self._stop_task_manager()
        # 重置 agent，下次调用时重新懒加载（新 session 需要新 state）
        self._agent = None
        self._task_manager = None
        self._active_reply = None
        self._scheduled_tasks.clear()
        # 重置回灌循环状态
        self._agent_turn_lock = asyncio.Lock()
        self._backfill_utterances = asyncio.Queue()
        self._backfill_deltas = asyncio.Queue()
        self._backfill_tool_results = asyncio.Queue()
        self._backfill_tool_calls = asyncio.Queue()
        self._task_start_mock = {}
        self._busy_count = 0

    async def achat(self, user_text: str) -> str:
        """非流式对话：返回完整回复。"""
        agent = self._ensure_agent()

        # 注入 pending 时间上下文
        actual_input = self._inject_time_context(user_text)

        self._history.append({"role": "user", "content": actual_input})

        parts: list[str] = []
        async with self._agent_turn_lock:
            async for event in agent.astream(actual_input):
                chunk = _extract_text(event)
                if chunk:
                    parts.append(chunk)

        response = "".join(parts)
        self._history.append({"role": "assistant", "content": response})
        return response

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        """流式对话：投喂输入流，返回 StreamingReply 对象。

        插话打断契约（文字层，2026-08-26，仅接入层实现、不改底层框架）：
        - 第一个输入 chunk 到达 = 用户开口 → 立即 interrupt 旧的活跃流（若有），
          与音频层"用户开口即丢弃当前 TTS 播放"的打断语义对齐（v2_frontend_voice
          的插话打断在 TTS 层做，文字层由本接入层补齐）
        - v2_agent 底层不支持流式输入：聚合完整输入（等假人说完）再调底层
        - 被打断的旧轮次不会写回模型链（底层 response 未完成即被取消，
          model_api_state 不更新）——即"丢弃"语义：新轮基于打断前的链续接，
          被打断轮的半截话仅保留在本接入层 _history 供裁判回看
        """
        # 第一个 chunk = 用户开口信号：先打断旧流（插话打断）
        first: str | None = None
        async for c in chunks:
            first = c
            break
        if first is None:
            # 空输入流：不打断、不调底层，直接返回空回复
            reply = StreamingReply()
            await reply.finish()
            return reply
        old_reply = self._active_reply
        if old_reply is not None and not old_reply.is_done:
            old_reply.interrupt()
            # 半截话立即同步入 history（保证与后续 user 条目顺序确定）
            partial = old_reply.collected_text or ""
            self._history.append({
                "role": "assistant",
                "content": f"{partial}［被用户打断，未说完］" if partial else "［被用户打断，尚未开口］",
            })

        # 聚合剩余输入（模拟流式 ASR 接收端：说完才得到完整文本）
        rest: list[str] = [first]
        async for c in chunks:
            rest.append(c)
        user_text = "".join(rest)

        agent = self._ensure_agent()

        # 注入 pending 时间上下文
        actual_input = self._inject_time_context(user_text)

        self._history.append({"role": "user", "content": actual_input})
        reply = StreamingReply()
        self._active_reply = reply

        async def _produce() -> None:
            parts: list[str] = []
            self._mark_busy()  # 回复流生成占用忙碌信号（时间快进不能穿透进行中的回复）
            with anyio.CancelScope() as cs:
                reply._cancel_scope = cs  # 给 StreamingReply 持有，interrupt() 时调 cs.cancel()
                try:
                    async with self._agent_turn_lock:
                        async for event in agent.astream(actual_input):
                            if reply.is_interrupted:
                                break
                            translated = _translate_event(event)
                            if translated.type == AssistantEventType.TEXT_DELTA and translated.delta:
                                parts.append(translated.delta)
                                await reply.put_event(translated)
                            elif translated.type in (AssistantEventType.TOOL_CALL, AssistantEventType.TOOL_RESULT):
                                await reply.put_event(translated)
                    response = "".join(parts)
                    self._history.append({"role": "assistant", "content": response})
                except Exception as e:
                    self._history.append({"role": "assistant", "content": f"[错误: {e}]"})
                finally:
                    await reply.finish()
                    self._mark_idle()

        asyncio.create_task(_produce())
        return reply

    def set_time_source(self, get_now: Callable[[], datetime]) -> None:
        """注入实时虚拟时间源（由 Runner 在初始化时调用）。

        时间自然流逝模型下，set_reminder 等工具通过该时间源取当前虚拟时刻：
        助手回复期间时间照常流逝 → trigger_time 天然包含回复耗时，
        不再需要任何"时间偏移修正"补丁。
        """
        self._get_now = get_now

    def _current_virtual_time(self) -> datetime:
        """当前虚拟时间：优先实时时间源，回退到最近同步的快照。"""
        if self._get_now is not None:
            return self._get_now()
        return self._current_time or datetime.now()

    def _event_mock_time(self, event: Any) -> datetime:
        """事件产生时的虚拟时刻（消除消费延迟偏差，2026-09-03 修复）。

        TaskCreatedEvent / TaskSuccessEvent 继承 EventBase，其 timestamp 是
        事件产生（emit）时的墙钟时刻，独立于消费循环。多工具并行时，消费循环
        （_consume_task_events）会被回灌 LLM 生成阻塞而延迟消费；直接用
        `_current_virtual_time()`（消费时刻）会滞后，导致起止时刻几乎重合、
        duration_ms 塌缩为 ~0.5ms 的假值。

        这里用「当前虚拟时刻 −（当前墙钟 − 事件墙钟）」反推事件产生时的虚拟时刻：
        消费延迟窗口内 await_idle 保证无快进，mock 与 wall 按 1:1 流逝，反推成立。
        无 timestamp 属性（如测试桩 SimpleNamespace）时回退当前虚拟时刻。
        """
        ts = getattr(event, "timestamp", None)
        if ts is not None:
            return self._current_virtual_time() - (datetime.now() - ts)
        return self._current_virtual_time()

    async def aupdate_context(
        self,
        car_info: dict[str, Any],
        current_time: Optional[datetime] = None,
    ) -> ContextUpdateResult:
        """通知助手外部上下文变化（车态 + 时间）。

        - 时间推进时，检查定时任务管理器是否有到期任务。
        - 到期任务作为系统消息注入 Agent 对话，Agent 自然响应即为主动话语。
        - 时间锚点注入：收集待注入的 WorldTick 事件（trigger_time - 5s），
          放入 ContextUpdateResult.injected_events。
        """
        injected_events: list[WorldTickScriptEvent] = []

        if current_time is not None:
            old_time = self._current_time
            self._current_time = current_time
            self._pending_time_context = (
                f"[系统通知：当前时间已更新为 {current_time.strftime('%Y年%m月%d日 %H:%M:%S')}]"
            )

            # 收集待注入的时间锚点（WorldTick）
            for wt_abs, desc in self._scheduled_tasks.get_pending_world_ticks():
                if current_time is not None and wt_abs > current_time:
                    relative_offset = wt_abs - current_time
                    injected_events.append(
                        WorldTickScriptEvent(
                            event_t0_plus_timedelta=relative_offset,
                        )
                    )

            # 检查到期定时任务（快进时）
            if old_time is not None:
                due_tasks = self._scheduled_tasks.get_due_tasks(old_time, current_time)
                if due_tasks:
                    # 日志：到期任务信息
                    print(f"\n[ScheduledTask] 快进区间: {old_time.strftime('%H:%M:%S')} → {current_time.strftime('%H:%M:%S')}")
                    print(f"[ScheduledTask] 到期任务数: {len(due_tasks)}")
                    for i, t in enumerate(due_tasks):
                        print(f"[ScheduledTask]   [{i+1}] id={t.task_id}  触发时间={t.trigger_time.strftime('%H:%M:%S')}  描述={t.description}")
                    descriptions = "; ".join(t.description for t in due_tasks)
                    # 将到期任务作为系统消息注入 Agent，触发主动响应
                    agent = self._ensure_agent()
                    prompt = (
                        f"[系统通知：当前时间已更新为 {current_time.strftime('%Y年%m月%d日 %H:%M:%S')}。"
                        f"您设置的以下提醒已到期：{descriptions}。请立即提醒用户。]"
                    )
                    print(f"[ScheduledTask] 注入系统消息: {prompt}")
                    self._history.append({"role": "user", "content": prompt})
                    parts: list[str] = []
                    # 流式分段（chunk 级时间戳）：记录相对生成起点的偏移秒，
                    # 供 Runner 以 trigger 时刻为锚点重建主动话语的起止区间与流式内容
                    segments: list[tuple[float, str]] = []
                    gen_start = datetime.now()
                    async with self._agent_turn_lock:
                        async for event in agent.astream(prompt):
                            chunk = _extract_text(event)
                            if chunk:
                                parts.append(chunk)
                                segments.append(((datetime.now() - gen_start).total_seconds(), chunk))
                    response = "".join(parts)
                    print(f"[ScheduledTask] Agent 回复: {response}")
                    self._history.append({"role": "assistant", "content": response})
                    return ContextUpdateResult(
                        proactive_text=response,
                        injected_events=injected_events,
                        proactive_segments=segments,
                    )

        return ContextUpdateResult(injected_events=injected_events)

    async def adump_history(self) -> list[dict[str, str]]:
        """导出对话历史。"""
        return list(self._history)

    def get_pending_scheduled_tasks(self) -> list[tuple[datetime, str]]:
        """返回所有未触发的定时任务 (trigger_time, description)。

        供 Runner 在时间快进时判断中间停靠点，避免一步跳过定时任务触发时间。
        """
        return self._scheduled_tasks.get_pending_triggers()

    def _inject_time_context(self, user_text: str) -> str:
        """将 pending 时间上下文注入到用户消息开头，仅注入一次。"""
        if self._pending_time_context is not None:
            ctx = self._pending_time_context
            self._pending_time_context = None
            return f"{ctx}\n\n{user_text}"
        return user_text

    # ---------------- 内部方法 ----------------

    def _ensure_agent(self) -> Any:
        """懒加载 ReactAgentWithTaskRunner。"""
        if self._agent is not None:
            return self._agent

        self._task_manager = TaskManager()
        tools = [
            VirtualCarControlTool(self.virtual_car, task_manager=self._task_manager),
            NavigationControlTool(self.virtual_car, chat_id=self._chat_id, task_manager=self._task_manager),
            MediaControlTool(self.virtual_car, task_manager=self._task_manager),
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
            model=self.model,
            tools=tools,
            system_prompt=self.system_prompt,
            max_turns=10,
        )
        self._start_task_manager()
        return self._agent

    # ---------------- 异步工具结果回灌循环 ----------------

    def _start_task_manager(self) -> None:
        """启动 TaskManager runner 与事件监听任务。

        参考 v2 AgentRunner._listen_task：TaskManager.run() 驱动内部
        DynamicStreamTaskRunner 真正执行 async 工具（POI/音乐等），
        _consume_task_events 监听 TaskSuccessEvent 把真实结果回灌给 agent。
        """
        if self._task_manager_task is not None and not self._task_manager_task.done():
            return
        assert self._task_manager is not None
        self._task_manager_task = asyncio.create_task(
            self._task_manager.run(),
            name="tested-assistant-task-manager",
        )
        self._backfill_listener_task = asyncio.create_task(
            self._consume_task_events(),
            name="tested-assistant-backfill-listener",
        )

    def _stop_task_manager(self) -> None:
        """尽力取消上一会话的 TaskManager 后台任务（创建新会话前调用）。"""
        for task in (self._task_manager_task, self._backfill_listener_task):
            if task is not None and not task.done():
                task.cancel()
        self._task_manager_task = None
        self._backfill_listener_task = None

    async def _consume_task_events(self) -> None:
        """消费 TaskManager 对外事件流，维护统一忙碌计数并回灌真实结果。

        忙碌信号覆盖两类活动（与回复流 _produce 的 busy 叠加）：
        - 后台异步任务执行：TaskCreatedEvent +1，任务终态 -1
        - 回灌回复生成：TaskSuccessEvent 后由后台任务串行生成 +1/-1
          （_spawn_backfill_generation 同步 +1、生成收尾 -1；生成受
          _agent_turn_lock 串行，不阻塞本监听循环，避免工具事件被憋到
          锁释放后批量出现）
        """
        task_manager = self._task_manager
        assert task_manager is not None
        async for event in task_manager.astream():
            if isinstance(event, TaskCreatedEvent):
                self._mark_busy()  # 任务执行中
                # 工具调用落盘：把 TaskCreatedEvent 排队为 TOOL_CALL（Runner drain 时
                # record_tool_call → 前端工具泳道）。tool_name 用 event.name，
                # 与回灌 AsyncTaskResultBackfill.tool_name 一致。
                # 时刻取事件产生时的虚拟时刻（_event_mock_time 反推），
                # 避免多工具并行时消费循环被回灌阻塞导致的 start 滞后，
                # 也避免 wall_to_mock 在 drain 时因快进重锚定而时间漂移。
                now_mock = self._event_mock_time(event)
                self._task_start_mock[event.task_id] = now_mock
                await self._backfill_tool_calls.put(
                    (now_mock, event.task_id, event.name, event.arguments)
                )
                continue
            if isinstance(event, (TaskSuccessEvent, TaskFailureEvent, TaskCancelledEvent)):
                # 任务执行结束，先释放"任务执行中"的 busy
                self._mark_idle()
                if isinstance(event, TaskSuccessEvent):
                    # 真实结果排队（不取锁）：立即落盘到工具泳道
                    await self._record_backfill_tool_result(event)
                    # 回灌回复生成单独占一个 busy、放到后台任务串行生成，
                    # 不阻塞本监听循环——否则后续工具的 TaskCreated/TaskSuccess
                    # 会被憋到长助话语（"正在查询…"贯穿多个工具窗口）释放锁后
                    # 才批量处理，实时模式下工具与主动话语"瞬间涌入"
                    self._spawn_backfill_generation(event)

    async def _record_backfill_tool_result(self, event: TaskSuccessEvent) -> None:
        """把一个异步任务的真实结果排队为 TOOL_RESULT（落到工具泳道）。

        不取 agent_turn_lock：结果落盘与实际回复生成解耦，监听循环可立即
        继续处理后续工具的 TaskCreated/TaskSuccess，避免工具区间被长助话语
        憋到锁释放后才批量出现。

        携带 task_id 供前端按 id 精确配对（并行同名工具不误配），并计算
        真实耗时 duration_ms = result 时刻 − call 时刻（事件产生时的虚拟时刻，
        由 _event_mock_time 反推，避开消费延迟导致的起止时刻塌缩）。
        """
        result_obj = getattr(event, "result", None)
        tool_name = getattr(result_obj, "tool_name", "") if result_obj is not None else ""
        if not tool_name:
            return
        task_id = getattr(event, "task_id", None)
        raw_result = getattr(result_obj, "result", None)
        now_mock = self._event_mock_time(event)
        start_mock = self._task_start_mock.pop(task_id, None) if task_id else None
        duration_ms = (
            (now_mock - start_mock).total_seconds() * 1000.0
            if start_mock is not None
            else 0.0
        )
        await self._backfill_tool_results.put(
            (now_mock, task_id, tool_name, raw_result, duration_ms)
        )

    def _spawn_backfill_generation(self, event: TaskSuccessEvent) -> None:
        """把回灌回复生成放到后台任务串行运行，不阻塞监听循环。

        生成回复仍受 _agent_turn_lock 串行化（模型链单线程），多个任务的
        生成任务按锁的 FIFO 顺序依次执行；busy 计数在此同步 +1，在任务收尾
        _mark_idle -1，供 await_idle 判定"回灌全部生成完毕"。
        """
        self._mark_busy()

        async def _run() -> None:
            try:
                await self._handle_backfill(event)
            finally:
                self._mark_idle()

        asyncio.create_task(_run(), name="tested-assistant-backfill-generation")

    async def _handle_backfill(self, event: TaskSuccessEvent) -> None:
        """把一个异步任务的真实结果回灌给 agent，产出回复并排队供 Runner 记录。

        底层 ReactAgentWithTaskRunner.astream 接受 TaskSuccessEvent 为输入，
        内部取 nl_repr(input.result)（即 AsyncTaskResultBackfill 的
        "[工具结果回灌] ..." 文本）追加到模型链，生成自然的后续回复。
        """
        agent = self._agent
        if agent is None:
            return
        parts: list[str] = []
        segments: list[tuple[datetime, str]] = []
        started_wall: Optional[datetime] = None
        ended_wall: Optional[datetime] = None
        async with self._agent_turn_lock:
            async for out in agent.astream(event):
                text = _extract_text(out)
                if text:
                    now = datetime.now()
                    if started_wall is None:
                        started_wall = now
                    ended_wall = now
                    parts.append(text)
                    segments.append((now, text))
                    # 实时推送增量：让 Runner 逐 token 发射 assistant_delta，
                    # 前端打字机显示，而非等整段回复生成完后一次性 utterance
                    # "瞬间出现"（回灌回复的 LLM 生成是慢速逐 token 产出）。
                    # 虚拟时刻取生成当下（_current_virtual_time），与工具回灌
                    # 队列一致，规避 Runner drain 时快进重锚定导致的时间漂移。
                    await self._backfill_deltas.put((self._current_virtual_time(), text))
        response = "".join(parts).strip()
        if response:
            self._history.append({"role": "assistant", "content": response})
            await self._backfill_utterances.put(
                BackfillUtterance(
                    started_wall=started_wall or ended_wall or datetime.now(),
                    ended_wall=ended_wall or started_wall or datetime.now(),
                    text=response,
                    segments=segments,
                )
            )

    def drain_backfill_utterances(self) -> list[BackfillUtterance]:
        """取出并清空已产出的回灌回复（每条含起止 wall 时刻与流式 segments）。"""
        out: list[BackfillUtterance] = []
        while not self._backfill_utterances.empty():
            try:
                out.append(self._backfill_utterances.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def drain_backfill_deltas(self) -> list[tuple[datetime, str]]:
        """取出并清空回灌回复的流式增量（供 Runner 实时发射 assistant_delta）。

        每条 = (mock_time, text)：mock_time 为增量产出时的虚拟时刻，生成当下取
        （_current_virtual_time），与工具回灌队列一致，规避 Runner drain 时快进
        重锚定导致的时间漂移。Runner 侧无需再 wall_to_mock。
        """
        out: list[tuple[datetime, str]] = []
        while not self._backfill_deltas.empty():
            try:
                out.append(self._backfill_deltas.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def drain_backfill_tool_results(
        self,
    ) -> list[tuple[datetime, Optional[str], str, Any, float]]:
        """取出并清空已产出的异步工具真实结果。

        每条 = (mock_time, task_id, tool_name, result, duration_ms)。
        mock_time 为事件产生时的虚拟时刻（非 wall），task_id 供精确配对，
        duration_ms 为 call→result 的虚拟执行耗时。
        """
        out: list[tuple[datetime, Optional[str], str, Any, float]] = []
        while not self._backfill_tool_results.empty():
            try:
                out.append(self._backfill_tool_results.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def drain_backfill_tool_calls(self) -> list[tuple[datetime, str, str, dict[str, Any]]]:
        """取出并清空已创建的异步工具调用。

        每条 = (mock_time, task_id, tool_name, tool_args)：mock_time 为事件产生
        时的虚拟时刻（非 wall），task_id 供与结果端精确配对。
        """
        out: list[tuple[datetime, str, str, dict[str, Any]]] = []
        while not self._backfill_tool_calls.empty():
            try:
                out.append(self._backfill_tool_calls.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def _mark_busy(self) -> None:
        """占用一个忙碌信号（进入进行中活动）。"""
        self._busy_count += 1

    def _mark_idle(self) -> None:
        """释放一个忙碌信号（活动结束）。"""
        if self._busy_count > 0:
            self._busy_count -= 1

    async def await_idle(self, timeout: float = 30.0) -> None:
        """等待助手所有进行中活动结束（超时则静默返回，不抛异常）。

        统一权威忙碌信号——覆盖三类活动：
        - 回复流生成（achat_stream 的 _produce）
        - 后台异步任务执行（TaskCreatedEvent → 终态）
        - 回灌回复生成（TaskSuccessEvent 后的 LLM 生成）

        竞态兜底（2026-08-31）：busy_count 的增减由 _consume_task_events 异步投影，
        存在「任务已 submit 但 TaskCreatedEvent 尚未投递计数」窗口。task_manager.get_active_tasks()
        是同步原子查询（submit_task 单事件循环内同步写 _store），用它同步判空覆盖该窗口；
        再加连续两拍稳定判空，兜住事件投影的异步延迟。
        """
        task_manager = self._task_manager
        deadline = asyncio.get_running_loop().time() + timeout
        idle_rounds = 0
        while asyncio.get_running_loop().time() < deadline:
            active = bool(task_manager.get_active_tasks()) if task_manager is not None else False
            busy = self._busy_count > 0 or active
            if busy:
                idle_rounds = 0
            else:
                idle_rounds += 1
                if idle_rounds >= 2:
                    return
            await asyncio.sleep(0.05)

    async def await_async_idle(self, timeout: float = 30.0) -> None:
        """向后兼容别名：等价 await_idle（详见 await_idle 文档）。"""
        await self.await_idle(timeout=timeout)


def _translate_event(event: Any) -> AssistantEvent:
    """将 v2_agent 原生事件翻译为 AssistantEvent。

    检测逻辑（按优先级）：
    1. tool_calls 属性 → TOOL_CALL（模型决定调用工具）
    2. tool_result / output 属性 → TOOL_RESULT（工具返回结果）
    3. delta / text 属性 → TEXT_DELTA（文本增量）
    4. 其他事件 → 空 TEXT_DELTA（会被调用方过滤）

    注：v2 真实 agent 的工具调用/结果不经过 astream yield 流，而是走
    TaskManager.astream()（TaskCreatedEvent / TaskSuccessEvent），由
    _consume_task_events 统一处理——此处的 tool_calls / tool_result 分支
    仅用于兼容其他（同步工具流式）agent 实现。
    """
    now = datetime.now()

    # 检测工具调用
    tool_calls = getattr(event, "tool_calls", None)
    if tool_calls:
        if isinstance(tool_calls, list) and len(tool_calls) > 0:
            tc = tool_calls[0]
            return AssistantEvent(
                type=AssistantEventType.TOOL_CALL,
                wall_time=now,
                tool_name=getattr(tc, "name", str(tc)),
                tool_args=getattr(tc, "args", {}) if hasattr(tc, "args") else {},
            )

    # 检测工具结果
    tool_result = getattr(event, "tool_result", None) or getattr(event, "output", None)
    if tool_result is not None:
        return AssistantEvent(
            type=AssistantEventType.TOOL_RESULT,
            wall_time=now,
            tool_name=getattr(event, "tool_name", "") or getattr(event, "name", ""),
            tool_result=tool_result,
            tool_duration_ms=getattr(event, "duration_ms", 0.0),
        )

    # 默认：文本增量
    delta = getattr(event, "delta", None) or getattr(event, "text", None) or ""
    return AssistantEvent(
        type=AssistantEventType.TEXT_DELTA,
        wall_time=now,
        delta=delta,
    )


def _extract_text(event: Any) -> str:
    """从 agent 事件中提取文本增量（兼容旧版）。

    aicore v2 的 AgentOutTextDeltaEvent 有 delta 字段；
    AgentOutTextStartEvent / AgentOutTextDoneEvent 无 payload；
    TaskCreatedEvent 等任务事件无文本。
    """
    delta = getattr(event, "delta", None)
    if delta:
        return delta
    text = getattr(event, "text", None)
    if text:
        return text
    return ""
