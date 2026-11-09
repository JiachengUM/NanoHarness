"""Plan 编排引擎（稳定层）。

只放与具体 Plan schema 无关的稳定部分：DAG 构建、泛型的 create_plan、以及唯一的
plan-and-act 编排入口 :func:`astream_plact`。

PlanSpec 协议和工具描述生成见 plan_spec.py；事件类型见 events.py；
错误类型和 repair 数据结构见 errors.py。达成判据的两种形态见 criterion.py。

一个模式 + 注入的把控
---------------------
plact 只有**一条**流水线（``preflight → plan → audit → run → repair/gate → finish``），
没有开关矩阵。唯一可变的是**注入的把控**（``judge``，见 :mod:`aicore.agents.plan.judge`）：

- 额外的把控（preflight / plan_audit / diagnosis / round_gate / finish）做不做，由注入的实现用
  ``supports()`` 声明；core 里没有 ``enable_*``，只有 ``if judge.supports(point)``。
- 达成判据的形态由 ``judge.criterion`` 注入：把控是 LLM / Jev 时用自然语言断言（谁来判就是
  把控自己），**不注入把控**时退回 jq（规则层确定性求值）——那是"没有把控"的退化，不是第二套编排。
- 把控不可用时怎么退，也由实现自己决定（Jev 直接抛错、LLM 转保守裁决），core 不感知。

计划生成（``create_plan``）与原实现共用同一份实现（``spec.build_sys_prompt`` / 结构化输出 /
repair 上下文），差别只多一个注入的 ``criterion``。
"""

import json
from contextlib import aclosing
from typing import Any, AsyncGenerator

from pydantic import BaseModel

from aicore.models.model_api import UserMessage, ModelState, ModelAPI, ModelCallParams
from aicore.tools import ToolProtocol
from aicore.utils.nl_repr import nl_repr

from aicore.agents.plan.criterion import (
    KIND_ASSERTION,
    KIND_JQ,
    CriterionKind,
    bind_criterion,
    kind_mismatch_message,
    mismatched_step_ids,
)
from aicore.agents.plan.events import (
    FinishOutcome,
    JudgeDecisionEvent,
    PlActFinishEvent,
    PlActRoundStartEvent,
    PlActErrorsEvent,
    PlanCreatedEvent,
    PlanStepStartedEvent,
    PlanStepAssertStartedEvent,
    PlanStepAssertCompletedEvent,
    PlanStepDiagnosisStartedEvent,
    PlanStepDiagnosisCompletedEvent,
    PlanStepDoneEvent,
    PlanRunnerErrorEvent,
    PlActEvent,
    is_plact_event,
)
from aicore.agents.plan.judge import JudgeOutcome, PlanJudge, Point
from aicore.agents.plan.plan_spec import PlanSpec, generate_tools_description
from aicore.agents.plan.errors import (
    PlanError,
    RepairPolicy,
    PlanRepairContext,
    SchemaErrorDetail,
    SemanticGapError,
)
from aicore.agents.plan.plan_dag_runner import PlanDAGRunner
from aicore.agents.plan.trim import (
    DEFAULT_TRIM,
    TrimPolicy,
    build_finish_state,
    build_plan_audit_state,
    build_preflight_state,
    build_round_gate_state,
)

__all__ = [
    "generate_tools_description",
    "PlanSpec",
    "PlanError",
    "RepairPolicy",
    "PlanRepairContext",
    "PlActFinishEvent",
    "PlActRoundStartEvent",
    "PlActErrorsEvent",
    "PlanCreatedEvent",
    "PlanStepStartedEvent",
    "PlanStepAssertStartedEvent",
    "PlanStepAssertCompletedEvent",
    "PlanStepDiagnosisStartedEvent",
    "PlanStepDiagnosisCompletedEvent",
    "PlanStepDoneEvent",
    "PlanRunnerErrorEvent",
    "JudgeDecisionEvent",
    "PlActEvent",
    "is_plact_event",
    "create_plan",
    "astream_plact",
    "derive_execution_outcome",
]

# 判定完成后、最终回答的补充要求：疑似虚构时重生成一次回答。
_FABRICATION_RETRY = 0.5

_CLARIFY_INSTRUCTION = (
    "用户的请求缺少关键信息，无法直接执行。请只用一句口语化的话向用户问清缺失的关键信息："
    "直接问、不要解释、不要道歉、不要给方案。\n"
    "用户请求：{query}"
)

_FABRICATION_GUARD = (
    "再次强调：上面的步骤结果里有子目标并未真正完成。你的回答中**不得**声称已经完成它们，"
    "必须如实说明哪些部分没有做到、以及原因。"
)


def _structured_output_failure_message(result: Any, fallback: str) -> str:
    metadata = getattr(result, "metadata", {})
    metadata_text = json.dumps(metadata, ensure_ascii=False, default=str)
    return f"{fallback}; metadata={metadata_text}"


def _format_repair_message(ctx: PlanRepairContext) -> str:
    """将上一轮的 repair context 格式化为用户消息文本。

    属于编排层职责：错误由 core 定义，如何向 LLM 陈述错误也由 core 决定，
    与 plan schema 结构无关。按 policy 决定要求 LLM 做全量重生成还是局部更新。
    """
    if ctx.policy == RepairPolicy.REGENERATE_PLAN:
        error_lines = "\n".join(f"- {e.nl_repr()}" for e in ctx.errors)
        return (
            f"上一轮计划（第 {ctx.round} 轮）出现以下错误，请修正后重新输出完整计划：\n"
            f"{error_lines}"
        )
    if ctx.policy == RepairPolicy.REGENERATE_STEP:
        step_lines = "\n".join(f"- {e.nl_repr()}" for e in ctx.errors)
        plan_lines = (
            nl_repr(ctx.failed_plan.model_dump(mode="json"))
            if ctx.failed_plan is not None
            else "（无可用的上一轮计划）"
        )
        return (
            f"上一轮计划（第 {ctx.round} 轮）中以下步骤出错，请重新输出完整计划，"
            f"并修正这些步骤：\n{step_lines}\n\n上一轮计划：\n{plan_lines}"
        )
    raise ValueError(f"unexpected repair policy for _format_repair_message: {ctx.policy}")


async def create_plan[StateT: ModelState, TT: ToolProtocol[BaseModel], PlanT: BaseModel](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    tools: list[TT],
    spec: PlanSpec[PlanT],
    criterion: CriterionKind,
    params: ModelCallParams | None = None,
    repair_context: PlanRepairContext | None = None,
    state: StateT | None = None,
) -> tuple[PlanT, StateT]:
    """用指定 spec 生成结构化 Plan，返回 (plan, updated_state)。

    ``criterion`` 是**注入**的达成判据形态（由把控决定，见 :func:`astream_plact`），它同时决定：

    1. 系统提示词里唯一变化的那一段——经 :func:`~aicore.agents.plan.criterion.bind_criterion`
       把形态绑到 spec 上再取提示词（不实现该能力的历史 spec 原样使用其冻结提示词）；
    2. 解析后的形态校验——模型写了另一种形态时按 ``plan.schema`` 错误上抛，进 repair 轮
       （错误文案里带明确要求），而不是静默接受一个没人能判的判据。

    state 可由调用方从 provider-neutral history 重建，也可在 repair 轮中续接上一轮
    planning state。repair_context 非 None 时发送格式化修复消息；否则发送当前 query。
    state 为 None 时先从 spec.build_sys_prompt 创建全新 state。
    """
    if state is None:
        state = model_api.initial_state(
            system_prompt=bind_criterion(spec, criterion).build_sys_prompt(tools)
        )

    msg = UserMessage(
        text=(
            _format_repair_message(repair_context)
            if repair_context is not None
            else query
        )
    )

    result = await model_api.structured_output(
        msg,
        output_type=spec.plan_type,
        state=state,
        params=params,
    )
    if result.parsed is None:
        raise ValueError(_structured_output_failure_message(result, "structured plan generation failed"))

    plan = result.parsed
    wrong = mismatched_step_ids(plan, criterion)
    if wrong:
        # 形态不符 = 这步的判据没人能判：当作 schema 错误退回修复轮（提示词里已写明要求，
        # 这里再把"该怎么改"复述一遍）。
        raise ValueError(kind_mismatch_message(criterion, wrong))
    return plan, result.state


def _decision_event(outcome: JudgeOutcome[Any]) -> JudgeDecisionEvent:
    """判定结果 → 事件（裁决 + 原子答案 + 耗时，供 trace 与离线校准统计）。"""
    return JudgeDecisionEvent(
        stage=outcome.point,
        backend=outcome.backend,
        decision=outcome.decision,
        answers=outcome.answers,
        latency_ms=outcome.latency_ms,
    )


def _judged(judge: PlanJudge | None, point: Point) -> bool:
    """该判定点这次跑不跑：**唯一**的开关就是被注入的实现声明它承担不承担。"""
    return judge is not None and judge.supports(point)


async def astream_plact[
    StateT: ModelState, TT: ToolProtocol[BaseModel], PlanT: BaseModel
](
    query: str,
    *,
    model_api: ModelAPI[StateT],
    state: StateT,
    tools: list[TT],
    spec: PlanSpec[PlanT],
    judge: PlanJudge | None = None,
    plan_state: StateT | None = None,
    max_turns: int = 5,
    params: ModelCallParams | None = None,
    trim_policy: TrimPolicy = DEFAULT_TRIM,
    retry_on_fabrication: bool = False,
) -> AsyncGenerator[PlActEvent, None]:
    """判据驱动的 plan-and-act（plact 的唯一入口：计划 → 执行 → 修复 → 收尾）。

    流程（每轮）：
    1. yield PlActRoundStartEvent（标识轮次边界，用于 trace）
    2. ``create_plan`` 生成结构化计划，yield PlanCreatedEvent
    3. （若把控承担 PLAN_AUDIT）执行前的语义审计：不过 → plan.semantics 错误 → 整图重规划
    4. 执行 DAG：每个 step 按其判据形态做达成判定（断言 → 把控；jq → 规则层），
       未达成 → 补救裁决（replan 走 PlanRunnerErrorEvent / 无解与降级走 unmet）
    5. 有错误：yield PlActErrorsEvent；（若把控承担 ROUND_GATE）闸门决定继续 / 止损 / 判无解
    6. repair 轮：错误打包成 PlanRepairContext，下一轮 create_plan 携带它重新生成
    最后：汇总各步结果生成最终回答（+ 若把控承担 FINISH，做收尾评估），yield PlActFinishEvent。

    ``judge`` 是这一版**唯一**的变体来源：
    - ``judge=None``：没有把控，判据是 jq（规则层求值），入口不分流、执行前不审计、
      轮次按 max_turns 收敛、收尾用代码可推的结论——即"原实现"的行为；
    - 注入把控：额外把控取它的 ``supports()``，判据形态取它的 ``criterion``。

    ``retry_on_fabrication`` 默认关闭：它会在疑似虚构时多打一次生成式调用（额外成本换诚实度）。
    """
    criterion = judge.criterion if judge is not None else KIND_JQ
    if criterion == KIND_ASSERTION and not _judged(judge, Point.STEP_ASSERT):
        raise ValueError(
            "达成判据形态是自然语言断言，但没有注入承担 step_assert 的把控："
            "计划里的达成判据会没人判定（静默放行）。请注入把控，或让判据退回 jq 形态。"
        )

    # ── 阶段 0：入口分流（没有把控时没有这个状态，永远进 plan）────────────────
    preflight = None
    if _judged(judge, Point.PREFLIGHT):
        assert judge is not None
        preflight_outcome = await judge.decide(
            Point.PREFLIGHT,
            build_preflight_state(query=query, tools=tools, policy=trim_policy),
        )
        yield _decision_event(preflight_outcome)
        preflight = preflight_outcome.decision

    if preflight is not None and preflight.path in ("direct", "clarify"):
        async for event in _answer_without_plan(
            query=query,
            model_api=model_api,
            state=state,
            judge=judge,
            path=preflight.path,
            params=params,
            trim_policy=trim_policy,
            rationale=preflight.rationale,
        ):
            yield event
        return

    # ── 阶段 1：plan →（审计）→ 执行 →（闸门）→ repair 循环 ────────────────
    repair_context: PlanRepairContext | None = None
    runner: PlanDAGRunner | None = None
    errors: list[PlanError] = []
    failures: list[dict[str, Any]] = []
    round_notes: list[str] = []
    steps_done = 0
    turn = 0
    # plan 必须在循环外初始化：首轮 create_plan 就抛异常时，收尾评估仍会引用它。
    plan: PlanT | None = None

    for turn in range(max_turns):
        yield PlActRoundStartEvent(round=turn, repair_context=repair_context)
        errors = []
        plan = None
        aborted = False
        # 本轮的 runner（与跨轮的 `runner` 区分：审计阶段终止时 runner 还是上一轮的）。
        runner_this_round: PlanDAGRunner | None = None

        # ── plan 生成 ──────────────────────────────────────────────────────
        try:
            plan, plan_state = await create_plan(
                query,
                model_api=model_api,
                tools=tools,
                spec=spec,
                criterion=criterion,
                params=params,
                repair_context=repair_context,
                state=plan_state,
            )
        except Exception as e:
            errors = [
                PlanError(source="plan.schema", detail=SchemaErrorDetail(message=str(e)))
            ]
            aborted = True

        if not aborted:
            assert plan is not None
            yield PlanCreatedEvent(plan=plan, round=turn)

            # ── 计划语义审计：执行**之前**拦下语义缺陷 ────────────────────
            # dag_checker 只查语法/引用形状；"按字面完美执行也满足不了用户"这类缺陷原本
            # 要等执行完、判据判 false 才暴露，代价是一整层工具调用（还可能有副作用）。
            if _judged(judge, Point.PLAN_AUDIT):
                assert judge is not None and plan is not None
                audit_outcome = await judge.decide(
                    Point.PLAN_AUDIT,
                    build_plan_audit_state(query=query, plan=plan, policy=trim_policy),
                )
                yield _decision_event(audit_outcome)
                audit = audit_outcome.decision
                if not audit.passed:
                    errors = [
                        PlanError(
                            source="plan.semantics",
                            detail=SemanticGapError(
                                gap_kind=audit.gap_kind,
                                coverage=audit.coverage,
                                check_strictness=audit.check_strictness,
                                rationale=audit.rationale,
                            ),
                        )
                    ]
                    aborted = True

        # ── 执行 DAG ──────────────────────────────────────────────────────
        if not aborted and not errors:
            assert plan is not None
            runner_this_round = PlanDAGRunner(
                tools=tools,  # type: ignore[arg-type]
                model_api=model_api,
                query=query,
                judge=judge,
                trim_policy=trim_policy,
            )
            runner = runner_this_round
            async with aclosing(
                runner.run(spec.build_dag(plan))  # type: ignore[arg-type]
            ) as run_gen:
                async for event in run_gen:
                    if isinstance(event, PlanStepDoneEvent):
                        steps_done += 1
                    yield event
                    # 判定结果（诊断 / 断言验收）在事件之后 drain 成独立事件。
                    for judgement in runner.drain_judgements():
                        yield _decision_event(judgement)
                    # 与原生一致：只做层间打断，本层已并行发出的调用不取消。
                    if isinstance(event, PlanRunnerErrorEvent):
                        errors.extend(event.errors)
                        break

        if not errors:
            break  # 本轮无错误：成功出口

        yield PlActErrorsEvent(round=turn, errors=errors, policy=RepairPolicy.REGENERATE_PLAN)
        failures.extend(_failure_records(turn, errors, runner_this_round))

        if turn == max_turns - 1:
            break  # 轮次耗尽

        repair_context = PlanRepairContext(
            errors=errors,
            failed_plan=plan,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=turn + 1,
        )

        # ── 轮次闸门：还值不值得再修一轮 ──────────────────────────────────
        # 没有把控时只有"errors 非空 → 再修" + 固定 max_turns，既不知道有没有希望，
        # 也不知道这个错是不是已经修了好几轮的同一个（跨轮证据在 failures 里）。
        if _judged(judge, Point.ROUND_GATE):
            assert judge is not None
            gate_outcome = await judge.decide(
                Point.ROUND_GATE,
                build_round_gate_state(
                    query=query,
                    round_no=turn,
                    max_turns=max_turns,
                    errors=errors,
                    failures=failures,
                    policy=trim_policy,
                ),
            )
            yield _decision_event(gate_outcome)
            gate = gate_outcome.decision
            if gate.action != "continue":
                if gate.action == "mark_unsolvable":
                    round_notes.append(
                        "以下子目标经多轮重规划仍未达成，请如实向用户说明无法完成，"
                        f"不要谎称已完成：{'、'.join(_failed_goals(errors, runner_this_round))}"
                    )
                break

    # ── 阶段 2：汇总并生成最终回答 ─────────────────────────────────────────
    unmet = runner.unmet_goals if runner else {}
    results_text = "\n".join(runner.step_results) if runner else ""
    notes = _unmet_notes(unmet) + round_notes
    note_text = ("\n\n注意：\n- " + "\n- ".join(notes)) if notes else ""

    answer_msg = UserMessage(
        text=f"各步骤执行结果如下：\n{results_text}{note_text}\n\n请根据以上结果，回答用户的问题：{query}"
    )
    response = await model_api.invoke(answer_msg, state=state, params=params)
    final_text = response.text

    if errors:
        reason: str | None = errors[0].nl_repr()
    elif unmet:
        reason = "存在未达成子目标：" + "；".join(
            f"{v['step_goal']}（{v['verdict']}: {v['reason']}）" for v in unmet.values()
        )
    else:
        reason = None

    confidence: float | None = None
    reported: float | None = None
    ask_user: float | None = None
    forced = bool(errors) or bool(unmet)
    if _judged(judge, Point.FINISH):
        assert judge is not None
        finish_outcome = await judge.decide(
            Point.FINISH,
            build_finish_state(
                query=query,
                plan=plan,
                step_outputs=runner.runtime_state if runner else {},
                step_results=runner.step_results if runner else [],
                unmet=unmet,
                final_response=final_text,
                forced=forced,
                reason=reason,
                policy=trim_policy,
            ),
        )
        yield _decision_event(finish_outcome)
        finish = finish_outcome.decision
        # 评估没做成时（assessed=False）不编造置信度，退回"没有收尾评估"的行为。
        confidence = finish.effective_confidence() if finish.assessed else None
        reported = finish.confidence_reported if finish.assessed else None
        ask_user = finish.ask_user_worth if finish.assessed else None

        # 疑似虚构：给一次如实重述的机会。默认关闭（多一次生成式调用，先度量判定质量）。
        if retry_on_fabrication and finish.fabricated > _FABRICATION_RETRY:
            follow_up = UserMessage(text=f"{answer_msg.text}\n\n{_FABRICATION_GUARD}")
            response = await model_api.invoke(
                follow_up, state=getattr(response, "state", state), params=params
            )
            final_text = response.text

    yield PlActFinishEvent(
        response=final_text,
        round=turn,
        forced=forced,
        reason=reason,
        confidence=confidence,
        confidence_reported=reported,
        outcome=derive_execution_outcome(
            errors=errors, unmet=unmet, steps_done=steps_done
        ),
        ask_user_worth=ask_user,
    )


def derive_execution_outcome(
    *, errors: list[PlanError], unmet: dict[str, dict[str, str]], steps_done: int
) -> FinishOutcome:
    """结局归类：**代码可推的部分不占判定预算**。

    - 一个 step 都没跑成且错误都在 plan 层（schema/logic/semantics）→ not_executed；
    - 有未解决错误或未达成子目标 → partial；
    - 其余 → success。

    ``FinishDecision.outcome`` 仍会被把控给出并落进事件：两者的一致性本身是一项可观测量
    （把控说 success 而代码判 partial，就是一次误判）。
    """
    plan_level = {"plan.schema", "plan.logic", "plan.semantics"}
    if steps_done == 0 and errors and all(e.source in plan_level for e in errors):
        return "not_executed"
    if errors or unmet:
        return "partial"
    return "success"


async def _answer_without_plan[
    StateT: ModelState,
](
    *,
    query: str,
    model_api: ModelAPI[StateT],
    state: StateT,
    judge: PlanJudge | None,
    path: str,
    params: ModelCallParams | None,
    trim_policy: TrimPolicy,
    rationale: str,
) -> AsyncGenerator[PlActEvent, None]:
    """入口分流判为 direct / clarify：跳过 plan 与 DAG，一次生成 + 一次收尾评估。

    ``clarify`` 需要一句面向用户的问句——这是**生成**职责，仍交给 LLM；
    把控只负责判断"该不该问"，分工不混。
    """
    message = (
        UserMessage(text=_CLARIFY_INSTRUCTION.format(query=query))
        if path == "clarify"
        else UserMessage(text=query)
    )
    response = await model_api.invoke(message, state=state, params=params)
    final_text = response.text

    forced = path == "clarify"
    reason = f"入口分流判定为 {path}：{rationale}"
    confidence: float | None = None
    reported: float | None = None
    ask_user: float | None = None
    outcome: FinishOutcome = "clarify" if forced else "success"

    if _judged(judge, Point.FINISH):
        assert judge is not None
        finish_outcome = await judge.decide(
            Point.FINISH,
            build_finish_state(
                query=query,
                plan=None,
                step_outputs={},
                step_results=[],
                unmet={},
                final_response=final_text,
                forced=forced,
                reason=reason,
                policy=trim_policy,
            ),
        )
        yield _decision_event(finish_outcome)
        finish = finish_outcome.decision
        confidence = finish.effective_confidence() if finish.assessed else None
        reported = finish.confidence_reported if finish.assessed else None
        ask_user = finish.ask_user_worth if finish.assessed else None

    yield PlActFinishEvent(
        response=final_text,
        round=0,
        forced=forced,
        reason=reason,
        confidence=confidence,
        confidence_reported=reported,
        outcome=outcome,
        ask_user_worth=ask_user,
    )


def _failure_records(
    round_no: int, errors: list[PlanError], runner: PlanDAGRunner | None
) -> list[dict[str, Any]]:
    """把一轮的失败归一成"跨轮失败记忆"的一条条记录（轮次闸门的证据）。

    runner 每轮新建、自身没有记忆，所以"同一 goal 换 approach 后仍失败"这个证据门槛
    必须由编排层累积。记录保持扁平且短，便于放进判定器 state 的预算。
    """
    records: list[dict[str, Any]] = []
    for error in errors:
        records.append(
            {
                "round": round_no,
                "step_id": getattr(error.detail, "step_id", None),
                "source": error.source,
                "kind": getattr(error.detail, "kind", None),
                "detail": nl_repr(error.detail),
            }
        )
    if runner is not None:
        for step_id, info in runner.unmet_goals.items():
            records.append(
                {
                    "round": round_no,
                    "step_id": step_id,
                    "source": "step.unmet",
                    "kind": info.get("verdict"),
                    "detail": info.get("reason", ""),
                }
            )
    return records


def _failed_goals(errors: list[PlanError], runner: PlanDAGRunner | None) -> list[str]:
    """从本轮错误/unmet 里取出一句人话的子目标描述（供最终回答的诚实说明使用）。"""
    goals: list[str] = []
    unmet = runner.unmet_goals if runner is not None else {}
    for error in errors:
        step_id = getattr(error.detail, "step_id", None)
        if step_id in unmet:
            goals.append(str(unmet[step_id].get("step_goal", step_id)))
        elif step_id:
            goals.append(f"步骤 {step_id}（{error.source}）")
        else:
            goals.append(f"计划整体（{error.source}）")
    for step_id, info in unmet.items():
        goal = str(info.get("step_goal", step_id))
        if goal not in goals:
            goals.append(goal)
    return goals or ["（未指明具体子目标）"]


def _unmet_notes(unmet: dict[str, dict[str, str]]) -> list[str]:
    """未达成子目标 → 最终回答里必须如实说明的注意事项（与原实现同构）。"""
    unsolvable = [v for v in unmet.values() if v["verdict"] == "unsolvable"]
    degraded = [v for v in unmet.values() if v["verdict"] == "degraded"]
    notes: list[str] = []
    if unsolvable:
        s = "；".join(f"{v['step_goal']}（{v['reason']}）" for v in unsolvable)
        notes.append(f"以下子目标经判定无法完成，请如实向用户说明，不要谎称已完成：{s}")
    if degraded:
        s = "；".join(f"{v['step_goal']}（{v['reason']}）" for v in degraded)
        notes.append(f"以下子目标只是部分达成、结果不完美，请在回答中说明其局限：{s}")
    return notes
