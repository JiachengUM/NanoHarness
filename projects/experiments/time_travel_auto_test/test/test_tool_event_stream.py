"""工具事件流正确性测试（后端）。

验证 2026-09-03 修复的工具调用/结果事件链路：

1. 助手侧 backfill 队列在「事件产生时」捕获 mock_time（虚拟时间，非 wall），
   并携带 task_id 供前端精确配对。
2. Runner 三条 drain 把队列项如实落盘为 TOOL_CALL / TOOL_RESULT：
   - mock_time 原样透传（不再 wall_to_mock 重换算 → 无时间漂移）
   - task_id 透传（前端按 id 精确配对并行同名工具，不误配）
   - duration_ms 透传（真实 call→result 虚拟耗时，不再硬编码 0）
3. 并行同名工具各自独立 task_id，duration_ms 各不误配。

这些测试不依赖真 LLM / TaskManager：直接驱动助手侧 _handle_backfill 与
Runner 侧 drain 纯函数，断言事件流的字段与时间戳正确。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Optional

import pytest

from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    ContextUpdateResult,
    StreamingReply,
    is_assistant,
)
from projects.experiments.time_travel_auto_test.case_runner.runner import CaseRunner
from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    TraceRecorder,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import (
    TestedAssistant,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar


# ---------------- 最小助手（供 Runner drain 映射测试） ----------------


class FakeAssistant:
    """只暴露 drain 队列与协议方法，隔离验证 Runner 侧 drain → trace 映射。"""

    def __init__(self) -> None:
        self._tool_calls: list[tuple[datetime, str, str, dict[str, Any]]] = []
        self._tool_results: list[tuple[datetime, Optional[str], str, Any, float]] = []

    def create(self, session_id: str, system_prompt: str = "") -> None:
        pass

    async def achat(self, user_text: str) -> str:
        return ""

    async def achat_stream(self, chunks) -> StreamingReply:
        reply = StreamingReply()
        await reply.finish()
        return reply

    async def aupdate_context(self, car_info, current_time=None) -> ContextUpdateResult:
        return ContextUpdateResult()

    async def adump_history(self) -> list[dict[str, str]]:
        return []

    def drain_backfill_tool_calls(self) -> list[tuple[datetime, str, str, dict[str, Any]]]:
        out = list(self._tool_calls)
        self._tool_calls.clear()
        return out

    def drain_backfill_tool_results(self) -> list[tuple[datetime, Optional[str], str, Any, float]]:
        out = list(self._tool_results)
        self._tool_results.clear()
        return out


def _run_drain(
    tool_calls: list[tuple[datetime, str, str, dict[str, Any]]],
    tool_results: list[tuple[datetime, Optional[str], str, Any, float]],
) -> tuple[
    list[tuple[datetime, RecordKind, dict]],
    list[tuple[datetime, RecordKind, dict]],
]:
    """驱动 Runner 的 drain 方法，抽取 TOOL_CALL / TOOL_RESULT 落盘记录。"""
    assistant = FakeAssistant()
    assistant._tool_calls = list(tool_calls)
    assistant._tool_results = list(tool_results)
    assert is_assistant(assistant)
    runner = CaseRunner(assistant=assistant)
    runner._trace = TraceRecorder()  # 干净 trace，避免残留
    runner._drain_backfill_tool_calls()
    runner._drain_backfill_tool_results()
    calls = [
        (ts, kind, rec)
        for ts, kind, rec in runner.trace.records
        if kind == RecordKind.TOOL_CALL
    ]
    results = [
        (ts, kind, rec)
        for ts, kind, rec in runner.trace.records
        if kind == RecordKind.TOOL_RESULT
    ]
    return calls, results


# ---------------- Runner drain → trace 映射 ----------------


def test_runner_drains_tool_call_with_mock_time_and_task_id() -> None:
    """TOOL_CALL 落盘：mock_time 原样透传（非 wall_to_mock），task_id 透传。"""
    call_mock = datetime(2025, 1, 1, 12, 0, 0)
    calls, results = _run_drain(
        [(call_mock, "task-1", "poi_search", {"q": "博物馆"})],
        [],
    )
    assert results == []
    assert len(calls) == 1
    ts, _, rec = calls[0]
    assert ts == call_mock  # 快进后也不会因 wall_to_mock 漂移
    assert rec["task_id"] == "task-1"
    assert rec["tool_name"] == "poi_search"
    assert rec["tool_args"] == {"q": "博物馆"}


def test_runner_drains_tool_result_with_real_duration_and_task_id() -> None:
    """TOOL_RESULT 落盘：duration_ms 透传真实耗时（非 0），mock/task_id 透传。"""
    result_mock = datetime(2025, 1, 1, 12, 0, 3)
    calls, results = _run_drain(
        [],
        [(result_mock, "task-1", "poi_search", {"名称": "上海博物馆"}, 3000.0)],
    )
    assert calls == []
    assert len(results) == 1
    ts, _, rec = results[0]
    assert ts == result_mock
    assert rec["task_id"] == "task-1"
    assert rec["duration_ms"] == 3000.0
    assert rec["result"] == {"名称": "上海博物馆"}


def test_parallel_same_name_tools_keep_distinct_task_ids_and_durations() -> None:
    """并行同名工具：call/result 各自独立 task_id + 独立真实耗时，不误配。"""
    c1 = datetime(2025, 1, 1, 12, 0, 0)
    c2 = datetime(2025, 1, 1, 12, 0, 1)
    r1 = datetime(2025, 1, 1, 12, 0, 3)  # t1 耗时 3s
    r2 = datetime(2025, 1, 1, 12, 0, 10)  # t2 耗时 9s
    calls, results = _run_drain(
        [
            (c1, "t1", "poi_search", {"q": "A"}),
            (c2, "t2", "poi_search", {"q": "B"}),
        ],
        [
            (r1, "t1", "poi_search", "A结果", 3000.0),
            (r2, "t2", "poi_search", "B结果", 9000.0),
        ],
    )
    assert len(calls) == 2
    assert len(results) == 2
    by_task = {rec["task_id"]: (ts, rec) for ts, _, rec in results}
    assert set(by_task) == {"t1", "t2"}
    assert by_task["t1"][0] == r1
    assert by_task["t2"][0] == r2
    assert by_task["t1"][1]["duration_ms"] == 3000.0
    assert by_task["t2"][1]["duration_ms"] == 9000.0


# ---------------- 助手侧 _handle_backfill：并行同名不误配 ----------------


@pytest.mark.anyio
async def test_assistant_parallel_same_name_result_distinct_duration() -> None:
    """助手侧回灌结果队列：并行同名工具按 task_id 各带独立真实耗时。"""
    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="parallel")

    t0 = datetime(2025, 1, 1, 12, 0, 0)
    assistant._task_start_mock["t1"] = t0
    assistant._task_start_mock["t2"] = t0 + timedelta(seconds=1)

    assistant._current_time = t0 + timedelta(seconds=3)
    await assistant._handle_backfill(
        SimpleNamespace(task_id="t1", result=SimpleNamespace(tool_name="poi_search", result="A"))
    )
    assistant._current_time = t0 + timedelta(seconds=10)
    await assistant._handle_backfill(
        SimpleNamespace(task_id="t2", result=SimpleNamespace(tool_name="poi_search", result="B"))
    )

    results = assistant.drain_backfill_tool_results()
    assert len(results) == 2
    by_task = {r[1]: r for r in results}
    assert set(by_task) == {"t1", "t2"}
    # r = (mock_time, task_id, tool_name, raw_result, duration_ms)
    assert by_task["t1"][0] == t0 + timedelta(seconds=3)
    assert by_task["t2"][0] == t0 + timedelta(seconds=10)
    assert by_task["t1"][4] == pytest.approx(3000.0)
    assert by_task["t2"][4] == pytest.approx(9000.0)
    # 起始时刻已消费（pop），不残留
    assert "t1" not in assistant._task_start_mock
    assert "t2" not in assistant._task_start_mock


# ---------------- 助手侧 _event_mock_time：消费延迟反推修复 ----------------

def test_event_mock_time_backdates_to_emission_time() -> None:
    """事件携带 timestamp（emit 墙钟）时，_event_mock_time 反推到事件产生时刻。

    回归 2026-09-03 修复：多工具并行时消费循环被回灌 LLM 生成阻塞，
    直接取 `_current_virtual_time()` 会滞后，导致起止时刻几乎重合、
    duration_ms 塌缩为 ~0.5ms 假值。改为按事件自带 timestamp 反推。
    """
    assistant = TestedAssistant(virtual_car=VirtualCar())
    now_mock = datetime(2025, 1, 1, 12, 0, 0)
    assistant._current_time = now_mock  # 无 _get_now，回退用当前快照当作"现在"

    # 事件在 2 秒前产生（消费循环被阻塞 2s 后才拿到该事件）
    event = SimpleNamespace(timestamp=datetime.now() - timedelta(seconds=2))

    got = assistant._event_mock_time(event)
    expected = now_mock - timedelta(seconds=2)
    # 容差 0.5s：datetime.now() 求值与 timestamp 构造之间有微小真实流逝
    assert abs((got - expected).total_seconds()) < 0.5


def test_event_mock_time_falls_back_without_timestamp() -> None:
    """事件无 timestamp（测试桩/SimpleNamespace）时回退当前虚拟时刻。"""
    assistant = TestedAssistant(virtual_car=VirtualCar())
    now_mock = datetime(2025, 1, 1, 12, 0, 0)
    assistant._current_time = now_mock

    event = SimpleNamespace(task_id="x")  # 无 timestamp

    assert assistant._event_mock_time(event) == now_mock