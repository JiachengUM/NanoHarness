"""Judge 数据模型（§0.10 用数据模型规范，不用裸 dict）。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AssertionType(str, Enum):
    """断言类型。"""

    MUST_PASS = "must_pass"  # 必过项：任一不过 → 0 分
    BONUS = "bonus"  # 加分项：过得越多分数越高


class JudgeInput(BaseModel):
    """Judge 的输入：一个 case 跑完后的完整上下文。"""

    case_id: str
    case_name: str
    case_description: str = ""
    # 带时间线的 trace 文本（已渲染好的高可读字符串）
    timeline_text: str
    # 必过断言（自然语言）
    must_pass_assertions: list[str]
    # 加分断言（自然语言，可选）
    bonus_assertions: list[str] = Field(default_factory=list)
    # 结构化断言结果（state_check 已由 Runner 自动判定，都算必过项）
    state_check_summary: dict[str, Any] = Field(default_factory=dict)
    # 助手视角的对话历史（可选，由 adump_history 导出）
    assistant_history: list[dict[str, str]] = Field(default_factory=list)
    # 假人人设信息（让裁判价值观对齐假人）
    fake_person_profiles: list[dict[str, str]] = Field(default_factory=list)


class AssertionResult(BaseModel):
    """单条断言的评判结果。"""

    assertion: str
    assertion_type: AssertionType
    passed: bool
    reasoning: str
    evidence: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    """打分明细。

    打分规则（见 CONTEXT §2.7）：
    - 必过项任一不过 → 0 分
    - 必过全过 + 加分全过 → 满分 100
    - 必过全过 + 加分全没过 → 及格分 60
    - 必过全过 + 加分部分过 → 60 + 40 * (加分通过比例)
    - 无加分项时，必过全过即满分
    """

    must_pass_total: int
    must_pass_passed: int
    bonus_total: int
    bonus_passed: int
    # state_check 也算必过项，合并到 must_pass 统计
    state_check_total: int = 0
    state_check_passed: int = 0
    score: float  # 0-100
    passed: bool  # 是否及格（score >= 60）


class JudgeVerdict(BaseModel):
    """Judge 终局评判结果。"""

    case_id: str
    overall_passed: bool
    score: float  # 0-100
    score_breakdown: ScoreBreakdown
    assertion_results: list[AssertionResult]
    summary: str
    judged_at: datetime = Field(default_factory=datetime.now)
    # 解析失败时的原始 LLM 回复（便于诊断），成功时为 None
    raw_response: Optional[str] = None
