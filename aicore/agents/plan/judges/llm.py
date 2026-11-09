"""LLM 后端：同一份裁剪后的 state，一次结构化输出直接产出裁决。

与 Jev 后端的差别只有两处，且都是刻意的：

1. **数值来源**：Jev 给校准概率（``answers`` 里带完整分布，可离线做校准统计），LLM 只能自报，
   所以它的 outcome 里 ``answers`` 为空。这是 A/B 的自变量本身，不是实现缺陷。
2. **失败策略**：Jev 直接抛错；LLM 在**本实现内部**转成保守裁决（``backend="llm:fallback"``），
   照原实现"判定不可用 → 保守处理"的行为。core / runner 因此不需要任何 try/except，
   也不需要知道谁会失败、失败怎么办。

共享的**规则性出口**（那些"两条后端必须一致、不该交给判定器自由发挥"的裁决规则，例如"判据
不可用 → 不按断言的结论定成败"）由 :func:`~aicore.agents.plan.judges.points.route_*` 提供：
LLM 后端在解析后立即应用，Jev 后端的组合方程末尾调用同一个函数（``route(compose(a)) == compose(a)``
有测试钉住）。这条也不动 A/B 的自变量——被收到代码里的只是规则性出口。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Iterable

from pydantic import BaseModel

from aicore.models.model_api import ModelAPI, ModelCallParams, UserMessage

from aicore.agents.plan.criterion import KIND_ASSERTION, CriterionKind
from aicore.agents.plan.decisions import (
    DiagnosisDecision,
    FinishDecision,
    PlanAuditDecision,
    PreflightDecision,
    RoundGateDecision,
    StepAssertDecision,
)
from aicore.agents.plan.diagnosis import Replan
from aicore.agents.plan.judge import ALL_POINTS, JudgeOutcome, Point
from aicore.agents.plan.judges.points import ALL_POINTS as POINT_TABLE
from aicore.agents.plan.trim import render_state

__all__ = ["LlmJudge", "LlmJudgeError"]


class LlmJudgeError(RuntimeError):
    """LLM 判定器的结构化输出解析失败（内部转保守裁决，不冒出本类）。"""


class LlmJudge:
    """LLM 判定器（注入的另一份把控实现）。

    ``points`` 与 :class:`~aicore.agents.plan.judges.jev.JevJudge` 同义：默认全部判定点。
    """

    name = "llm"
    criterion: CriterionKind = KIND_ASSERTION

    def __init__(
        self,
        model_api: ModelAPI[Any],
        *,
        params: ModelCallParams | None = None,
        points: Iterable[Point] | None = None,
    ) -> None:
        self._model_api = model_api
        self._params = params
        self._points: frozenset[Point] = (
            frozenset(points) if points is not None else ALL_POINTS
        )

    def supports(self, point: Point) -> bool:
        return point in self._points

    async def decide(self, point: Point, state: dict[str, Any]) -> JudgeOutcome[Any]:
        definition = POINT_TABLE[point]
        started = perf_counter()
        try:
            judge_state = self._model_api.initial_state(
                system_prompt=definition.system_prompt
            )
            result = await self._model_api.structured_output(
                UserMessage(text=render_state(state)),
                output_type=definition.schema,
                state=judge_state,
                params=self._params,
            )
            if result.parsed is None:
                raise LlmJudgeError(
                    f"LLM 判定器（{point.value}）结构化输出解析失败；"
                    f"metadata={getattr(result, 'metadata', {})}"
                )
            decision: BaseModel = result.parsed
            if definition.route is not None:
                decision = definition.route(decision)
            backend = self.name
        except Exception as e:
            # 判定不可用 → 保守裁决（在实现内部收口，core 不感知）。backend 明确标出来，
            # 免得 trace 里把"没判成"当成"判成这样"。
            decision = _conservative_decision(point, e)
            backend = f"{self.name}:fallback"
        return JudgeOutcome(
            point=point,
            backend=backend,
            decision=decision,
            answers={},
            latency_ms=(perf_counter() - started) * 1000,
        )


def _conservative_decision(point: Point, error: Exception) -> BaseModel:
    """判定器不可用时的保守裁决（每个判定点各自的"退回到没有这个把控"）。

    - preflight：退回无状态入口（原实现永远进 plan）；
    - plan_audit：不拦计划（判定器故障不该把计划判死，理由记在 rationale 里）；
    - step_assert / diagnosis：保守重规划（与原实现一致）；
    - round_gate：继续（不因故障提前止损，收敛仍由 max_turns 保证）；
    - finish：`assessed=False`，不编造置信度，core 退回"没有收尾评估"的行为。
    """
    reason = f"判定器不可用（{type(error).__name__}: {error}）"
    if point is Point.PREFLIGHT:
        return PreflightDecision(path="plan", rationale=reason)
    if point is Point.PLAN_AUDIT:
        return PlanAuditDecision(passed=True, rationale=reason)
    if point is Point.STEP_ASSERT:
        return StepAssertDecision(
            passed=False,
            rationale=reason,
            diagnosis=Replan(
                failed_assumption="达成验收不可用", retry_direction="保守默认重规划"
            ),
        )
    if point is Point.DIAGNOSIS:
        return DiagnosisDecision(
            decision=Replan(
                failed_assumption="补救诊断不可用", retry_direction="保守默认重规划"
            ),
            rationale=reason,
        )
    if point is Point.ROUND_GATE:
        return RoundGateDecision(action="continue", rationale=reason)
    if point is Point.FINISH:
        return FinishDecision(assessed=False, rationale=reason)
    raise ValueError(f"未知判定点 {point!r}")  # pragma: no cover - Point 是闭合枚举
