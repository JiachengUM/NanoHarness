"""VirtualCar v2 测试：devices 为真相源，car_info 为只读视图。"""

from datetime import timedelta

import pytest

from projects.experiments.time_travel_auto_test.script_events.script_event import (
    VirtualCarPerformScriptEvent,
    VirtualCarSetStateArgs,
    VirtualCarSetStatePerformAction,
    VirtualCarStateCheckAction,
    VirtualCarStateCheckArgs,
    VirtualCarStateCheckScriptEvent,
)
from projects.experiments.time_travel_auto_test.case_runner.virtual_car_driver import (
    VirtualCarDriver,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import (
    VirtualCar,
    VirtualCarSetStateOutcome,
    VirtualCarStateCheckOutcome,
    format_car_info,
)


def test_init_from_car_info_basic() -> None:
    """从 car_info dict 初始化，解析到 devices。"""
    car = VirtualCar({
        "车辆当前行驶速度": "0 km/h（静止）",
        "车辆当前档位": "P档（驻车档）",
        "车内温度": "29摄氏度",
        "空调开启状态及模式": "关闭中",
        "当前位置": "上海平金中心地下停车场B2",  # 自由元数据
    })

    # devices 字段被正确解析
    assert car.devices.driving.speed_kmh == 0
    assert car.devices.driving.gear.value == "P档"
    assert car.devices.ac.temperature == 29
    assert car.devices.ac.is_on is False

    # car_info 只读视图能还原
    info = car.car_info
    assert info["车辆当前行驶速度"] == "0 km/h（静止）"
    assert info["车辆当前档位"] == "P档（驻车档）"
    assert info["车内温度"] == "29摄氏度"
    assert info["空调开启状态及模式"] == "关闭中"
    # 自由元数据透传
    assert info["当前位置"] == "上海平金中心地下停车场B2"


def test_set_state_updates_devices() -> None:
    """set_state 写入 devices，car_info 视图同步更新。"""
    car = VirtualCar({"车内温度": "24摄氏度"})
    driver = VirtualCarDriver(car)

    result = driver.drive(
        VirtualCarPerformScriptEvent(
            event_t0_plus_timedelta=timedelta(seconds=0),
            target="car",
            action=VirtualCarSetStatePerformAction(
                args=VirtualCarSetStateArgs(
                    fields={
                        "空调开启状态及模式": "制冷中",
                        "车内温度": "22摄氏度",
                    },
                ),
            ),
        ),
    )

    assert isinstance(result.outcome, VirtualCarSetStateOutcome)
    # devices 被更新
    assert car.devices.ac.is_on is True
    assert car.devices.ac.temperature == 22
    # car_info 视图同步
    assert car.car_info["空调开启状态及模式"] == "制冷中"
    assert car.car_info["车内温度"] == "22摄氏度"


def test_state_check_pass_and_fail() -> None:
    """state_check 从 devices 读值对比。"""
    car = VirtualCar({"车内温度": "22摄氏度", "空调开启状态及模式": "制冷中"})
    driver = VirtualCarDriver(car)

    # 通过
    passed = driver.drive(
        VirtualCarStateCheckScriptEvent(
            event_t0_plus_timedelta=timedelta(seconds=1),
            target="car",
            action=VirtualCarStateCheckAction(
                args=VirtualCarStateCheckArgs(
                    expected_fields={"车内温度": "22摄氏度"},
                ),
            ),
        ),
    )
    assert isinstance(passed.outcome, VirtualCarStateCheckOutcome)
    assert passed.outcome.passed is True

    # 失败
    failed = driver.drive(
        VirtualCarStateCheckScriptEvent(
            event_t0_plus_timedelta=timedelta(seconds=2),
            target="car",
            action=VirtualCarStateCheckAction(
                args=VirtualCarStateCheckArgs(
                    expected_fields={"车内温度": "20摄氏度"},
                ),
            ),
        ),
    )
    assert isinstance(failed.outcome, VirtualCarStateCheckOutcome)
    assert failed.outcome.passed is False
    assert failed.outcome.mismatches["车内温度"]["expected"] == "20摄氏度"
    assert failed.outcome.mismatches["车内温度"]["actual"] == "22摄氏度"


def test_free_form_fields_passthrough() -> None:
    """自由元数据 key 透传，不解析到 devices。"""
    car = VirtualCar({
        "当前位置": "公司停车场",
        "当前系统时间": "2026-06-16 08:30",
    })

    # car_info 能拿到
    assert car.car_info["当前位置"] == "公司停车场"
    assert car.car_info["当前系统时间"] == "2026-06-16 08:30"


def test_set_state_free_form_field() -> None:
    """set_state 自由元数据 key 直接写入。"""
    car = VirtualCar({})
    driver = VirtualCarDriver(car)

    driver.drive(
        VirtualCarPerformScriptEvent(
            event_t0_plus_timedelta=timedelta(seconds=0),
            target="car",
            action=VirtualCarSetStatePerformAction(
                args=VirtualCarSetStateArgs(
                    fields={"当前系统时间": "2026-06-19 周五 18:30"},
                ),
            ),
        ),
    )

    assert car.car_info["当前系统时间"] == "2026-06-19 周五 18:30"


def test_format_car_info() -> None:
    """format_car_info 格式化。"""
    assert format_car_info({}) == "无"
    text = format_car_info({"车速": "60 km/h"})
    assert "车速" in text and "60 km/h" in text


def test_car_info_text_for_prompt() -> None:
    """car_info_text 供假人 prompt 使用。"""
    car = VirtualCar({"车内温度": "28摄氏度"})
    text = car.car_info_text()
    assert "车内温度" in text
    assert "28摄氏度" in text


def test_case_004_driving_scenario_roundtrip() -> None:
    """case-004 场景：车态变更（0→40km/h, P→D）往返一致。"""
    car = VirtualCar({
        "车辆当前行驶速度": "0 km/h（静止）",
        "车辆当前档位": "P档（驻车档）",
    })
    driver = VirtualCarDriver(car)

    # 模拟驾驶员上路
    driver.drive(
        VirtualCarPerformScriptEvent(
            event_t0_plus_timedelta=timedelta(seconds=0),
            target="car",
            action=VirtualCarSetStatePerformAction(
                args=VirtualCarSetStateArgs(
                    fields={
                        "车辆当前行驶速度": "40 km/h",
                        "车辆当前档位": "D档（前进档）",
                    },
                ),
            ),
        ),
    )

    assert car.car_info["车辆当前行驶速度"] == "40 km/h"
    assert car.car_info["车辆当前档位"] == "D档（前进档）"
    assert car.devices.driving.speed_kmh == 40
    assert car.devices.driving.gear.value == "D档"


def test_set_field_get_field_for_car_control() -> None:
    """车控工具专用接口 set_field/get_field。"""
    car = VirtualCar({"车内温度": "25摄氏度"})

    # 读
    assert "25摄氏度" in str(car.get_field("车内温度"))

    # 写
    car.set_field("车内温度", "20摄氏度")
    assert car.devices.ac.temperature == 20
    assert "20摄氏度" in str(car.get_field("车内温度"))
