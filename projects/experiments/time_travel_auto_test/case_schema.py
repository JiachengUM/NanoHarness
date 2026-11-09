from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Self

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonEventMemoryEntry,
    FakePersonIntent,
    FakePersonState,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    ActionType,
    FakePersonScriptEvent,
    ScriptPerformEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarStateCheckScriptEvent,
)

DEFAULT_MAX_ROUND = 8


class FakePersonInfo(BaseModel):
    """场景内一名假人的初始信息（JSON 可序列化；由 runner 构造 `FakePerson` 运行时实体）。"""

    role_id: str = Field(description="与 script_events 中 fake_person 事件的 target 对应")
    profile: str = Field(description="人设，自然语言预设")
    event_memory: list[FakePersonEventMemoryEntry] = Field(default_factory=list)
    state: Optional[FakePersonState] = None
    intent: Optional[FakePersonIntent] = None


class VirtualCarInfo(BaseModel):
    """场景内虚拟车的初始信息（由 runner 构造 `VirtualCar` 运行时实体）。"""

    car_info: dict[str, Any] = Field(
        default_factory=dict,
        description="虚拟车初始状态 k/v，如车内温度、当前位置",
    )


class TestCase(BaseModel):
    """一个车载助手测试场景：假人/虚拟车初始信息 + 剧本事件时间线 + 判据。"""

    id: str = Field(..., description="测试用例唯一 id")
    case_name: str = Field(..., description="测试用例名称")
    case_description: str = Field(default="无", description="场景综合描述")
    tags: list[str] = Field(default_factory=list)
    t0: Optional[datetime] = Field(
        default=None,
        description=(
            "场景起始时间（ISO 8601 格式，如 2025-01-03T18:00:00）；"
            "None 表示运行时动态设置（默认使用 datetime.now()）"
        ),
    )
    max_round: int = Field(
        default=DEFAULT_MAX_ROUND,
        description=f"假人 LLM 单段对话最大轮数，默认 {DEFAULT_MAX_ROUND}",
    )
    fake_persons: list[FakePersonInfo] = Field(
        ...,
        min_length=1,
        description="场景内假人初始信息，至少一名",
    )
    virtual_car: VirtualCarInfo = Field(
        default_factory=VirtualCarInfo,
        description="虚拟车初始 car_info",
    )
    script_events: list[ScriptPerformEvent] = Field(
        default_factory=list,
        description=(
            "剧本演绎时间线。event_t0_plus_timedelta 为 None 表示边界驱动（上一轮结束后立即执行）；"
            "有时戳表示锚点驱动（精确时间点执行，可打断）。"
            "假人 speak；虚拟车 set_state 仅用于模拟非助手车控的外部世界演进。"
        ),
    )
    virtual_car_state_check_assertions: list[VirtualCarStateCheckScriptEvent] = Field(
        default_factory=list,
        description=(
            "虚拟车 k/v 状态断言（按 event_t0_plus_timedelta 调度）。"
            "仅含 state_check 动作，不得出现在 script_events 中。"
        ),
    )
    text_script: str = Field(
        default="无",
        description="预期对话文本剧本，供假人 LLM 与 Judge 参考",
    )
    must_pass_assertions: list[str] = Field(
        ...,
        description="自然语言必过断言；至少一条非空字符串。任一不过 → 0 分",
    )
    bonus_assertions: list[str] = Field(
        default_factory=list,
        description="自然语言加分断言；可选。过得越多分数越高",
    )

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        if not any(s.strip() for s in self.must_pass_assertions):
            raise ValueError("must_pass_assertions 至少需要一条非空字符串")

        role_ids = [person.role_id for person in self.fake_persons]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("fake_persons 中 role_id 不能重复")

        known_person_targets = set(role_ids)
        for index, event in enumerate(self.script_events):
            if isinstance(event, FakePersonScriptEvent):
                if event.target not in known_person_targets:
                    raise ValueError(
                        f"script_events[{index}] 假人 target={event.target!r} "
                        f"不在 fake_persons 中（已知: {sorted(known_person_targets)!r}）",
                    )
                if event.action.action_type != ActionType.PERFORM:
                    raise ValueError(
                        f"script_events[{index}] 假人事件必须为 perform 动作",
                    )
            elif isinstance(event, VirtualCarPerformScriptEvent):
                if event.target != "car":
                    raise ValueError(
                        f"script_events[{index}] 虚拟车事件 target 应为 'car'，"
                        f"收到 {event.target!r}",
                    )
                if event.action.action_type != ActionType.PERFORM:
                    raise ValueError(
                        f"script_events[{index}] 虚拟车演绎事件必须为 perform 动作",
                    )

        for index, event in enumerate(self.virtual_car_state_check_assertions):
            if event.action.action_type != ActionType.STATE_CHECK:
                raise ValueError(
                    f"virtual_car_state_check_assertions[{index}] 必须为 state_check 动作",
                )
            if event.target != "car":
                raise ValueError(
                    f"virtual_car_state_check_assertions[{index}] target 应为 'car'，"
                    f"收到 {event.target!r}",
                )

        return self


TestCase.__test__ = False  # noqa: PT019 — 避免 pytest 把模型当作测试类收集

test_case_adapter = TypeAdapter(TestCase)
test_cases_adapter = TypeAdapter(list[TestCase])


def load_test_cases_from_json(data: str | bytes | bytearray) -> list[TestCase]:
    """从 JSON 字符串批量导入。顶层可为 ``[case, ...]``、``{\"cases\": [...]}`` 或单个 case 对象。"""
    parsed = json.loads(data)
    if isinstance(parsed, list):
        return test_cases_adapter.validate_python(parsed)
    if isinstance(parsed, dict) and "cases" in parsed:
        return test_cases_adapter.validate_python(parsed["cases"])
    return [test_case_adapter.validate_python(parsed)]


def load_test_cases_from_json_file(path: str | Path) -> list[TestCase]:
    return load_test_cases_from_json(Path(path).read_text(encoding="utf-8"))


def dump_test_cases_to_json(cases: list[TestCase], *, indent: int = 2) -> str:
    payload = [case.model_dump(mode="json") for case in cases]
    return json.dumps(payload, ensure_ascii=False, indent=indent)
