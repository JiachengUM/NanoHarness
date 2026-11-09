import json
from datetime import timedelta

import pytest

from projects.experiments.time_travel_auto_test.case_schema import (
    FakePersonInfo,
    TestCase,
    VirtualCarInfo,
    dump_test_cases_to_json,
    load_test_cases_from_json,
)
from projects.experiments.time_travel_auto_test.fake_person.models import FakePersonSpeakArgs, FakePersonSpeakPerformAction
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarStateCheckArgs,
    VirtualCarStateCheckScriptEvent,
    VirtualCarStateCheckAction,
)


def _sample_case() -> TestCase:
    return TestCase(
        id="case-001",
        case_name="有点热",
        case_description="主驾觉得热，期望助手开空调",
        tags=["空调"],
        fake_persons=[
            FakePersonInfo(
                role_id="userA",
                profile="张三，35岁，注重舒适",
            ),
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车内温度": "28摄氏度",
                "空调开启状态及模式": "关闭中",
            },
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="userA",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="有点热，开空调吧"),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=10),
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "制冷中"},
                    ),
                ),
            ),
        ],
        text_script="用户：有点热\n助手：好的，已为您打开空调",
        must_pass_assertions=["助手应帮助用户降温"],
    )


def test_test_case_info_fields() -> None:
    case = _sample_case()

    assert case.fake_persons[0].profile.startswith("张三")
    assert case.virtual_car.car_info["车内温度"] == "28摄氏度"


def test_load_test_cases_from_json_roundtrip() -> None:
    original = _sample_case()
    payload = dump_test_cases_to_json([original])
    loaded = load_test_cases_from_json(payload)

    assert len(loaded) == 1
    assert loaded[0].id == original.id
    assert loaded[0].fake_persons[0].role_id == "userA"
    assert loaded[0].virtual_car.car_info["车内温度"] == "28摄氏度"
    assert len(loaded[0].script_events) == 1
    assert len(loaded[0].virtual_car_state_check_assertions) == 1
    assert isinstance(loaded[0].script_events[0], FakePersonScriptEvent)


def test_load_test_cases_wrapped_cases_key() -> None:
    case = _sample_case()
    wrapped = json.dumps({"cases": [case.model_dump(mode="json")]}, ensure_ascii=False)
    loaded = load_test_cases_from_json(wrapped)
    assert len(loaded) == 1
    assert loaded[0].case_name == "有点热"


def test_script_event_target_must_match_fake_person() -> None:
    case = _sample_case()
    bad = case.model_dump()
    bad["script_events"][0]["target"] = "unknown"
    with pytest.raises(ValueError, match="不在 fake_persons 中"):
        TestCase.model_validate(bad)


def test_state_check_must_not_be_in_script_events() -> None:
    case = _sample_case()
    bad = case.model_dump(mode="json")
    bad["script_events"].append(bad["virtual_car_state_check_assertions"][0])
    bad["virtual_car_state_check_assertions"] = []
    with pytest.raises(Exception):
        TestCase.model_validate(bad)
