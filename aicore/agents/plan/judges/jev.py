"""Jev 后端：一次 ``system_one`` 拿全部原子判断，再由组合方程算出裁决。

判定点的"怎么问、怎么合"全在 :mod:`.points` 的表里，本类只做两件事：把注入的
:class:`~aicore.agents.plan.judge.Point` 查成判定点定义，把客户端返回的原子答案交给该点的
组合方程。换判定点、加判定点都不需要动本类。

失败策略：**直接抛错，不静默降级**（``JevError`` / ``JevTimeoutError`` 原样冒出）。静默降级
会让 A/B 不可归因——分不清"判得对"和"根本没判"。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Iterable

from aicore.agents.plan.criterion import KIND_ASSERTION, CriterionKind
from aicore.agents.plan.judge import ALL_POINTS, JudgeOutcome, Point
from aicore.agents.plan.judges.jev_client import JevClient
from aicore.agents.plan.judges.points import ALL_POINTS as POINT_TABLE

__all__ = ["JevJudge"]


class JevJudge:
    """Jev 判定器。

    ``points`` 声明本实现承担哪些判定点（默认全部）：额外的把控（preflight / plan_audit /
    diagnosis / round_gate / finish）要不要，就是构造时给不给——core 里没有任何开关。
    """

    name = "jev"
    criterion: CriterionKind = KIND_ASSERTION

    def __init__(
        self,
        client: JevClient,
        *,
        points: Iterable[Point] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._points: frozenset[Point] = (
            frozenset(points) if points is not None else ALL_POINTS
        )
        self._timeout = timeout

    def supports(self, point: Point) -> bool:
        return point in self._points

    async def decide(self, point: Point, state: dict[str, Any]) -> JudgeOutcome[Any]:
        definition = POINT_TABLE[point]
        questions = definition.questions(state)
        started = perf_counter()
        response = await self._client.system_one(
            state=state, questions=questions, timeout=self._timeout
        )
        return JudgeOutcome(
            point=point,
            backend=self.name,
            decision=definition.compose(response.answers),
            answers=response.as_json(),
            latency_ms=response.latency_ms or (perf_counter() - started) * 1000,
        )
