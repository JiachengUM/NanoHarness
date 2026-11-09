"""VirtualCarDriver：虚拟车事件驱动器。

职责：
- 接收 VirtualCarScriptEvent，根据 action_type 分发执行
- perform → 写车态；state_check → 断言车态
- 与数据模型 VirtualCar 分离：VirtualCar 仅持有设备状态，Driver 负责行为

未来扩展（详见 CONTEXT.md §7）：
- 虚拟车 perform 动作通过 VirtualCarPerformAction discriminated union 扩展
- 当前仅 SET_STATE，未来可加入 SIMULATE_BUTTON（模拟物理按键）等
- 新增动作时在 _set_state 同级加 _simulate_button 等私有方法，在 drive() 中按 kind 分发
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from projects.experiments.time_travel_auto_test.script_events.script_event import (
    ActionType,
    VirtualCarScriptEvent,
    VirtualCarSetStatePerformAction,
    VirtualCarStateCheckAction,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import (
    VirtualCar,
    VirtualCarEventResult,
    VirtualCarSetStateOutcome,
    VirtualCarStateCheckOutcome,
)


class VirtualCarDriver:
    """虚拟车事件驱动器：消费剧本事件，驱动虚拟车状态变更或断言。

    用法：
        driver = VirtualCarDriver(car)
        result = driver.drive(event, event_at=...)
    """

    def __init__(self, car: VirtualCar) -> None:
        self._car = car

    def drive(
        self,
        event: VirtualCarScriptEvent,
        *,
        event_at: datetime | None = None,
    ) -> VirtualCarEventResult:
        """执行虚拟车剧本事件（set_state 或 state_check）。

        未来扩展：perform 类新增动作时，按 event.action.kind 分发到对应私有方法。
        """
        if event.target != "car":
            raise ValueError(f"虚拟车剧本事件 target 应为 'car'，收到 {event.target!r}")

        action = event.action
        if action.action_type == ActionType.PERFORM:
            # 按 kind 分发 perform 动作；当前仅 SET_STATE
            if action.kind == "set_state":
                outcome = self._set_state(action)  # type: ignore[arg-type]
            else:
                raise ValueError(f"未支持的虚拟车 perform kind={action.kind!r}")
        elif action.action_type == ActionType.STATE_CHECK:
            outcome = self._state_check(action)  # type: ignore[arg-type]
        else:
            raise ValueError(f"未支持的虚拟车 action_type={action.action_type!r}")

        return VirtualCarEventResult(event_at=event_at, outcome=outcome)

    def _set_state(self, action: VirtualCarSetStatePerformAction) -> VirtualCarSetStateOutcome:
        """set_state：通过 car.set_field 写入设备状态。"""
        fields = action.args.fields
        updated_fields: dict[str, Any] = {}

        for key, value in fields.items():
            self._car.set_field(key, value)
            updated_fields[key] = self._car.get_field(key)

        return VirtualCarSetStateOutcome(
            updated_fields=updated_fields,
            car_info=dict(self._car.car_info),
        )

    def _state_check(self, action: VirtualCarStateCheckAction) -> VirtualCarStateCheckOutcome:
        """state_check：从 car.car_info 读出实际值，对比 expected。"""
        expected = action.args.expected_fields
        actual_car_info = dict(self._car.car_info)
        mismatches: dict[str, dict[str, Any]] = {}

        for key, expected_value in expected.items():
            actual_value = actual_car_info.get(key)
            if actual_value != expected_value:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}

        return VirtualCarStateCheckOutcome(
            expected_fields=dict(expected),
            passed=len(mismatches) == 0,
            mismatches=mismatches,
            car_info=actual_car_info,
        )