"""假人数据模型：纯数据容器，行为由 FakePersonDriver 负责。

未来扩展规划（详见 CONTEXT.md §7）：
- 假人动作种类：当前仅 SPEAK，未来可能加入 MANUAL_CONTROL（模拟手动操作车控）、
  STATE_CHANGE（模拟人物状态变更，如"睡着了"）、GESTURE（模拟手势/动作）
- 假人动作通过 FakePersonAction discriminated union 扩展，新增动作只需：
  1. 在 FakePersonActionKind 加新枚举值
  2. 定义对应的 Action + Args 类
  3. 加入 FakePersonAction Union
  4. 在 FakePersonDriver.drive() 中分发
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class FakePersonEventMemoryEntry(BaseModel):
    """假人侧事件记忆（对齐火山 event_memory 语义）。"""

    content: str = Field(description="记忆内容，如「昨天去了外滩」")
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="可选：记忆对应的发生时间",
    )


class FakePersonState(BaseModel):
    """人物状态：自然语言一句话描述，不做穷举结构化。"""

    description: str = Field(
        description="如「心情很好，但感觉比较热，阳光有点刺眼」",
    )


class FakePersonIntent(BaseModel):
    """当前意图：可选预设；不设置时由假人自行演绎。"""

    description: str = Field(description="如「想上厕所」")


# ---------------------------------------------------------------------------
# 剧本动作
#
# 假人动作通过 FakePersonAction discriminated union 扩展。
# 当前仅 SPEAK，未来新增动作时在 FakePersonActionKind 加枚举值，
# 定义对应 Action 类，加入 FakePersonAction Union 即可。
# ---------------------------------------------------------------------------


class FakePersonActionKind(str, Enum):
    """假人剧本动作种类。

    当前仅 SPEAK（说话）。未来可扩展：
    - MANUAL_CONTROL: 模拟假人手动操作车控（如按空调按钮、调座椅）
    - STATE_CHANGE: 模拟假人自身状态变更（如"睡着了"、"下车了"）
    - GESTURE: 模拟假人做手势/动作（如"指了一下窗外"）
    """

    SPEAK = "speak"


class FakePersonSpeakArgs(BaseModel):
    content: Optional[str] = Field(
        default=None,
        description="固定台词；None 表示自主发挥，由 LLM 生成",
    )


class FakePersonSpeakPerformAction(BaseModel):
    action_type: Literal["perform"] = "perform"
    kind: Literal[FakePersonActionKind.SPEAK] = FakePersonActionKind.SPEAK
    args: FakePersonSpeakArgs


# FakePersonAction: discriminated union，当前仅 SPEAK，未来在此扩展
FakePersonAction = Annotated[
    Union[
        FakePersonSpeakPerformAction,
        # 未来：FakePersonManualControlPerformAction,
        # 未来：FakePersonStateChangePerformAction,
        # 未来：FakePersonGesturePerformAction,
    ],
    Field(discriminator="kind"),
]


def format_event_memory(entries: list[FakePersonEventMemoryEntry]) -> Optional[str]:
    if not entries:
        return None
    lines: list[str] = []
    for entry in entries:
        if entry.occurred_at is not None:
            lines.append(f"- [{entry.occurred_at.isoformat()}] {entry.content}")
        else:
            lines.append(f"- {entry.content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Outcome 类型
# ---------------------------------------------------------------------------


class FakePersonSpeakOutcome(BaseModel):
    kind: Literal["speak"] = "speak"
    script_content: Optional[str] = Field(
        description="剧本给定台词；None 表示需假人自主发挥",
    )
    utterance: Optional[str] = Field(
        default=None,
        description="实际说出的话；固定台词时直接填入，自主发挥时由 LLM 填入",
    )


# ---------------------------------------------------------------------------
# FakePerson 纯数据模型
# ---------------------------------------------------------------------------


class FakePerson(BaseModel):
    """场景中的假人：纯数据容器。

    角色自身字段（profile / state / intent / event_memory）。
    演绎行为由 FakePersonDriver 负责。
    """

    role_id: str = Field(description="与 script_events 中 fake_person 事件的 target 对应")
    profile: str = Field(description="人设，自然语言预设")
    event_memory: list[FakePersonEventMemoryEntry] = Field(default_factory=list)
    state: Optional[FakePersonState] = None
    intent: Optional[FakePersonIntent] = None