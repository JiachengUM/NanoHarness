"""EventBus + TraceRecorder 层1事件挂钩测试。

设计原则（§0.4）：新功能必须附上可运行测试。
全部纯 Python，无 LLM 依赖。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    StateCheckRecord,
    TraceRecorder,
)
from projects.experiments.time_travel_auto_test.visualizer.event_bus import (
    EventBus,
    to_jsonable,
)


def _collect(bus: EventBus) -> list[dict]:
    events: list[dict] = []
    bus.subscribe(events.append)
    return events


# ---------------- EventBus 信封 ----------------


def test_envelope_structure_and_seq_increment() -> None:
    bus = EventBus()
    events = _collect(bus)
    t = datetime(2026, 8, 26, 14, 30, 0)

    bus.emit("utterance", {"content": "你好"}, t)
    bus.emit("system", {"kind": "world_tick"}, t + timedelta(seconds=1))

    assert len(events) == 2
    e1, e2 = events
    # 双时间戳信封
    assert e1["seq"] == 1
    assert e1["mock_time"] == t.isoformat()
    assert e1["kind"] == "utterance"
    assert e1["payload"] == {"content": "你好"}
    assert "T" in e1["wall_time"]  # ISO 格式墙钟
    assert e2["seq"] == 2
    assert e2["mock_time"] == (t + timedelta(seconds=1)).isoformat()


def test_emit_without_subscriber_is_noop() -> None:
    """旁路总线：无订阅者时静默丢弃，返回 -1。"""
    bus = EventBus()
    assert bus.has_subscriber is False
    seq = bus.emit("utterance", {}, datetime.now())
    assert seq == -1
    assert bus.has_subscriber is False


def test_mock_time_none_allowed() -> None:
    bus = EventBus()
    events = _collect(bus)
    bus.emit("case_started", {"case_id": "x"}, None)
    assert events[0]["mock_time"] is None


# ---------------- to_jsonable ----------------


def test_to_jsonable_handles_nested_and_exotic() -> None:
    t = datetime(2026, 8, 26, 14, 0, 0)
    value = {
        "time": t,
        "items": [1, "a", {"inner": (t,)}],
        "exotic": object,  # 类型对象 → str 兜底
    }
    out = to_jsonable(value)
    assert out["time"] == t.isoformat()
    assert out["items"][2]["inner"][0] == t.isoformat()
    assert isinstance(out["exotic"], str)


# ---------------- TraceRecorder 层1挂钩 ----------------


def test_recorder_without_bus_unchanged() -> None:
    """不注入 bus 时行为与旧版完全一致（向后兼容）。"""
    rec = TraceRecorder()
    t0 = datetime(2026, 8, 26, 14, 0, 0)
    rec.record_utterance(
        role="assistant",
        content="好的",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0,
        ended_at=t0 + timedelta(seconds=1),
    )
    assert len(rec.get_utterances()) == 1


def test_recorder_emits_utterance_event_with_full_fields() -> None:
    bus = EventBus()
    events = _collect(bus)
    rec = TraceRecorder(event_bus=bus)
    t0 = datetime(2026, 8, 26, 14, 0, 0)

    rec.record_utterance(
        role="assistant",
        content="已经帮您设置好了",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0,
        ended_at=t0 + timedelta(seconds=9),
        is_partial=True,
        interrupted_by_barge_in=True,
        ttft=10.5,
        segments=[(t0, "已经"), (t0 + timedelta(seconds=1), "帮您")],
    )

    assert len(events) == 1
    ev = events[0]
    assert ev["kind"] == "utterance"
    # 信封 mock_time = 落盘时刻（ended_at），话语区间在 payload 里
    assert ev["mock_time"] == (t0 + timedelta(seconds=9)).isoformat()
    p = ev["payload"]
    assert p["speaker_kind"] == "assistant_reply"
    assert p["role"] == "assistant"
    assert p["content"] == "已经帮您设置好了"
    assert p["is_partial"] is True
    assert p["interrupted_by_barge_in"] is True
    assert p["ttft"] == 10.5
    assert p["is_proactive"] is False
    # segments 序列化为 [[iso, str], ...]
    assert p["segments"][0] == [t0.isoformat(), "已经"]
    assert p["segments"][1] == [(t0 + timedelta(seconds=1)).isoformat(), "帮您"]


def test_recorder_emits_all_layer1_kinds() -> None:
    """8 种层1事件全覆盖：utterance/state_check/car_set_state/acceleration/
    system/tool_call/tool_result/long_pause。"""
    bus = EventBus()
    events = _collect(bus)
    rec = TraceRecorder(event_bus=bus)
    t0 = datetime(2026, 8, 26, 14, 0, 0)

    rec.record_state_check(
        t0,
        StateCheckRecord(
            expected_fields={"空调": "制冷中"},
            actual_fields={"空调": "制冷中"},
            passed=True,
        ),
    )
    rec.record_set_state(t0, {"空调温度": 26})
    rec.record_acceleration(t0, t0 + timedelta(minutes=35))
    rec.record_system_event(t0, "world_tick", "锚点到达")
    rec.record_tool_call(t0, "set_reminder", {"minutes": 35, "desc": "拿快递"})
    rec.record_tool_result(t0, "set_reminder", {"ok": True}, 123.4)
    rec.record_long_pause(t0, 8.2)

    kinds = [e["kind"] for e in events]
    assert kinds == [
        "state_check",
        "car_set_state",
        "acceleration",
        "system",
        "tool_call",
        "tool_result",
        "long_pause",
    ]
    # 抽查关键 payload
    assert events[0]["payload"]["passed"] is True
    assert events[1]["payload"]["updated_fields"] == {"空调温度": 26}
    assert events[2]["payload"]["to"] == (t0 + timedelta(minutes=35)).isoformat()
    assert events[4]["payload"]["tool_name"] == "set_reminder"
    assert events[5]["payload"]["duration_ms"] == 123.4
    assert events[6]["payload"]["pause_seconds"] == 8.2


def test_events_are_json_serializable() -> None:
    """信封必须能过 json.dumps（WS 推送前提）。"""
    import json

    bus = EventBus()
    events = _collect(bus)
    rec = TraceRecorder(event_bus=bus)
    t0 = datetime(2026, 8, 26, 14, 0, 0)

    rec.record_tool_call(t0, "set_reminder", {"minutes": 35, "desc": "拿快递"})
    rec.record_tool_result(t0, "control_car", ("tuple", "result"), 50.0)
    rec.record_state_check(
        t0,
        StateCheckRecord(expected_fields={"a": 1}, actual_fields={"a": 2}, passed=False),
    )

    text = json.dumps(events, ensure_ascii=False)
    assert '"tool_call"' in text


# ---------------- Runner 层2过程事件 ----------------

import pytest

from projects.experiments.time_travel_auto_test.case_runner.mock_assistant import (
    MockAssistant,
)
from projects.experiments.time_travel_auto_test.case_runner.runner import (
    CaseRunner,
    RunnerConfig,
)
from projects.experiments.time_travel_auto_test.case_schema import (
    load_test_cases_from_json_file,
)
from projects.experiments.time_travel_auto_test.test.test_case_runner_e2e import (
    FIXTURE_CASES_FILE,
)


@pytest.mark.anyio
async def test_runner_emits_lifecycle_events() -> None:
    """case_started / case_finished 生命周期事件（层2）。"""
    bus = EventBus()
    events = _collect(bus)
    case = next(
        c for c in load_test_cases_from_json_file(FIXTURE_CASES_FILE) if c.id == "case-001"
    )

    runner = CaseRunner(
        assistant=MockAssistant(),
        config=RunnerConfig(use_streaming=False, fast_mode=True),
        event_bus=bus,
    )
    result = await runner.run(case)

    kinds = [e["kind"] for e in events]
    assert kinds[0] == "case_started"
    assert kinds[-1] == "case_finished"

    started = events[0]["payload"]
    assert started["case_id"] == "case-001"
    assert started["case_name"]
    assert "t0" in started

    finished = events[-1]["payload"]
    assert finished["case_id"] == "case-001"
    assert finished["error"] is None
    assert finished["state_check_passed"] is True
    assert finished["total_utterances"] == 2
    # 层1事件夹在生命周期事件之间
    assert "utterance" in kinds
    assert "state_check" in kinds


@pytest.mark.anyio
async def test_runner_emits_chunk_delta_streams() -> None:
    """fake_person_delta / assistant_delta chunk 流（打字机数据源）。"""
    bus = EventBus()
    events = _collect(bus)
    case = next(
        c for c in load_test_cases_from_json_file(FIXTURE_CASES_FILE) if c.id == "case-001"
    )

    runner = CaseRunner(
        assistant=MockAssistant(),
        config=RunnerConfig(use_streaming=True, fast_mode=False),
        event_bus=bus,
    )
    result = await runner.run(case)

    assert result.error is None
    fp_deltas = [e for e in events if e["kind"] == "fake_person_delta"]
    asst_deltas = [e for e in events if e["kind"] == "assistant_delta"]
    # case-001 假人说话一次（多 chunk），助手回复一次（mock 一次性 put_chunk，≥1 个 delta）
    assert len(fp_deltas) >= 2
    assert all("target" in e["payload"] and "delta" in e["payload"] for e in fp_deltas)
    assert len(asst_deltas) >= 1
    # chunk 事件须带虚拟时间戳（wall_to_mock 换算）
    assert all(e["mock_time"] is not None for e in fp_deltas + asst_deltas)
    # 拼接 delta 应还原完整台词
    joined = "".join(e["payload"]["delta"] for e in fp_deltas)
    assert "空调" in joined

    # 信封流不变式：seq 递增序下 mock_time 不倒退（快进只会向前跳）。
    # 话语落盘事件若回填 started_at 会违反此不变式（delta 已带更晚时间）。
    mock_times = [e["mock_time"] for e in events if e["mock_time"] is not None]
    assert mock_times == sorted(mock_times), "信封 mock_time 出现倒退"
    # 生命周期事件都带虚拟时间（含 case_finished —— 回放模式定位终点）
    assert events[0]["mock_time"] is not None
    assert events[-1]["mock_time"] is not None


@pytest.mark.anyio
async def test_runner_without_bus_unchanged() -> None:
    """不注入 bus 时 Runner 行为不变（向后兼容）。"""
    case = next(
        c for c in load_test_cases_from_json_file(FIXTURE_CASES_FILE) if c.id == "case-001"
    )
    runner = CaseRunner(
        assistant=MockAssistant(),
        config=RunnerConfig(use_streaming=False, fast_mode=True),
    )
    result = await runner.run(case)
    assert result.error is None
    assert result.trace_summary["total_utterances"] == 2


# ---------------- 回放模式数据链路（2026-08-27） ----------------


@pytest.mark.anyio
async def test_case_started_contains_initial_car_info() -> None:
    """case_started 携带 initial_car_info —— 前端车态时间机的初值。"""
    bus = EventBus()
    events = _collect(bus)
    case = next(
        c for c in load_test_cases_from_json_file(FIXTURE_CASES_FILE) if c.id == "case-001"
    )
    runner = CaseRunner(
        assistant=MockAssistant(),
        config=RunnerConfig(use_streaming=False, fast_mode=True),
        event_bus=bus,
    )
    await runner.run(case)

    started = events[0]["payload"]
    # initial_car_info 是 devices 派生的全量视图：覆盖 case 指定键 + 含分组字段默认值
    for key, value in case.virtual_car.car_info.items():
        assert started["initial_car_info"][key] == value
    assert "多媒体播放状态" in started["initial_car_info"]
    assert "主驾是否有人" in started["initial_car_info"]
    # 分组元数据随事件下发（前端虚拟车状态面板分层展示）
    assert started["car_state_groups"]["媒体"][0] == "多媒体播放状态"
    assert "座椅与方向盘" in started["car_state_groups"]


@pytest.mark.anyio
async def test_assistant_car_control_emits_car_set_state() -> None:
    """助手车控 set_field → car_set_state 事件（带虚拟时间）。

    case-001 的 MockAssistant 在"开空调"分支调 virtual_car.set_field——
    此前该路径对事件流不可见（只有剧本 set_state 有记录），回放模式下
    助手的车控操作会从车态时间机里消失。
    """
    bus = EventBus()
    events = _collect(bus)
    case = next(
        c for c in load_test_cases_from_json_file(FIXTURE_CASES_FILE) if c.id == "case-001"
    )
    runner = CaseRunner(
        assistant=MockAssistant(),
        config=RunnerConfig(use_streaming=False, fast_mode=True),
        event_bus=bus,
    )
    result = await runner.run(case)
    assert result.error is None

    car_events = [e for e in events if e["kind"] == "car_set_state"]
    assert len(car_events) == 1, "助手车控应恰好发一条 car_set_state"
    ev = car_events[0]
    assert ev["payload"]["updated_fields"] == {"空调开启状态及模式": "制冷中"}
    # 事件时间 = 当前虚拟时刻（回放时车态变化时点与助手操作时序一致）
    assert ev["mock_time"] is not None
    t0 = events[0]["payload"]["t0"]
    assert ev["mock_time"] >= t0


@pytest.mark.anyio
async def test_script_set_state_single_multi_field_record() -> None:
    """剧本多字段 set_state 恰好一条事件（钩子抑制，不拆分不双记录）。

    case-004 的 PT2M 剧本 set_state 同时改"车速 + 档位"两个字段——
    保持既有"多字段一条"trace 格式，Judge 测试不受影响。
    """
    bus = EventBus()
    events = _collect(bus)
    case = next(
        c for c in load_test_cases_from_json_file(FIXTURE_CASES_FILE) if c.id == "case-004"
    )
    runner = CaseRunner(
        assistant=MockAssistant(),
        config=RunnerConfig(use_streaming=False, fast_mode=True),
        event_bus=bus,
    )
    result = await runner.run(case)
    assert result.error is None

    car_events = [e for e in events if e["kind"] == "car_set_state"]
    # 剧本 set_state（车速+档位一条）+ 助手开门车控（副驾门状态一条）
    script_event = next(
        e for e in car_events
        if "车辆当前行驶速度" in e["payload"]["updated_fields"]
    )
    # 两个字段合在一条事件里（未被钩子逐字段拆分）
    assert script_event["payload"]["updated_fields"] == {
        "车辆当前行驶速度": "40 km/h",
        "车辆当前档位": "D档（前进档）",
    }
    # 该剧本 set_state 恰好一条（无重复）
    assert sum(
        1 for e in car_events
        if "车辆当前行驶速度" in e["payload"]["updated_fields"]
    ) == 1
