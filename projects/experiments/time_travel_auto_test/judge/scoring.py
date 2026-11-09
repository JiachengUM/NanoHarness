"""打分公式（独立模块，便于测试和调参）。

打分规则（见 CONTEXT §2.7）：
- 必过项任一不过 → 0 分
- 必过全过 + 加分全过 → 满分 100
- 必过全过 + 加分全没过 → 及格分 60
- 必过全过 + 加分部分过 → 60 + 40 * (加分通过比例)
- 无加分项时，必过全过即满分
"""

from __future__ import annotations

from projects.experiments.time_travel_auto_test.judge.models import ScoreBreakdown

# 常量（§0.2 写死，有需求再抽配置）
PASS_SCORE = 60.0  # 及格分
FULL_SCORE = 100.0  # 满分
BONUS_RANGE = FULL_SCORE - PASS_SCORE  # 加分项能贡献的分数区间 = 40


def compute_score(
    must_pass_passed: int,
    must_pass_total: int,
    bonus_passed: int,
    bonus_total: int,
    *,
    state_check_passed: int = 0,
    state_check_total: int = 0,
) -> ScoreBreakdown:
    """根据必过/加分通过情况计算分数。

    state_check 也算必过项（按用户要求：状态检查本质是 code_assertion，都是必过项），
    和 NL 必过断言合并判定。

    Args:
        must_pass_passed: NL 必过断言通过数
        must_pass_total: NL 必过断言总数
        bonus_passed: 加分断言通过数
        bonus_total: 加分断言总数
        state_check_passed: state_check 通过数（算必过项）
        state_check_total: state_check 总数（算必过项）

    Returns:
        ScoreBreakdown: 含 score 和 passed
    """
    # state_check 合并到必过项统计
    combined_must_pass_total = must_pass_total + state_check_total
    combined_must_pass_passed = must_pass_passed + state_check_passed

    # 任一必过项不过 → 0 分
    if combined_must_pass_passed < combined_must_pass_total:
        score = 0.0
    elif bonus_total == 0:
        # 必过全过 + 无加分项 → 满分
        score = FULL_SCORE
    else:
        # 必过全过 + 有加分项 → 60 + 40 * (加分通过比例)
        bonus_ratio = bonus_passed / bonus_total
        score = PASS_SCORE + BONUS_RANGE * bonus_ratio

    return ScoreBreakdown(
        must_pass_total=must_pass_total,
        must_pass_passed=must_pass_passed,
        bonus_total=bonus_total,
        bonus_passed=bonus_passed,
        state_check_total=state_check_total,
        state_check_passed=state_check_passed,
        score=score,
        passed=score >= PASS_SCORE,
    )
