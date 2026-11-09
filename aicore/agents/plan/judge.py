"""把控（judge）契约：plact core 与"谁来判"之间的唯一接口。

分层
----
======================  ==================================================================
层                       内容
======================  ==================================================================
本模块（core 契约）        :class:`Point`（判定点词汇）、:class:`PlanJudge`（协议）、
                        :class:`JudgeOutcome`（判定结果信封：裁决 + 证据 + 耗时）
:mod:`.decisions`        各判定点的裁决类型（纯数据，core 与实现共用）
``aicore/agents/plan/judges/``  具体实现（Jev / LLM）：怎么问、问什么、怎么由答案算出裁决
======================  ==================================================================

core 只 import 本模块与 :mod:`.decisions`／:mod:`.trim`，**不 import 任何实现**：换把控
（Jev ↔ LLM ↔ 测试替身 ↔ 不注入）是构造参数的一处改动，编排、runner、事件形状都不变。

必需能力与额外把控
------------------
- :data:`REQUIRED_POINTS`（只有 ``step_assert``）：达成判据是"自然语言断言"时，必须有谁来做
  这一步验收，否则计划里会出现一个没人执行的达成门——那是静默放行，core 在入口直接拒。
- :data:`OPTIONAL_POINTS`：preflight / plan_audit / diagnosis / round_gate / finish 是**额外的
  把控**。注入的实现用 :meth:`PlanJudge.supports` 声明自己做不做；core 里没有任何开关，
  只有 ``if judge.supports(point)`` 这一种判断。没被承担的点退回"没有把控"的行为
  （入口无状态、执行前不审计、轮次按 max_turns 收敛、收尾用代码可推的结论）。

判（事实）与合（规则）的分工见 :mod:`.decisions` 与 ``judges/points.py``：判据形态由
:attr:`PlanJudge.criterion` 注入（见 :mod:`.criterion`），规则性出口写在代码里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from aicore.agents.plan.criterion import CriterionKind

__all__ = [
    "Point",
    "event_source",
    "REQUIRED_POINTS",
    "OPTIONAL_POINTS",
    "ALL_POINTS",
    "JudgeOutcome",
    "PlanJudge",
]


class Point(StrEnum):
    """判定点词汇（core 与实现共用的名字）。"""

    PREFLIGHT = "preflight"
    """入口分流：plan / direct / clarify。"""

    PLAN_AUDIT = "plan_audit"
    """执行前的计划语义审计。"""

    STEP_ASSERT = "step_assert"
    """step 达成验收（必需：达成判据是自然语言断言时，这是唯一的达成门）。"""

    DIAGNOSIS = "diagnosis"
    """过程错误 / 未达成之后的补救裁决。"""

    ROUND_GATE = "round_gate"
    """本轮有错时，还值不值得再修一轮。"""

    FINISH = "finish"
    """收尾评估：覆盖度 / 虚构 / 如实说明 → 置信度与结局。"""


# 必需能力：达成判据是 nature_assertion 时，没有它就没有达成判定（core 入口会拒）。
REQUIRED_POINTS: frozenset[Point] = frozenset({Point.STEP_ASSERT})

# 额外的把控：做不做由注入的实现用 supports() 声明，core 里没有开关。
OPTIONAL_POINTS: frozenset[Point] = frozenset(
    {
        Point.PREFLIGHT,
        Point.PLAN_AUDIT,
        Point.DIAGNOSIS,
        Point.ROUND_GATE,
        Point.FINISH,
    }
)

ALL_POINTS: frozenset[Point] = REQUIRED_POINTS | OPTIONAL_POINTS


def event_source(backend: str) -> str:
    """把控实现名 → 事件的 ``source`` 标签。

    实现名可以更精确（如 ``llm:fallback`` 表示"LLM 判定失败后转的保守裁决"），但事件里的
    ``source`` 是既有的窄枚举（rule / llm / jev / fallback），所以这里做一次收敛：
    兜底裁决一律记 ``fallback``，精确名字留在 ``JudgeDecisionEvent.backend`` 里。
    """
    return "fallback" if backend.endswith(":fallback") else backend


@dataclass(frozen=True)
class JudgeOutcome[DecisionT: BaseModel]:
    """一次判定的完整结果：裁决 + 证据（原子答案 / 概率分布）+ 耗时。

    ``answers`` 只有 Jev 这类"能给出可校准量"的实现才填；它落进事件后是离线做校准统计、
    阈值调参的唯一数据源（LLM 后端为空）。
    """

    point: Point
    backend: str
    decision: DecisionT
    answers: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


@runtime_checkable
class PlanJudge(Protocol):
    """把控协议。实现方只需回答两件事：承担哪些判定点、每个判定点给出什么裁决。"""

    name: str
    """实现名（进事件与 trace）：jev / llm / ..."""

    criterion: CriterionKind
    """本实现要求的达成判据形态。core 据此注入计划生成，并据此决定 runner 的验收方式。"""

    def supports(self, point: Point) -> bool:
        """是否承担该判定点（额外的把控由实现自己声明，core 不设开关）。"""
        ...

    async def decide(
        self, point: Point, state: dict[str, Any]
    ) -> JudgeOutcome[Any]:
        """对该判定点给出裁决。

        失败策略由实现自己决定并**在实现内部**收口：Jev 后端直接抛错（项目约定：不静默降级，
        否则"判得对"与"根本没判"分不清），LLM 后端在内部转成保守裁决并把 backend 标出来。
        core 因此不需要知道谁会失败、失败怎么办。
        """
        ...
