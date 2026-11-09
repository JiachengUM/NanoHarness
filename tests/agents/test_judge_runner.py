"""Jev 版 runner（``PlanDAGRunner``）的路由单测——完全离线。

要冻结的行为：
1. 规则前置层的分支**与原实现完全一致**，且命中规则时**不打判定器**（省一次判定往返）；
2. 未命中规则时裁决来自判定器，并如实标进 ``DiagnosisResult.source``（"jev"）；
3. 三种裁决的路由与原生语义一致：replan → PlanRunnerErrorEvent；skip_unsolvable → unmet +
   下游级联 skip；accept_degraded → unmet 但下游照常；
4. **断言验收**（改用自然语言断言后的达成判定）：断言逐条判三态——被证伪 → 交补救方程
   （replan / 无解 / 降级），无证据 → 降级接受（产出保留、下游照常），全部成立 → 达成。
   它与补救裁决是同一次判定，不再有"结构检查过了再补一刀"的短路；
5. 判定器失败直接抛出（不静默降级）；
6. **判据可靠性分流**（A 轴，与三态正交）：被证伪的断言全部“不可靠”时分两支——
   invented（判据是计划自设的）→ 忽略断言结论、改看 goal（达成就干净放行）；
   unverifiable/低置信（判不了）→ 不判失败也不拿 goal 当依据，保产出 + 降级披露；
   只要有一条 grounded 且确信的断言被证伪 → 真失败。防洗白：goal 低时一律交补救方程。
"""

from __future__ import annotations

from typing import Any

import pytest

from aicore.agents.plan.events import (
    PlanRunnerErrorEvent,
    PlanStepDoneEvent,
    PlanStepSkippedEvent,
)
from tests.agents._fake_jev import choice_answer, noul_answer
from aicore.agents.plan.events import (
    PlanStepAssertCompletedEvent,
    PlanStepAssertStartedEvent,
)
from aicore.agents.plan.judges.points import (
    CAUSE_DATA_ABSENT,
    CAUSE_PLAN_MISTAKE,
    CLAUSE_FALSIFIED,
    CLAUSE_UNSUPPORTED,
    QUALITY_GROUNDED,
    QUALITY_INVENTED,
    QUALITY_UNVERIFIABLE,
    Q_ASSERT_GOAL,
    Q_DIAG_BLOCKING,
    Q_DIAG_CAUSE,
    Q_DIAG_HARD,
    Q_DIAG_RETRY,
    Q_DIAG_USABLE,
    clause_quality_question_id,
    clause_question_id,
)
from aicore.agents.plan.plan_dag_runner import PlanDAGRunner

from tests.agents._judge_helpers import RejectingJudge, ScriptedJudge, make_tool
from tests.agents._plan_verify_helpers import build, outputs, step

FAILING_CHECK = '.s1.outputs.Out.field == "expected"'
PASSING_CHECK = '(.s1.outputs.Out.field // "") != ""'


def _step(step_id: str, **kwargs: Any) -> Any:
    """构一个"工具返回 dict、concept 单对象"的 step，保证投影走 passthrough（不打模型）。"""
    sid = step_id

    def check(template: str) -> str:
        return template.replace("s1", sid)

    if kwargs.pop("fails", False):
        kwargs["success_check"] = check(FAILING_CHECK)
    return step(
        step_id,
        step_outputs=outputs("Out", is_list=False, attributes=["field"]),
        **kwargs,
    )


async def _collect(runner: PlanDAGRunner, dag: Any) -> tuple[list[Any], list[Any]]:
    """跑一遍 runner，返回（事件, 判定结果）。"""
    events: list[Any] = []
    judgements: list[Any] = []
    async for event in runner.run(dag):
        events.append(event)
        judgements.extend(runner.drain_judgements())
    return events, judgements


def _done(events: list[Any], step_id: str) -> PlanStepDoneEvent:
    return next(e for e in events if isinstance(e, PlanStepDoneEvent) and e.step_id == step_id)


def _skipped(events: list[Any], step_id: str) -> PlanStepSkippedEvent:
    return next(e for e in events if isinstance(e, PlanStepSkippedEvent) and e.step_id == step_id)


def _ast_step(step_id: str, assertion: list[str], **kwargs: Any) -> Any:
    """带自然语言断言的 step：工具返回 dict、concept 单对象，投影走 passthrough。"""
    return step(
        step_id,
        assertion=assertion,
        step_outputs=outputs("Out", is_list=False, attributes=["field"]),
        **kwargs,
    )


def _make_runner(scripted: ScriptedJudge, **kwargs: Any) -> PlanDAGRunner:
    return PlanDAGRunner([], model_api=None, query="查一下北京天气", judge=scripted.judge, **kwargs)


# ────────────────────────── 规则前置层优先，且不打判定器 ──────────────────────────


@pytest.mark.anyio
async def test_rule_layer_short_circuits_without_calling_judge():
    """工具执行失败 → 规则层直接判 replan；判定器一次都不该被调用。"""
    scripted = ScriptedJudge()
    tools = [make_tool("op", value=None, raises=True)]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=scripted.judge)
    events, judgements = await _collect(runner, build([_step("s1", op="op", inputs={"q": "x"})]))

    error_events = [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].errors[0].source == "step.remediation"
    assert judgements == []
    assert scripted.calls_for("diagnosis") == []


# ──────────── 判定器接管补救裁决（中间配置：jq 判据 + 断言验收关闭）────────────
#
# 这三条钉的是 DIAGNOSIS 判定点的路由：判据是 jq 形态时，未通过就交诊断判定点
# （断言形态则把"验收 + 补救"并进一次 step_assert，见下一段）。


@pytest.mark.anyio
async def test_judge_replan_routes_to_runner_error_event():
    scripted = ScriptedJudge(
        diagnosis={
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.9),
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.2),
        }
    )
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(
        tools, model_api=None, query="q", judge=scripted.judge
    )
    events, judgements = await _collect(
        runner, build([_step("s1", op="op", inputs={"q": "x"}, fails=True)])
    )

    error_events = [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].errors[0].source == "step.remediation"
    assert "换一条仍忠于用户意图的做法重试" in error_events[0].errors[0].detail.diagnosis_reason
    # 判定器确实被问到了，且带回了原子答案（供离线校准统计）
    assert [j.point for j in judgements] == ["diagnosis"]
    assert judgements[0].backend == "jev"
    assert set(judgements[0].answers) >= {Q_DIAG_HARD, Q_DIAG_RETRY, Q_DIAG_CAUSE}


@pytest.mark.anyio
async def test_judge_unsolvable_marks_unmet_and_cascades_to_downstream():
    scripted = ScriptedJudge(
        diagnosis={
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_DATA_ABSENT),
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.95),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.1),  # 换 approach 也没戏
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.1),
        }
    )
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(
        tools, model_api=None, query="q", judge=scripted.judge
    )
    steps = [
        _step("s1", op="op", inputs={"q": "x"}, fails=True),
        _step(
            "s2",
            op="op",
            depends_on=["s1"],
            inputs={"q": "{{ .s1.outputs.Out.field }}"},
            success_check=PASSING_CHECK.replace("s1", "s2"),
        ),
    ]
    events, _ = await _collect(runner, build(steps))

    assert not [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert _done(events, "s1").unmet is not None
    assert _done(events, "s1").unmet.verdict == "unsolvable"
    assert _skipped(events, "s2").reason == "upstream_unsolvable"
    assert runner.unmet_goals["s1"]["verdict"] == "unsolvable"


@pytest.mark.anyio
async def test_judge_degraded_marks_unmet_but_keeps_downstream_running():
    scripted = ScriptedJudge(
        diagnosis={
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.1),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.9),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.1),
        }
    )
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(
        tools, model_api=None, query="q", judge=scripted.judge
    )
    steps = [
        _step("s1", op="op", inputs={"q": "x"}, fails=True),
        _step(
            "s2",
            op="op",
            depends_on=["s1"],
            inputs={"q": "{{ .s1.outputs.Out.field }}"},
            success_check=PASSING_CHECK.replace("s1", "s2"),
        ),
    ]
    events, _ = await _collect(runner, build(steps))

    assert _done(events, "s1").unmet is not None
    assert _done(events, "s1").unmet.verdict == "degraded"
    # 下游照常执行（降级接受 ≠ 阻塞）
    assert _done(events, "s2").unmet is None
    assert not [e for e in events if isinstance(e, PlanStepSkippedEvent)]


# ────────────────────────── 断言验收 + 补救裁决（一次判定）──────────────────────────


def _clause_override(index: int, verdict: str) -> dict[str, Any]:
    qid = clause_question_id(index)
    return {qid: choice_answer(qid, verdict)}


def _quality_override(index: int, quality: str) -> dict[str, Any]:
    """A 轴（判据可靠性）的覆盖：与三态覆盖正交，可同时使用。"""
    qid = clause_quality_question_id(index)
    return {qid: choice_answer(qid, quality)}


# ────────────────────────── 判据可靠性分流（A 轴） ──────────────────────────

# 一个“计划自设的判据被证伪”现场：用户只说“找一家”，计划却断言“至少返回5家”。
# 实测判定器对这条结论很确信（conf=0.94），所以能救它的只能是 A 轴。
_INVENTED_FALSIFIED = (
    _clause_override(0, CLAUSE_FALSIFIED)
    | _quality_override(0, QUALITY_INVENTED)
    | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
)


def _replans(events: list[Any]) -> bool:
    return bool([e for e in events if isinstance(e, PlanRunnerErrorEvent)])


def _remediation_source(events: list[Any]) -> str | None:
    for event in events:
        if isinstance(event, PlanRunnerErrorEvent) and event.errors:
            return event.errors[0].source
    return None


def _runner(scripted: ScriptedJudge, tools: list[Any]) -> PlanDAGRunner:
    return PlanDAGRunner(
        tools, model_api=None, query="用户要找一家评分高的烤鸭店", judge=scripted.judge
    )


@pytest.mark.anyio
async def test_invented_clause_is_ignored_and_goal_decides():
    """判据是计划自设的（用户没要求“至少5家”）→ 断言结论不作数，改看 goal。

    默认 goal=0.95（达成）→ 干净放行：既不重规划，也不产生 unmet（断言的失败本就不该
    变成对用户的披露——没人要求过 5 家）。
    """
    scripted = ScriptedJudge(step_assert=_INVENTED_FALSIFIED)
    tools = [make_tool("op", value={"field": "actual"})]
    events, _ = await _collect(
        _runner(scripted, tools),
        build([_ast_step("s1", ["至少返回5家"], op="op", inputs={"q": "x"})]),
    )

    assert not _replans(events), "自设判据不该把整张图打回重规划"
    done = _done(events, "s1")
    assert done.unmet is None and done.process_error is None
    completed = next(e for e in events if isinstance(e, PlanStepAssertCompletedEvent))
    assert completed.decision.passed is True
    assert completed.decision.assert_verdict_ignored is True
    assert completed.decision.clause_quality == [QUALITY_INVENTED]
    assert completed.decision.unreliable_clauses == [0]


@pytest.mark.anyio
async def test_invented_clause_with_low_goal_still_replans():
    """防洗白：判据是自设的，但该步目标本身也没达成 → 照旧交补救方程。

    否则“这条断言过严”就会变成把“没做到”包装成放行的合法通道。
    """
    scripted = ScriptedJudge(
        step_assert=_INVENTED_FALSIFIED
        | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.3)}  # < ASSERT_GOAL_FLOOR
    )
    tools = [make_tool("op", value={"field": "actual"})]
    events, _ = await _collect(
        _runner(scripted, tools),
        build([_ast_step("s1", ["至少返回5家"], op="op", inputs={"q": "x"})]),
    )

    assert _remediation_source(events) == "step.remediation"


@pytest.mark.anyio
async def test_unverifiable_clause_degrades_without_consulting_goal():
    """判不了的判据既不判失败、也**不拿 goal 当依据**（goal 同样被这条断言带偏）。"""
    scripted = ScriptedJudge(
        step_assert=(
            _clause_override(0, CLAUSE_FALSIFIED)
            | _quality_override(0, QUALITY_UNVERIFIABLE)
            | {Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.2)}  # goal 不可信
            | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
        )
    )
    tools = [make_tool("op", value={"field": "actual"})]
    events, _ = await _collect(
        _runner(scripted, tools),
        build([_ast_step("s1", ["这家店当前正在营业"], op="op", inputs={"q": "x"})]),
    )

    assert not _replans(events)
    done = _done(events, "s1")
    assert done.unmet is not None and done.unmet.verdict == "degraded"
    assert "无法用产出判定" in done.unmet.reason


@pytest.mark.anyio
async def test_grounded_clause_falsified_still_replans():
    """防洗白：只要有一条“用户明说”的判据被证伪，就是真失败。"""
    scripted = ScriptedJudge(
        step_assert=_clause_override(0, CLAUSE_FALSIFIED)
        | _quality_override(0, QUALITY_GROUNDED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    tools = [make_tool("op", value={"field": "actual"})]
    events, _ = await _collect(
        _runner(scripted, tools),
        build([_ast_step("s1", ["结果与用户要的 expected 一致"], op="op", inputs={"q": "x"})]),
    )

    assert _remediation_source(events) == "step.remediation"


@pytest.mark.anyio
async def test_assert_all_clauses_hold_marks_step_done():
    """断言全部成立 → 达成，且判定点确实是 step_assert（不再是 jq 判据 + 语义补刀两个点）。"""
    scripted = ScriptedJudge()
    tools = [make_tool("op", value={"field": "expected"})]
    runner = PlanDAGRunner(tools, model_api=None, query="用户要 expected", judge=scripted.judge)
    events, judgements = await _collect(
        runner,
        build([_ast_step("s1", ["结果与用户要的一致"], op="op", inputs={"q": "x"})]),
    )

    assert _done(events, "s1").unmet is None
    assert [j.point for j in judgements] == ["step_assert"]
    # 判定生命周期事件在 done 之前、成对出现
    assert [e.type for e in events] == [
        "plan.step.started",
        "plan.step.assert.started",
        "plan.step.assert.completed",
        "plan.step.done",
    ]
    assert isinstance(events[1], PlanStepAssertStartedEvent)
    assert events[1].assertion == ["结果与用户要的一致"]
    completed = events[2]
    assert isinstance(completed, PlanStepAssertCompletedEvent)
    assert completed.decision.passed is True


@pytest.mark.anyio
async def test_assert_unsupported_clause_degrades_and_downstream_still_runs():
    """断言无证据（字段给不出）→ 降级接受：产出保留、下游照常执行。

    这是本次改动要修的 badcase：jq 判据落到投影不出的字段上时，产出完全正常也必然判失败，
    再被一次修不好的整体重规划带走（连无关分支的下游一起丢掉）。
    """
    scripted = ScriptedJudge(step_assert=_clause_override(0, CLAUSE_UNSUPPORTED))
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=scripted.judge)
    steps = [
        _ast_step("s1", ["这家店当前正在营业"], op="op", inputs={"q": "x"}),
        _ast_step(
            "s2",
            ["拿到了上一步的地址"],
            op="op",
            depends_on=["s1"],
            inputs={"q": "{{ .s1.outputs.Out.field }}"},
        ),
    ]
    events, judgements = await _collect(runner, build(steps))

    done = _done(events, "s1")
    assert done.unmet is not None and done.unmet.verdict == "degraded"
    assert "无产出可判" in done.unmet.message
    # 下游照常执行：s2 有 done 事件——既没被级联跳过，也没被整体重规划中断。
    # 脚本判定器的覆盖按判定点给（不按 step 区分），所以 s2 的断言同样落在"无证据"、
    # 同样 degraded——这正好把"降级接受不阻塞下游"钉住。
    assert _done(events, "s2").unmet.verdict == "degraded"
    assert not [e for e in events if isinstance(e, PlanStepSkippedEvent)]
    assert not [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert [j.point for j in judgements] == ["step_assert", "step_assert"]


@pytest.mark.anyio
async def test_assert_falsified_clause_goes_through_remediation_and_replans():
    """被证伪 = 真的没做到：交补救方程，判定器说换 approach 可解 → 触发整体重规划。"""
    scripted = ScriptedJudge(
        step_assert=_clause_override(0, CLAUSE_FALSIFIED)
        | {Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE)}
    )
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(tools, model_api=None, query="用户要 expected", judge=scripted.judge)
    events, _ = await _collect(
        runner,
        build([_ast_step("s1", ["结果与用户要的一致"], op="op", inputs={"q": "x"})]),
    )

    errors = [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert len(errors) == 1
    assert errors[0].errors[0].source == "step.remediation"
    assert "第 [1] 条断言被产出证伪" in errors[0].errors[0].detail.message


@pytest.mark.anyio
async def test_assert_falsified_can_still_be_unsolvable_and_cascades_like_native():
    """合并后没有丢掉"判无解"出口：硬约束 + 数据确实没有 + 无替代做法 → 无解 + 级联跳过。"""
    scripted = ScriptedJudge(
        step_assert=_clause_override(0, CLAUSE_FALSIFIED)
        | {
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_DATA_ABSENT),
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.95),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.1),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.1),
        }
    )
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=scripted.judge)
    steps = [
        _ast_step("s1", ["找到了用户指定的那家店"], op="op", inputs={"q": "x"}),
        _ast_step(
            "s2",
            ["拿到了上一步的地址"],
            op="op",
            depends_on=["s1"],
            inputs={"q": "{{ .s1.outputs.Out.field }}"},
        ),
    ]
    events, _ = await _collect(runner, build(steps))

    assert _done(events, "s1").unmet.verdict == "unsolvable"
    assert _skipped(events, "s2").reason == "upstream_unsolvable"


@pytest.mark.anyio
async def test_jq_criterion_is_verified_by_rules_not_by_the_judge():
    """判据是 jq 形态 → 规则层求值，不打 step_assert（把关控的预算留给断言形态）。"""
    scripted = ScriptedJudge()
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=scripted.judge)
    events, judgements = await _collect(
        runner, build([_step("s1", op="op", inputs={"q": "x"})])
    )
    assert _done(events, "s1").unmet is None
    assert judgements == [] and scripted.calls_for("step_assert") == []


@pytest.mark.anyio
async def test_assertion_step_without_a_step_assert_judge_fails_loudly():
    """断言形态但没有把控承担 step_assert → 直接报错，绝不静默当成达成。"""
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(
        tools, model_api=None, query="q", judge=RejectingJudge(points=set())
    )
    with pytest.raises(RuntimeError, match="没有达成门"):
        await _collect(
            runner, build([_ast_step("s1", ["拿到结果"], op="op", inputs={"q": "x"})])
        )


@pytest.mark.anyio
async def test_process_error_skips_assert_judgement_and_uses_rule_layer():
    """过程错误（工具执行失败）与"产出达没达标"无关：不打断言判定，规则层直接定夺。"""
    scripted = ScriptedJudge()
    tools = [make_tool("op", value=None, raises=True)]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=scripted.judge)
    events, _ = await _collect(
        runner, build([_ast_step("s1", ["拿到结果"], op="op", inputs={"q": "x"})])
    )

    errors = [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert len(errors) == 1 and errors[0].errors[0].source == "step.remediation"
    assert not [e for e in events if isinstance(e, PlanStepAssertStartedEvent)]
    assert scripted.calls_for("step_assert") == []


# ────────────────────────── 失败即抛错（不静默降级）──────────────────────────


@pytest.mark.anyio
async def test_judge_failure_propagates_instead_of_falling_back():
    judge = RejectingJudge(RuntimeError("jev down"))
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=judge)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="jev down"):
        await _collect(
            runner, build([_step("s1", op="op", inputs={"q": "x"}, fails=True)])
        )
    assert judge.calls == 1


@pytest.mark.anyio
async def test_runner_without_judge_behaves_like_native():
    """不给判定器时退回原生路径（诊断走 model_api，这里 model_api 为 None → 保守 replan）。"""
    tools = [make_tool("op", value={"field": "actual"})]
    runner = PlanDAGRunner(tools, model_api=None, query="q", judge=None)
    events, _ = await _collect(
        runner, build([_step("s1", op="op", inputs={"q": "x"}, fails=True)])
    )
    error_events = [e for e in events if isinstance(e, PlanRunnerErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].errors[0].source == "step.remediation"
