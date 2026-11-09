"""``astream_plact`` 的端到端测试（离线可跑）+ 真机 A/B 对比脚本。

两种用法：

1. **pytest 收集**：跑离线用例（假判定器 + 假模型 + 固定的 plan），断言判定点确实插进了
   正确的阶段、事件顺序正确、新字段（confidence / outcome）语义正确。不需要网络。
2. **直接运行**：真机 A/B —— 同一条 query 跑同一根流水线，只换注入的把控
   （native=不注入 / jev / llm），把每个阶段的判定结果与耗时并排打印。
   需要 TYPESAFE_API_KEY 与 volcengine 配额：

   .. code-block:: bash

       uv run python tests/agents/test_plact_judge.py
       uv run python tests/agents/test_plact_judge.py --judges llm     # 用 LLM 当判定器做对照
       uv run python tests/agents/test_plact_judge.py --mock-tools     # 工具走 mock，不打第三方接口
       uv run python tests/agents/test_plact_judge.py --cases 1         # 只跑第 1 个 case（快）
       uv run python tests/agents/test_plact_judge.py --no-plan-audit  # 关掉把控承担的 plan_audit 门

产物：

1. **每份实验一份 event trace**（``--dump-dir``，默认 ``reports/plact_jev_ab_<时间戳>/``）——
   ``c<case>.<judge>.trace.json`` = run 配置 + 指标 + 全量事件（含 plan / tool_output /
   判定器 answers 与概率）；另有 ``summary.json`` 汇总所有 run 的指标。
2. **终端对比报表**：① 运行总览（每次实验一行）② 判定点明细（次数/耗时/裁决）
   ③ 同 query 跨判定器对比 ④ 失败归因。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import anyio
import pytest
from pydantic import BaseModel
from rich.cells import cell_len, set_cell_size
from rich.console import Console
from rich.table import Table

import aicore.agents.plan.core as plact_core
from aicore.agents.plan.events import (
    PlActErrorsEvent,
    PlActFinishEvent,
    PlActRoundStartEvent,
    PlanCreatedEvent,
    PlanStepDiagnosisCompletedEvent,
    PlanStepDoneEvent,
    PlanStepSkippedEvent,
    PlanStepStartedEvent,
)
from aicore.agents.plan.experiment.plan_schema_v1 import (
    StructuredPlanV1,
    plan_spec_v1,
)
from aicore.agents.plan.judges.jev_client import JevAnswer
from tests.agents._fake_jev import choice_answer, noul_answer, score_answer
from aicore.agents.plan.events import (
    JudgeDecisionEvent,
    PlanStepAssertCompletedEvent,
)
from aicore.agents.plan.judge import Point
from aicore.agents.plan.judges.points import (
    CAUSE_PLAN_MISTAKE,
    Q_AUDIT_COVERAGE,
    Q_AUDIT_GAP,
    Q_DIAG_CAUSE,
    Q_DIAG_RETRY,
    Q_FIN_COVERAGE,
    Q_FIN_DISCLOSED,
    Q_FIN_FABRICATED,
    Q_FIN_OUTCOME,
    Q_GATE_SAME,
    Q_GATE_WORTH,
    Q_PATH,
)
from tests.agents._judge_helpers import (
    FakeModelAPI,
    ScriptedJudge,
    FakeState,
    make_tool,
)
from tests.agents._plan_verify_helpers import outputs, step


def _fixed_plan() -> StructuredPlanV1:
    """离线用例的固定计划：达成判据是自然语言断言（把控来判定）。"""
    return StructuredPlanV1(
        goal="查北京天气",
        steps=[
            step(
                "s1",
                op="op",
                inputs={"q": "x"},
                step_outputs=outputs("Out", is_list=False, attributes=["field"]),
                assertion=["拿到了天气信息"],
            )
        ],
    )


def _scripted(**overrides: dict[str, JevAnswer]) -> ScriptedJudge:
    return ScriptedJudge(**overrides)


async def _run(
    *,
    query: str = "查一下北京明天的天气",
    judge: Any,
    model_api: Any,
    plan_factory: Any = None,
    monkeypatch: Any = None,
    **kwargs: Any,
) -> list[Any]:
    """跑一遍 plact（把控驱动），返回全部事件（plan 生成被替换成固定计划）。"""
    judge = getattr(judge, "judge", judge)  # 允许直接传 ScriptedJudge
    factory = plan_factory or (lambda: _fixed_plan())
    if monkeypatch is not None:
        async def fake_create_plan(query: str, **_: Any):
            return factory(), FakeState()

        monkeypatch.setattr(plact_core, "create_plan", fake_create_plan)

    events: list[Any] = []
    async for event in plact_core.astream_plact(
        query,
        model_api=model_api,
        state=FakeState(),
        judge=judge,
        tools=[make_tool("op", value={"field": "value"})],
        spec=plan_spec_v1,  # type: ignore[arg-type]
        max_turns=3,
        **kwargs,
    ):
        events.append(event)
    return events


def _judge_events(events: list[Any], stage: str) -> list[JudgeDecisionEvent]:
    return [e for e in events if isinstance(e, JudgeDecisionEvent) and e.stage == stage]


# ══════════════════════════════════════════════════════════════════════
# 离线端到端用例
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_happy_path_runs_all_judgement_points_in_order(monkeypatch):
    judge = _scripted()
    events = await _run(judge=judge, model_api=FakeModelAPI(), monkeypatch=monkeypatch)

    stages = [e.stage for e in events if isinstance(e, JudgeDecisionEvent)]
    assert stages == ["preflight", "plan_audit", "step_assert", "finish"]
    assert judge.client.calls[0]["state"]["judge_point"] == "preflight"

    # 事件流顺序：preflight 判定在最前（它是入口闸门，发生在第一轮之前），
    # 之后才是 round 开始 → 计划 → 步骤 → 收尾。
    order = [type(e).__name__ for e in events]
    assert order[-1] == "PlActFinishEvent"
    plan_order = [
        type(e).__name__ for e in events if not isinstance(e, JudgeDecisionEvent)
    ]
    assert plan_order[0] == "PlActRoundStartEvent"
    assert "PlanCreatedEvent" in plan_order and "PlanStepDoneEvent" in plan_order

    finish = events[-1]
    assert isinstance(finish, PlActFinishEvent)
    assert finish.forced is False
    assert finish.outcome == "success"
    assert finish.confidence is not None and finish.confidence > 0.9
    assert finish.response == "这是最终回答"


@pytest.mark.anyio
async def test_preflight_clarify_skips_planning_entirely(monkeypatch):
    judge = _scripted(
        preflight={Q_PATH: choice_answer(Q_PATH, "clarify", probabilities={"clarify": 0.95})}
    )
    events = await _run(judge=judge, model_api=FakeModelAPI(), monkeypatch=monkeypatch)

    assert not [e for e in events if isinstance(e, PlanCreatedEvent)]
    assert not [e for e in events if isinstance(e, PlActRoundStartEvent)]
    assert judge.calls_for("plan_audit") == [] and judge.calls_for("step_assert") == []

    finish = events[-1]
    assert finish.outcome == "clarify" and finish.forced is True
    # 澄清问句仍由 LLM 生成（判定器只判"该不该问"，不产文本）
    plan_answer = [e for e in events if isinstance(e, PlActFinishEvent)][0]
    assert plan_answer.response == "这是最终回答"


@pytest.mark.anyio
async def test_plan_audit_failure_triggers_repair_round_before_execution(monkeypatch):
    """审计不通过 → 不进执行、直接走 repair；第二轮审计通过后才执行。"""

    class _SeqJudge(ScriptedJudge):
        def __init__(self, audit_sequence: list[dict[str, JevAnswer]]) -> None:
            self._audit_sequence = list(audit_sequence)
            self._audit_n = 0
            super().__init__()

        def _respond(self, state, questions):  # type: ignore[override]
            answers = super()._respond(state, questions)
            if state.get("judge_point") == "plan_audit":
                if self._audit_n < len(self._audit_sequence):
                    answers.update(self._audit_sequence[self._audit_n])
                self._audit_n += 1
            return answers

    judge = _SeqJudge(
        [
            {
                Q_AUDIT_COVERAGE: noul_answer(Q_AUDIT_COVERAGE, 0.1),
                Q_AUDIT_GAP: choice_answer(Q_AUDIT_GAP, "check_too_loose"),
            },
            {},  # 第二轮用默认（通过）
        ]
    )
    events = await _run(judge=judge, model_api=FakeModelAPI(), monkeypatch=monkeypatch)

    assert len([e for e in events if isinstance(e, PlanCreatedEvent)]) == 2
    assert len([e for e in events if isinstance(e, PlActRoundStartEvent)]) == 2
    # 第一轮没有执行任何 step（审计在执行前拦下）
    assert len([e for e in events if isinstance(e, PlanStepDoneEvent)]) == 1

    errors = [e for e in events if isinstance(e, PlActErrorsEvent)]
    assert errors and errors[0].errors[0].source == "plan.semantics"
    assert errors[0].errors[0].detail.kind == "plan.semantics"

    finish = events[-1]
    assert finish.forced is False and finish.outcome == "success"


@pytest.mark.anyio
async def test_round_gate_can_stop_early_instead_of_burning_max_turns(monkeypatch):
    """诊断判 replan、闸门判止损：循环提前退出，而不是跑满 max_turns。"""
    model_api = FakeModelAPI()
    judge = _scripted(
        diagnosis={
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.9),
        },
        round_gate={
            Q_GATE_WORTH: noul_answer(Q_GATE_WORTH, 0.05),
            Q_GATE_SAME: noul_answer(Q_GATE_SAME, 0.95),
        },
        # 收尾判定如实反映"只部分达成、且已说明"
        finish={
            Q_FIN_COVERAGE: score_answer(Q_FIN_COVERAGE, 1.0),
            Q_FIN_DISCLOSED: noul_answer(Q_FIN_DISCLOSED, 0.9),
            Q_FIN_OUTCOME: choice_answer(Q_FIN_OUTCOME, "partial"),
        },
    )
    broken = StructuredPlanV1(
        goal="查北京天气",
        steps=[
            step(
                "s1",
                op="op",
                inputs={"q": "x"},
                step_outputs=outputs("Out", is_list=False, attributes=["field"]),
                success_check='.s1.outputs.Out.field == "expected"',  # 工具返回 "value" → 必然失败
            )
        ],
    )
    events = await _run(
        judge=judge,
        model_api=model_api,
        plan_factory=lambda: broken,
        monkeypatch=monkeypatch,
    )

    # max_turns=3，但闸门在第一轮后就止损 → 只有 1 个 round
    assert len([e for e in events if isinstance(e, PlActRoundStartEvent)]) == 1
    assert len(judge.calls_for("round_gate")) == 1

    finish = events[-1]
    assert finish.forced is True
    assert finish.outcome == "partial"
    # 判定器给的置信度必须反映出"只部分达成"（覆盖 1/3 档 → 约 0.33）
    assert finish.confidence is not None and finish.confidence < 0.5
    # 闸门判"多轮同根因无解"时，必须把"如实说明无法完成"的要求带进最终回答的提示里
    assert finish.reason  # reason 沿用原生语义：取首条错误的可读描述
    assert "经多轮重规划仍未达成" in model_api.invoke_calls[-1]


@pytest.mark.anyio
async def test_finish_confidence_reflects_fabrication(monkeypatch):
    judge = _scripted(
        finish={
            Q_FIN_COVERAGE: score_answer(Q_FIN_COVERAGE, 3.0),
            Q_FIN_FABRICATED: noul_answer(Q_FIN_FABRICATED, 0.95),
            Q_FIN_DISCLOSED: noul_answer(Q_FIN_DISCLOSED, 0.1),
            Q_FIN_OUTCOME: choice_answer(Q_FIN_OUTCOME, "success"),
        }
    )
    events = await _run(judge=judge, model_api=FakeModelAPI(), monkeypatch=monkeypatch)

    finish = events[-1]
    # 判定器自称 success，但虚构概率极高 → 置信度必须反映出来；
    # 而 outcome 由代码按 errors/unmet 推出（这里确实都满足，故为 success）——
    # 两个来源不一致这件事本身就落在事件里，供 A/B 统计。
    assert finish.confidence is not None and finish.confidence < 0.2
    assert finish.outcome == "success"


@pytest.mark.anyio
async def test_judge_failure_propagates_end_to_end(monkeypatch):
    from tests.agents._judge_helpers import RejectingJudge

    with pytest.raises(RuntimeError, match="typesafe 挂"):
        await _run(
            judge=RejectingJudge(RuntimeError("typesafe 挂")),
            model_api=FakeModelAPI(),
            monkeypatch=monkeypatch,
        )


def test_core_is_implementation_agnostic():
    """plact core 不许 import 任何把控实现：换把控（或干脆不注入）不该惊动 core。

    在子进程里查 sys.modules：pytest 本进程早就把实现 import 进来了，同进程查不出问题。
    """
    import subprocess
    import sys

    code = (
        "import sys;"
        "import aicore.agents.plan.core;"
        "impls=[m for m in sys.modules if m.startswith('aicore.agents.plan.judges')"
        " or m == 'typesafe_sdk'];"
        "print(','.join(sorted(impls)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert out == "", f"core 依赖了实现：{out}"


@pytest.mark.anyio
async def test_assertion_criterion_without_a_step_assert_judge_is_rejected_at_entry():
    """判据形态与把控能力不匹配时，入口直接拒——绝不出现"没人判定"的达成门。"""
    from tests.agents._judge_helpers import RejectingJudge

    judge = RejectingJudge(points={Point.PREFLIGHT})  # 不承担 step_assert
    with pytest.raises(ValueError, match="step_assert"):
        async for _ in plact_core.astream_plact(
            "查天气",
            model_api=FakeModelAPI(),
            state=FakeState(),
            judge=judge,
            tools=[],
            spec=plan_spec_v1,  # type: ignore[arg-type]
            max_turns=1,
        ):
            pass


@pytest.mark.anyio
async def test_no_judge_means_jq_criterion_and_no_extra_controls(monkeypatch):
    """不注入把控 = 同一模式下最简的配置：判据退回 jq，入口不分流、执行前不审计、收尾不评估。"""
    jq_plan = StructuredPlanV1(
        goal="查北京天气",
        steps=[
            step(
                "s1",
                op="op",
                inputs={"q": "x"},
                step_outputs=outputs("Out", is_list=False, attributes=["field"]),
            )
        ],
    )
    events = await _run(
        judge=None,
        model_api=FakeModelAPI(),
        monkeypatch=monkeypatch,
        plan_factory=lambda: jq_plan,
    )

    assert _judge_events(events, "preflight") == []
    assert _judge_events(events, "plan_audit") == []
    assert _judge_events(events, "finish") == []
    finish = events[-1]
    assert isinstance(finish, PlActFinishEvent)
    assert finish.confidence is None and finish.outcome == "success"


# ══════════════════════════════════════════════════════════════════════
# 真机 A/B 对比脚本
# ══════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[2]

AB_QUERIES = [
    "先查一下北京明天的天气，如果气温超过 30 度就把空调调到 22 度，再找一家评分高的烤鸭店并导航过去",
    "帮我找周杰伦的《晴天》并播放",
    "你叫什么名字？",
]


@dataclass
class RunRecord:
    """一次实验（query × judge）：全量事件流 + 派生指标。"""

    index: int
    case_index: int
    query: str
    judge_name: str
    started_at: str
    elapsed_s: float
    events: list[Any]
    metrics: dict[str, Any]

    @property
    def title(self) -> str:
        return f"#{self.index:02d} [{self.judge_name}]"


# 判定点裁决里值得进表格/摘要的字段（各 stage 裁决对象不同，按存在与否抽取）
_DECISION_KEYS = (
    "path",
    "passed",
    "action",
    "outcome",
    "gap_kind",
    "goal_coverage",
    "fabricated",
    "disclosed",
    "confidence",
)


def _jsonable(value: Any) -> Any:
    """任意事件/模型/枚举 → json 可序列化结构（兜底 str，不允许因序列化失败丢 trace）。"""
    if isinstance(value, BaseModel):
        try:
            return _jsonable(value.model_dump(mode="json"))
        except Exception:  # pragma: no cover - 兜底
            return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)
    return value


def _write_json(path: Path, payload: Any) -> None:
    """原子写 JSON：先写临时文件再 replace，避免中断留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _decision_summary(decision: Any) -> dict[str, Any]:
    """从任意判定点裁决里抽公共字段（diagnosis 外面包了一层信封，先拆掉）。"""
    data = _jsonable(decision)
    if isinstance(data, dict) and isinstance(data.get("decision"), dict):
        data = data["decision"]
    if not isinstance(data, dict):
        return {"value": data}
    return {k: data[k] for k in _DECISION_KEYS if data.get(k) is not None}


def _print_event(event: Any) -> None:
    """实时打印的摘要；全量数据看 dump。"""
    if isinstance(event, JudgeDecisionEvent):
        print(
            f"  ⟡ {event.stage:<14} {event.latency_ms:7.0f}ms  {_decision_summary(event.decision)}"
        )
    elif isinstance(event, PlActFinishEvent):
        print(
            f"  ✔ finish: forced={event.forced} outcome={event.outcome} "
            f"confidence={event.confidence} round={event.round}"
        )
        print(f"    {event.response}")
    elif isinstance(event, PlActFinishEvent):
        print(f"  ✔ finish: forced={event.forced} round={event.round}")
        print(f"    {event.response}")
    elif isinstance(event, PlanStepAssertCompletedEvent):
        d = event.decision
        print(
            f"  ⟡ {'step_assert':<14} {event.step_id} passed={d.passed} "
            f"证伪={d.falsified_clauses} 无证据={d.unsupported_clauses} {d.rationale}"
        )
    elif isinstance(event, (PlActErrorsEvent, PlanCreatedEvent, PlanStepDoneEvent)):
        print(f"  · {type(event).__name__}: {event.model_dump(exclude={'tool_output'})}"[:300])


def _fmt_counter(counter: dict[str, int]) -> str:
    return ", ".join(f"{k}×{v}" for k, v in counter.items()) or "—"


def _short(text: str, width: int) -> str:
    """按**显示宽度**截断（CJK 算 2 列）—— 否则中文会把表格撑开折行。"""
    if cell_len(text) <= width:
        return text
    return set_cell_size(text, max(width - 1, 0)) + "…"


def _collect_metrics(
    events: list[Any], elapsed_s: float, *, interrupted: str | None = None
) -> dict[str, Any]:
    """从事件流派生指标（只读）：单次实验的轮次/步骤/错误/判定点/结局。"""
    done = [e for e in events if isinstance(e, PlanStepDoneEvent)]
    asserts = [e for e in events if isinstance(e, PlanStepAssertCompletedEvent)]
    skipped = [e for e in events if isinstance(e, PlanStepSkippedEvent)]
    errors = [e for e in events if isinstance(e, PlActErrorsEvent)]
    diagnoses = [e for e in events if isinstance(e, PlanStepDiagnosisCompletedEvent)]
    decisions = [e for e in events if isinstance(e, JudgeDecisionEvent)]
    finish = next((e for e in reversed(events) if isinstance(e, PlActFinishEvent)), None)

    judge_stages: dict[str, dict[str, Any]] = {}
    for stage in dict.fromkeys(d.stage for d in decisions):  # 保序去重
        calls = [d for d in decisions if d.stage == stage]
        judge_stages[stage] = {
            "calls": len(calls),
            "total_ms": round(sum(d.latency_ms for d in calls), 1),
            "verdicts": [_decision_summary(d.decision) for d in calls],
        }
    return {
        "elapsed_s": round(elapsed_s, 3),
        "interrupted": interrupted,
        "rounds": sum(1 for e in events if isinstance(e, PlActRoundStartEvent)),
        "plans": sum(1 for e in events if isinstance(e, PlanCreatedEvent)),
        "steps_started": sum(1 for e in events if isinstance(e, PlanStepStartedEvent)),
        "steps_done": len(done),
        "asserts": len(asserts),
        "assert_failed": sum(1 for e in asserts if not e.decision.passed),
        "steps_skipped": len(skipped),
        "skip_reasons": dict(Counter(e.reason for e in skipped)),
        "error_events": len(errors),
        "error_count": sum(len(e.errors) for e in errors),
        "error_sources": dict(Counter(err.source for e in errors for err in e.errors)),
        "diagnoses": len(diagnoses),
        "diagnosis_sources": dict(Counter(d.source for d in diagnoses)),
        "unmet": dict(Counter(e.unmet.verdict for e in done if e.unmet is not None)),
        "judge_stages": judge_stages,
        "judge_calls": sum(v["calls"] for v in judge_stages.values()),
        "judge_total_ms": round(sum(v["total_ms"] for v in judge_stages.values()), 1),
        "forced": None if finish is None else finish.forced,
        "outcome": None if finish is None else getattr(finish, "outcome", None),
        "confidence": None if finish is None else getattr(finish, "confidence", None),
        "reason": None if finish is None else finish.reason,
        "answer_chars": 0 if finish is None else len(finish.response),
        "answer": "" if finish is None else finish.response,
    }


def _run_meta(record: RunRecord, args: argparse.Namespace) -> dict[str, Any]:
    """一次实验的配置与时间（trace 与 summary 共用一份，避免重复展开事件）。"""
    return {
        "index": record.index,
        "case_index": record.case_index,
        "query": record.query,
        "judge": record.judge_name,
        "model": args.model,
        "max_turns": args.max_turns,
        "mock_tools": bool(args.mock_tools),
        "mock_websearch": args.mock_websearch if args.mock_tools else None,
        "plan_audit": not args.no_plan_audit,
        "started_at": record.started_at,
        "elapsed_s": round(record.elapsed_s, 3),
    }


def _trace_payload(record: RunRecord, args: argparse.Namespace) -> dict[str, Any]:
    """一份自包含 trace：run 配置 + 指标 + 全量事件（含 tool_output / answers / plan）。"""
    return {
        "run": _run_meta(record, args),
        "metrics": record.metrics,
        "events": [
            {"class": type(event).__name__, **_jsonable(event)} for event in record.events
        ],
    }


async def _run_real(
    query: str,
    *,
    index: int,
    case_index: int,
    judge_name: str,
    tools: list[Any],
    model_api: Any,
    max_turns: int,
    enable_plan_audit: bool = True,
) -> RunRecord:
    """跑一次实验：边流边打事件，返回可落盘的 RunRecord（中断也返回，不拖垮整批实验）。"""
    from aicore.agents.plan.judges.jev import JevJudge
    from aicore.agents.plan.judges.jev_client import AsyncJevClient
    from aicore.agents.plan.judges.llm import LlmJudge

    # 三臂共用同一条流水线、同一个 spec；唯一的自变量是**注入的把控**：
    #   native = 不注入（判据退回 jq，由规则层求值）→ 原实现的行为
    #   jev / llm = 注入把控（判据是自然语言断言，谁来判由注入的实现决定）
    judge: Any = None
    if judge_name == "jev":
        judge = JevJudge(AsyncJevClient())
    elif judge_name == "llm":
        judge = LlmJudge(model_api)
    if not enable_plan_audit:
        # 审计是执行前的纸面判定门：把"判定器质量"与"审计门假阳性"拆成两个自变量。
        judge = _without_point(judge, Point.PLAN_AUDIT)

    stream = plact_core.astream_plact(
        query,
        model_api=model_api,
        state=model_api.initial_state(system_prompt="你是一个友好的车载助手。"),
        judge=judge,
        tools=tools,
        spec=plan_spec_v1,
        max_turns=max_turns,
    )

    print(f"\n{'=' * 78}\n[{judge_name}] {query}\n{'=' * 78}")
    events: list[Any] = []
    started_at = datetime.now().isoformat(timespec="seconds")
    started = perf_counter()
    interrupted: str | None = None
    try:
        async for event in stream:
            events.append(event)
            _print_event(event)
    except Exception as e:  # 判定器/模型挂掉不该让整批实验白跑，落盘后继续下一组
        interrupted = f"{type(e).__name__}: {e}"
        print(f"  ✗ 中断：{interrupted}")
    elapsed_s = perf_counter() - started
    print(f"  total: {elapsed_s:.1f}s  events={len(events)}")
    return RunRecord(
        index=index,
        case_index=case_index,
        query=query,
        judge_name=judge_name,
        started_at=started_at,
        elapsed_s=elapsed_s,
        events=events,
        metrics=_collect_metrics(events, elapsed_s, interrupted=interrupted),
    )


def _without_point(judge: Any, point: "Point") -> Any:
    """把某个判定点从实现承担的范围里去掉（A/B 归因用；core 里没有开关）。"""
    if judge is None:
        return None
    judge._points = frozenset(judge._points) - {point}  # type: ignore[attr-defined]
    return judge


def _build_tools(args: argparse.Namespace) -> list[Any]:
    """工具集：默认真机；``--mock-tools`` 时换成同契约、只换 worker 的 mock 版。"""
    if args.mock_tools:
        from tests.agents._mock_tools import get_mock_tools

        print(
            f"[mock tools] WebSearch={args.mock_websearch}，其余工具返回固定数据；"
            f"plan / DAG / 概念投影 / 诊断 / 收尾仍是真机"
        )
        return get_mock_tools(chat_id="User", websearch=args.mock_websearch)

    from projects.mind.toolset.dag import get_default_tools

    return get_default_tools(chat_id="User")


# ══════════════════════════════════════════════════════════════════════
# 结果对比表
# ══════════════════════════════════════════════════════════════════════


def _bar(value: float, *, scale: float, width: int = 8) -> str:
    """极简条形，给数字加一点可比的视觉刻度。"""
    if scale <= 0:
        return "·" * width
    filled = max(0, min(width, round(value / scale * width)))
    return "█" * filled + "·" * (width - filled)


def _outcome_text(record: RunRecord) -> str:
    """一次实验的结局单元：✔/✖ + outcome + 置信度。"""
    metrics = record.metrics
    if metrics["interrupted"]:
        return "✗ 中断"
    if metrics["forced"] is None:
        return "— 无 finish"
    mark = "✔" if not metrics["forced"] else "✖"
    outcome = metrics["outcome"] or ("success" if not metrics["forced"] else "forced")
    confidence = "" if metrics["confidence"] is None else f" {metrics['confidence']:.2f}"
    return f"{mark} {outcome}{confidence}"


def _overview_table(records: list[RunRecord]) -> Table:
    """① 每次实验一行的总览（同一 query 的 native / jev 相邻，方便直接对比）。"""
    table = Table(title="① 运行总览", title_justify="left", header_style="bold")
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("judge", no_wrap=True)
    table.add_column("query", max_width=26, overflow="ellipsis")
    table.add_column("耗时", justify="right", no_wrap=True)
    table.add_column("轮", justify="right", no_wrap=True)
    table.add_column("步:执行/跳/验", justify="right", no_wrap=True)
    table.add_column("错", justify="right", no_wrap=True)
    table.add_column("结果", no_wrap=True)
    slowest = max((r.elapsed_s for r in records), default=1.0)
    previous_query: str | None = None
    for record in records:
        if previous_query is not None and record.query != previous_query:
            table.add_section()
        previous_query = record.query
        metrics = record.metrics
        table.add_row(
            f"{record.index:02d}",
            record.judge_name,
            _short(record.query, 26),
            f"{record.elapsed_s:6.1f}s {_bar(record.elapsed_s, scale=slowest, width=6)}",
            str(metrics["rounds"]),
            f"{metrics['steps_done']}/{metrics['steps_skipped']}/{metrics['asserts']}",
            str(metrics["error_count"]),
            _outcome_text(record),
        )
    return table


def _judge_table(records: list[RunRecord]) -> Table | None:
    """② 判定点明细：每 stage 的调用次数/耗时/每次裁决（native 无判定点，故可能为空）。"""
    rows = [
        (record, stage, payload)
        for record in records
        for stage, payload in record.metrics["judge_stages"].items()
    ]
    if not rows:
        return None
    table = Table(title="② 判定点明细", title_justify="left", header_style="bold")
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("judge", no_wrap=True)
    table.add_column("stage", no_wrap=True)
    table.add_column("次", justify="right", no_wrap=True)
    table.add_column("平均", justify="right", no_wrap=True)
    table.add_column("裁决", max_width=72, overflow="ellipsis")
    previous: str | None = None
    for record, stage, payload in rows:
        if previous is not None and record.title != previous:
            table.add_section()
        previous = record.title
        verdicts = "; ".join(
            " ".join(f"{k}={v}" for k, v in verdict.items()) for verdict in payload["verdicts"]
        )
        table.add_row(
            f"{record.index:02d}",
            record.judge_name,
            stage,
            str(payload["calls"]),
            f"{payload['total_ms'] / max(payload['calls'], 1):5.0f}ms",
            _short(verdicts, 72),
        )
    return table


def _comparison_table(records: list[RunRecord]) -> Table:
    """③ 同一 query 跨判定器横向对比（判定开销单独标出，它是 jev 的代价所在）。"""
    judges = list(dict.fromkeys(r.judge_name for r in records))
    grouped: dict[str, list[RunRecord]] = {}
    for record in records:
        grouped.setdefault(record.query, []).append(record)
    table = Table(title="③ 同 query 跨判定器对比", title_justify="left", header_style="bold")
    table.add_column("query", max_width=30, overflow="ellipsis")
    for judge in judges:
        table.add_column(judge, max_width=50, overflow="ellipsis")
    for query, group in grouped.items():
        by_judge = {r.judge_name: r for r in group}
        cells = []
        for judge in judges:
            record = by_judge.get(judge)
            if record is None:
                cells.append("—")
                continue
            metrics = record.metrics
            judge_ms = (
                f" +{metrics['judge_total_ms'] / 1000:.1f}s判定" if metrics["judge_calls"] else ""
            )
            cells.append(
                f"{metrics['elapsed_s']:5.1f}s{judge_ms} · {metrics['rounds']}轮·"
                f"{metrics['error_count']}err · {_outcome_text(record)}"
            )
        table.add_row(f"#{group[0].index:02d} {_short(query, 24)}", *cells)
    return table


def _attribution_table(records: list[RunRecord]) -> Table | None:
    """④ 失败归因：错误来源 / 诊断来源 / 未达成 / 跳过原因（全绿时不打）。"""
    rows = [
        r
        for r in records
        if r.metrics["error_count"]
        or r.metrics["unmet"]
        or r.metrics["steps_skipped"]
        or r.metrics["interrupted"]
        or r.metrics["diagnoses"]
    ]
    if not rows:
        return None
    table = Table(title="④ 失败归因", title_justify="left", header_style="bold")
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("judge", no_wrap=True)
    table.add_column("错误来源", max_width=30, overflow="ellipsis")
    table.add_column("诊断来源", max_width=18, overflow="ellipsis")
    table.add_column("未达成", max_width=14, overflow="ellipsis")
    table.add_column("跳过原因", max_width=20, overflow="ellipsis")
    table.add_column("中断", max_width=26, overflow="ellipsis")
    for record in rows:
        metrics = record.metrics
        table.add_row(
            f"{record.index:02d}",
            record.judge_name,
            _short(_fmt_counter(metrics["error_sources"]), 30),
            _short(_fmt_counter(metrics["diagnosis_sources"]), 18),
            _short(_fmt_counter(metrics["unmet"]), 14),
            _short(_fmt_counter(metrics["skip_reasons"]), 20),
            _short(metrics["interrupted"] or "—", 26),
        )
    return table


def _print_report(records: list[RunRecord], dump_dir: Path) -> None:
    """实验结束后的对比报表（终端表格）。"""
    console = Console()
    console.print()
    console.print(_overview_table(records))
    if (judge_table := _judge_table(records)) is not None:
        console.print(judge_table)
    console.print(_comparison_table(records))
    if (attribution_table := _attribution_table(records)) is not None:
        console.print(attribution_table)
    console.print(f"\ntrace 目录：{dump_dir}")


async def _amain(args: argparse.Namespace) -> None:
    from aicore.models.model_api import create_model_api

    model_api = create_model_api(model=args.model, backend="responses")
    tools = _build_tools(args)
    dump_dir = (
        Path(args.dump_dir)
        if args.dump_dir
        else REPO_ROOT / "reports" / f"plact_jev_ab_{datetime.now():%Y%m%d_%H%M%S}"
    )

    records: list[RunRecord] = []
    index = 0
    skipped_cases: list[int] = []
    for case_index, query in enumerate(AB_QUERIES, start=1):
        if args.cases and case_index not in args.cases:
            skipped_cases.append(case_index)
            continue
        for judge_name in args.judges:
            index += 1
            record = await _run_real(
                query,
                index=index,
                case_index=case_index,
                judge_name=judge_name,
                tools=tools,
                model_api=model_api,
                max_turns=args.max_turns,
                enable_plan_audit=not args.no_plan_audit,
            )
            records.append(record)
            trace_path = dump_dir / f"c{case_index:02d}.{judge_name}.trace.json"
            _write_json(trace_path, _trace_payload(record, args))
            print(f"  dump: {trace_path}")
    if skipped_cases:
        print(f"[skip] 未选中的 case：{skipped_cases}（--cases 可指定，如 --cases 1）")

    _write_json(
        dump_dir / "summary.json",
        {
            "run": {
                "model": args.model,
                "max_turns": args.max_turns,
                "mock_tools": bool(args.mock_tools),
                "mock_websearch": args.mock_websearch if args.mock_tools else None,
                "plan_audit": not args.no_plan_audit,
            },
            "runs": [
                {"run": _run_meta(r, args), "metrics": r.metrics} for r in records
            ],
        },
    )
    _print_report(records, dump_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="plact: 原生 vs Jev 判定器 A/B")
    parser.add_argument(
        "--judges",
        nargs="+",
        default=["native", "jev"],
        choices=["native", "jev", "llm"],
    )
    parser.add_argument("--model", default="doubao-seed-2-0-pro-260215")
    parser.add_argument("--max-turns", type=int, default=3)
    parser.add_argument(
        "--mock-tools",
        action="store_true",
        help="工具走 mock（不打高德/QQ音乐/火山车控/Ark bot），其余链路仍是真机",
    )
    parser.add_argument(
        "--mock-websearch",
        choices=["ok", "empty", "error"],  # 与 tests/agents/_mock_tools.WEBSEARCH_MODES 保持一致
        default="ok",
        help="--mock-tools 时 WebSearch 的行为：正常 / 空结果 / 抛 429 异常",
    )
    parser.add_argument(
        "--no-plan-audit",
        action="store_true",
        help=(
            "关掉把控承担的 plan_audit 语义门（把该判定点从实现承担范围里去掉）："
            "审计在计划生成后、执行前拦语义缺陷，误报会让整轮 0 步执行；"
            "跑基线或定位判定器质量时关掉它，A/B 只留判定器这一个自变量。不注入把控的臂不受影响"
        ),
    )
    parser.add_argument(
        "--dump-dir",
        default=None,
        help="event trace 落盘目录（每次实验一份 JSON），默认 reports/plact_jev_ab_<时间戳>/",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        type=int,
        default=None,
        metavar="N",
        help=f"只跑指定 case（AB_QUERIES 的 1-based 序号，可多个：--cases 1 2）；默认全部 {len(AB_QUERIES)} 个",
    )
    args = parser.parse_args()
    anyio.run(_amain, args, backend="asyncio")


if __name__ == "__main__":
    main()
