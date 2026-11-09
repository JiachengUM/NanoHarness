"""手搓 JSON 用例 fixtures 的导入 / 导出 / roundtrip 测试。"""

from __future__ import annotations

import json
from pathlib import Path

from projects.experiments.time_travel_auto_test.case_schema import (
    dump_test_cases_to_json,
    load_test_cases_from_json,
    load_test_cases_from_json_file,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarStateCheckScriptEvent,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"
FIXTURE_CASES_FILE = CASES_DIR / "fixture_cases.json"

EXPECTED_CASE_IDS = [
    "case-001",
    "case-002",
    "case-003",
    "case-004",
    "case-005",
    "case-006",
    "case-007",
    "case-008",
    "case-009",
    "case-010",
    "case-011",
    "case-012",
]


def _speak_content(event: FakePersonScriptEvent) -> str | None:
    return event.action.args.content


def _load_fixture_cases():
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    assert len(cases) == 12
    return cases


def test_load_fixture_cases_json_file() -> None:
    cases = _load_fixture_cases()
    assert [c.id for c in cases] == EXPECTED_CASE_IDS
    for case in cases:
        assert case.id
        assert len(case.fake_persons) >= 1
        assert case.must_pass_assertions

def test_fixture_cases_roundtrip() -> None:
    originals = _load_fixture_cases()

    exported = dump_test_cases_to_json(originals)
    reloaded = load_test_cases_from_json(exported)

    assert len(reloaded) == 12
    assert [c.id for c in reloaded] == [c.id for c in originals]

    for original, loaded in zip(originals, reloaded, strict=True):
        assert loaded.model_dump(mode="json") == original.model_dump(mode="json")


def test_fixture_scenario_variants() -> None:
    by_id = {case.id: case for case in _load_fixture_cases()}

    # case-001：仅假人 speak + 助手车控结果由 state_check 验收
    c1 = by_id["case-001"]
    speak_events = [e for e in c1.script_events if isinstance(e, FakePersonScriptEvent)]
    assert _speak_content(speak_events[0]) == "你好小涂，有点热，把空调打开吧。"
    assert c1.script_events == speak_events
    assert len(c1.virtual_car_state_check_assertions) == 1
    # case-001 有加分项（测试打分机制）
    assert len(c1.bonus_assertions) == 1
    assert "主动询问" in c1.bonus_assertions[0]

    # case-002：首句固定 + 续聊自主发挥
    c2 = by_id["case-002"]
    c2_speaks = [e for e in c2.script_events if isinstance(e, FakePersonScriptEvent)]
    assert _speak_content(c2_speaks[0]) is not None
    assert _speak_content(c2_speaks[1]) is None
    assert c2.virtual_car_state_check_assertions == []

    # case-003：首句即自主发挥
    c3 = by_id["case-003"]
    assert _speak_content(c3.script_events[0]) is None  # type: ignore[arg-type]

    # case-004：车态变为行驶 + 再次要求开门
    c4 = by_id["case-004"]
    car_performs = [e for e in c4.script_events if isinstance(e, VirtualCarPerformScriptEvent)]
    assert car_performs[0].action.args.fields["车辆当前行驶速度"] == "40 km/h"
    assert c4.virtual_car_state_check_assertions[0].action.args.expected_fields["车辆当前行驶速度"] == "40 km/h"
    c4_speaks = [e for e in c4.script_events if isinstance(e, FakePersonScriptEvent)]
    assert len(c4_speaks) == 2
    assert all(_speak_content(e) is not None for e in c4_speaks)

    # case-005：首句自主 + 行驶 + 续聊自主
    c5 = by_id["case-005"]
    c5_speaks = [e for e in c5.script_events if isinstance(e, FakePersonScriptEvent)]
    assert _speak_content(c5_speaks[0]) is None
    assert _speak_content(c5_speaks[1]) is None
    car_performs = [e for e in c5.script_events if isinstance(e, VirtualCarPerformScriptEvent)]
    assert "导航目的地" not in car_performs[0].action.args.fields
    assert isinstance(c5.virtual_car_state_check_assertions[0], VirtualCarStateCheckScriptEvent)
    assert c5.virtual_car_state_check_assertions[0].action.args.expected_fields["导航目的地"] == "上海浦东国际机场T2航站楼"

    # case-006：边界驱动跨多轮记忆（无时间戳）
    c6 = by_id["case-006"]
    assert "边界驱动" in c6.case_description
    # 时间戳为None表示边界驱动
    assert all(e.event_t0_plus_timedelta is None for e in c6.script_events)
    # 6个事件：3句固定台词 + 3句自主发挥（轮间边界检测）
    c6_speaks = [e for e in c6.script_events if isinstance(e, FakePersonScriptEvent)]
    assert len(c6_speaks) == 6
    assert _speak_content(c6_speaks[0]) == "记一下，我住在浦东前滩。"
    assert _speak_content(c6_speaks[1]) is None  # 边界检测自主发挥
    assert _speak_content(c6_speaks[2]) == "我搬家了，现在住在嘉定新城。"
    assert _speak_content(c6_speaks[3]) is None  # 边界检测自主发挥
    assert _speak_content(c6_speaks[4]) == "我家现在在哪儿？"
    assert _speak_content(c6_speaks[5]) is None  # 边界检测自主发挥

    # case-007：长期习惯时间锚点（P5D快进）
    c7 = by_id["case-007"]
    assert "长期习惯" in c7.case_name
    assert "时间加速" in c7.tags
    # 第1个事件是PT0S固定台词
    assert c7.script_events[0].event_t0_plus_timedelta.total_seconds() == 0
    # 第2个事件是P5D车态变更（5天后）
    assert c7.script_events[1].event_t0_plus_timedelta.days == 5
    # 第3个事件是P5DT10S边界驱动（快进5天后立即执行）
    assert c7.script_events[2].event_t0_plus_timedelta.days == 5
    assert c7.script_events[2].event_t0_plus_timedelta.seconds == 10


def test_wrapped_cases_json_format() -> None:
    originals = _load_fixture_cases()[:2]
    wrapped = json.dumps(
        {"cases": [c.model_dump(mode="json") for c in originals]},
        ensure_ascii=False,
    )
    loaded = load_test_cases_from_json(wrapped)
    assert [c.id for c in loaded] == [c.id for c in originals]
