import re
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Sequence

import anyio
import jq

from aicore.agents.plan.dag_checker import check_dag, _REF_RE
from aicore.agents.plan.events import (
    PlanRunnerErrorEvent,
    PlanStepAssertCompletedEvent,
    PlanStepAssertStartedEvent,
    PlanStepDiagnosisCompletedEvent,
    PlanStepDiagnosisStartedEvent,
    PlanStepDoneEvent,
    PlanStepSkippedEvent,
    PlanStepStartedEvent,
    StepUnmet,
)
from aicore.agents.plan.dag_runner import BareDag
from aicore.agents.plan.criterion import (
    JqExprCriterion,
    NatureAssertionCriterion,
    SuccessCheck,
)
from aicore.agents.plan.decisions import StepAssertDecision
from aicore.agents.plan.diagnosis import (
    DiagnosisResult,
    Replan,
    SkipUnsolvable,
    _rule_based_diagnosis,
    diagnose_success_check_failure,
)
from aicore.agents.plan.judge import JudgeOutcome, PlanJudge, Point, event_source
from aicore.agents.plan.trim import (
    DEFAULT_TRIM,
    TrimPolicy,
    build_diagnosis_state,
    build_step_assert_state,
)
from aicore.agents.plan.experiment.plan_schema_v1 import PlanStepV1
from aicore.agents.plan.errors import (
    PlanError,
    PlanErrorDetail,
    ParamsErrorDetail,
    InputRefErrorDetail,
    ExecutionErrorDetail,
    ConditionErrorDetail,
    ProjectionErrorDetail,
    RemediationErrorDetail,
)

from aicore.models.model_api import ModelAPI
from aicore.tools.concept_outputs import _normalize
from aicore.tools.concept_outputs_v3 import (
    concept_tool_outputs_v3 as concept_tool_outputs,
)
from aicore.tools.protocol import TaskToolProtocolGeneral, validate_tool_arguments
from aicore.tools.runner.task_tool_runner import TaskToolRunner
from aicore.core.types import SafeResult
from aicore.utils.nl_repr import nl_repr

type PlanDag = BareDag[PlanStepV1]
type RunnerEvent = (
    PlanStepStartedEvent
    | PlanStepAssertStartedEvent
    | PlanStepAssertCompletedEvent
    | PlanStepDiagnosisStartedEvent
    | PlanStepDiagnosisCompletedEvent
    | PlanStepDoneEvent
    | PlanRunnerErrorEvent
    | PlanStepSkippedEvent
)

EMPTY_LIST_OUTPUT_MESSAGE = "is_list output is empty"


def _normalize_tool_output(raw: Any) -> dict[str, Any] | list[Any]:
    """归一化工具原始返回为 dict/list，作为诊断证据（RemediationErrorDetail.tool_output）。

    工具可能返回纯文本/标量——如带 criteria 的 poi/music 搜索走 LLM 文本筛选后 return 一段
    markdown 字符串。这些非 dict/list 的返回若直接塞进 tool_output 字段会触发 pydantic 校验失败，
    这里统一包一层 {"text": ...} 兜底，保证任意工具返回都不致崩溃。
    """
    normalized = _normalize(raw)
    if isinstance(normalized, (dict, list)):
        return normalized
    return {"text": normalized}


@dataclass
class _StepOutcome:
    """一个非 skipped step 执行后、进入统一验证尾段前的中间态。

    无论 params 校验 / condition 求值 / tool 执行 / 投影哪一层失败，都归一到这里：失败只表现为
    proj 为空 + process_error 非 None。验证尾段对所有 outcome 一律求值 success_check，失败即诊断。

    - raw_tool_output：工具原始返回（未跑为 {}；投影失败但工具成功时保留真实数据，供诊断）。
    - proj：concept 投影后的 outputs（失败/未跑为 {}）。
    - process_error：input_ref/params/condition/execution/projection 之一，或 None（两层皆成功）。

    这三者是彼此正交的最小事实集，proj 空 ⟺ process_error 非 None 的不变式由填充逻辑维持。
    给 PlanStepDoneEvent.tool_output 的 SafeResult 不作为字段存储——它只是「工具成败」这一视图，
    可从 raw_tool_output + process_error 投影得到（见 tool_output property），不是关于 step 的独立事实。
    """

    step: PlanStepV1
    resolved_inputs: dict[str, Any]
    raw_tool_output: Any = field(default_factory=dict)
    proj: dict[str, Any] = field(default_factory=dict)
    process_error: PlanErrorDetail | None = None

    @property
    def tool_output(self) -> SafeResult[Any]:
        """PlanStepDoneEvent.tool_output 的 SafeResult 视图，按需从 raw + process_error 投影。

        关键区分：它表达的是**工具**成败，不是**步骤**成败。投影是工具之后的一层，故
        「投影失败但工具成功」（process_error 为 ProjectionErrorDetail）时仍是成功 + 真实 raw；
        只有 input_ref/params/condition（工具没跑）与 execution（工具跑了但失败）才给 error 结果。
        """
        pe = self.process_error
        if pe is None or isinstance(pe, ProjectionErrorDetail):
            return SafeResult(data=self.raw_tool_output)
        return SafeResult(error=nl_repr(pe))


@dataclass
class _StepVerdict:
    """一个 step 的达成裁决，由 :meth:`PlanDAGRunner._decide_step` 写、验证尾段读。

    passed=True 时其余字段为 None；passed=False 时 failure_message 与 diagnosis 必有值
    （不变式由 _decide_step 的每个实现维持）。process_error_kind 只供诊断事件归因。
    """

    passed: bool = True
    failure_message: str | None = None
    process_error_kind: str | None = None
    diagnosis: DiagnosisResult | None = None


class PlanDAGRunner:
    def __init__(
        self,
        tools: Sequence[TaskToolProtocolGeneral],
        model_api: ModelAPI[Any] | None = None,
        query: str = "",
        *,
        judge: PlanJudge | None = None,
        trim_policy: TrimPolicy = DEFAULT_TRIM,
    ):
        """按名称索引 tools，初始化运行状态容器。

        ``judge`` 是**注入的把控**（见 :mod:`aicore.agents.plan.judge`）：达成判据是自然语言
        断言时由它做验收与补救裁决；``None`` 或不承担某判定点时退回"没有把控"的行为（判据由
        规则层用 jq 求值、补救走原生成式诊断）。runner 不认识任何具体实现。

        runtime_state 结构：{step_id: {"inputs": resolved, "outputs": concept_dict}}
        outputs 经过 concept_tool_outputs 投影，结构为 {ConceptName: instance_or_list}。

        query 是原始用户请求，仅用于 success_check 失败后的补救诊断（判断失败约束是用户硬性
        要求还是 plan 的操作化猜测）；不传时诊断退化为默认 replan。
        """
        self._tools: dict[str, TaskToolProtocolGeneral] = {t.name: t for t in tools}
        self._model_api = model_api
        self._query = query
        self._judge = judge
        self._trim = trim_policy
        # 判定结果先攒着，由编排层在拿到事件后 drain 成 JudgeDecisionEvent。
        # 放在 runner 上是因为判定发生在 run() 的事件流内部（在 done 事件之前）。
        self._judgements: list[JudgeOutcome[Any]] = []
        self._runtime_state: dict[str, dict[str, Any]] = {}
        self._skipped: set[str] = set()
        # _skipped 的子集：因诊断判无解（skip_unsolvable）或其无解链传播而跳过的步骤。
        # 用于把「无解导致的下游跳过」与「condition_false 导致的普通 upstream_skipped」区分开，
        # 下游 reason 取 upstream_unsolvable 并沿链继续传播。
        self._unsolvable: set[str] = set()
        # success_check 失败且诊断为非 replan 的步骤：step_id -> {step_goal, verdict, reason}。
        # verdict ∈ {"unsolvable", "degraded"}。供 step_results 呈现、并让编排层据此降级最终回答。
        self._unmet: dict[str, dict[str, str]] = {}

    async def run(self, dag: PlanDag) -> AsyncGenerator[RunnerEvent, None]:
        """按拓扑层顺序执行 DAG，同层内并行，层间串行。承诺不抛出异常。

        DAG 校验失败时 yield PlanRunnerErrorEvent 后立即返回，不执行任何步骤。

        统一验证模型：非 skipped 的每个 step 执行后都进入「验证尾段」——无论 params 校验 /
        condition 求值 / tool 执行 / 投影哪一层失败，都归一为「outputs 为空 + 携带 process_error」，
        由 success_check 统一判定是否达成，未达成即交补救诊断（诊断内含规则前置层）。
        唯一的失败触发器是 success_check 判 false（含求值前就有 process_error 使 outputs 为空）；
        process_error 不再作为独立 PlanRunnerErrorEvent 驱动策略，只作诊断上下文 + 挂到 done 事件。
        诊断结论：replan → PlanRunnerErrorEvent(step.remediation)；无解/降级 → PlanStepDoneEvent.unmet。

        跳过（upstream_skipped / condition_false）仍写入 runtime_state（outputs 为空），供 step_results 展示。
        """
        validation_errors = check_dag(dag, self._tools)
        if validation_errors:
            yield PlanRunnerErrorEvent(errors=validation_errors)
            return

        for level in dag.topo_levels(lambda s: s.step_id):
            runner: TaskToolRunner = TaskToolRunner()

            # 本层所有待验证的 step（不含 skipped）。valid 是其中入 runner 的子集，
            # 顺序严格等于 runner.add_tool 顺序，用于把 runner.results 对齐回 outcome。
            outcomes: list[_StepOutcome] = []
            valid: list[_StepOutcome] = []

            for step in level:
                skipped_deps = [dep for dep in step.depends_on if dep in self._skipped]
                if skipped_deps:
                    # 无解链传播：只要有一个被跳过的前序是无解（或无解链上的），本步 reason 记
                    # upstream_unsolvable 并继续污染下游；否则是普通 condition_false 引发的 upstream_skipped。
                    unsolvable_cause = any(
                        dep in self._unsolvable for dep in skipped_deps
                    )
                    reason = (
                        "upstream_unsolvable"
                        if unsolvable_cause
                        else "upstream_skipped"
                    )
                    self._skipped.add(step.step_id)
                    if unsolvable_cause:
                        self._unsolvable.add(step.step_id)
                    self._runtime_state[step.step_id] = {
                        "inputs": {},
                        "outputs": {},
                        "skipped": reason,
                    }
                    yield PlanStepSkippedEvent(
                        step_id=step.step_id,
                        step_goal=step.step_goal,
                        reason=reason,
                    )
                    continue

                if step.condition:
                    condition_error: str | None = None
                    result: Any = None
                    try:
                        result = self._eval_condition(step.condition)
                    except Exception as e:
                        condition_error = str(e)
                    else:
                        if not isinstance(result, bool):
                            condition_error = (
                                f"condition must evaluate to a boolean, got {result!r}"
                            )

                    if condition_error is not None:
                        # condition 求值失败：不早退，记为 process_error，汇入统一验证尾段。
                        outcomes.append(
                            _StepOutcome(
                                step=step,
                                resolved_inputs={},
                                process_error=ConditionErrorDetail(
                                    step_id=step.step_id,
                                    condition=step.condition,
                                    message=condition_error,
                                ),
                            )
                        )
                        continue

                    if result is False:
                        self._skipped.add(step.step_id)
                        self._runtime_state[step.step_id] = {
                            "inputs": {},
                            "outputs": {},
                            "skipped": "condition_false",
                        }
                        yield PlanStepSkippedEvent(
                            step_id=step.step_id,
                            step_goal=step.step_goal,
                            reason="condition_false",
                            condition=step.condition,
                        )
                        continue

                resolved, input_ref_error = self._resolve_inputs(
                    step.inputs, step.step_id
                )
                if input_ref_error is not None:
                    # input 引用运行时解析失败：工具不跑，记为 process_error，汇入统一验证尾段。
                    outcomes.append(
                        _StepOutcome(
                            step=step,
                            resolved_inputs=resolved,
                            process_error=input_ref_error,
                        )
                    )
                    continue
                try:
                    args = validate_tool_arguments(self._tools[step.op], resolved)
                    runner.add_tool(self._tools[step.op], args)
                    oc = _StepOutcome(step=step, resolved_inputs=resolved)
                    outcomes.append(oc)
                    valid.append(oc)
                except Exception as e:
                    # params 校验失败：工具不跑，记为 process_error，汇入统一验证尾段。
                    outcomes.append(
                        _StepOutcome(
                            step=step,
                            resolved_inputs=resolved,
                            process_error=ParamsErrorDetail(
                                step_id=step.step_id,
                                tool_name=step.op,
                                message=str(e),
                            ),
                        )
                    )

            # 执行入 runner 的步骤并投影；填回各 valid outcome 的 safe / raw / proj / process_error。
            if valid:
                for outcome in valid:
                    yield PlanStepStartedEvent(
                        step_id=outcome.step.step_id,
                        step_goal=outcome.step.step_goal,
                        resolved_inputs=outcome.resolved_inputs,
                    )
                raws: list[Any] = [{}] * len(valid)
                projected: list[dict[str, Any]] = [{}] * len(valid)
                projection_errors: dict[int, ProjectionErrorDetail] = {}

                async def project_at(idx: int, step: PlanStepV1, raw: Any) -> None:
                    co = step.outputs
                    import time

                    started = time.perf_counter()
                    output = await concept_tool_outputs(
                        raw, co.concept, co.is_list, self._model_api, tool_name=step.op
                    )
                    print(
                        f"concept output for step {step.step_id} cost {time.perf_counter() - started:.1f}s, raw size {len(str(raw))}, is_list {co.is_list}, output size {len(str(output.data))}"
                    )
                    if output.error:
                        projection_errors[idx] = ProjectionErrorDetail(
                            step_id=step.step_id,
                            concept_name=co.concept.name,
                            message=output.error,
                            item_errors=output.item_errors,
                        )
                    # elif not output.data:
                    #     message = (
                    #         EMPTY_LIST_OUTPUT_MESSAGE
                    #         if co.is_list
                    #         else "projection returned empty"
                    #     )
                    #     projection_errors[idx] = ProjectionErrorDetail(
                    #         step_id=step.step_id,
                    #         concept_name=co.concept.name,
                    #         message=message,
                    #         item_errors=output.item_errors,
                    #     )
                    else:
                        projected[idx] = {co.concept.name: output.data}

                async with anyio.create_task_group() as tg:
                    import time

                    started = time.perf_counter()
                    async for idx, event in runner.run_indexed():
                        raw = event.output.data if event.output.data is not None else {}
                        raws[idx] = raw
                        tg.start_soon(project_at, idx, valid[idx].step, raw)
                        print(
                            f"=== step {valid[idx].step.step_id} tool call finished, cost {time.perf_counter() - started:.1f}s"
                        )

                # execution 错误优先于 projection：tool 失败时投影基于空 raw、结果无意义。
                for idx, oc in enumerate(valid):
                    safe = runner.results[idx]
                    oc.raw_tool_output = raws[idx]
                    if not safe.is_success:
                        oc.process_error = ExecutionErrorDetail(
                            step_id=oc.step.step_id,
                            tool_name=oc.step.op,
                            message=safe.error or "",
                        )
                    elif proj_err := projection_errors.get(idx):
                        oc.process_error = proj_err
                    else:
                        assert projected[idx], (
                            f"step {oc.step.step_id!r}: execution and projection both succeeded but proj is empty"
                        )
                        oc.proj = projected[idx]

            # ── 统一验证尾段：对本层每个 outcome 求值 success_check，失败即诊断 ──────────────
            remediation_errors: list[PlanError] = []
            for oc in outcomes:
                # 先写 runtime_state 再求值：success_check 可引用自身 outputs（失败时为空 → 判 false）。
                self._runtime_state[oc.step.step_id] = {
                    "inputs": oc.resolved_inputs,
                    "outputs": oc.proj,
                }
                async for event in self._verify_step(oc, remediation_errors):
                    yield event

            if remediation_errors:
                yield PlanRunnerErrorEvent(errors=remediation_errors)
                return

    async def _verify_step(
        self, oc: _StepOutcome, remediation_errors: list[PlanError]
    ) -> AsyncGenerator[RunnerEvent, None]:
        """统一验证尾段：达成判定 → 裁决路由 → done 事件。

        「这步达成了吗」由 :meth:`_decide_step` 给出（原生=jq 求值 success_check，JEV=判定器），
        本方法只负责**裁决的路由**：三种出口（replan 上报 / unmet 落账 / 达成）与 done 事件的
        形状在此收口，两条后端逐字共用，避免语义分叉。

        remediation_errors 是本层的聚合容器：replan 在此追加，由调用方在本层全部 done 证据之后
        统一上报（一次性重规划），因此这里不自行中止。
        """
        step = oc.step
        verdict = _StepVerdict()
        async for event in self._decide_step(oc, verdict):
            yield event

        step_unmet: StepUnmet | None = None
        if not verdict.passed:
            assert verdict.diagnosis is not None and verdict.failure_message is not None, (
                f"step {step.step_id!r}: 判未达成必须带上失因与补救裁决"
            )
            failure_message = verdict.failure_message
            diagnosis = verdict.diagnosis.decision
            if isinstance(diagnosis, Replan):
                # 换 approach 可解：先保留本层所有 done 证据，再聚合上报触发整体重规划。
                remediation_errors.append(
                    PlanError(
                        source="step.remediation",
                        detail=RemediationErrorDetail(
                            step_id=step.step_id,
                            diagnosis_reason=(
                                f"失败假设：{diagnosis.failed_assumption}；"
                                f"重试方向：{diagnosis.retry_direction}"
                            ),
                            success_check=step.success_check,
                            message=failure_message,
                            outputs_snapshot=oc.proj,
                            tool_output=_normalize_tool_output(oc.raw_tool_output),
                        ),
                    )
                )
            else:
                # 非 replan 裁决（无解 / 降级接受）：写进 runtime_state 与 _unmet，
                # 并作为 done 事件的 unmet 属性透出，供 step_results 与编排层最终降级使用。
                if isinstance(diagnosis, SkipUnsolvable):
                    unmet_verdict = "unsolvable"
                    reason = diagnosis.unsolvable_reason
                    # 无解：本步产出不作数，标记已跳过使下游依赖它的步骤级联跳过；
                    # 同时进 _unsolvable，使下游 reason 记 upstream_unsolvable（区别于普通跳过）。
                    self._skipped.add(step.step_id)
                    self._unsolvable.add(step.step_id)
                else:
                    unmet_verdict = "degraded"
                    reason = diagnosis.limitation
                self._unmet[step.step_id] = {
                    "step_goal": step.step_goal,
                    "verdict": unmet_verdict,
                    "reason": reason,
                }
                self._runtime_state[step.step_id]["unmet"] = {
                    "verdict": unmet_verdict,
                    "reason": reason,
                }
                step_unmet = StepUnmet(
                    verdict=unmet_verdict,
                    success_check=step.success_check,
                    message=failure_message,
                    reason=reason,
                )

        yield PlanStepDoneEvent(
            step_id=step.step_id,
            step_goal=step.step_goal,
            raw_inputs=step.inputs,
            resolved_inputs=oc.resolved_inputs,
            tool_output=oc.tool_output,
            concept_output=oc.proj,
            unmet=step_unmet,
            process_error=oc.process_error,
        )

    async def _decide_step(
        self, oc: _StepOutcome, verdict: _StepVerdict
    ) -> AsyncGenerator[RunnerEvent, None]:
        """达成判定 + 补救裁决：**按判据形态分派**，形态由计划自己声明（见 criterion）。

        ===========================  ==================================================
        判据形态 / 情形               谁来做达成判定
        ===========================  ==================================================
        ``nature_assertion``          判定器（STEP_ASSERT）：断言逐条判三态，"被证伪"才交补救
        ``jq_expr``                   规则层：runner 用 jq 确定性求值
        **过程错误**（任何形态）        规则层：入参/引用/条件/执行/投影失败与"产出达没达标"
                                     无关，规则层能确定性定夺，不值得占判定预算
        ===========================  ==================================================

        事件在判定调用**前后**各发一次：started 的时戳到 completed 的间隔就是判定耗时
        （trace 靠它归因延迟），所以本方法写成 async generator、裁决经 out 参数 ``verdict``
        回传——否则 started 只能等判定返回后才发出，间隔会被抹平。
        """
        step = oc.step
        check = step.success_check

        if oc.process_error is not None:
            # 过程错误优先：此时产出为空/不完整，"断言是否成立"没有信息量，
            # 由规则层（+ 诊断判定点）确定性定夺。
            async for event in self._decide_via_diagnosis(
                oc, verdict, message=nl_repr(oc.process_error)
            ):
                yield event
            return

        if isinstance(check, NatureAssertionCriterion):
            async for event in self._decide_via_assert(oc, verdict):
                yield event
            return

        assert isinstance(check, JqExprCriterion), (
            f"step {step.step_id!r}: 未知的达成判据形态 {check!r}"
        )
        check_err = self._eval_success_check(check)
        if check_err is None:
            return
        async for event in self._decide_via_diagnosis(oc, verdict, message=check_err):
            yield event

    async def _decide_via_assert(
        self, oc: _StepOutcome, verdict: _StepVerdict
    ) -> AsyncGenerator[RunnerEvent, None]:
        """自然语言断言形态：一次 STEP_ASSERT 判定（断言验收 + 补救裁决同时产出）。

        ``diagnosis`` 与达成判定出自同一次推理，因此不会再出现原实现那种"判定器自己说产出
        仍可用（0.81）却判 replan"的自相矛盾裁决。

        没有把控时直接抛错：断言形态下"没有谁来做达成判定"意味着这步没有达成门，属于
        编程错误（core 在入口已经用 ``REQUIRED_POINTS`` 拦过一道），绝不能静默当成达成。
        """
        step = oc.step
        check = step.success_check
        assert isinstance(check, NatureAssertionCriterion)
        if self._judge is None or not self._judge.supports(Point.STEP_ASSERT):
            raise RuntimeError(
                f"step {step.step_id!r}: 达成判据是自然语言断言，但没有注入承担 "
                f"{Point.STEP_ASSERT.value} 的把控——这步会没有达成门"
            )

        state = build_step_assert_state(
            query=self._query,
            step=step,
            concept_output=oc.proj,
            tool_output=oc.raw_tool_output,
            # runtime_state 此刻已含本层各步（base runner 在求值前写入），故跨步断言比对的
            # 上游产出从这里取；不带它就只能落"无证据"→ 降级。
            all_step_outputs=self._runtime_state,
            policy=self._trim,
        )
        yield PlanStepAssertStartedEvent(
            step_id=step.step_id,
            step_goal=step.step_goal,
            assertion=list(check.assertions),
        )
        outcome = await self._judge.decide(Point.STEP_ASSERT, state)
        self._judgements.append(outcome)
        decision: StepAssertDecision = outcome.decision
        self._apply_assert_decision(
            verdict, decision, source=event_source(outcome.backend), step=step
        )
        yield PlanStepAssertCompletedEvent(
            step_id=step.step_id,
            step_goal=step.step_goal,
            source=event_source(outcome.backend),  # type: ignore[arg-type]
            decision=decision,
        )

    async def _decide_via_diagnosis(
        self, oc: _StepOutcome, verdict: _StepVerdict, *, message: str
    ) -> AsyncGenerator[RunnerEvent, None]:
        """未达成（规则层判定）→ 诊断事件对 → 补救裁决（规则前置层 → 判定点 DIAGNOSIS）。"""
        step = oc.step
        verdict.passed = False
        verdict.failure_message = message
        verdict.process_error_kind = (
            oc.process_error.kind if oc.process_error is not None else None
        )
        yield PlanStepDiagnosisStartedEvent(
            step_id=step.step_id,
            step_goal=step.step_goal,
            success_check=step.success_check,
            failure_message=message,
            process_error_kind=verdict.process_error_kind,  # type: ignore[arg-type]
        )
        diagnosis_result = await self._diagnose_failure(
            step,
            step.success_check,
            message,
            oc.proj,
            oc.raw_tool_output,
            oc.process_error,
        )
        verdict.diagnosis = diagnosis_result
        yield PlanStepDiagnosisCompletedEvent(
            step_id=step.step_id,
            step_goal=step.step_goal,
            source=diagnosis_result.source,
            decision=diagnosis_result.decision,
        )

    @staticmethod
    def _apply_assert_decision(
        verdict: _StepVerdict,
        decision: StepAssertDecision,
        *,
        source: str,
        step: PlanStepV1,
    ) -> None:
        """把断言裁决翻译成父类的 ``_StepVerdict``（判定输出 → 路由输入的唯一边界）。

        判未达成时 ``decision.diagnosis`` 必有值（由 ``compose_step_assert`` 保证：每个
        passed=False 的出口都带一个补救裁决）。真出现缺失说明判定器自己构造了非法裁决
        （LLM 后端可能），此时保守取 replan——不静默当成达成。

        注：判据自设 / 判不准这两种情形的分流**在判定方程里**（``compose_step_assert``），
        不在这里：那种情形下断言的结论本就不该成为失败依据，应该从根上就不进失败路径，
        而不是先判失败再把出口改成降级（那会让 decision 里留一个假事实，并被 unmet /
        披露 / 校准统计继承）。
        """
        verdict.passed = decision.passed
        if decision.passed:
            verdict.failure_message = None
            verdict.diagnosis = None
            return
        verdict.failure_message = decision.rationale or f"step {step.step_id!r} 断言未达成"
        verdict.diagnosis = DiagnosisResult(
            source=source,  # type: ignore[arg-type]
            decision=decision.diagnosis
            or Replan(
                failed_assumption="断言未达成但未给出补救裁决",
                retry_direction="保守默认重规划",
            ),
        )

    def drain_judgements(self) -> list[JudgeOutcome[Any]]:
        """取出并清空累积的判定结果（编排层在每个事件之后调用）。"""
        out, self._judgements = self._judgements, []
        return out

    @property
    def runtime_state(self) -> dict[str, dict[str, Any]]:
        """每步的运行时状态（``{step_id: {inputs, outputs, skipped?, unmet?}}``）。

        收尾判定（判定点 ``FINISH``）需要看到"每一步实际产出了什么"，这是唯一的结构化证据源；
        原实现把它当内部状态（``_runtime_state``），这里额外给一个只读入口。
        """
        return self._runtime_state

    @property
    def step_results(self) -> list[str]:
        """返回所有已执行/跳过步骤的输出摘要，顺序与执行顺序一致。"""
        lines: list[str] = []
        for sid, state in self._runtime_state.items():
            if unmet := state.get("unmet"):
                if unmet["verdict"] == "unsolvable":
                    # 无解：产出不作数，只呈现无法完成的结论
                    lines.append(f"{sid}: 未能完成（{unmet['reason']}）")
                else:
                    # 降级接受：产出仍可用、下游已用，附局限说明
                    lines.append(
                        f"{sid}: {state.get('outputs')}（部分达成：{unmet['reason']}）"
                    )
            elif reason := state.get("skipped"):
                if reason == "upstream_unsolvable":
                    # 前序无解导致的级联跳过：如实呈现「因前序无法完成而未执行」，别当普通跳过。
                    lines.append(f"{sid}: 未执行（前序步骤无法完成，已级联跳过）")
                else:
                    lines.append(f"{sid}: skipped ({reason})")
            else:
                lines.append(f"{sid}: {state.get('outputs')}")
        return lines

    @property
    def unmet_goals(self) -> dict[str, dict[str, str]]:
        """success_check 失败且诊断为非 replan 的步骤：step_id -> {step_goal, verdict, reason}。
        verdict ∈ {"unsolvable", "degraded"}；供编排层按 verdict 分类降级最终回答。"""
        return self._unmet

    async def _diagnose_failure(
        self,
        step: PlanStepV1,
        success_check: SuccessCheck | None,
        message: str,
        outputs_snapshot: dict[str, Any],
        tool_output: Any,
        process_error: PlanErrorDetail | None = None,
    ) -> DiagnosisResult:
        """对一次 step 未达成做补救裁决（规则前置层 → 注入的把控 → 兜底）。

        三层，顺序固定：

        1. **规则前置层**（``_rule_based_diagnosis``）：确定性规则能定夺的（"数据确实不可得"
           之类）不占判定预算；它与"谁来判"无关，逐字保留原行为。
        2. **注入的把控**（判定点 ``DIAGNOSIS``）：只有当注入的实现声明承担该判定点时才用。
        3. **兜底**：jq 形态 + 有 model_api 时走原生成式诊断（原实现的路径）；否则保守默认
           重规划——绝不静默当成"无需补救"。
        """
        process_error_kind = process_error.kind if process_error is not None else None
        rule = _rule_based_diagnosis(
            op=step.op,
            process_error_kind=process_error_kind,
            failure_message=message,
        )
        if rule is not None:
            return DiagnosisResult(source="rule", decision=rule)

        if self._judge is not None and self._judge.supports(Point.DIAGNOSIS):
            # 通用裁剪：无论把控是 Jev 还是 LLM，看到的都是这份压缩后的 state。
            state = build_diagnosis_state(
                query=self._query,
                step=step,
                failure_message=message,
                outputs_snapshot=outputs_snapshot,
                tool_output=tool_output,
                process_error_kind=process_error_kind,
                policy=self._trim,
            )
            outcome = await self._judge.decide(Point.DIAGNOSIS, state)
            self._judgements.append(outcome)
            return DiagnosisResult(
                source=event_source(outcome.backend),  # type: ignore[arg-type]
                decision=outcome.decision.decision
                or Replan(
                    failed_assumption="补救诊断未给出裁决",
                    retry_direction="保守默认重规划",
                ),
            )

        if isinstance(success_check, JqExprCriterion) and self._model_api is not None:
            try:
                return await diagnose_success_check_failure(
                    query=self._query,
                    step_goal=step.step_goal,
                    op=step.op,
                    inputs=step.inputs,
                    success_check=success_check.expression,
                    outputs_snapshot=outputs_snapshot,
                    tool_output=_normalize_tool_output(tool_output),
                    failure_message=message,
                    process_error_kind=process_error_kind,
                    model_api=self._model_api,
                )
            except Exception as e:
                return DiagnosisResult(
                    source="fallback",
                    decision=Replan(
                        failed_assumption="补救诊断调用失败",
                        retry_direction=f"保守默认重规划：{e}",
                    ),
                )

        return DiagnosisResult(
            source="fallback",
            decision=Replan(
                failed_assumption="没有可用的补救诊断（未注入把控，且判据不是 jq 形态）",
                retry_direction="保守默认重规划",
            ),
        )

    def _eval_condition(self, condition: str) -> Any:
        """用 jq 对 self._runtime_state 求值表达式，隔离 jq 库的未类型化调用面。"""
        return jq.compile(condition).input_value(self._runtime_state).first()  # type: ignore

    def _eval_success_check(self, check: JqExprCriterion) -> str | None:
        """求值 jq 形态的达成判据，返回错误信息字符串，None 表示达成。

        与 condition 求值语义一致（jq 布尔式），但结果解读相反：
        求值抛异常、结果非布尔、或结果为 false，均视为 step_goal 未达成并返回错误说明；
        仅当结果严格为 True 时返回 None。
        """
        try:
            result = self._eval_condition(check.expression)
        except Exception as e:
            return f"success_check evaluation failed: {e}"
        if result is True:
            return None
        if result is False:
            return "success_check evaluated to false"
        return f"success_check must evaluate to a boolean, got {result!r}"

    def _resolve_ref_result(
        self, ref: str, step_id: str
    ) -> tuple[Any, InputRefErrorDetail | None]:
        """将 input 模板中的受限 jq path 解析为 runtime_state 中的实际值。

        jq 数组迭代（如 .s1.outputs.Song[].play_id）会产生多条结果；此时返回 list，
        用于保持批量投影的传参语义。普通 path 只产生一条结果，直接返回该值。
        """
        expr = ref.strip()
        if not expr.startswith("."):
            return None, InputRefErrorDetail(
                step_id=step_id,
                ref=expr,
                message="input ref must be a jq path starting with '.'",
            )
        try:
            values = jq.compile(expr).input_value(self._runtime_state).all()  # type: ignore
        except Exception as e:
            return None, InputRefErrorDetail(
                step_id=step_id,
                ref=expr,
                message=f"jq evaluation failed: {e}",
            )
        if len(values) == 0:
            return None, InputRefErrorDetail(
                step_id=step_id,
                ref=expr,
                message="jq evaluation returned no results",
            )
        if len(values) == 1:
            value = values[0]
        else:
            value = values
        # if value is None:
        #     return value, InputRefErrorDetail(
        #         step_id=step_id,
        #         ref=expr,
        #         message="jq evaluation returned null",
        #     )
        # if value == []:
        #     return value, InputRefErrorDetail(
        #         step_id=step_id,
        #         ref=expr,
        #         message="jq evaluation returned an empty list",
        #     )
        return value, None

    def _resolve_ref(self, ref: str) -> Any:
        """兼容旧调试脚本的便捷入口；运行时使用 _resolve_ref_result 保留错误明细。"""
        value, error = self._resolve_ref_result(ref, step_id="<unknown>")
        return None if error is not None else value

    def _resolve_value(
        self,
        v: Any,
        step_id: str = "<unknown>",
    ) -> tuple[Any, InputRefErrorDetail | None]:
        """递归解析值中的模板引用。"""
        if isinstance(v, str) and "{{" in v:
            if match := _REF_RE.fullmatch(v):
                return self._resolve_ref_result(match.group(1).strip(), step_id)

            def _sub(m: re.Match[str]) -> str:
                r, err = self._resolve_ref_result(m.group(1).strip(), step_id)
                if err is not None:
                    if nonlocal_error[0] is None:
                        nonlocal_error[0] = err
                    return ""
                return nl_repr(r, separator=", ", use_numbering=False)

            nonlocal_error: list[InputRefErrorDetail | None] = [None]
            rendered = _REF_RE.sub(_sub, v)
            return rendered, nonlocal_error[0]
        if isinstance(v, dict):
            d: dict[str, Any] = v  # type: ignore[assignment]
            resolved: dict[str, Any] = {}
            first_error: InputRefErrorDetail | None = None
            for k, val in d.items():
                resolved_val, error = self._resolve_value(val, step_id)
                resolved[k] = resolved_val
                if first_error is None and error is not None:
                    first_error = error
            return resolved, first_error
        if isinstance(v, list):
            lst: list[Any] = v  # type: ignore[assignment]
            resolved_list: list[Any] = []
            first_error: InputRefErrorDetail | None = None
            for item in lst:
                resolved_item, error = self._resolve_value(item, step_id)
                resolved_list.append(resolved_item)
                if first_error is None and error is not None:
                    first_error = error
            return resolved_list, first_error
        return v, None

    def _resolve_inputs(
        self,
        inputs: dict[str, Any],
        step_id: str = "<unknown>",
    ) -> tuple[dict[str, Any], InputRefErrorDetail | None]:
        """对步骤的 inputs dict 做全量引用解析。"""
        resolved: dict[str, Any] = {}
        first_error: InputRefErrorDetail | None = None
        for k, v in inputs.items():
            resolved_value, error = self._resolve_value(v, step_id)
            resolved[k] = resolved_value
            if first_error is None and error is not None:
                first_error = error
        return resolved, first_error
