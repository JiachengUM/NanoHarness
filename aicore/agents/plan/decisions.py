"""各判定点的裁决模型：把控（judge）与 core 之间的**契约**。

core 只依赖本模块（纯数据）与 :mod:`aicore.agents.plan.judge` 的协议，不依赖任何具体实现；
所有实现（Jev / LLM / 测试替身）都返回这里的类型。

设计约束：**同一判定点的两种后端必须产出同一个类型**，否则 core/runner 需要为"谁来判"
分支，A/B 对比也就无法在同一根流水线上跑。所以这里定义的类型同时充当：

- Jev 后端：``judges/points.py`` 的组合方程（代码组合原子答案）的返回值；
- LLM 后端：``structured_output`` 的 ``output_type``。

字段取舍遵循两条规则：
1. **判定器只填概率/标签，不填叙事**：自由文本（rationale）是证据，不参与控制流；
   控制流只读数值与枚举，保证可复现、可统计。
2. **代码能推的不要判定器填**：例如 ``execution_outcome`` 的位置由 core 按 ``errors``
   的 source 直接推（plan.schema/plan.logic → not_executed；step.* → partial），
   不占问题预算也不引入非确定性。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aicore.agents.plan.diagnosis import AcceptDegraded, Replan, SkipUnsolvable

__all__ = [
    "PreflightDecision",
    "PlanAuditDecision",
    "DiagnosisAtoms",
    "StepAssertDecision",
    "DiagnosisDecision",
    "RoundGateDecision",
    "FinishDecision",
    "DiagnosisOutcome",
]

# 复用 diagnosis.py 的三出口：判定器的裁决必须能直接喂给 runner 的既有路由。
DiagnosisOutcome = Replan | SkipUnsolvable | AcceptDegraded

# 断言判据的**可靠性**（A 轴）：与“成立/被证伪/无证据”三态**正交**——
# 三态回答“产出对这条断言是什么结论”，本轴回答“这条断言本身值不值得当判据”。
# 分开的理由：用户只说“找一家”而计划断言“至少返回5家”时，三态只会说“产出不符”
# （实测判定器以 conf=0.94 确信，且它没判错），“这是计划自设的”只能靠补救诊断里那个
# A-or-B 的 Noul 去猜（实测 0.68 → 灰区 → 白花一轮）。提成显式标签后，路由才能在
# “判据不适用（→ 忽略断言，改看 goal）”与“判不准（→ 不失败、也不咨询 goal）”之间分流。
ClauseQuality = Literal["grounded", "invented", "unverifiable", "unknown"]

CLAUSE_QUALITY_TEXT: dict[str, str] = {
    "grounded": "用户请求里有依据，或用产出/上游产出能判真假",
    "invented": "用户请求里没有这个数量/阈值/口径，是计划自己设的",
    "unverifiable": "判据落在本步产出给不出的东西上，产出再好也判不了",
    "unknown": "判定器未给出（LLM 后端漏填时的兜底）",
}

# 判定点的名字，用于事件与 state 的 judge_point 字段。
JudgePointName = Literal["preflight", "plan_audit", "step_assert", "diagnosis", "round_gate", "finish"]


class PreflightDecision(BaseModel):
    """入口分流：这条请求该走 plan、直接回答，还是先澄清。"""

    path: Literal["plan", "direct", "clarify"] = Field(
        description="plan=按 DAG 规划执行；direct=无需工具直接回答；clarify=关键信息缺失，先问用户。"
    )
    needs_plan: float = Field(default=0.0, description="是否必须调用工具（0-1）。")
    blocking_ambiguity: float = Field(default=0.0, description="信息缺失是否严重到任何计划都只能猜（0-1）。")
    goal_count: Literal["one", "two", "three_plus"] = Field(
        default="one", description="独立子目标的数量档位。"
    )
    risk_score: float = Field(default=0.0, description="错误执行的后果程度（量表分，档位见 criteria）。")
    risk_level: Literal["low", "medium", "high"] = Field(default="low")
    needs_confirmation: float = Field(default=0.0, description="执行前是否需要用户确认（0-1）。")
    confidence: float | None = Field(default=None, description="路由分布的尖锐度。")
    rationale: str = Field(default="", description="判断依据，仅供 trace。")

    @property
    def route_confidence(self) -> float:
        return 0.0 if self.confidence is None else self.confidence


class PlanAuditDecision(BaseModel):
    """计划语义审计：静态结构合法之外，这个计划"按字面完美执行"能否满足用户请求。"""

    passed: bool = Field(description="是否允许进入执行。")
    coverage: float = Field(default=0.0, description="完美执行后对用户诉求的覆盖度（0-1）。")
    check_strictness: float = Field(default=0.0, description="success_check 的严格度：过低会放过未达成（0-1）。")
    gap_kind: Literal[
        "none",
        "missing_explicit_goal",
        "missing_implicit_need",
        "constraint_mismatch",
        "check_too_loose",
        "dependency_invalid",
    ] = Field(default="none", description="最主要的一处缺口类型。")
    risk_level: Literal["low", "medium", "high"] = Field(default="low")
    needs_confirmation: float = Field(default=0.0, description="执行前是否需要用户确认（0-1）。")
    confidence: float | None = Field(default=None)
    rationale: str = Field(default="")


class DiagnosisAtoms(BaseModel):
    """补救裁决的**原子事实**（两条后端都填这些；outcome 由代码算）。

    为什么把三选一从模型手里收到代码：对齐之前 Jev 臂的 outcome 是方程算的、LLM 臂的是
    模型直接挑的——同一份实验里两条后端的控制流不同，A/B 结果无法归因。现在两条后端都只
    提供事实，``replan / skip_unsolvable / accept_degraded`` 一律由组合方程给出。

    数值语义（两侧一致，LLM 请按同一把尺子给）：
    ``constraint_is_user_requirement``——未满足的那条约束是用户请求里明说的（高）还是计划
    自己操作化时猜的（低）；``alternative_can_satisfy``——换一条仍忠于用户意图的做法能否
    满足；``output_still_usable``——产出对用户/下游还够不够用；``downstream_blocking``——
    下游是不是真的依赖"未满足的那个方面"。0.5 = 说不清。
    """

    constraint_is_user_requirement: float = Field(
        default=0.0, description="未满足的约束是否用户请求里明说的（0-1）。"
    )
    alternative_can_satisfy: float = Field(
        default=0.0, description="换一条忠于用户意图的做法能否满足该约束（0-1）。"
    )
    output_still_usable: float = Field(
        default=0.0, description="产出对用户或下游是否仍够用（0-1）。"
    )
    downstream_blocking: float = Field(
        default=0.0, description="下游是否真依赖未满足的那个方面（0-1）。"
    )
    failure_cause: Literal[
        "plan_assumption_wrong",
        "params_or_ref_wrong",
        "data_does_not_exist",
        "tool_cannot_do_it",
        "tool_execution_failed",
    ] = Field(
        default="plan_assumption_wrong",
        description="失败根因：计划猜错 / 入参引用写错 / 数据确实没有 / 工具做不到 / 执行报错。",
    )


class StepAssertDecision(BaseModel):
    """step 断言验收 + 补救裁决：一次判定同时给出"达成没有"与"没达成怎么办"。

    达成判据是该步自声明的断言（不是 jq 表达式），逐条判三态：

    - ``falsified_clauses``：被产出**证伪**的断言下标——真的没做到，交补救裁决；
    - ``unsupported_clauses``：产出既没支持也没反驳的断言下标（字段缺失/结果为空）——
      判不了不等于产出错了：不重规划也不宣称达成，落成"降级接受"（产出保留、下游照常、
      最终回答如实说明这条断言无法确认）。

    三态里刻意保留"无证据"，是因为 jq 判据最常误伤的不是"产出不合格"，而是
    "判据落到产出给不出的字段上"（实测：POI 数据没有"是否营业"字段，计划却用
    ``is_open == true`` 验收它）——那种情况下产出完全正常，重规划永远修不好。

    ``diagnosis`` 仅在 ``passed=False`` 时非 None；其语义与 :data:`DiagnosisOutcome` 一致，
    由同一次判定的原子答案组合（JEV）或判定器直接给出（LLM）。
    """

    passed: bool = Field(description="本步是否达成（所有断言都成立才算达成）。")
    goal_achieved: float = Field(
        default=0.0, description="综合达成度（0-1）；只作证据与校准，不直接当门（门是断言）。"
    )
    falsified_clauses: list[int] = Field(
        default_factory=list, description="被产出证伪的断言下标（从 0 起）。"
    )
    clause_quality: list[ClauseQuality] = Field(
        default_factory=list,
        description=(
            "逐条断言的判据可靠性（下标与 assertion 对齐，与三态正交）："
            "invented=用户没要求、计划自设的数量/阈值；unverifiable=本步产出判不了。"
        ),
    )
    clause_certainty: list[float] = Field(
        default_factory=list,
        description=(
            "判定器对每条断言结论（三态）的把握，0~1，下标与 assertion 对齐。"
            "低于阈值时那条结论不能当失败依据（真·两可）。注：两条后端这个数的**统计含义不同**"
            "（Jev=组合分布尖锐度；LLM=自报），所以它只当“两可”的安全网，"
            "常规分支靠 clause_quality 与三态标签。"
        ),
    )
    unsupported_clauses: list[int] = Field(
        default_factory=list, description="产出无法判定真假的断言下标（从 0 起）。"
    )
    assert_verdict_ignored: bool = Field(
        default=False,
        description=(
            "**被证伪的**断言结论被判为不可用（判据自设，或判定器对结论两可），"
            "因而未作为成败依据；只监控这一支：常用说明断言系统在退化成“只看 goal”的弱判定。"
        ),
    )
    diagnosis_atoms: DiagnosisAtoms | None = Field(
        default=None,
        description=(
            "需要补救时的原子事实（两条后端都填）：Jev 从原子答案取，LLM 自己填。"
            "``diagnosis`` 的三选一由代码按它算，不要自己抢答。"
        ),
    )

    @property
    def unreliable_clauses(self) -> list[int]:
        """判据本身不可靠的断言下标（计划自设 / 本步判不了）。

        与 ``falsified_clauses`` 正交：这里说的是“这条断言不该当失败依据”，
        不是“产出没做到”——两者交叉才是完整的判定面（见 runner 的质量门）。
        """
        return [
            index
            for index, quality in enumerate(self.clause_quality)
            if quality in ("invented", "unverifiable")
        ]
    output_usable: float = Field(
        default=0.0, description="产出对用户/下游是否够用（0-1）。"
    )
    confidence: float | None = Field(default=None)
    rationale: str = Field(default="")
    diagnosis: DiagnosisOutcome | None = Field(
        default=None,
        description=(
            "passed=False 时的补救裁决（replan / skip_unsolvable / accept_degraded）："
            "**由代码按 diagnosis_atoms 经组合方程算出**，判定器只填事实。"
        ),
    )


class DiagnosisDecision(DiagnosisAtoms):
    """补救诊断信封（= 原子事实 + 代码算出的裁决）。

    两条后端产出同一个类型：

    - Jev 后端：``decision`` 由组合方程从 Noul 答案算；
    - LLM 后端：模型填原子字段（及可选 rationale），``route_diagnosis`` 用同一方程算 ``decision``。

    ``decision`` 默认 None 是为了让 LLM 的结构化输出有“只填事实”的合法形态；
    下游拿到 None 说明判定器没填事实，调用方按保守默认处理（同原实现的兼容路径）。
    """

    decision: DiagnosisOutcome | None = Field(
        default=None, description="三选一裁决（由组合方程填，判定器不要填）。"
    )
    confidence: float | None = Field(
        default=None,
        description="判定置信度（Jev=分布尖锐度；LLM 可自报，仅作对比）。",
    )
    rationale: str = Field(default="", description="判断依据，仅供 trace。")


class RoundGateDecision(BaseModel):
    """轮次闸门：本轮有错，还值不值得再花一轮重规划。"""

    action: Literal["continue", "stop", "mark_unsolvable"] = Field(
        description="continue=再修一轮；stop=止损、带当前结果出答案；mark_unsolvable=多轮无解，如实说明无法完成。"
    )
    worth_another_round: float = Field(default=0.0, description="再重规划一轮成功的机会（0-1）。")
    same_root_cause: float = Field(default=0.0, description="本轮失败与历史失败是否同一根因（0-1）。")
    confidence: float | None = Field(default=None)
    rationale: str = Field(default="")


class FinishDecision(BaseModel):
    """收尾评估：答案达成到什么程度、有没有虚构、置信度多少。"""

    goal_coverage: float = Field(default=0.0, description="对用户原始诉求的覆盖度（0-1）。")
    fabricated: float = Field(default=0.0, description="回答是否声称完成了实际未完成的事（0-1）。")
    disclosed: float = Field(default=0.0, description="存在未达成时是否如实说明（0-1）。")
    outcome: Literal["success", "partial", "not_executed", "clarify"] = Field(
        default="success", description="本次执行的结局归类。"
    )
    ask_user_worth: float = Field(default=0.0, description="是否值得回问用户或给替代方案（0-1）。")
    confidence: float | None = Field(
        default=None, description="答案置信度；Jev 由组合方程算，LLM 后端留空由 core 兜底公式算。"
    )
    confidence_reported: float | None = Field(
        default=None, description="判定器自报的置信度（LLM 用，仅作对比）。"
    )
    assessed: bool = Field(
        default=True,
        description=(
            "这次评估是否真的做成了。判定器不可用时置 False：此时不得拿默认字段去算置信度"
            "（那会凭空造出一个 0.0 的结论），core 会退回「没有收尾评估」的行为。"
        ),
    )
    rationale: str = Field(default="")

    def effective_confidence(self, fallback: float | None = None) -> float | None:
        """取置信度：优先组合方程算出的 ``confidence``，否则由三个数值字段兜底计算。"""
        if self.confidence is not None:
            return self.confidence
        if fallback is not None:
            return fallback
        return combine_finish_confidence(
            goal_coverage=self.goal_coverage,
            fabricated=self.fabricated,
            disclosed=self.disclosed,
        )


def combine_finish_confidence(
    *, goal_coverage: float, fabricated: float, disclosed: float
) -> float:
    """答案置信度的组合方程（两条后端共用，故放在模型层而非某个后端里）。

    ``覆盖度 × (1 - 虚构) × 如实说明的折减``：三个因子对应三类独立的失败模式——
    没做完、谎称做完、做不完但不说。任一项塌掉，整体置信度就该塌掉。
    """
    coverage = _clamp(goal_coverage)
    honesty = 1.0 - _clamp(fabricated)
    disclosure = 0.5 + 0.5 * _clamp(disclosed)
    return round(coverage * honesty * disclosure, 4)


def _clamp(value: Any) -> float:
    """把判定器给的数收进 [0, 1]（外部数值不可全信，越界即视为边界值）。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return min(1.0, max(0.0, number))
