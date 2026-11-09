"""CaseRunner 端到端测试：用 mock assistant 跑通完整流程。

不依赖真实 LLM，验证：
1. Runner 能加载 case、初始化、调度事件
2. 假人固定台词 → 助手 mock 回复 → trace 记录
3. 虚拟车 set_state / state_check 正确执行
4. RunResult 正确返回
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

import pytest

from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    AssistantEvent,
    AssistantEventType,
    ContextUpdateResult,
    StreamingReply,
)
from projects.experiments.time_travel_auto_test.case_runner.mock_assistant import (
    MockAssistant,
)
from projects.experiments.time_travel_auto_test.visualizer.event_bus import EventBus
from projects.experiments.time_travel_auto_test.case_runner.runner import (
    CaseRunner,
    RunnerConfig,
)
from projects.experiments.time_travel_auto_test.case_runner.trace import RecordKind
from projects.experiments.time_travel_auto_test.case_schema import (
    FakePersonInfo,
    TestCase,
    VirtualCarInfo,
    load_test_cases_from_json_file,
)
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonSpeakArgs,
    FakePersonSpeakPerformAction,
)
from projects.experiments.time_travel_auto_test.judge.prompt import render_timeline_text
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarSetStateArgs,
    VirtualCarSetStatePerformAction,
    VirtualCarStateCheckAction,
    VirtualCarStateCheckArgs,
    VirtualCarStateCheckScriptEvent,
    WorldTickScriptEvent,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"
FIXTURE_CASES_FILE = CASES_DIR / "fixture_cases.json"


@pytest.mark.anyio
async def test_case_001_simple_flow() -> None:
    """case-001：假人说话 → 助手回复 → state_check。"""
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    case = next(c for c in cases if c.id == "case-001")

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.case_id == "case-001"
    assert result.error is None
    # trace 应有：1 假人说话 + 1 助手回复 + 1 state_check
    summary = result.trace_summary
    assert summary["total_utterances"] == 2  # 假人 + 助手
    assert summary["total_state_checks"] == 1
    # state_check 应通过（mock 助手开了空调）
    assert result.state_check_passed is True
    assert summary["state_checks_passed"] == 1
    assert summary["state_checks_failed"] == 0


@pytest.mark.anyio
async def test_case_004_driving_scenario() -> None:
    """case-004：开门请求 → 车态变更 → state_check → 再次请求。"""
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    case = next(c for c in cases if c.id == "case-004")

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.error is None
    # case-004 有 3 个 script_events（2 假人 + 1 车态）+ 1 state_check
    summary = result.trace_summary
    # 假人说话 2 次 + 助手回复 2 次 = 4 utterances
    assert summary["total_utterances"] == 4
    assert summary["total_state_checks"] == 1
    # state_check 验证车速 40km/h（mock 助手不操作车速，由剧本 set_state 写入）
    assert result.state_check_passed is True


@pytest.mark.anyio
async def test_case_008_pure_boundary() -> None:
    """case-008：纯边界驱动（4 个边界事件）。"""
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    case = next(c for c in cases if c.id == "case-008")

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.error is None
    # 4 个假人说话 + 4 个助手回复 = 8 utterances
    summary = result.trace_summary
    assert summary["total_utterances"] == 8


@pytest.mark.anyio
async def test_case_012_state_check_failure() -> None:
    """case-012：state_check 失败场景。

    mock 助手用 "空调状态" key 开空调，但 case-012 state_check 期望 "空调开启状态及模式"。
    实际 mock 助手只在 "开空调" 时写 "空调开启状态及模式"，
    case-012 用户说 "打开空调制冷" 触发写入，state_check 期望 "制冷中" 应通过。
    """
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    case = next(c for c in cases if c.id == "case-012")

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.error is None
    # mock 助手开空调写入 "空调开启状态及模式"="制冷中"，state_check 应通过
    # 注意 case-012 初始 car_info 用了 "空调状态" key（不一致），但 mock 助手写的是标准 key
    summary = result.trace_summary
    assert summary["total_state_checks"] == 1


@pytest.mark.anyio
async def test_case_007_long_period_with_fast_mode() -> None:
    """case-007：长周期 case（P5D 锚点），用 fast_mode 跳过 5 天等待。"""
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    case = next(c for c in cases if c.id == "case-007")

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.error is None
    # case-007: PT0S 假人 + P5D 车态 + P5DT10S 假人 = 2 假人 + 2 助手 = 4 utterances
    summary = result.trace_summary
    assert summary["total_utterances"] == 4


@pytest.mark.anyio
async def test_case_010_long_period_with_fast_mode() -> None:
    """case-010：长周期 case（P5D 锚点），用 fast_mode 跳过。"""
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    case = next(c for c in cases if c.id == "case-010")

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.error is None
    # case-010: PT0S 假人 + P5D 车态 + P5DT5S 假人 = 2 假人 + 2 助手 = 4 utterances
    summary = result.trace_summary
    assert summary["total_utterances"] == 4


@pytest.mark.anyio
async def test_run_with_streaming() -> None:
    """测试流式模式。"""
    case = TestCase(
        id="test-stream",
        case_name="流式测试",
        case_description="测试流式回复",
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="开空调"),
                ),
            ),
        ],
        text_script="用户：开空调",
    )

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=True, fast_mode=True),
    )

    result = await runner.run(case)

    assert result.error is None
    assert result.trace_summary["total_utterances"] == 2


@pytest.mark.anyio
async def test_tool_execution_gap_not_long_pause() -> None:
    """工具执行期间（call→result）的间隔是正常执行时间，不算流式停顿。

    ToolGapMockAssistant 在 TOOL_CALL 后 sleep 2.5s（> 2s 阈值）再发
    TOOL_RESULT——修复前会被误报为 long_pause。
    """
    case = TestCase(
        id="test-tool-gap",
        case_name="工具执行间隔测试",
        case_description="工具执行期间不记流式停顿",
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="帮我定个提醒"),
                ),
            ),
        ],
        text_script="用户：帮我定个提醒",
    )

    bus = EventBus()
    events: list[dict] = []
    bus.subscribe(lambda envelope: events.append(envelope))

    assistant = ToolGapMockAssistant(tool_delay=2.5)
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=True, fast_mode=True),
        event_bus=bus,
    )

    result = await runner.run(case)

    assert result.error is None
    kinds = [e["kind"] for e in events]
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert "long_pause" not in kinds, "工具执行间隔被误报为流式停顿"


@pytest.mark.anyio
async def test_case_started_emits_script_plan() -> None:
    """case_started 携带剧本时间表（script_plan）：前端"未来区"预设事件竖线的数据源。

    锚点驱动事件（假人说话/剧本改车态/状态检查）按时刻排序进入时间表；
    边界驱动事件（无锚点时刻）无法定位，不进入。
    """
    t0 = datetime.now().replace(microsecond=0)
    case = TestCase(
        id="test-script-plan",
        case_name="剧本时间表测试",
        case_description="case_started 应携带锚点事件预览清单",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="开下空调"),
                ),
            ),
            VirtualCarPerformScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=30),
                target="car",
                action=VirtualCarSetStatePerformAction(
                    args=VirtualCarSetStateArgs(fields={"车速": "60 km/h"}),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=60),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "制冷中"},
                    ),
                ),
            ),
        ],
    )

    bus = EventBus()
    events: list[dict] = []
    bus.subscribe(lambda envelope: events.append(envelope))

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
        event_bus=bus,
    )
    result = await runner.run(case)
    assert result.error is None

    started = next(e for e in events if e["kind"] == "case_started")
    plan = started["payload"]["script_plan"]
    # 三类锚点事件进入时间表，且按时刻升序
    assert [item["kind"] for item in plan] == [
        "fake_person_speak",
        "car_set_state",
        "state_check",
    ]
    assert [item["at"] for item in plan] == sorted(item["at"] for item in plan)
    # 假人说话：target + 台词
    assert plan[0]["target"] == "user"
    assert plan[0]["label"] == "user：开下空调"
    assert plan[0]["at"] == t0.isoformat()
    # 剧本改车态：car 泳道 + 字段文本
    assert plan[1]["target"] == "car"
    assert "剧本改车态" in plan[1]["label"] and "车速=60 km/h" in plan[1]["label"]
    # 状态检查：car 泳道 + 预期字段文本
    assert plan[2]["target"] == "car"
    assert "状态检查" in plan[2]["label"] and "空调开启状态及模式=制冷中" in plan[2]["label"]


@pytest.mark.anyio
async def test_car_set_state_source_script_vs_assistant() -> None:
    """车态变更来源标注：剧本 set_state → source=script；助手车控 → source=assistant。

    前端按来源三色区分（金色=剧本/红色=助手/蓝色=假人预留），
    数据链：VirtualCar.on_field_change 钩子 / _execute_virtual_car_perform
    → TraceRecorder.record_set_state(source=...) → car_set_state 事件 + trace 落盘。
    """
    t0 = datetime.now().replace(microsecond=0)
    case = TestCase(
        id="test-car-source",
        case_name="车态变更来源测试",
        case_description="剧本改车态与助手车控的 car_set_state 事件应标注来源",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            # 假人说"开空调" → MockAssistant 调 virtual_car.set_field（助手路径）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="开空调"),
                ),
            ),
            # 剧本直接 set_state（上帝视角路径）
            VirtualCarPerformScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=10),
                target="car",
                action=VirtualCarSetStatePerformAction(
                    args=VirtualCarSetStateArgs(fields={"车速": "40 km/h"}),
                ),
            ),
        ],
    )

    bus = EventBus()
    events: list[dict] = []
    bus.subscribe(lambda envelope: events.append(envelope))

    assistant = MockAssistant()
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=False, fast_mode=True),
        event_bus=bus,
    )
    result = await runner.run(case)
    assert result.error is None

    car_events = [e for e in events if e["kind"] == "car_set_state"]
    by_source = {e["payload"]["source"]: e for e in car_events}
    # 助手路径：MockAssistant 开空调写"空调开启状态及模式"
    assert "assistant" in by_source
    assert by_source["assistant"]["payload"]["updated_fields"] == {
        "空调开启状态及模式": "制冷中"
    }
    # 剧本路径：set_state 写车速（多字段一条）
    assert "script" in by_source
    assert by_source["script"]["payload"]["updated_fields"] == {"车速": "40 km/h"}
    # 无未知来源（旧调用方）事件
    assert all(e["payload"]["source"] is not None for e in car_events)

    # trace 落盘同样携带来源（回放导出链路）
    set_state_records = [
        payload
        for _, kind, payload in runner.trace.records
        if kind == RecordKind.VIRTUAL_CAR_SET_STATE
    ]
    assert {r["source"] for r in set_state_records} == {"assistant", "script"}


def _build_single_turn_case(case_id: str, user_text: str) -> TestCase:
    """构造单轮对话 case（停顿检测类测试共用）。"""
    return TestCase(
        id=case_id,
        case_name=case_id,
        case_description="停顿检测测试",
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content=user_text),
                ),
            ),
        ],
        text_script=f"用户：{user_text}",
    )


@pytest.mark.anyio
async def test_tool_boundary_gaps_not_long_pause() -> None:
    """工具前后间隙（LLM 思考）不算流式停顿。

    真实 agent 的工具调用节奏：文本 →(思考 2.5s)→ TOOL_CALL →(执行 0.1s)→
    TOOL_RESULT →(思考 2.5s)→ 文本。修复前 TEXT→TOOL_CALL 和
    TOOL_RESULT→TEXT 的间隙会被误报为 long_pause（插话响应常含工具调用，
    误报的红色停顿标记看起来像"被插话失败"）。
    """
    case = _build_single_turn_case("test-tool-boundary-gap", "帮我定个提醒")

    bus = EventBus()
    events: list[dict] = []
    bus.subscribe(lambda envelope: events.append(envelope))

    assistant = ToolGapMockAssistant(
        tool_delay=0.1, pre_tool_delay=2.5, post_tool_delay=2.5,
    )
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=True, fast_mode=True),
        event_bus=bus,
    )

    result = await runner.run(case)

    assert result.error is None
    kinds = [e["kind"] for e in events]
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert "long_pause" not in kinds, "工具边界间隙（LLM 思考）被误报为流式停顿"


@pytest.mark.anyio
async def test_text_stream_stall_still_records_long_pause() -> None:
    """文本流内的真实停顿仍会被记录（回归保护）。

    相邻 TEXT_DELTA 间隔 > 2s 且无工具事件参与 → long_pause 必须记录。
    确保工具边界排除逻辑没有把停顿检测本身削弱掉。
    """
    case = _build_single_turn_case("test-text-stall", "帮我定个提醒")

    bus = EventBus()
    events: list[dict] = []
    bus.subscribe(lambda envelope: events.append(envelope))

    assistant = TextStallMockAssistant(stall_delay=2.5)
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(use_streaming=True, fast_mode=True),
        event_bus=bus,
    )

    result = await runner.run(case)

    assert result.error is None
    kinds = [e["kind"] for e in events]
    assert "long_pause" in kinds, "文本流内真实停顿未被记录"


@pytest.mark.anyio
async def test_empty_case() -> None:
    """空 case（无 script_events）。"""
    case = TestCase(
        id="test-empty",
        case_name="空测试",
        case_description="无事件",
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[],
    )

    assistant = MockAssistant()
    runner = CaseRunner(assistant=assistant, config=RunnerConfig(fast_mode=True))

    result = await runner.run(case)

    assert result.error is None
    assert result.trace_summary["total_utterances"] == 0
    assert result.state_check_passed is True  # 没有 state_check 视为通过


# ---------------- 时间加速 + 主动智能 + 打断 测试 ----------------


class ProactiveMockAssistant(MockAssistant):
    """能产生主动智能话语的 mock 助手。

    aupdate_context 收到 current_time 后，若 current_time 在某个预设窗口内，
    返回主动话语（模拟定时任务到期触发）。
    """

    def __init__(self) -> None:
        super().__init__()
        # 记录所有 aupdate_context 调用
        self.context_updates: list[tuple[dict, Optional[datetime]]] = []
        # 预设：current_time 在 [trigger_start, trigger_end) 内时返回这句话
        self.proactive_triggers: list[tuple[datetime, datetime, str]] = []
        # 命中触发时的生成延迟（秒），模拟真实 LLM 生成主动话语的耗时
        self.proactive_delay: float = 0.0

    def add_proactive_trigger(
        self,
        trigger_start: datetime,
        trigger_end: datetime,
        message: str,
    ) -> None:
        self.proactive_triggers.append((trigger_start, trigger_end, message))

    async def aupdate_context(
        self,
        car_info: dict[str, Any],
        current_time: Optional[datetime] = None,
    ) -> ContextUpdateResult:
        self.context_updates.append((dict(car_info), current_time))
        if current_time is not None:
            for i, (start, end, msg) in enumerate(self.proactive_triggers):
                if start <= current_time < end:
                    # 每个 trigger 只触发一次，防止快进后常规 aupdate 重复触发
                    self.proactive_triggers[i] = (start, start, msg)  # 使区间为空
                    if self.proactive_delay > 0:
                        await asyncio.sleep(self.proactive_delay)
                    return ContextUpdateResult(proactive_text=msg)
        return ContextUpdateResult()


class SlowMockAssistant(MockAssistant):
    """慢回复的 mock 助手：流式回复分多个 chunk，每个间隔 reply_delay/num_chunks 秒。

    不支持插话打断：收到输入流后聚合完整文本再生成回复，
    旧流继续说完整——用于测试中立观察者模型的并发流记录：
    插话与助手回复时间重叠如实记录；流式投喂下两条助手流并行。
    """

    def __init__(self, reply_delay: float = 5.0, num_chunks: int = 5) -> None:
        super().__init__()
        self.reply_delay = reply_delay
        self.num_chunks = num_chunks

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        """流式回复：聚合输入后分 num_chunks 个 chunk，总耗时 reply_delay 秒。"""
        # 聚合输入流——不支持打断，照旧说完（首/末 chunk 时刻由 _collect_input 记录）
        await self._collect_input(chunks)

        reply_text = "这是一段很长很长的回复，" * self.num_chunks
        chunk_delay = self.reply_delay / self.num_chunks
        reply = StreamingReply()

        async def _produce() -> None:
            try:
                # 把回复分成 num_chunks 段，每段间隔 chunk_delay 秒
                chunks_out = [reply_text[i:i + 10] for i in range(0, len(reply_text), 10)][: self.num_chunks]
                for chunk in chunks_out:
                    await asyncio.sleep(chunk_delay)
                    if reply.is_interrupted:
                        break
                    await reply.put_chunk(chunk)
            except Exception:
                pass
            finally:
                await reply.finish()

        asyncio.create_task(_produce())
        return reply


class ToolGapMockAssistant(MockAssistant):
    """围绕工具调用的间隙模拟 mock 助手。

    事件序列（各段延迟可配）：
        TEXT_DELTA →(pre_tool_delay)→ TOOL_CALL →(tool_delay)→ TOOL_RESULT
        →(post_tool_delay)→ TEXT_DELTA

    用于验证：工具边界间隙（LLM 决定调工具的思考、工具执行、LLM 看到
    结果后恢复生成）都是 agent 正常节奏，不应被误报为流式停顿（long_pause）。
    """

    def __init__(
        self,
        tool_delay: float = 2.5,
        pre_tool_delay: float = 0.0,
        post_tool_delay: float = 0.0,
    ) -> None:
        super().__init__()
        self.tool_delay = tool_delay
        self.pre_tool_delay = pre_tool_delay
        self.post_tool_delay = post_tool_delay

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        await self._collect_input(chunks)
        reply = StreamingReply()

        async def _produce() -> None:
            try:
                await reply.put_chunk("好的，")
                if self.pre_tool_delay > 0:
                    await asyncio.sleep(self.pre_tool_delay)
                await reply.put_event(AssistantEvent(
                    type=AssistantEventType.TOOL_CALL,
                    wall_time=datetime.now(),
                    tool_name="set_reminder",
                    tool_args={"minutes": 35, "text": "拿快递"},
                ))
                await asyncio.sleep(self.tool_delay)
                await reply.put_event(AssistantEvent(
                    type=AssistantEventType.TOOL_RESULT,
                    wall_time=datetime.now(),
                    tool_name="set_reminder",
                    tool_result="已设置提醒",
                    tool_duration_ms=self.tool_delay * 1000,
                ))
                if self.post_tool_delay > 0:
                    await asyncio.sleep(self.post_tool_delay)
                await reply.put_chunk("已帮您设置提醒。")
            finally:
                await reply.finish()

        asyncio.create_task(_produce())
        return reply


class TextStallMockAssistant(MockAssistant):
    """文本流内停顿的 mock 助手：相邻 TEXT_DELTA 之间 sleep stall_delay 秒。

    用于验证：真正的文本流停顿（无工具事件参与）仍会被记录为 long_pause
    ——停顿检测本身没有被工具边界排除逻辑削弱。
    """

    def __init__(self, stall_delay: float = 2.5) -> None:
        super().__init__()
        self.stall_delay = stall_delay

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        await self._collect_input(chunks)
        reply = StreamingReply()

        async def _produce() -> None:
            try:
                await reply.put_chunk("好的，")
                await asyncio.sleep(self.stall_delay)
                await reply.put_chunk("已帮您设置提醒。")
            finally:
                await reply.finish()

        asyncio.create_task(_produce())
        return reply


class BargeInMockAssistant(MockAssistant):
    """支持插话打断的 mock 助手。

    收到输入流第一个 chunk（用户开口）时立即中断自己的旧输出流
    （旧 StreamingReply.interrupt()），等输入流耗尽（用户说完）后
    生成新回复——演示流式输入协议的打断能力测试契约：
    框架如实记录旧流半截话 + 新流完整回复。
    """

    def __init__(self, reply_delay: float = 5.0, num_chunks: int = 5) -> None:
        super().__init__()
        self.reply_delay = reply_delay
        self.num_chunks = num_chunks
        self._active_reply: Optional[StreamingReply] = None

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        # 1. 消费输入流：第一个 chunk → 插话打断，中断旧流；聚合完整文本
        first_wall: Optional[datetime] = None
        last_wall: Optional[datetime] = None
        parts: list[str] = []
        async for c in chunks:
            now = datetime.now()
            if first_wall is None:
                first_wall = now
                # 用户开口 → 中断旧输出流（打断能力契约）
                if self._active_reply is not None:
                    self._active_reply.interrupt()
                    self._active_reply = None
            last_wall = now
            parts.append(c)
        if first_wall is not None:
            self.first_chunk_walls.append(first_wall)
            self.last_chunk_walls.append(last_wall)

        # 2. 等用户说完后生成完整回复文本
        reply_text = "这是一段很长很长的回复，" * self.num_chunks

        # 3. 后台分 chunk 吐出（中途可被下一次插话打断）
        reply = StreamingReply()

        async def _produce() -> None:
            try:
                pieces = [reply_text[i:i + 10] for i in range(0, len(reply_text), 10)][: self.num_chunks]
                delay = self.reply_delay / max(len(pieces), 1)
                for piece in pieces:
                    await asyncio.sleep(delay)
                    if reply.is_interrupted:
                        break
                    await reply.put_chunk(piece)
            finally:
                await reply.finish()

        asyncio.create_task(_produce())
        self._active_reply = reply
        return reply


@pytest.mark.anyio
async def test_time_acceleration_triggers_aupdate_context() -> None:
    """时间加速：锚点距 t0 > 阈值时快进，快进前调 aupdate_context(current_time=target)。

    注意：t0 用 datetime.now() 让虚拟时间对齐真实时间，
    否则 scheduler 用 datetime.now() 对比 anchor_time 计算等待秒数会出错。
    """
    t0 = datetime.now().replace(microsecond=0)
    case = TestCase(
        id="test-accel",
        case_name="时间加速测试",
        case_description="验证快进时 aupdate_context 收到 current_time",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            # T0：假人说话
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="记着周五提醒我"),
                ),
            ),
            # T+2分钟：假人再次说话（触发快进，>60s 阈值）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(minutes=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="今天是不是该提醒我了？"),
                ),
            ),
        ],
        text_script="用户：记着周五提醒我 → 2分钟后 → 今天是不是该提醒我了？",
    )

    assistant = ProactiveMockAssistant()
    # 不开 fast_mode（fast_mode 下不触发快进）
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=False,
            fast_mode=False,
            enable_acceleration=True,
            # 降低阈值让测试不用真等 60s
            acceleration_threshold=timedelta(seconds=1),
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    # 验证 aupdate_context 收到了快进时的 current_time（t0+2分钟）
    # 快进通知至少 1 次（可能还有快进后假人说话触发的常规更新，current_time 相近）
    target_time = t0 + timedelta(minutes=2)
    accel_updates = [
        u for u in assistant.context_updates
        if u[1] is not None and abs((u[1] - target_time).total_seconds()) < 5
    ]
    assert len(accel_updates) >= 1, (
        f"应有至少一次快进通知（target={target_time}），实际: {assistant.context_updates}"
    )
    # 第一次 aupdate_context 的 current_time 应为 None（第一轮假人说话后，未快进）
    assert assistant.context_updates[0][1] is None or assistant.context_updates[0][1] == t0, (
        f"第一次更新 current_time 应为 None 或 t0（未快进），实际: {assistant.context_updates[0]}"
    )


@pytest.mark.anyio
async def test_proactive_intelligence_via_aupdate_context() -> None:
    """主动智能：快进时 aupdate_context 返回主动话语，记入 trace。"""
    t0 = datetime.now().replace(microsecond=0)
    target_time = t0 + timedelta(minutes=2)

    case = TestCase(
        id="test-proactive",
        case_name="主动智能测试",
        case_description="快进到目标时间时助手应主动提醒",
        t0=t0,
        must_pass_assertions=["助手应主动提醒事项"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="记着两分钟后提醒我放周杰伦的歌"),
                ),
            ),
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(minutes=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="现在该放歌了吧？"),
                ),
            ),
        ],
        text_script="用户：放歌 → 2分钟后 → 现在该放歌了吧？",
    )

    assistant = ProactiveMockAssistant()
    # 设置主动智能触发：快进到目标时间时返回提醒话语
    assistant.add_proactive_trigger(
        trigger_start=target_time,
        trigger_end=target_time + timedelta(seconds=1),
        message="您之前让我两分钟后放周杰伦的歌，现在到时间了，已为您播放。",
    )

    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=False,
            fast_mode=False,
            enable_acceleration=True,
            acceleration_threshold=timedelta(seconds=1),
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    # trace 应包含：假人说话1 + 助手回复1 + 主动提醒 + 假人说话2 + 助手回复2 = 5
    summary = result.trace_summary
    assert summary["total_utterances"] == 5, f"期望 5 条 utterance，实际 {summary['total_utterances']}"
    # 验证主动话语在 trace 中
    dialogue = summary["dialogue_text"]
    assert "放周杰伦的歌" in dialogue, f"主动提醒话语应记入 trace: {dialogue}"


@pytest.mark.anyio
async def test_proactive_utterance_timestamp_includes_ttft() -> None:
    """主动话语时间戳 = 任务触发时刻 + 开口延迟（ttft），不是触发瞬间。

    回归（2026-08-26）：修复前 started_at 直接用 trigger 时刻，与渲染标注
    "触发后 Xs 开口"自相矛盾（时间戳说此刻开口、标注说 X 秒后才开口）。
    """
    t0 = datetime.now().replace(microsecond=0)
    target_time = t0 + timedelta(minutes=2)

    case = TestCase(
        id="test-proactive-ttft",
        case_name="主动话语时间戳含开口延迟",
        case_description="快进触发定时任务，主动话语开口应晚于任务到期时刻",
        t0=t0,
        must_pass_assertions=["助手应主动提醒"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="两分钟后提醒我喝水"),
                ),
            ),
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(minutes=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="有什么事吗？"),
                ),
            ),
        ],
    )

    assistant = ProactiveMockAssistant()
    assistant.proactive_delay = 0.15  # 模拟真实 LLM 生成主动话语耗时
    assistant.add_proactive_trigger(
        trigger_start=target_time,
        trigger_end=target_time + timedelta(seconds=1),
        message="您之前让我两分钟后提醒喝水，现在到时间了。",
    )

    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=False,
            fast_mode=False,
            enable_acceleration=True,
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    proactive = [u for u in runner.trace.get_utterances() if u.is_proactive]
    assert len(proactive) == 1
    u = proactive[0]
    assert u.ttft is not None and u.ttft > 0, "开口延迟应被测量并记入 ttft"
    assert u.started_at > target_time, (
        f"开口时刻应晚于任务到期时刻 {target_time}（trigger + ttft），实际 {u.started_at}"
    )
    assert u.started_at - target_time < timedelta(seconds=2), (
        f"开口延迟应在合理范围（proactive_delay=0.15s），实际 {u.started_at - target_time}"
    )


# ---------------- WorldTick 锚点（定时任务两级触发保障）测试 ----------------


class ScheduledTaskMockAssistant(MockAssistant):
    """带定时任务 + WorldTick 注入语义的 mock 助手。

    复刻 demos/v2_agent_to_test/tools/scheduled_tasks 的行为契约：
    - achat 收到含"提醒"的语句时注册定时任务（trigger = 虚拟当前时刻 + delay），
      同时记录待注入的 WorldTick 锚点（trigger - 5s）
    - aupdate_context(current_time)：一次性消费待注入锚点（wt_abs > current_time
      才注入，过期不注入）；触发 [old_time, current_time] 内到期的任务并返回主动话语
    - get_pending_scheduled_tasks：返回未触发任务的 (trigger_time, description)
    """

    WORLD_TICK_BUFFER = timedelta(seconds=5)
    PROACTIVE_MSG = "【测试】您设置的提醒时间到了。"

    def __init__(self, task_delay: timedelta = timedelta(minutes=30)) -> None:
        super().__init__()
        self.task_delay = task_delay
        self._get_now: Optional[Callable[[], datetime]] = None
        self._current_time: Optional[datetime] = None
        self._tasks: list[dict[str, Any]] = []
        self._pending_world_ticks: list[tuple[datetime, str]] = []

    def set_time_source(self, get_now: Callable[[], datetime]) -> None:
        self._get_now = get_now

    def _now(self) -> datetime:
        return self._get_now() if self._get_now is not None else datetime.now()

    async def achat(self, user_text: str) -> str:
        if "提醒" in user_text:
            trigger = self._now() + self.task_delay
            self._tasks.append(
                {"trigger_time": trigger, "description": "测试提醒", "triggered": False}
            )
            self._pending_world_ticks.append((trigger - self.WORLD_TICK_BUFFER, "测试提醒"))
            return "好的，已为您设置提醒。"
        return await super().achat(user_text)

    async def aupdate_context(
        self,
        car_info: dict[str, Any],
        current_time: Optional[datetime] = None,
    ) -> ContextUpdateResult:
        injected: list[WorldTickScriptEvent] = []
        if current_time is not None:
            old_time = self._current_time
            self._current_time = current_time
            # 一次性消费待注入锚点：wt_abs > current_time 才注入（过期不注入）
            ticks, self._pending_world_ticks = self._pending_world_ticks, []
            for wt_abs, _desc in ticks:
                if wt_abs > current_time:
                    injected.append(
                        WorldTickScriptEvent(
                            event_t0_plus_timedelta=wt_abs - current_time,
                        )
                    )
            # 触发 [old_time, current_time] 内到期的任务
            if old_time is not None:
                due = [
                    t for t in self._tasks
                    if not t["triggered"] and old_time <= t["trigger_time"] <= current_time
                ]
                for t in due:
                    t["triggered"] = True
                if due:
                    return ContextUpdateResult(
                        proactive_text=self.PROACTIVE_MSG,
                        injected_events=injected,
                    )
        return ContextUpdateResult(injected_events=injected)

    def get_pending_scheduled_tasks(self) -> list[tuple[datetime, str]]:
        return [
            (t["trigger_time"], t["description"]) for t in self._tasks if not t["triggered"]
        ]


def _get_world_tick_records(runner: CaseRunner) -> list[tuple[datetime, Any]]:
    """从 trace 提取所有 world_tick 系统事件记录 (at, payload)。"""
    return [
        (at, payload)
        for at, kind, payload in runner.trace.records
        if kind == RecordKind.SYSTEM and payload.get("kind") == "world_tick"
    ]


@pytest.mark.anyio
async def test_late_world_tick_silently_skipped() -> None:
    """迟到锚点静默跳过：任务已被多步快进的中间停靠触发，锚点不再记录。

    场景（复刻 scheduled demo 的时序）：
    - T0 假人设置 30 分钟提醒 → 流任务收尾 aupdate_context 注入锚点（trigger-5s）
    - T0+2h 追问事件先被调度器弹出（远期锚点跳过真实等待），其 _maybe_accelerate
      的中间停靠已把任务在 trigger 时刻触发
    - 回调结束后迟到锚点才弹出 → 附近无待触发任务 → 静默跳过，不记录
      "锚点到达"，避免系统事件噪音排在任务触发之后
    """
    t0 = datetime.now().replace(microsecond=0)
    case = TestCase(
        id="test-late-worldtick",
        case_name="迟到锚点静默跳过",
        case_description="任务由中间停靠触发后，迟到锚点不产生系统事件噪音",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="提醒我30分钟后喝水"),
                ),
            ),
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(hours=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    # 注意：追问文本不能含"提醒"（mock 的任务注册关键词），
                    # 否则会意外注册第二个任务、其锚点正常触发干扰断言
                    args=FakePersonSpeakArgs(content="现在几点了？"),
                ),
            ),
        ],
    )

    assistant = ScheduledTaskMockAssistant(task_delay=timedelta(minutes=30))
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=False,
            fast_mode=False,
            enable_acceleration=True,
            # 阈值需大于 WorldTick 的 5s 缓冲，锚点才"够得着"它锚定的任务
            acceleration_threshold=timedelta(seconds=10),
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    # 任务确实被触发了（中间停靠先到，主动提醒在 trace 中且只触发一次）
    dialogue = result.trace_summary["dialogue_text"]
    assert ScheduledTaskMockAssistant.PROACTIVE_MSG in dialogue
    assert dialogue.count(ScheduledTaskMockAssistant.PROACTIVE_MSG) == 1
    # 迟到锚点被静默跳过：无 world_tick 系统事件记录
    world_ticks = _get_world_tick_records(runner)
    assert world_ticks == [], (
        f"迟到锚点不应记录'锚点到达'（任务已由中间停靠触发），实际: {world_ticks}"
    )


@pytest.mark.anyio
async def test_world_tick_anchor_fires_pending_task() -> None:
    """准点锚点正常工作：锚点先于任何跨越它的快进弹出，记录到达并触发任务。

    场景：T0+10m 的追问在任务触发时刻（T0+30m）之前 → 锚点（T0+29m55s）成为
    唯一把时间推进到触发时刻的事件 → 记录"锚点到达"，随后触发主动提醒，
    trace 上锚点记录排在主动话语之前。
    """
    t0 = datetime.now().replace(microsecond=0)
    case = TestCase(
        id="test-worldtick-fire",
        case_name="准点锚点触发任务",
        case_description="锚点到达记录在任务触发话语之前",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="提醒我30分钟后喝水"),
                ),
            ),
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(minutes=10),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="现在几点了？"),
                ),
            ),
        ],
    )

    assistant = ScheduledTaskMockAssistant(task_delay=timedelta(minutes=30))
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=False,
            fast_mode=False,
            enable_acceleration=True,
            acceleration_threshold=timedelta(seconds=10),
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    # 主动提醒被触发，且只触发一次
    dialogue = result.trace_summary["dialogue_text"]
    assert ScheduledTaskMockAssistant.PROACTIVE_MSG in dialogue
    assert dialogue.count(ScheduledTaskMockAssistant.PROACTIVE_MSG) == 1
    # 锚点到达被记录，且时刻不晚于主动话语开口时刻
    world_ticks = _get_world_tick_records(runner)
    assert len(world_ticks) == 1, f"应恰好记录一次锚点到达，实际: {world_ticks}"
    proactive = [u for u in runner.trace.get_utterances() if u.is_proactive]
    assert len(proactive) == 1
    assert world_ticks[0][0] <= proactive[0].started_at, "锚点到达应排在主动话语之前"


@pytest.mark.anyio
async def test_interjection_overlaps_without_interruption() -> None:
    """中立观察者：助手回复慢，假人插话与回复时间重叠，但框架不打断助手。

    t0 用 datetime.now() 让虚拟时间对齐真实时间，scheduler 才能正确等待 2s。

    预期行为：
    - 假人 T0 说"给我讲个长故事"，助手流式回复耗时 5s
    - 假人 T0+2s 插话"算了别讲了"——不等助手说完，如实开口（与回复重叠）
    - 框架不打断助手 → 第一句回复完整说完（无半截话）
    - 流式投喂（第一个字即投，不等说完、不等助手空闲）→ 助手收到插话
      第一个 chunk 的时刻早于假人说完；助手（不支持打断）两条流并行，
      两条助手话语区间重叠（如实记录并发流）
    """
    t0 = datetime.now().replace(microsecond=0)

    case = TestCase(
        id="test-interrupt",
        case_name="中立观察者插话重叠测试",
        case_description="助手正在回复时假人插话，框架不打断，如实记录双方重叠",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            # T0：假人说话，触发助手慢回复（耗时 5s）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="给我讲个长故事"),
                ),
            ),
            # T+2s：假人插话"算了别讲了"（落在助手回复窗口内）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="算了别讲了"),
                ),
            ),
        ],
        text_script="用户：讲个故事 → 2秒后插话 → 算了别讲了",
    )

    assistant = SlowMockAssistant(reply_delay=5.0)  # 5 秒才回完，插话落在回复窗口内
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=True,
            fast_mode=False,
            enable_acceleration=False,  # 2s < 阈值，不会快进
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    summary = result.trace_summary
    # 中立观察者：框架不打断助手 → 不应有半截话
    assert not summary["has_partial_utterance"], (
        f"中立模式下不应有框架打断导致的半截话，summary: {summary}"
    )
    # 插话与助手回复在时间上重叠 → 如实检测到双方同时说话
    assert summary["has_overlapping_speech"], (
        f"应检测到双方同时说话，summary: {summary}"
    )
    assert summary["overlap_count"] >= 1
    # 总 utterance: 假人说话1 + 助手完整回复1 + 假人插话 + 助手回复2 = 4
    assert summary["total_utterances"] == 4, f"期望 4 条，实际 {summary['total_utterances']}"

    # 助手第一句回复完整记录（未被截断）
    utterances = runner.trace.get_utterances()
    fp1, asst1, fp2, asst2 = utterances
    full_reply = "这是一段很长很长的回复，" * 5
    expected_content = full_reply[:50]  # 5 个 chunk × 10 字
    assert asst1.role == "assistant" and not asst1.is_partial
    assert asst1.content == expected_content, (
        f"助手第一句回复应完整记录，实际: {asst1.content!r}"
    )
    # 插话语句完整记录且确实与助手回复重叠
    assert fp2.content == "算了别讲了"
    assert fp2.started_at < asst1.ended_at and fp2.ended_at > asst1.started_at, (
        f"插话 [{fp2.started_at} → {fp2.ended_at}] 应与助手回复 "
        f"[{asst1.started_at} → {asst1.ended_at}] 时间重叠"
    )
    # 第一个字即投（不等说完、不等助手空闲）→ 第二条回复开口早于第一条说完：并发流重叠
    assert asst2.role == "assistant" and asst2.content == expected_content
    assert asst2.started_at < asst1.ended_at, (
        f"流式投喂下两条助手流应并行：回复2 [{asst2.started_at} → {asst2.ended_at}] "
        f"开口应早于回复1说完 {asst1.ended_at}（实际为排队串行）"
    )
    # 流式投喂（第一个字即投）的结构性证明：助手收到的插话输入逐字到达。
    # 首/末 chunk 相隔 ≈ 假人说话时长（5 字 × 0.05s/字 = 0.25s）；
    # 若是说完才投（旧模型），所有 chunk 一次性到达，相隔 ≈ 0。
    # 结构性断言不受事件循环调度精度影响。
    assert len(assistant.first_chunk_walls) == 2, (
        f"应有两路投喂输入流，实际 {len(assistant.first_chunk_walls)}"
    )
    spread_s = (assistant.last_chunk_walls[1] - assistant.first_chunk_walls[1]).total_seconds()
    assert spread_s >= 0.1, (
        f"插话输入应逐字流式到达（首末 chunk 相隔 {spread_s:.3f}s），"
        f"而非说完后一次性投喂"
    )


@pytest.mark.anyio
async def test_barge_in_assistant_interrupts_old_stream() -> None:
    """流式投喂 + 插话打断：支持打断的助手在用户开口（第一个 chunk）时中断旧流。

    验证框架能测出打断能力（协议契约）：
    - 旧流被助手自己中断 → 记为半截话（is_partial=True，内容截断）
    - 旧流在插话开口后很快收尾（中断点附近）
    - 新流在假人说完后生成，完整回复
    """
    t0 = datetime.now().replace(microsecond=0)

    case = TestCase(
        id="test-barge-in",
        case_name="插话打断能力测试",
        case_description="支持打断的助手在用户开口时中断旧流，框架如实记录半截话",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            # T0：假人说话，触发助手慢回复（耗时 5s）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="给我讲个长故事"),
                ),
            ),
            # T+2s：假人插话（落在助手回复窗口内）→ 助手插话打断中断旧流
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="算了别讲了"),
                ),
            ),
        ],
        text_script="用户：讲个故事 → 2秒后插话 → 助手中断旧流并回应插话",
    )

    assistant = BargeInMockAssistant(reply_delay=5.0)
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=True,
            fast_mode=False,
            enable_acceleration=False,
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    summary = result.trace_summary
    # 助手自己插话打断中断旧流 → 半截话被如实记录
    assert summary["has_partial_utterance"], (
        f"插话打断应产生半截话记录，summary: {summary}"
    )

    utterances = runner.trace.get_utterances()
    fp1, asst1, fp2, asst2 = utterances
    full_reply = "这是一段很长很长的回复，" * 5
    expected_full = full_reply[:50]  # 5 个 chunk × 10 字

    # 旧流：半截话（内容被截断，少于完整回复）
    assert asst1.role == "assistant" and asst1.is_partial
    assert len(asst1.content) < len(expected_full), (
        f"旧流应被插话打断截断，实际内容 {asst1.content!r}"
    )
    # 旧流在插话开口后很快收尾（一个 chunk 周期 ≈ 1s 内，留 2s 余量）
    assert asst1.ended_at - fp2.started_at < timedelta(seconds=2), (
        f"旧流应在插话开口 {fp2.started_at} 后很快结束，实际 {asst1.ended_at}"
    )
    # 新流：假人说完后生成，完整回复
    assert asst2.role == "assistant" and not asst2.is_partial
    assert asst2.content == expected_full
    assert asst2.started_at >= fp2.ended_at, "新流应在假人说完后开口"


@pytest.mark.anyio
async def test_overlapping_speech_rendering() -> None:
    """重叠渲染：Judge 视图以"双方同时说话"切片块呈现重叠窗口内双方文字。

    - 重叠块标记双方在重叠窗口内各自说出的内容（切片式）
    - 假人插话短、完整落在重叠窗口内 → 切片内容 = 完整插话
    - 助手切片 = 完整回复的子串（窗口内说出的那部分）
    """
    t0 = datetime.now().replace(microsecond=0)

    case = TestCase(
        id="test-overlap-render",
        case_name="重叠说话渲染测试",
        case_description="插话与回复重叠，Judge 视图渲染双方同时说话切片块",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="给我讲个长故事"),
                ),
            ),
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=2),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="算了别讲了"),
                ),
            ),
        ],
        text_script="用户：讲个故事 → 2秒后插话 → 算了别讲了",
    )

    assistant = SlowMockAssistant(reply_delay=5.0)
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=True,
            fast_mode=False,
            enable_acceleration=False,
        ),
    )

    result = await runner.run(case)
    assert result.error is None

    rendered = render_timeline_text(runner.trace)

    # 重叠块存在，块内双方各一行"（同时段说到）"
    assert "双方同时说话" in rendered, f"渲染应含重叠块标记:\n{rendered}"
    assert rendered.count("（同时段说到）") >= 2, f"块内应列出双方各自切片:\n{rendered}"

    # 提取块内的助手/假人行，验证切片内容
    block_lines = [
        line for line in rendered.splitlines() if "（同时段说到）" in line
    ]
    fp_line = next(line for line in block_lines if "假人(" in line)
    asst_line = next(line for line in block_lines if line.strip().startswith("助手"))
    # 假人插话完整落在重叠窗口内 → 切片 = 完整插话
    assert "算了别讲了" in fp_line, f"假人切片应含完整插话: {fp_line}"
    # 助手切片是完整回复的子串（非空）
    full_reply = ("这是一段很长很长的回复，" * 5)[:50]
    asst_sliced = asst_line.split("（同时段说到）:", 1)[1].strip()
    assert asst_sliced and asst_sliced in full_reply, (
        f"助手切片应为完整回复的子串，实际: {asst_sliced!r}"
    )


@pytest.mark.anyio
async def test_natural_time_flow_during_reply() -> None:
    """自然时间流逝：助手回复期间虚拟时间不冻结，话语时间戳如实反映耗时。

    - 假人 T0 说话，助手流式回复耗时 2s
    - 无快进（10s 间隔 < 阈值），第二句假人台词在 T0+10s 触发
    - 断言：助手话语区间覆盖真实耗时（开口晚于假人说完、说完距 T0 ≥ 1.5s），
      第二句假人台词时刻 ≈ T0+10s —— 时间戳来自自然流逝的虚拟时间
    """
    t0 = datetime.now().replace(microsecond=0)

    case = TestCase(
        id="test-natural-flow",
        case_name="自然时间流逝测试",
        case_description="助手回复期间时间自然流逝，trace 时间戳如实反映",
        t0=t0,
        must_pass_assertions=["测试"],
        fake_persons=[FakePersonInfo(role_id="user", profile="测试用户")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="给我讲个长故事"),
                ),
            ),
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=10),
                target="user",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="好了别讲了"),
                ),
            ),
        ],
        text_script="用户：讲个故事 → 10秒后 → 好了别讲了",
    )

    assistant = SlowMockAssistant(reply_delay=2.0)  # 回复耗时 2s
    runner = CaseRunner(
        assistant=assistant,
        config=RunnerConfig(
            use_streaming=True,
            fast_mode=False,
            enable_acceleration=False,  # 不快进，时间自然流逝
        ),
    )

    result = await runner.run(case)

    assert result.error is None
    utterances = runner.trace.get_utterances()
    # 假人说1 + 助手回1 + 假人说2 + 助手回2 = 4 条
    assert len(utterances) == 4, f"期望 4 条话语，实际 {len(utterances)}"

    fp1, asst1, fp2, asst2 = utterances

    # 1) 因果有序：助手开口晚于假人说完（无时间倒置）
    assert asst1.started_at >= fp1.ended_at, (
        f"助手开口({asst1.started_at}) 应晚于假人说完({fp1.ended_at})"
    )

    # 2) 时间自然流逝：助手回复耗时 2s，说完时刻距 t0 ≥ 1.5s（非冻结在 T0）
    elapsed = (asst1.ended_at - t0).total_seconds()
    assert elapsed >= 1.5, (
        f"助手回复期间时间应自然流逝（期望 ≥1.5s，实际 {elapsed:.2f}s）"
    )

    # 3) 第二句假人台词在锚点 T0+10s 附近触发（pin 容差内对齐）
    fp2_offset = (fp2.ended_at - t0).total_seconds()
    assert 8.0 <= fp2_offset <= 12.5, (
        f"第二句假人台词应约在 T0+10s（实际 T0+{fp2_offset:.2f}s）"
    )

    # 4) 两条假人台词之间隔 ≈ 10s：虚拟时间与真实时间 1:1
    gap = (fp2.started_at - fp1.started_at).total_seconds()
    assert 8.0 <= gap <= 12.5, f"假人两句话间隔应 ≈10s（实际 {gap:.2f}s）"
