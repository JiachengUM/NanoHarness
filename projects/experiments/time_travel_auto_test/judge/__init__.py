"""Judge 模块：基于 Trace 的终局评判。

目录结构（与 fake_person/ 对齐）：
- models.py  — JudgeInput / JudgeVerdict / AssertionResult / AssertionType
- scoring.py — 打分公式（必过 + 加分 → 分数）
- prompt.py  — JUDGE_SYSTEM_PROMPT + render_timeline_text
- judge.py   — Judge 类主逻辑
"""

from projects.experiments.time_travel_auto_test.judge.judge import (
    Judge,
)
from projects.experiments.time_travel_auto_test.judge.models import (
    AssertionResult,
    AssertionType,
    JudgeInput,
    JudgeVerdict,
    ScoreBreakdown,
)
from projects.experiments.time_travel_auto_test.judge.prompt import (
    render_timeline_text,
)
from projects.experiments.time_travel_auto_test.judge.scoring import (
    compute_score,
)

__all__ = [
    "Judge",
    "JudgeInput",
    "JudgeVerdict",
    "AssertionResult",
    "AssertionType",
    "ScoreBreakdown",
    "compute_score",
    "render_timeline_text",
]
