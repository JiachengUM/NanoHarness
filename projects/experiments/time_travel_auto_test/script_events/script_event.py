from __future__ import annotations

from datetime import timedelta
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, field_validator


class ActionType(str, Enum):
    """剧本动作类型：执行演绎（perform），或在指定时刻检查状态（state_check）。"""

    PERFORM = "perform"
    STATE_CHECK = "state_check"


# ---------------------------------------------------------------------------
# 现阶段范围：实时全双工对话场景测试
#
# - 假人动作定义见 fake_person/models.py，通过 FakePersonAction discriminated union 扩展
# - 虚拟车 set_state（写 car_info dict）+ state_check k/v 断言
# - 未来扩展：虚拟车 perform 可加入更多动作种类（如 SIMULATE_BUTTON 模拟物理按键）
# ---------------------------------------------------------------------------


class ScriptEventType(str, Enum):
    """JSON 导入/导出用的显式 tag；Python 侧仍优先用 isinstance 区分子类。"""

    FAKE_PERSON = "fake_person"
    VIRTUAL_CAR = "virtual_car"
    WORLD_TICK = "world_tick"


# ---------------------------------------------------------------------------
# 虚拟车：演绎动作（经驱动器改状态）+ state_check 断言
# ---------------------------------------------------------------------------


class VirtualCarActionKind(str, Enum):
    """虚拟车剧本动作种类。

    perform 类动作（写车态）：
    - SET_STATE: 写 car_info dict（当前唯一；由 VirtualCarDriver 映射到 devices）

    未来可扩展的 perform 动作：
    - SIMULATE_BUTTON: 模拟物理按键事件（如"乘客按下空调AC按钮"）
    - SIMULATE_SENSOR: 模拟传感器读数注入（如"车外温度传感器报 42°C"）

    注意：state_check 类动作（校验车态）不走 VirtualCarActionKind，
    而是独立的 VirtualCarStateCheckAction（action_type=state_check），
    对应 VirtualCarStateCheckScriptEvent 事件类型。
    """

    SET_STATE = "set_state"


class VirtualCarSetStateArgs(BaseModel):
    fields: dict[str, Any] = Field(
        description="写入虚拟车 car_info 的 k/v；同 key 覆盖，至少一项",
    )

    @field_validator("fields")
    @classmethod
    def fields_must_not_be_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("fields 至少需要一项 k/v")
        return v


class VirtualCarSetStatePerformAction(BaseModel):
    action_type: Literal[ActionType.PERFORM] = ActionType.PERFORM
    kind: Literal[VirtualCarActionKind.SET_STATE] = VirtualCarActionKind.SET_STATE
    args: VirtualCarSetStateArgs


# VirtualCarPerformAction: discriminated union，当前仅 SET_STATE，未来在此扩展
VirtualCarPerformAction = Annotated[
    Union[
        VirtualCarSetStatePerformAction,
        # 未来：VirtualCarSimulateButtonPerformAction,
        # 未来：VirtualCarSimulateSensorPerformAction,
    ],
    Field(discriminator="kind"),
]


class VirtualCarStateCheckArgs(BaseModel):
    expected_fields: dict[str, Any] = Field(
        description="虚拟车状态字段断言，key 为状态字段名，value 为预期值",
    )

    @field_validator("expected_fields")
    @classmethod
    def expected_fields_must_not_be_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("expected_fields 至少需要一项 k/v 断言")
        return v


class VirtualCarStateCheckAction(BaseModel):
    action_type: Literal[ActionType.STATE_CHECK] = ActionType.STATE_CHECK
    args: VirtualCarStateCheckArgs


# ---------------------------------------------------------------------------
# 剧本事件
# ---------------------------------------------------------------------------

from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonAction,
    FakePersonSpeakPerformAction,
)


class ScriptEventBase(BaseModel):
    """剧本事件公共字段（基类）。

    event_type 主要为 JSON 文件导入导出服务（discriminator）；
    运行时业务逻辑仍应用 isinstance(event, FakePersonScriptEvent) 等。
    类型标注与 JSON 反序列化请用 ``ScriptEvent``（discriminated union）。
    """

    event_t0_plus_timedelta: Optional[timedelta] = Field(
        default=None,
        description=(
            "事件发生时间相对于场景 t0 的偏移量。"
            "None 表示边界驱动模式：上一轮自然结束后立即执行此事件"
        ),
    )
    event_type: ScriptEventType = Field(description="JSON tag，决定反序列化为哪个子类")
    target: str = Field(description="事件目标主体 id，如 userA、car、world")


class FakePersonScriptEvent(ScriptEventBase):
    """假人剧本事件：驱动假人执行动作。

    action 为 FakePersonAction discriminated union，当前仅 SPEAK。
    未来新增动作种类（如 MANUAL_CONTROL 模拟手动操作车控）时，
    在 fake_person/models.py 的 FakePersonAction Union 中添加即可，
    无需修改此事件类。
    """

    event_type: Literal[ScriptEventType.FAKE_PERSON] = ScriptEventType.FAKE_PERSON
    target: str = Field(description="假人角色 id，如 userA、driver")
    action: FakePersonAction


class VirtualCarPerformScriptEvent(ScriptEventBase):
    """虚拟车剧本演绎事件：perform 类动作（改车态）。

    action 为 VirtualCarPerformAction discriminated union，当前仅 SET_STATE。
    未来新增动作种类（如 SIMULATE_BUTTON 模拟物理按键）时，
    在 VirtualCarPerformAction Union 中添加即可，无需修改此事件类。

    state_check 类动作（校验车态）不走此事件，而是独立的
    VirtualCarStateCheckScriptEvent（action_type=state_check）。
    """

    event_type: Literal[ScriptEventType.VIRTUAL_CAR] = ScriptEventType.VIRTUAL_CAR
    target: Literal["car"] = Field(
        default="car",
        description="虚拟车目标；现阶段场景内仅有一辆虚拟车",
    )
    action: VirtualCarPerformAction


class VirtualCarStateCheckScriptEvent(ScriptEventBase):
    """虚拟车状态断言事件：在指定时刻对 car_info 做 k/v 检查（仅 state_check）。"""

    event_type: Literal[ScriptEventType.VIRTUAL_CAR] = ScriptEventType.VIRTUAL_CAR
    target: Literal["car"] = Field(
        default="car",
        description="虚拟车目标；现阶段场景内仅有一辆虚拟车",
    )
    action: VirtualCarStateCheckAction


class WorldTickScriptEvent(ScriptEventBase):
    """时间锚点事件：没有执行主体，只表示"时间演进到此刻必须停一下"。

    来源：
    - 剧本显式定义（如 delay 后检查状态）
    - 被测助手运行时注入（定时任务触发时间）

    特点：
    - 无 action 字段（没有可执行的动作体）
    - target 固定为 "world"
    - event_t0_plus_timedelta 必须不为 None（总是锚点事件）
    - Runner 遇到此事件时只推进时间、记 trace，不执行任何操作
    """

    event_type: Literal[ScriptEventType.WORLD_TICK] = ScriptEventType.WORLD_TICK
    target: Literal["world"] = Field(
        default="world",
        description="WorldTick 无特定执行主体",
    )
    event_t0_plus_timedelta: timedelta = Field(
        description="WorldTick 总是锚点事件，必须有时间偏移",
    )


# 虚拟车 perform() 可消费演绎或断言事件
VirtualCarScriptEvent = VirtualCarPerformScriptEvent | VirtualCarStateCheckScriptEvent

ScriptPerformEvent = Annotated[
    Union[FakePersonScriptEvent, VirtualCarPerformScriptEvent],
    Field(discriminator="event_type"),
]

# 调度器可处理的全部事件类型（含 state_check + world_tick）
ScriptEvent = FakePersonScriptEvent | VirtualCarPerformScriptEvent | VirtualCarStateCheckScriptEvent | WorldTickScriptEvent

script_perform_event_adapter = TypeAdapter(ScriptPerformEvent)
script_event_adapter = script_perform_event_adapter
virtual_car_state_check_script_event_adapter = TypeAdapter(VirtualCarStateCheckScriptEvent)
