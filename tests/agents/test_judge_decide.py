"""判定方程（组合方程）单测：原子答案 → 裁决，全部是纯函数，不需要网络。

这些用例是判定器的"真值表"：把每个分支的边界钉下来。判据改阈值、改分支顺序时，
这里的用例会立刻报警——这是把裁决写成代码（而非交给模型现编）换来的可回归性。

约定：覆盖默认答案一律传 **mapping 字面量**（``{Q_X: ...}``）而不是关键字参数——
``compose(Q_DIAG_HARD=...)`` 传进去的名字是字符串 ``"Q_DIAG_HARD"`` 而非它的值，
覆盖会静默失效。这个坑用签名堵掉（helper 只收 mapping）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from aicore.agents.plan.diagnosis import AcceptDegraded, Replan, SkipUnsolvable
from aicore.agents.plan.judges.jev_client import JevAnswer
from tests.agents._fake_jev import choice_answer, noul_answer, score_answer
from aicore.agents.plan.decisions import (
    DiagnosisAtoms,
    DiagnosisDecision,
    StepAssertDecision,
    combine_finish_confidence,
)
from aicore.agents.plan.judges.llm import LlmJudge
from aicore.agents.plan.judge import Point
from aicore.agents.plan.judges.points import (
    CAUSE_DATA_ABSENT,
    CAUSE_EXEC_FAILED,
    CAUSE_PARAM_ERROR,
    CAUSE_PLAN_MISTAKE,
    CAUSE_TOOL_UNSUPPORTED,
    DIAGNOSIS,
    FINISH,
    GRAY_ZONE,
    PLAN_AUDIT,
    PREFLIGHT,
    Q_AMBIGUITY,
    Q_AUDIT_COVERAGE,
    Q_AUDIT_GAP,
    Q_AUDIT_STRICTNESS,
    Q_DIAG_BLOCKING,
    Q_DIAG_CAUSE,
    Q_DIAG_HARD,
    Q_DIAG_RETRY,
    Q_DIAG_USABLE,
    Q_FIN_COVERAGE,
    Q_FIN_DISCLOSED,
    Q_FIN_FABRICATED,
    Q_FIN_OUTCOME,
    Q_GATE_SAME,
    Q_GATE_WORTH,
    Q_NEEDS_PLAN,
    Q_PATH,
    ROUND_GATE,
    STEP_ASSERT,
    ASSERT_GOAL_FLOOR,
    ASSERT_GOAL_PASS,
    CLAUSE_FALSIFIED,
    CLAUSE_HOLDS,
    CLAUSE_UNSUPPORTED,
    QUALITY_GROUNDED,
    QUALITY_INVENTED,
    QUALITY_UNKNOWN,
    QUALITY_UNVERIFIABLE,
    Q_ASSERT_GOAL,
    clause_quality_question_id,
    clause_question_id,
    route_diagnosis,
    route_step_assert,
)

from tests.agents._judge_helpers import FakeState, _all_pass_answers


class _CannedDecisionModel:
    """最小 ModelAPI：structured_output 直接回一个预先造好的裁决（模拟 LLM 后端填 schema）。"""

    def __init__(self, decision: Any, *, error: Exception | None = None) -> None:
        self.decision = decision
        self.error = error
        self.calls = 0

    def initial_state(self, *, system_prompt: str | None = None) -> Any:
        return FakeState()

    async def structured_output(self, *_: Any, **__: Any) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(parsed=self.decision, metadata={})


def _answers(
    point: str, overrides: Mapping[str, JevAnswer] | None = None
) -> dict[str, JevAnswer]:
    """取某判定点的"一切正常"默认答案，并按 mapping 覆盖若干维度。"""
    base = _all_pass_answers(point, {})
    if overrides:
        base.update(overrides)
    return base


# ────────────────────────────── preflight ──────────────────────────────


def test_preflight_follows_route_when_atomic_judgements_agree():
    d = PREFLIGHT.compose(_answers("preflight"))
    assert d.path == "plan"
    assert d.needs_confirmation < 0.2 and d.risk_level == "low"
    assert d.rationale == "原子判断与路由一致"


def test_preflight_rail_upgrades_direct_to_clarify_when_ambiguous():
    d = PREFLIGHT.compose(
        _answers(
            "preflight",
            {
                Q_PATH: choice_answer(Q_PATH, "direct"),
                Q_AMBIGUITY: noul_answer(Q_AMBIGUITY, 0.95),
            },
        )
    )
    assert d.path == "clarify"
    assert "保守升为 clarify" in d.rationale


def test_preflight_rail_never_downgrades_plan_to_direct():
    """护栏只单向升级谨慎度。

    真机验证过的反例："打开车窗"的 needs_plan 低到 0.22（判断失误），而路由 Choice 看得到
    工具目录、正确选了 plan。早期版本有一条 plan→direct 的降级护栏，会把正确路由改错。
    """
    d = PREFLIGHT.compose(
        _answers(
            "preflight",
            {
                Q_PATH: choice_answer(Q_PATH, "plan"),
                Q_NEEDS_PLAN: noul_answer(Q_NEEDS_PLAN, 0.05),
            },
        )
    )
    assert d.path == "plan"
    assert d.needs_plan == 0.05  # 不一致如实记录，供离线看路由与原子判断的一致率


# ────────────────────────────── plan_audit ──────────────────────────────


def test_plan_audit_passes_only_when_coverage_and_strictness_both_ok():
    assert PLAN_AUDIT.compose(_answers("plan_audit")).passed is True


def test_plan_audit_blocks_loose_success_check():
    loose = PLAN_AUDIT.compose(
        _answers(
            "plan_audit",
            {
                Q_AUDIT_STRICTNESS: noul_answer(Q_AUDIT_STRICTNESS, 0.15),
                Q_AUDIT_GAP: choice_answer(Q_AUDIT_GAP, "check_too_loose"),
            },
        )
    )
    assert loose.passed is False
    assert loose.gap_kind == "check_too_loose"
    assert "success_check 写得太松" in loose.rationale


def test_plan_audit_blocks_missing_goal():
    thin = PLAN_AUDIT.compose(
        _answers(
            "plan_audit",
            {
                Q_AUDIT_COVERAGE: noul_answer(Q_AUDIT_COVERAGE, 0.2),
                Q_AUDIT_GAP: choice_answer(Q_AUDIT_GAP, "missing_explicit_goal"),
            },
        )
    )
    assert thin.passed is False and thin.gap_kind == "missing_explicit_goal"


# ────────────────────────────── step_assert ──────────────────────────────


def _clauses(*verdicts: str) -> dict[str, JevAnswer]:
    """构一个「n 条断言、各给指定三态」的答案集（断言下标 = 传入顺序）。"""
    return {
        clause_question_id(i): choice_answer(clause_question_id(i), verdict)
        for i, verdict in enumerate(verdicts)
    }


def _assert(overrides: Mapping[str, JevAnswer] | None = None):
    return STEP_ASSERT.compose(_answers("step_assert", overrides))


def test_step_assert_passes_when_all_clauses_hold():
    d = _assert(_clauses(CLAUSE_HOLDS, CLAUSE_HOLDS))
    assert d.passed is True
    assert d.diagnosis is None
    assert d.falsified_clauses == [] and d.unsupported_clauses == []
    assert d.rationale == "2 条断言全部成立"


def test_step_assert_unsupported_clause_degrades_instead_of_replanning():
    """判据落到产出给不出的字段上 → 降级接受，不被重规划带走。

    这是本次改动要修的那个 badcase：POI 数据里没有"是否营业"字段，计划却写了"营业中"
    这条断言；jq 时代它表现为 success_check=false，必然触发一次修不好的整体重规划。
    断言验收能把它判成"无证据"，于是产出保留、下游照常，只在回答里说明局限。
    """
    d = _assert(
        _clauses(CLAUSE_HOLDS, CLAUSE_UNSUPPORTED)
        # 判定器其它维度都指向「产出可用、换做法也不必重规划」
        | {
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.9),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.9),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.8),
        }
    )
    assert d.passed is False
    assert d.unsupported_clauses == [1] and d.falsified_clauses == []
    assert isinstance(d.diagnosis, AcceptDegraded)
    assert "第 [2] 条断言" in d.diagnosis.limitation


def test_step_assert_falsified_clause_goes_through_remediation_equation():
    """被证伪才是"真的没做到"：补救裁决复用 diagnosis 的方程（此处判重规划）。"""
    d = _assert(
        _clauses(CLAUSE_HOLDS, CLAUSE_FALSIFIED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    assert d.passed is False
    assert d.falsified_clauses == [1]
    assert isinstance(d.diagnosis, Replan)
    assert "第 [2] 条断言" in d.rationale


def test_step_assert_falsified_can_still_be_unsolvable():
    """合并后并没有丢掉"判无解"这个出口：硬约束 + 数据确实没有 + 无替代做法。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | {
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_DATA_ABSENT),
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.95),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.1),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.1),
        }
    )
    assert isinstance(d.diagnosis, SkipUnsolvable)


def test_step_assert_falsified_outranks_unsupported():
    """既有被证伪又有无证据时，按更严重的来（走补救方程，而不是降级接受）。"""
    d = _assert(
        _clauses(CLAUSE_UNSUPPORTED, CLAUSE_FALSIFIED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    assert d.falsified_clauses == [1] and d.unsupported_clauses == [0]
    assert isinstance(d.diagnosis, Replan)


def test_step_assert_without_clauses_falls_back_to_aggregate_goal():
    """模型漏写断言（或判定器跑在 jq 版计划上）时的兜底：按整体达成度判。"""
    passed = _assert({Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, ASSERT_GOAL_PASS + 0.1)})
    assert passed.passed is True and passed.diagnosis is None

    failed = _assert(
        {
            Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, ASSERT_GOAL_PASS - 0.1),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
        }
    )
    assert failed.passed is False
    assert isinstance(failed.diagnosis, Replan)
    assert "无断言可判" in failed.rationale


# ──────────────────── 判据可靠性分流（A 轴 × 三态 × goal） ────────────────────


def _qualities(*qualities: str) -> dict[str, JevAnswer]:
    """构一个“n 条断言的判据可靠性”答案集（与 :func:`_clauses` 正交，可叠加）。"""
    return {
        clause_quality_question_id(i): choice_answer(clause_quality_question_id(i), q)
        for i, q in enumerate(qualities)
    }


def test_invented_clause_is_ignored_and_goal_decides_achieved():
    """判据是计划自设的（用户只说“找一家”，计划写“至少5家”）→ 忽略断言结论，看 goal。

    goal 达成 → **干净放行**（passed=True）：断言的失败本就不该变成对用户的披露。
    """
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | _qualities(QUALITY_INVENTED)
        # 实测：判定器对“被证伪”很确信（0.94），所以能救这条的只能是 A 轴
        | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.7)}
    )
    assert d.passed is True and d.diagnosis is None
    assert d.assert_verdict_ignored is True
    assert d.falsified_clauses == [0]  # 证据仍如实保留，便于事后校准
    assert "计划自设" in d.rationale


def test_invented_clause_in_goal_gray_zone_degrades():
    """goal 落在灰区（FLOOR~PASS）时不静默放行：降级 + 披露，但不重规划。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | _qualities(QUALITY_INVENTED)
        | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, ASSERT_GOAL_FLOOR + 0.1)}
    )
    assert d.passed is False
    assert d.assert_verdict_ignored is True
    assert isinstance(d.diagnosis, AcceptDegraded)
    assert "灰区" in d.rationale


def test_invented_clause_with_low_goal_goes_to_remediation():
    """防洗白：判据是自设的，但 goal 低于下限 → 仍需补救（不拿“判据不靠谱”当借口）。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | _qualities(QUALITY_INVENTED)
        | {
            Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, ASSERT_GOAL_FLOOR - 0.1),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
        }
    )
    assert d.passed is False
    assert d.assert_verdict_ignored is True
    assert isinstance(d.diagnosis, Replan)


def test_unverifiable_clause_degrades_without_consulting_goal():
    """判不了（判据不可判）→ 既不当失败、也**不拿 goal 当依据**：goal 同样被这条断言带偏
    （实测 nav 那条：无证据 conf=0.79，goal 只敢给 0.40）。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | _qualities(QUALITY_UNVERIFIABLE)
        | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.2)}  # 低，但不该被参考
    )
    assert d.passed is False
    assert d.assert_verdict_ignored is True
    assert isinstance(d.diagnosis, AcceptDegraded)
    assert "无法用产出判定" in d.diagnosis.limitation


def test_low_confidence_verdict_counts_as_unreliable_even_if_grounded():
    """判据合法但判定器只有 0.4 把握（真·两可）→ 同样不当失败依据（证据支）。"""
    qid = clause_question_id(0)
    d = _assert(
        {qid: choice_answer(qid, CLAUSE_FALSIFIED, confidence=0.4, probabilities={CLAUSE_FALSIFIED: 0.4})}
        | _qualities(QUALITY_GROUNDED)
        | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.95)}
    )
    assert d.passed is False and d.assert_verdict_ignored is True
    assert isinstance(d.diagnosis, AcceptDegraded)


def test_grounded_confident_clause_still_fails():
    """有“用户明说且判得确信”的断言被证伪 → 真失败，不因 _assert_verdict_ignored 机制溜走。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | _qualities(QUALITY_GROUNDED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    assert d.passed is False and d.assert_verdict_ignored is False
    assert isinstance(d.diagnosis, Replan)


def test_unknown_quality_is_treated_as_reliable():
    """保守约定：quality 缺失（LLM 后端漏填）不当“不可靠”，否则一个字段缺失就能把断言关掉。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    assert d.clause_quality == [QUALITY_UNKNOWN]
    assert d.unreliable_clauses == []
    assert d.assert_verdict_ignored is False
    assert isinstance(d.diagnosis, Replan)


def test_one_reliable_falsified_clause_beats_an_invented_one():
    """混合情形：自设判据 + 用户判据同时被证伪 → 按真失败（全有或全无，不给洗白留缝）。"""
    d = _assert(
        _clauses(CLAUSE_FALSIFIED, CLAUSE_FALSIFIED)
        | _qualities(QUALITY_INVENTED, QUALITY_GROUNDED)
        | {
            Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.95),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
        }
    )
    assert d.assert_verdict_ignored is False
    assert isinstance(d.diagnosis, Replan)


def test_invented_and_unverifiable_mix_takes_the_conservative_branch():
    """都是“不可靠”，但一支属于“判据不适用”、一支属于“判不了”→ 取更保守的证据支：

    因为“判不了”意味着 goal 也不可信（同样被这条判不了的断言带偏），不该拿它当依据。
    """
    d = _assert(
        _clauses(CLAUSE_FALSIFIED, CLAUSE_FALSIFIED)
        | _qualities(QUALITY_INVENTED, QUALITY_UNVERIFIABLE)
        | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.95)}  # 高，但不该被参考
    )
    assert isinstance(d.diagnosis, AcceptDegraded)
    assert "无法用产出判定" in d.diagnosis.limitation


def test_missing_certainty_is_not_treated_as_uncertain():
    """后端不给把握（confidence=None）≠ 判不准：只有**显式**低于阈值的把握才进证据支，

    否则一个字段漏填就能把真失败变成降级接受。
    """
    qid = clause_question_id(0)
    d = _assert(
        {qid: JevAnswer(id=qid, kind="choice", choice=CLAUSE_FALSIFIED, confidence=None)}
        | _qualities(QUALITY_GROUNDED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    assert d.clause_certainty == [1.0]
    assert d.assert_verdict_ignored is False
    assert isinstance(d.diagnosis, Replan)


def test_certainty_is_recorded_for_calibration():
    """把握落进裁决（可统计“多少失败是因为判不准”）。"""
    qid = clause_question_id(0)
    d = _assert(
        {qid: choice_answer(qid, CLAUSE_HOLDS, confidence=0.83)} | _qualities(QUALITY_GROUNDED)
    )
    assert d.clause_certainty == [0.83]


def test_goal_question_is_assertion_blind():
    """B 轴必须与断言解耦：实测那条 case 的 goal 被计划自设的「至少5家」反向拉到 0.55，

    卡在灰区、本可干净放行的一步只落到降级披露。这是提示词回归护栏。
    """
    questions = STEP_ASSERT.questions(
        {"step": {"step_goal": "找一家评分高的烤鸭店", "assertion": ["至少返回5家"]}}
    )
    text = questions[Q_ASSERT_GOAL].instructions
    assert "不要参考本步自己声明的 assertion" in text
    assert "用户原始请求" in text


# ──────────────────── 两条后端的对称性（共享路由 + 幂等） ────────────────────


def _llm_style(**facts: Any):
    """造一个“LLM 后端直填 schema”形态的裁决（含有它自己的 passed/diagnosis）。"""
    facts.setdefault("goal_achieved", 0.95)
    return StepAssertDecision(**facts)


def test_llm_style_decision_gets_the_same_routing_as_jev():
    """同一组事实下，LLM 直填的裁决与 Jev 组合方程得到**同一个结果**。

    这里刻意让模型自己判错（判了失败 + 重规划），验证规则由代码接管、与后端无关。
    """
    facts = dict(
        falsified_clauses=[0],
        clause_quality=[QUALITY_INVENTED],
        clause_certainty=[0.94],
        goal_achieved=0.95,
    )
    llm = route_step_assert(
        _llm_style(**facts, passed=False, diagnosis=Replan(failed_assumption="x", retry_direction="y"))
    )
    jev = _assert(_clauses(CLAUSE_FALSIFIED) | _qualities(QUALITY_INVENTED))

    assert (llm.passed, llm.assert_verdict_ignored) == (jev.passed, jev.assert_verdict_ignored)
    assert llm.passed is True and llm.diagnosis is None


def test_llm_style_unsupported_clause_is_normalized_to_degrade():
    """无证伪、只有无证据 → 降级接受：这条规则也不允许 LLM 后端自己选重规划。"""
    llm = route_step_assert(
        _llm_style(
            passed=False,
            unsupported_clauses=[1],
            clause_quality=[QUALITY_GROUNDED, QUALITY_GROUNDED],
            diagnosis=Replan(failed_assumption="x", retry_direction="y"),
        )
    )
    assert isinstance(llm.diagnosis, AcceptDegraded)
    assert "第 [2] 条断言" in llm.diagnosis.limitation


def test_llm_style_failure_without_clause_evidence_falls_back_to_goal():
    """判失败但一条逐条证据都没报（模型漏填）→ 按“无断言可判”的同一兜底看 goal。

    否则模型只要不报“哪条断言失败”，就能绕开整套路由规则。
    """
    achieved = route_step_assert(_llm_style(passed=False, goal_achieved=0.9))
    assert achieved.passed is True and achieved.assert_verdict_ignored is True

    failed = route_step_assert(_llm_style(passed=False, goal_achieved=0.3))
    assert failed.passed is False and failed.assert_verdict_ignored is True


def test_route_is_idempotent():
    """幂等：Jev 路径已经把规则算进去了，再走一次不能变形（两条后端共用同一个函数的依据）。"""
    cases = [
        _assert(_clauses(CLAUSE_HOLDS)),
        _assert(_clauses(CLAUSE_FALSIFIED) | _qualities(QUALITY_INVENTED)),
        _assert(_clauses(CLAUSE_FALSIFIED) | _qualities(QUALITY_UNVERIFIABLE)),
        _assert(_clauses(CLAUSE_UNSUPPORTED)),
        _assert(
            _clauses(CLAUSE_FALSIFIED)
            | _qualities(QUALITY_GROUNDED)
            | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
        ),
    ]
    for decision in cases:
        assert route_step_assert(decision) == decision


@pytest.mark.anyio
async def test_llm_judge_applies_the_shared_route():
    """钩子本身：LlmJudge 解析后立刻应用 point.route（未接钩子时这条规则就是 Jev 专属）。"""
    canned = _llm_style(
        passed=False,
        falsified_clauses=[0],
        clause_quality=[QUALITY_INVENTED],
        clause_certainty=[0.9],
        goal_achieved=0.9,
        diagnosis=Replan(failed_assumption="x", retry_direction="y"),
    )
    judge = LlmJudge(_CannedDecisionModel(canned))
    outcome = await judge.decide(Point.STEP_ASSERT, {"judge_point": "step_assert", "step": {"assertion": ["至少返回5家"]}})

    assert outcome.decision.passed is True
    assert outcome.decision.assert_verdict_ignored is True


# ────────────────── 诊断三选一的对齐（不再由 LLM 自己挑） ──────────────────


def _stub_atoms(**overrides: Any) -> DiagnosisDecision:
    """造一个“LLM 直填原子事实”形态的诊断信封（decision 留空、由方程填）。"""
    defaults: dict[str, Any] = {
        "constraint_is_user_requirement": 0.2,
        "alternative_can_satisfy": 0.9,
        "output_still_usable": 0.9,
        "downstream_blocking": 0.1,
        "failure_cause": CAUSE_PLAN_MISTAKE,
    }
    defaults.update(overrides)
    return DiagnosisDecision(**defaults)


def _jev_diagnosis(hard: float, retry: float, usable: float, blocking: float, cause: str):
    return DIAGNOSIS.compose(
        _answers(
            "diagnosis",
            {
                Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, hard),
                Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, retry),
                Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, usable),
                Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, blocking),
                Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, cause),
            },
        )
    )


@pytest.mark.parametrize(
    ("hard", "retry", "usable", "blocking", "cause"),
    [
        (0.2, 0.9, 0.9, 0.1, CAUSE_PLAN_MISTAKE),  # ① 可修 → replan
        (0.1, 0.9, 0.1, 0.9, CAUSE_PARAM_ERROR),  # ① 写法问题即使约束硬也 replan
        (0.9, 0.1, 0.1, 0.9, CAUSE_DATA_ABSENT),  # ② 客观不可得 + 无替代 → 无解
        (0.9, 0.1, 0.0, 0.9, CAUSE_DATA_ABSENT),  # ②（usable 更低）→ 无解
        (0.2, 0.1, 0.95, 0.1, CAUSE_PLAN_MISTAKE),  # ③ 产出够用且不阻塞 → 降级
        (0.95, 0.1, 0.5, 0.9, CAUSE_TOOL_UNSUPPORTED),  # ④ 硬约束 + 没戏 → 无解
        (0.5, 0.5, 0.5, 0.5, CAUSE_PLAN_MISTAKE),  # ⑤ 灰区 → 保守重试
    ],
)
def test_diagnosis_outcome_is_identical_across_backends(hard, retry, usable, blocking, cause):
    """同一组原子事实，Jev 方程与 LLM 直填+route 必须给出同一个 outcome 与同一段理由。"""
    jev = _jev_diagnosis(hard, retry, usable, blocking, cause)
    llm = route_diagnosis(
        _stub_atoms(
            constraint_is_user_requirement=hard,
            alternative_can_satisfy=retry,
            output_still_usable=usable,
            downstream_blocking=blocking,
            failure_cause=cause,
            decision=Replan(failed_assumption="x", retry_direction="y"),  # 模型自己的抢答
        )
    )
    assert type(llm.decision) is type(jev.decision)
    assert llm.decision == jev.decision  # 连文案都来自同一份模板
    assert llm.rationale == jev.rationale


def test_route_diagnosis_ignores_the_model_own_pick():
    """模型自己挑的 outcome 不作数：事实指向降级接受，就得是降级接受。"""
    llm = route_diagnosis(
        _stub_atoms(
            constraint_is_user_requirement=0.2,
            alternative_can_satisfy=0.1,
            output_still_usable=0.95,
            downstream_blocking=0.1,
            decision=SkipUnsolvable(unsolvable_reason="我自己判无解"),
        )
    )
    assert isinstance(llm.decision, AcceptDegraded)
    assert "我自己判无解" not in llm.decision.limitation


def test_route_diagnosis_is_idempotent():
    assert route_diagnosis(route_diagnosis(_stub_atoms())) == route_diagnosis(_stub_atoms())


def test_step_assert_derives_remediation_from_atoms():
    """断言验收里的补救裁决也走方程：LLM 抢先填的 replan 会被事实推翻。"""
    d = route_step_assert(
        _llm_style(
            passed=False,
            falsified_clauses=[0],
            clause_quality=[QUALITY_GROUNDED],
            clause_certainty=[0.95],
            goal_achieved=0.9,
            diagnosis_atoms=DiagnosisAtoms(
                constraint_is_user_requirement=0.95,
                alternative_can_satisfy=0.1,
                output_still_usable=0.05,
                downstream_blocking=0.9,
                failure_cause=CAUSE_DATA_ABSENT,
            ),
            diagnosis=Replan(failed_assumption="抢答", retry_direction="抢答"),
        )
    )
    assert isinstance(d.diagnosis, SkipUnsolvable)


@pytest.mark.anyio
async def test_llm_judge_routes_the_diagnosis_point_too():
    judge = LlmJudge(_CannedDecisionModel(_stub_atoms()))
    outcome = await judge.decide(Point.DIAGNOSIS, {"judge_point": "diagnosis"})
    assert outcome.decision.decision is not None
    assert isinstance(outcome.decision.decision, Replan)  # 默认事实：可修 → replan


# ────────────────────────────── diagnosis ──────────────────────────────


def _diag(overrides: Mapping[str, JevAnswer] | None = None):
    return DIAGNOSIS.compose(_answers("diagnosis", overrides))


def test_diagnosis_replans_when_plan_assumption_was_wrong():
    d = _diag({Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)})
    assert isinstance(d.decision, Replan)
    assert "重试" in d.decision.retry_direction


def test_diagnosis_replans_on_fixable_writing_error_even_if_constraint_is_hard():
    d = _diag(
        {
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.95),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PARAM_ERROR),
        }
    )
    assert isinstance(d.decision, Replan)


def test_diagnosis_declares_unsolvable_when_hard_data_absent_and_no_alternative():
    d = _diag(
        {
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.95),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.1),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_DATA_ABSENT),
        }
    )
    assert isinstance(d.decision, SkipUnsolvable)
    assert "确实查不到所需信息" in d.decision.unsolvable_reason


def test_diagnosis_prefers_replan_when_another_approach_might_work():
    """真机反例："指定歌手的歌搜不到"实测 hard≈0.68 / retry≈0.9。

    两个答案同时成立时应先重试（换个工具真可能找到），而不是把可解问题错报成无解——
    真的反复失败会由轮次闸门 + 跨轮证据收敛。
    """
    d = _diag(
        {
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.68),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.9),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.12),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_DATA_ABSENT),
        }
    )
    assert isinstance(d.decision, Replan)


def test_diagnosis_accepts_degraded_when_output_is_usable_and_not_blocking():
    d = _diag(
        {
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.1),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.9),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.1),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_EXEC_FAILED),
        }
    )
    assert isinstance(d.decision, AcceptDegraded)
    assert "仅部分达成" in d.decision.limitation


def test_diagnosis_declares_unsolvable_when_hard_and_no_alternative():
    d = _diag(
        {
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.95),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.05),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.9),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.9),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_EXEC_FAILED),
        }
    )
    assert isinstance(d.decision, SkipUnsolvable)


def test_diagnosis_gray_zone_takes_conservative_replan_and_records_low_confidence():
    d = _diag(
        {
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.5),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.5),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.5),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.5),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_EXEC_FAILED),
        }
    )
    assert isinstance(d.decision, Replan)
    assert GRAY_ZONE in d.rationale
    assert d.confidence == 0.0  # 全维两可 → 置信度如实为 0


# ────────────────────────────── round_gate ──────────────────────────────


def test_round_gate_continues_when_repair_still_promising():
    assert ROUND_GATE.compose(_answers("round_gate")).action == "continue"


def test_round_gate_stops_when_hopeless():
    d = ROUND_GATE.compose(
        _answers("round_gate", {Q_GATE_WORTH: noul_answer(Q_GATE_WORTH, 0.05)})
    )
    assert d.action == "stop"


def test_round_gate_marks_unsolvable_on_repeated_same_root_cause():
    d = ROUND_GATE.compose(
        _answers(
            "round_gate",
            {
                Q_GATE_WORTH: noul_answer(Q_GATE_WORTH, 0.05),
                Q_GATE_SAME: noul_answer(Q_GATE_SAME, 0.95),
            },
        )
    )
    assert d.action == "mark_unsolvable"


# ────────────────────────────── finish ──────────────────────────────


def test_finish_confidence_combines_coverage_fabrication_and_disclosure():
    good = FINISH.compose(_answers("finish"))
    assert good.goal_coverage == 1.0
    assert good.confidence == combine_finish_confidence(
        goal_coverage=1.0, fabricated=good.fabricated, disclosed=good.disclosed
    )
    assert good.confidence > 0.9 and good.outcome == "success"


def test_finish_confidence_collapses_when_answer_is_fabricated():
    fabricated = FINISH.compose(
        _answers(
            "finish",
            {
                Q_FIN_FABRICATED: noul_answer(Q_FIN_FABRICATED, 1.0),
                Q_FIN_OUTCOME: choice_answer(Q_FIN_OUTCOME, "partial"),
            },
        )
    )
    assert fabricated.confidence == 0.0  # 满分覆盖但说了假话 → 置信度必须塌到 0
    assert "虚构" in fabricated.rationale


def test_finish_normalizes_score_level_into_coverage():
    half = FINISH.compose(
        _answers("finish", {Q_FIN_COVERAGE: score_answer(Q_FIN_COVERAGE, 1.0)})
    )
    assert half.goal_coverage == 1.0 / 3  # 4 档量表，分 1 → 覆盖 1/3


def test_finish_disclosure_scales_confidence_but_not_to_zero():
    quiet = FINISH.compose(
        _answers(
            "finish",
            {
                Q_FIN_COVERAGE: score_answer(Q_FIN_COVERAGE, 1.0),
                Q_FIN_DISCLOSED: noul_answer(Q_FIN_DISCLOSED, 0.0),
            },
        )
    )
    assert quiet.confidence == combine_finish_confidence(
        goal_coverage=1 / 3, fabricated=quiet.fabricated, disclosed=0.0
    )
    assert 0 < quiet.confidence < 1 / 3


# ────────────── LLM 后端的失败策略：在实现内部转保守裁决 ──────────────


@pytest.mark.anyio
async def test_llm_judge_turns_a_failed_call_into_a_conservative_verdict():
    """调用失败不冒出到 core：转保守裁决，并把 backend 标成 llm:fallback（可归因）。"""
    judge = LlmJudge(_CannedDecisionModel(None, error=RuntimeError("llm down")))

    preflight = await judge.decide(Point.PREFLIGHT, {"judge_point": "preflight"})
    audit = await judge.decide(Point.PLAN_AUDIT, {"judge_point": "plan_audit"})
    gate = await judge.decide(Point.ROUND_GATE, {"judge_point": "round_gate"})
    finish = await judge.decide(Point.FINISH, {"judge_point": "finish"})

    assert preflight.backend == "llm:fallback" and preflight.decision.path == "plan"
    assert audit.decision.passed is True  # 判定器故障不把计划判死
    assert gate.decision.action == "continue"  # 不因故障提前止损
    assert finish.decision.assessed is False  # 不编造置信度
    assert "llm down" in finish.decision.rationale


@pytest.mark.anyio
async def test_llm_judge_step_assert_failure_is_a_conservative_replan():
    judge = LlmJudge(_CannedDecisionModel(None, error=RuntimeError("llm down")))

    outcome = await judge.decide(Point.STEP_ASSERT, {"judge_point": "step_assert"})

    assert outcome.decision.passed is False
    assert outcome.decision.diagnosis is not None
    assert outcome.decision.diagnosis.outcome == "replan"
