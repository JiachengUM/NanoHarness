from typing import Literal, Any, TypeIs

from pydantic import BaseModel, Field, SerializeAsAny

from aicore.core.event import EventBase
from aicore.core.types import SafeResult
from aicore.agents.plan.criterion import SuccessCheck
from aicore.agents.plan.diagnosis import DiagnosisSource, RemediationDiagnosis
from aicore.agents.plan.judge import Point
from aicore.agents.plan.decisions import StepAssertDecision
from aicore.agents.plan.errors import (
    PlanError,
    PlanErrorDetail,
    RepairPolicy,
    PlanRepairContext,
)


# 结局归类。语义与 forced 不同：forced 是"执行层有没有未解决的错误"，outcome 是
# "用户诉求最后达成到什么程度"——后者才是消费层真正需要的量。
type FinishOutcome = Literal["success", "partial", "not_executed", "clarify"]


class PlActRoundStartEvent(EventBase):
    """每轮 plan-and-act 开始（首轮 round=0，repair 轮 round≥1）。

    repair_context 携带上一轮的错误，None 表示首轮。
    主要用途是 trace：标识轮次边界，区分 runner 层事件归属于哪一轮。
    """

    type: Literal["plact.round.start"] = Field(default="plact.round.start", init=False)  # type: ignore
    round: int
    repair_context: PlanRepairContext | None = None


class PlActErrorsEvent(EventBase):
    """本轮执行检测到错误，policy 决定后续行为。

    REGENERATE: 下一轮将重新生成 plan。
    ACCEPT_DEGRADED: 不再重试，用当前（部分）结果出答案，PlActFinishEvent.forced=True。
    """

    type: Literal["plact.errors"] = Field(default="plact.errors", init=False)  # type: ignore
    round: int
    errors: list[PlanError]
    policy: RepairPolicy


class PlActFinishEvent[R](EventBase):
    """完成：Agent 给出最终答案（成功或强制结束）。

    forced=True 表示执行存在未解决的错误（耗尽 max_turns 或 ACCEPT_DEGRADED 降级），
    response 为基于已有结果的 best-effort 回答，可信度低于 forced=False 的情况。

    注意：forced=False 仅保证执行层无显式错误，不保证 query 达成率或答案质量。

    ``outcome`` 补上 forced 混用的三种结束状态（success / partial / not_executed / clarify）；
    ``confidence`` 是答案置信度，由注入的把控给出（Jev=校准概率组合，LLM=自报值组合），
    没有把控或把控没做成时后者为 None——**不编造**一个看起来像评估结论的数。
    """

    type: Literal["plact.finish"] = Field(default="plact.finish", init=False)  # type: ignore
    response: R
    round: int = Field(..., description="轮次")
    forced: bool = Field(default=False, description="是否强制完成对话。")
    reason: str | None = Field(default=None, description="完成原因")
    confidence: float | None = Field(default=None, description="答案置信度（0-1）。")
    confidence_reported: float | None = Field(
        default=None, description="判定器自报的把握（用于与校准置信度对比）。"
    )
    outcome: FinishOutcome | None = Field(
        default=None, description="达成的结局归类。"
    )
    ask_user_worth: float | None = Field(
        default=None, description="是否值得回问用户/给替代方案（0-1）。"
    )


class PlanCreatedEvent(EventBase):
    """计划生成完成"""

    type: Literal["plan.created"] = Field(default="plan.created", init=False)  # type: ignore
    plan: SerializeAsAny[BaseModel]
    round: int = 0


class StepUnmet(BaseModel):
    """步骤执行完成但达成判据判定 step_goal 未达成，且补救诊断给出**非 replan** 的裁决。

    作为 PlanStepDoneEvent 的一个属性存在（一个 step 只产生一个 done 事件，未达成是它的一种状态，
    而非独立事件）。replan 裁决不落在这里——它走 PlanRunnerErrorEvent 触发整体重规划。

    verdict：
    - "unsolvable"：无解，产出不作数，依赖它的下游步骤级联跳过（以 upstream_skipped 呈现）；
    - "degraded"：降级接受，产出不完美但够用、下游照常执行，仅标记以便最终回答如实说明局限。
    两者最终回答都须据此降级（forced=True），并如实告知用户 reason 所述的原因。

    message 是判据未通过的客观原因；reason 是诊断给出的裁决理由。
    TODO(ask_user): 无解且存在用户可能接受的 near-miss 时，本应澄清而非静默降级；
        交互通道未实现前，此类情形暂并入 verdict="unsolvable"。
    """

    verdict: Literal["unsolvable", "degraded"]
    success_check: SuccessCheck | None = None
    message: str
    reason: str


class PlanStepStartedEvent(EventBase):
    """步骤已通过条件、引用解析和工具参数校验，即将进入本层真实工具执行。"""

    type: Literal["plan.step.started"] = Field(default="plan.step.started", init=False)  # type: ignore
    step_id: str
    step_goal: str
    resolved_inputs: dict[str, Any]


class PlanStepDiagnosisStartedEvent(EventBase):
    """一个 step 的达成判定开始，且判据由**规则层**求值（jq 形态 / 过程错误路径）。

    判据形态是自然语言断言时走 :class:`PlanStepAssertStartedEvent`（判定器验收）；
    过程错误（工具没跑成、执行报错、投影失败）不论判据形态都走本路径，由规则层确定性定夺。
    """
    type: Literal["plan.step.diagnosis.started"] = Field(default="plan.step.diagnosis.started", init=False)  # type: ignore
    step_id: str
    step_goal: str
    success_check: SuccessCheck | None = None
    failure_message: str
    process_error_kind: Literal[
        "input_ref", "params", "condition", "execution", "projection"
    ] | None = None


class PlanStepDiagnosisCompletedEvent(EventBase):
    type: Literal["plan.step.diagnosis.completed"] = Field(default="plan.step.diagnosis.completed", init=False)  # type: ignore
    step_id: str
    step_goal: str
    source: DiagnosisSource
    decision: RemediationDiagnosis


class PlanStepDoneEvent(EventBase):
    """计划步骤执行完成。

    unmet 非 None 表示该步骤虽执行完成，但 success_check 判定 step_goal 未达成、且诊断为非 replan
    （无解或降级接受）；为 None 表示达成（或 success_check 通过）。

    process_error 记录执行过程中的错误（input_ref / params / condition / execution / projection），仅供 trace
    观测：它不再作为独立的 PlanRunnerErrorEvent 驱动处置策略，而是作为补救诊断的输入；诊断结论才
    决定 replan（走 PlanRunnerErrorEvent）或 unmet。process_error 与 unmet 可并存（如投影失败 →
    诊断判无解）。
    """

    type: Literal["plan.step.done"] = Field(default="plan.step.done", init=False)  # type: ignore
    step_id: str
    step_goal: str
    raw_inputs: dict[str, Any] = Field(
        ..., description="plan 中声明的原始 inputs（含模板引用）"
    )
    resolved_inputs: dict[str, Any] = Field(
        ..., description="模板引用替换后实际传给 tool 的 inputs"
    )
    tool_output: SafeResult[Any] = Field(
        ..., description="工具原始返回值（含成功/失败状态）"
    )
    concept_output: dict[str, Any] = Field(
        ..., description="经 concept_tool_outputs 投影后的概念实例字典"
    )
    unmet: StepUnmet | None = Field(
        default=None,
        description="success_check 未达成且诊断为非 replan 的裁决；达成时为 None",
    )
    process_error: PlanErrorDetail | None = Field(
        default=None,
        description="执行过程错误（input_ref/params/condition/execution/projection），仅供 trace；作为诊断输入而非独立错误上报",
    )


class PlanRunnerErrorEvent(EventBase):
    """runner 层错误事件，涵盖 DAG 校验失败与步骤补救诊断要求重规划。

    DAG 校验错误可能聚合；同层 step.remediation 错误也会在各自 done 证据之后聚合上报。
    透传至 plact 层后直接 extend 到本轮错误列表。
    """

    type: Literal["plan.runner.error"] = Field(default="plan.runner.error", init=False)  # type: ignore
    errors: list[PlanError]


class PlanStepSkippedEvent(EventBase):
    """步骤未被执行，不计入错误。

    reason="condition_false"：该步骤自身 condition 求值为 false。
    reason="upstream_skipped"：depends_on 中存在被跳过的前序步骤（源头是 condition_false），级联跳过。
    reason="upstream_unsolvable"：depends_on 中存在（传递地）被诊断为无解 skip_unsolvable 的前序步骤，
      因失败传播而跳过——语义上区别于普通控制流跳过，需在最终回答里如实反映无法完成。
    condition 仅在 reason="condition_false" 时非 None。
    """

    type: Literal["plan.step.skipped"] = Field(default="plan.step.skipped", init=False)  # type: ignore
    step_id: str
    step_goal: str
    reason: Literal["condition_false", "upstream_skipped", "upstream_unsolvable"]
    condition: str | None = None


class JudgeDecisionEvent(EventBase):
    """一个判定点完成了一次判定（把控是 Jev 或 LLM）。

    stage 取值与 :class:`~aicore.agents.plan.judge.Point` 一致；除裁决本身外还带 ``answers``
    （归一化原子答案 + 完整概率分布）与 ``latency_ms``——这是后续做校准统计、阈值调参、
    "LLM 自报 vs 校准概率"对比的唯一数据来源。
    """

    type: Literal["plan.judge.decision"] = Field(default="plan.judge.decision", init=False)  # type: ignore
    stage: Point = Field(..., description="判定点名。")
    backend: str = Field(..., description="把控实现名（jev / llm / llm:fallback / ...）。")
    decision: SerializeAsAny[BaseModel] = Field(..., description="该判定点的裁决对象。")
    answers: dict[str, Any] = Field(
        default_factory=dict, description="归一化后的原子答案（含概率分布）；LLM 后端为空。"
    )
    latency_ms: float = Field(default=0.0, description="该次判定的耗时（毫秒）。")


class PlanStepAssertStartedEvent(EventBase):
    """断言验收开始（该步已执行完、产出已拿到，且判据形态是自然语言断言）。

    与 ``plan.step.diagnosis.*`` 的分工：那两个事件表示"规则层判定未通过、进入诊断"，
    只在失败时发生；本事件是**每个执行完的 step 都发生**的达成判定生命周期，
    所以 started 里只有该步声明的断言（通过与否要等判定返回才知道），没有失因。

    started 在判定调用**之前**发出：它到 completed 的间隔就是判定耗时（trace 靠它归因），
    ``tests/agents/test_plan_dag_runner_events.py`` 钉住了这一点。
    """

    type: Literal["plan.step.assert.started"] = Field(default="plan.step.assert.started", init=False)  # type: ignore
    step_id: str
    step_goal: str
    assertion: list[str] = Field(default_factory=list, description="该步声明的断言。")


class PlanStepAssertCompletedEvent(EventBase):
    """断言验收完成：裁决本身（含补救裁决）就落在 decision 里。

    ``decision.passed=False`` 时 ``decision.diagnosis`` 必有值（replan / skip_unsolvable /
    accept_degraded），由 runner 转成既有的两种路由（replan → PlanRunnerErrorEvent；
    其余 → PlanStepDoneEvent.unmet），因此消费方只需认这一个载荷。
    """

    type: Literal["plan.step.assert.completed"] = Field(default="plan.step.assert.completed", init=False)  # type: ignore
    step_id: str
    step_goal: str
    source: DiagnosisSource = Field(..., description="判定来源：jev / llm / fallback。")
    decision: StepAssertDecision


# plact.* 为 plact 编排层事件；plan.* 为 runner 层事件，透传至此。
PlActEvent = (
    PlActRoundStartEvent
    | PlActErrorsEvent
    | PlanCreatedEvent
    | PlanStepStartedEvent
    | PlanStepAssertStartedEvent
    | PlanStepAssertCompletedEvent
    | PlanStepDiagnosisStartedEvent
    | PlanStepDiagnosisCompletedEvent
    | PlanStepDoneEvent
    | PlanRunnerErrorEvent
    | PlanStepSkippedEvent
    | JudgeDecisionEvent
    | PlActFinishEvent[Any]
)


def is_plact_event(event: Any) -> TypeIs[PlActEvent]:
    return isinstance(event, (
        PlActRoundStartEvent,
        PlActErrorsEvent,
        PlActFinishEvent,
        PlanStepStartedEvent,
        PlanStepAssertStartedEvent,
        PlanStepAssertCompletedEvent,
        PlanStepDiagnosisStartedEvent,
        PlanStepDiagnosisCompletedEvent,
        PlanStepDoneEvent,
        PlanRunnerErrorEvent,
        PlanStepSkippedEvent,
        PlanCreatedEvent,
        JudgeDecisionEvent,
    ))
