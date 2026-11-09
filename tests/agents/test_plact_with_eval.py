"""单 case 达成率归因（test_plact 的扩展版）。

对单条 query 跑 plan→execute→answer 全流程，分析 plan 拓扑模式与引用模式、记录过程，
并对「原始 query 的达成率」做 root-cause 归因（唯一一次 structured_output LLM 调用）。

归因把每个未达成/错误映射到一个**可执行的优化 lever**（工具 / 模型表现 / 机制），
供批量脚本 test_plact_batch.py 做诱因分类与因果分析。

直接运行：
    uv run python tests/agents/test_plact_with_eval.py "先查北京明天天气，再导航到三里屯"
    uv run python tests/agents/test_plact_with_eval.py --input synthetic_complex_plan_queries.json --case-id case_0003
    uv run python tests/agents/test_plact_with_eval.py --skip-attribution        # 只跑执行 + 模式分析
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import anyio
from pydantic import BaseModel, Field
from rich import print as rprint

from aicore.agents.plan.core import astream_plact
from aicore.agents.plan.dag_checker import check_dag
from aicore.agents.plan.events import (
    PlActErrorsEvent,
    PlActFinishEvent,
    PlActRoundStartEvent,
    PlanCreatedEvent,
    PlanRunnerErrorEvent,
    PlanStepDoneEvent,
    PlanStepSkippedEvent,
)
from aicore.agents.plan.experiment.plan_schema_v1 import plan_spec_v1

# from aicore.agents.plan.experiment.plan_schema_v3 import plan_spec_v3 as plan_spec_v1
from aicore.models.credentials import ModelName
from aicore.models.model_api import ModelCallParams, UserMessage, create_model_api
from projects.mind.toolset import get_default_tools

DEFAULT_QUERY = (
    # "我在北京，下午想带爸妈去听个京剧或者传统音乐，老人家走不动也不能太折腾。"
    # "先看看现在路上堵不堵，要是堵就找近点的室内场馆，不堵可以去远点但是有名的地方。"
    # "每个地方都帮我看看有没有电梯无障碍设施，最后挑一个最合适的，再配点适合老人听的舒缓国风音乐。"
    # "这个周末我在南京和苏州之间二选一，想做一趟音乐主题小旅行，帮我看天气、路况和现场演出，选一个更稳的城市，再排下午到晚上的路线。"
    # "我想比较下北京和上海的爵士酒吧，看看哪个城市的爵士氛围更浓。先各找几家评分高的爵士酒吧，再看看两边周末天气和交通，先选一个城市，然后从选中的城市里挑出两三家串成一条酒吧路线，每个酒吧都看看停车，路上放爵士歌单。"
    # "播放一首周杰伦的晴天，然后空调开到20度",
    # "帮我找2025年买的小型纯电轿车，要车宽不超1.8米、转弯半径不超5.5米，有自动泊车功能，预算10到18万，还能选粉色车身的，还有对应的线下门店",
    # "帮我找常驻地10公里内、近3个月、支持积分兑换、含免费停车权益的新能源线下体验活动",
    # "帮我找广州到昆明自驾途中，距离G80广昆高速新兴出口5公里内，带温泉、有快充桩，房价300到500元的酒店，要3家",
    # "我在北京望京花园小区有插混车，想知道合规充电的要求，包括小区桩和公共桩的政策，还有吉利雷神的充电建议",
    # "帮我找一下比亚迪汉EV电池衰减到80%以下的国内正规第三方检测、认证修复机构，还有本地检测费用标准（含项目明细），以及是否支持上门检测和预约方式",
    # "帮我找国庆京蓉自驾中途的休息点，要100kW以上充电桩、有亲子项目、平价酒店，离高速不超20km，避开热门景区",
    # "帮我筛选符合这些条件的2025年通勤纯电SUV：CLTC续航≥500km、高压快充10分钟补能≥200km、车长≤4.8米、售价15-25万、南方冬季续航衰减≤20%",
    # "帮我查下2024款Model Y在-10度和在0度时用V2L外放电带1500W电暖器能续航多久",
    # "从杭州到天津，我现在电量只有15%，帮我算下充电总成本，总里程约1100公里",
    # "有没有2公里内、2023年后开的非连锁杭帮菜餐厅带露台？",
    # "给我推荐适合上海的2023款纯电MPV，要能对外放电，续航够长超500，还得是国六b，2024拿了五星碰撞",
    # "帮我找适合带2岁幼童的小众周边游方案，要求车程≤4小时，总预算控制在2000元，有儿童游乐和宝宝餐，是非热门目的地",
    # "帮我找嘉定区10公里内近3个月支持积分兑换还带免费停车的新能源线下体验活动",
    "帮我规划成都3天2晚亲子游，需要包含适合带5岁孩子的住宿，且住宿到熊猫基地、杜甫草堂的交通衔接要方便"
)


# ─────────────────────────── 归因 schema（唯一 per-case LLM 输出）───────────────────────────

Lever = Literal[
    "tool",  # 工具能力/数据缺口（含数据不存在、超纲）
    "model_plan",  # 提升 plan 生成（结构/引用/拆解/success_check），改 planning 提示词或 plan_schema description
    "model_diagnosis",  # 提升诊断判断，改诊断提示词/description
    "model_replan",  # 提升 replan，改 replan/repair 提示词（含多轮 repair 反复无效的情形）
    "model_answer",  # 提升回答合成，改 answer 提示词
    "mechanism",  # 提示词/description 补不了，必须动 runner 控制流 / schema 结构 / 加新机制
]


class CauseAttribution(BaseModel):
    issue: str = Field(description="原始 query 的哪个需求未达成 / 出了什么错。")
    root_cause: str = Field(
        description="该问题的根因，一句话说清；一个错误对应一条根因。"
    )
    lever: Lever = Field(
        description=(
            "该根因对应的优化杠杆。判据：靠「让模型表现更好」解决 → model_*；工具能力/数据缺口 → tool；"
            "需要改 runner 控制流或 schema 结构（而非 description/提示词）才能解决 → mechanism。"
            "plan 结构/引用/诊断准确性这类改 description 就能改善的一律归 model_*；mechanism 只留给必须动代码/结构的情形。"
        )
    )
    component: str = Field(
        default="",
        description=(
            "具体动哪儿：如 plan_schema_v1.steps.description / planning_prompt / diagnosis_prompt / "
            "某工具名（media、navigation、poi_search…） / runner.repair_stop。"
        ),
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="对该 lever 归类的把握。症状可能落在多层时，用 low 表达不确定。"
    )
    disclosed_in_answer: bool = Field(
        description="该问题是否已在最终回答里如实告知用户。根因明确且已如实告知时，本条到此为止。"
    )


class FulfillmentAttribution(BaseModel):
    grade: Literal["perfect", "imperfect_honest", "imperfect_flawed"] = Field(
        description=(
            "原始 query 的最终达成评级，只分 3 档：\n"
            "- perfect：完美解决，需求全部达成、回答与执行结果一致。\n"
            "- imperfect_honest：不完美，但如实回复——有未完成/查不到的部分且已在回答里诚实说明。\n"
            "- imperfect_flawed：不完美，且遗漏了需求或捏造了事实（答非所问、虚构成功、与执行结果矛盾、"
            "关键动作失败却未如实告知）。"
        )
    )
    attributions: list[CauseAttribution] = Field(
        default_factory=list,
        description=(
            "对每个未达成/错误给一条根因归因；每条的 issue 点明「原始 query 的哪个需求未达成」。"
            "每个问题只归一条根因；链路完全成功时列表为空。"
            "数据客观不存在也记为 tool（视作工具不够好），同样产出该条归因。"
        ),
    )
    notes: str = Field(default="", description="可选备注。")


# ─────────────────────────────────── 数据加载 ───────────────────────────────────


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str


def load_eval_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = (
        payload["cases"]
        if isinstance(payload, dict) and "cases" in payload
        else payload
    )
    if not isinstance(rows, list):
        raise ValueError(f"expected a list or a payload with a cases list: {path}")
    cases: list[EvalCase] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        inner = row.get("case") if isinstance(row.get("case"), dict) else row
        query = str(
            row.get("generated_query")
            or row.get("query")
            or inner.get("generated_query")
            or ""
        )
        if not query:
            continue
        cases.append(
            EvalCase(
                case_id=str(inner.get("case_id") or f"case_{idx:04d}"), query=query
            )
        )
    return cases


# ─────────────────────────────── plan 模式 / 引用模式 ───────────────────────────────

_TEMPLATE_REF = re.compile(r"\{\{\s*(/[^{}]+?)\s*\}\}")
_JQ_OUTPUT_REF = re.compile(r"\.([A-Za-z_]\w*)\.outputs\.[A-Za-z_]\w*")


def _plan_steps(plan: Any) -> list[Any]:
    steps = getattr(plan, "steps", None)
    if steps is None and isinstance(plan, dict):
        steps = plan.get("steps")
    return list(steps or [])


def _field(step: Any, name: str, default: Any = None) -> Any:
    if isinstance(step, dict):
        return step.get(name, default)
    return getattr(step, name, default)


def analyze_plan_shape(plan: Any | None) -> dict[str, Any]:
    """生成 plan 自身的拓扑标签 + 图特征（不与任何 expected 比较）。"""
    steps = _plan_steps(plan) if plan is not None else []
    ids = [str(_field(s, "step_id") or f"s{i + 1}") for i, s in enumerate(steps)]
    known = set(ids)
    edges = {
        (str(dep), sid)
        for s, sid in zip(steps, ids)
        for dep in (_field(s, "depends_on") or [])
        if str(dep) in known and str(dep) != sid
    }
    indeg = {sid: 0 for sid in ids}
    outdeg = {sid: 0 for sid in ids}
    for src, dst in edges:
        outdeg[src] += 1
        indeg[dst] += 1
    has_condition = any(_field(s, "condition") for s in steps)
    features = {
        "node_count": len(ids),
        "edge_count": len(edges),
        "max_indeg": max(indeg.values(), default=0),
        "max_outdeg": max(outdeg.values(), default=0),
        "has_join": any(v >= 2 for v in indeg.values()),
        "has_fanout": any(v >= 2 for v in outdeg.values()),
        "has_condition": has_condition,
        "longest_path": _longest_path(ids, edges),
    }
    return {"topology": _classify_topology(features), "features": features}


def _longest_path(ids: list[str], edges: set[tuple[str, str]]) -> int:
    outgoing: dict[str, list[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for src, dst in edges:
        outgoing[src].append(dst)
        indeg[dst] += 1
    queue = [i for i in ids if indeg[i] == 0]
    dist = {i: 1 for i in ids}
    while queue:
        cur = queue.pop(0)
        for nxt in outgoing[cur]:
            dist[nxt] = max(dist[nxt], dist[cur] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    return max(dist.values(), default=0)


def _classify_topology(f: dict[str, Any]) -> str | None:
    if f["node_count"] == 0:
        return None
    if f["has_condition"]:
        return "conditional"
    if f["has_fanout"] and f["has_join"]:
        return "fanout_join"
    if f["has_join"]:
        return "join"
    if f["has_fanout"]:
        return "branch"
    if f["max_indeg"] <= 1 and f["max_outdeg"] <= 1:
        return "deep_chain" if f["node_count"] >= 4 else "chain"
    return "dag"


def analyze_reference_patterns(plan: Any | None) -> list[str]:
    """记录生成 plan 中实际出现的引用形式。"""
    patterns: set[str] = set()
    for step in _plan_steps(plan) if plan is not None else []:
        inputs = _field(step, "inputs") or {}
        if isinstance(inputs, dict):
            for value in inputs.values():
                _scan_value(value, patterns, container="inputs")
        for jq_field in ("condition", "success_check"):
            expr = _field(step, jq_field)
            if isinstance(expr, str) and _JQ_OUTPUT_REF.search(expr):
                patterns.add(
                    "conditional" if jq_field == "condition" else "success_check_ref"
                )
    return sorted(patterns)


def _scan_value(value: Any, patterns: set[str], *, container: str) -> None:
    if isinstance(value, dict):
        if any(_has_ref(v) for v in value.values()):
            patterns.add("object")
        for v in value.values():
            _scan_value(v, patterns, container=container)
        return
    if isinstance(value, list):
        if any(_has_ref(v) for v in value):
            patterns.add("list")
        for v in value:
            _scan_value(v, patterns, container=container)
        return
    if not isinstance(value, str):
        return
    refs = _TEMPLATE_REF.findall(value)
    if not refs:
        return
    if len(refs) >= 2:
        patterns.add("multi")
    for path in refs:
        segs = [seg for seg in path.split("/") if seg]
        if "*" in path:
            patterns.add("wildcard")
        elif any(seg.isdigit() for seg in segs):
            patterns.add("indexed")
    only_ref = bool(re.fullmatch(r"\s*\{\{[^{}]+\}\}\s*", value))
    patterns.add("direct" if only_ref else "embedded")


def _has_ref(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_TEMPLATE_REF.search(value))
    if isinstance(value, dict):
        return any(_has_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_ref(v) for v in value)
    return False


# ───────────────────────────────── 序列化 helper ─────────────────────────────────


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        try:
            return value.model_dump(mode="json")
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _error_row(error: Any, *, round_no: int | None = None) -> dict[str, Any]:
    detail = getattr(error, "detail", None)
    row: dict[str, Any] = {
        "source": getattr(error, "source", None),
        "kind": getattr(detail, "kind", None),
        "step_id": getattr(detail, "step_id", None),
        "message": error.nl_repr() if hasattr(error, "nl_repr") else str(error),
    }
    if round_no is not None:
        row["round"] = round_no
    return row


def _diagnosis_line(error: Any) -> str:
    """控制台用的简洁错误行：诊断结论只给诊断/建议 message 与建议方向，不打印原始工具输出 / concept 投影。"""
    detail = getattr(error, "detail", None)
    kind = getattr(detail, "kind", None)
    if kind == "remediation":  # 补救诊断判 replan：只给建议方向 + 客观原因
        direction = getattr(detail, "diagnosis_reason", "")
        message = getattr(detail, "message", "")
        return f"目标未达成，诊断建议 replan：{direction}（{message}）"
    return error.nl_repr() if hasattr(error, "nl_repr") else str(error)


def _event_row(event: Any, *, round_no: int | None) -> dict[str, Any]:
    """把一个事件压成按序 trace 的一行（详细，落到 dump 文件）。"""
    name = type(event).__name__
    if isinstance(event, PlActRoundStartEvent):
        return {
            "event": name,
            "round": event.round,
            "repair": event.repair_context is not None,
        }
    if isinstance(event, PlanCreatedEvent):
        return {
            "event": name,
            "round": event.round,
            "step_count": len(_plan_steps(event.plan)),
            "plan": _jsonable(event.plan),
        }
    if isinstance(event, PlanRunnerErrorEvent):
        return {
            "event": name,
            "round": round_no,
            "errors": [_error_row(e) for e in event.errors],
        }
    if isinstance(event, PlActErrorsEvent):
        return {
            "event": name,
            "round": event.round,
            "policy": str(event.policy),
            "errors": [_error_row(e) for e in event.errors],
        }
    if isinstance(event, PlanStepDoneEvent):
        return {
            "event": name,
            "round": round_no,
            "step_id": event.step_id,
            "goal": event.step_goal,
            "resolved_inputs": _jsonable(event.resolved_inputs),
            "tool_output": _jsonable(event.tool_output),
            "concept_output": _jsonable(event.concept_output),
            "unmet": _jsonable(event.unmet) if event.unmet else None,
            "process_error": _jsonable(event.process_error)
            if event.process_error
            else None,
        }
    if isinstance(event, PlanStepSkippedEvent):
        return {
            "event": name,
            "round": round_no,
            "step_id": event.step_id,
            "goal": event.step_goal,
            "reason": event.reason,
        }
    if isinstance(event, PlActFinishEvent):
        return {
            "event": name,
            "round": event.round,
            "forced": event.forced,
            "reason": event.reason,
            "response": event.response,
        }
    return {"event": name, "round": round_no}


def _truncate(value: Any, *, max_chars: int) -> str:
    text = json.dumps(_jsonable(value), ensure_ascii=False, indent=2)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... <truncated>"


# ───────────────────────────────── 核心：单 case 运行 ─────────────────────────────────


async def run_single_case(
    case: EvalCase,
    *,
    model_api: Any,
    attrib_model_api: Any | None,
    tools: list[Any],
    params: ModelCallParams,
    max_turns: int = 5,
    skip_attribution: bool = False,
    verbose: bool = False,
    planning_system_prompt: str | None = None,
) -> dict[str, Any]:
    """跑单个 case 并归因。verbose=True 时流式打印过程（单 case 用），批量应保持 False。"""
    known_ops = {tool.name for tool in tools}
    started = time.perf_counter()
    if verbose:
        rprint(f"[dim]planning… (max_turns={max_turns})[/dim]")

    events: list[dict[str, Any]] = []  # 按序的详细事件 trace（dump 到临时文件）
    plans_by_round: list[dict[str, Any]] = []
    runtime_errors: list[
        dict[str, Any]
    ] = []  # 来自 PlanRunnerErrorEvent（replan-worthy）
    unresolved_errors: list[
        dict[str, Any]
    ] = []  # 最终一轮 PlActErrorsEvent 的错误（forced）
    step_done: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    current_round: int | None = None
    round_count = 0
    round_started_at: dict[int, float] = {}
    round_seconds: dict[int, float] = {}
    repair_count = 0
    step_goals: dict[
        str, str
    ] = {}  # step_id -> goal（用最新一轮 plan 维护，供 error 步展示 goal）
    finish: PlActFinishEvent[Any] | None = None

    # The batch benchmark explicitly seeds the planning state with the
    # schema-specific system prompt (including the tool manifest).  The answer
    # state remains provider-neutral and is passed separately to PlAct core.
    state = model_api.initial_state()
    plan_prompt = planning_system_prompt or plan_spec_v1.build_sys_prompt(tools)
    plan_state = model_api.initial_state(system_prompt=plan_prompt)
    async for event in astream_plact(
        case.query,
        model_api=model_api,
        state=state,
        plan_state=plan_state,
        tools=tools,
        spec=plan_spec_v1,
        max_turns=max_turns,
        params=params,
    ):
        events.append(_event_row(event, round_no=current_round))
        if isinstance(event, PlActRoundStartEvent):
            now = time.perf_counter()
            if current_round is not None and current_round in round_started_at:
                round_seconds[current_round] = round(
                    now - round_started_at[current_round], 4
                )
            current_round = event.round
            round_count += 1
            round_started_at[event.round] = now
            if event.repair_context is not None:
                repair_count += 1
                if verbose:
                    rprint(
                        f"[yellow]round {event.round}: repair (上一轮 {len(event.repair_context.errors)} 个错误)[/yellow]"
                    )
        elif isinstance(event, PlanCreatedEvent):
            static_errors = check_dag(plan_spec_v1.build_dag(event.plan), known_ops)
            step_goals = {
                str(_field(s, "step_id")): str(_field(s, "step_goal") or "")
                for s in _plan_steps(event.plan)
            }
            if verbose:
                rprint(
                    f"[dim]round {event.round}: plan created — {len(_plan_steps(event.plan))} steps, "
                    f"static_errors={len(static_errors)}. 开始执行… "
                    f"elapsed={time.perf_counter() - started:.1f}s[/dim]"
                )
            plans_by_round.append(
                {
                    "round": event.round,
                    "plan": _jsonable(event.plan),
                    "static_errors": [_error_row(e) for e in static_errors],
                    "shape": analyze_plan_shape(event.plan),
                    "reference_patterns": analyze_reference_patterns(event.plan),
                }
            )
        elif isinstance(event, PlanRunnerErrorEvent):
            runtime_errors.extend(
                _error_row(e, round_no=current_round) for e in event.errors
            )
            if verbose:
                for e in event.errors:
                    sid = getattr(getattr(e, "detail", None), "step_id", None)
                    goal = step_goals.get(str(sid), "") if sid else ""
                    label = f"step {sid} — {goal}" if sid else "plan"
                    rprint(
                        f"[red]  ✗ {label} "
                        f"(elapsed={time.perf_counter() - started:.1f}s): "
                        f"{_diagnosis_line(e)}[/red]"
                    )
        elif isinstance(event, PlActErrorsEvent):
            unresolved_errors = [
                _error_row(e, round_no=event.round) for e in event.errors
            ]
            if verbose:
                rprint(
                    f"[yellow]round {event.round}: {len(event.errors)} errors → {event.policy}[/yellow]"
                )
        elif isinstance(event, PlanStepDoneEvent):
            if verbose:
                if event.unmet:
                    mark = f" [yellow](未达成 {event.unmet.verdict}：{event.unmet.reason})[/yellow]"
                elif event.process_error:
                    mark = f" [red](process_error:{event.process_error.kind})[/red]"
                else:
                    mark = ""
                rprint(
                    f"[dim]  step {event.step_id} done "
                    f"(elapsed={time.perf_counter() - started:.1f}s) — "
                    f"{event.step_goal}{mark}[/dim]"
                )
            step_done.append(
                {
                    "round": current_round,
                    "step_id": event.step_id,
                    "goal": event.step_goal,
                    "resolved_inputs": _jsonable(event.resolved_inputs),
                    "tool_output": _jsonable(event.tool_output),
                    "concept_output": _jsonable(event.concept_output),
                    "unmet": _jsonable(event.unmet) if event.unmet else None,
                    "process_error": _jsonable(event.process_error)
                    if event.process_error
                    else None,
                }
            )
        elif isinstance(event, PlanStepSkippedEvent):
            if verbose:
                rprint(
                    f"[dim]  step {event.step_id} skipped "
                    f"(elapsed={time.perf_counter() - started:.1f}s) — "
                    f"{event.step_goal} ({event.reason})[/dim]"
                )
            skipped.append(
                {
                    "round": current_round,
                    "step_id": event.step_id,
                    "goal": event.step_goal,
                    "reason": event.reason,
                }
            )
        elif isinstance(event, PlActFinishEvent):
            if current_round is not None and current_round in round_started_at:
                round_seconds[current_round] = round(
                    time.perf_counter() - round_started_at[current_round], 4
                )
            if verbose:
                rprint(
                    f"[dim]answer ready (forced={event.forced}). total={time.perf_counter() - started:.1f}s[/dim]"
                )
            finish = event

    forced = bool(finish.forced) if finish else None
    final_plan = plans_by_round[-1] if plans_by_round else None
    # forced=False 时 unresolved_errors 已被修复，不作数
    if not forced:
        unresolved_errors = []

    record: dict[str, Any] = {
        "case_id": case.case_id,
        "query": case.query,
        "plan": {
            "topology": final_plan["shape"]["topology"] if final_plan else None,
            "graph_features": final_plan["shape"]["features"] if final_plan else None,
            "reference_patterns": final_plan["reference_patterns"]
            if final_plan
            else [],
            "final_plan": final_plan["plan"] if final_plan else None,
        },
        "static_errors": final_plan["static_errors"] if final_plan else [],
        "plans_by_round": plans_by_round,  # 各轮尝试的 plan + 静态错误（供按 round 组织的 evidence / dump）
        "execution": {
            "round_count": round_count,
            "round_seconds": [
                {"round": number, "seconds": seconds}
                for number, seconds in sorted(round_seconds.items())
            ],
            "repair_count": repair_count,
            "forced": forced,
            "runtime_errors": runtime_errors,
            "unresolved_errors": unresolved_errors,
            "step_done": step_done,
            "skipped": skipped,
        },
        "final_response": finish.response if finish else None,
        "attribution": None,
        "events": events,
        "timing": {"total_seconds": round(time.perf_counter() - started, 2)},
    }

    if not skip_attribution and attrib_model_api is not None and finish is not None:
        if verbose:
            rprint(
                "[dim]归因中（LLM structured_output，可能耗时十几秒到一两分钟）…[/dim]"
            )
        attrib_started = time.perf_counter()
        record["attribution"] = await _attribute_fulfillment(
            case=case,
            attrib_model_api=attrib_model_api,
            record=record,
            reason=finish.reason,
            params=params,
        )
        record["timing"]["attribution_seconds"] = round(
            time.perf_counter() - attrib_started, 2
        )

    return record


_LEVER_GUIDE = """\
【lever 分类（每条根因选且只选一个，对齐可执行的优化杠杆）】
① 工具 tool —— 工具能力不足/缺失/结果不全或错；数据客观不存在/超纲也归此（视作工具不够好）。
② 模型表现 model（手段=提示词 + plan_schema description 调优，模型固有不足也归此）：
   - model_plan：plan 生成质量（结构/引用/拆解/success_check 表达）。
   - model_diagnosis：诊断判断质量。
   - model_replan：repair 时重规划质量；同一问题跨多轮 repair 仍未消解，通常就归此（replan/repair 提示词该改）。
   - model_answer：最终回答合成质量（遗漏/虚构/未如实告知/泄露实现）。
③ 机制 mechanism —— 需要改 runner 控制流 / schema 结构 / 加新机制（而非 description/提示词）才能解决的根因。
关键：plan 结构/引用/诊断准确性这类「改 description 就能改善」的一律归 model_*；mechanism 只留给必须动代码/结构的情形。

【三原则】
- 达成率归因：聚焦「原始 query 达成到什么程度 + 未达成的根因」。
- 一错一根因：根因已明确且已如实告知用户（disclosed_in_answer=true）时，本条到此为止。
- 无效 repair 归 model_replan：evidence 的 rounds 按轮列出各轮错误。
  同一问题（同一 step / 同类错误）跨多轮 repair 仍未消解时，归 model_replan（replan/repair 提示词需改进），
  并在 root_cause 里说明多轮 repair 未见效。
"""


async def _attribute_fulfillment(
    *,
    case: EvalCase,
    attrib_model_api: Any,
    record: dict[str, Any],
    reason: str | None,
    params: ModelCallParams,
) -> dict[str, Any]:
    # 判达成率的决定性证据是最终一轮：完整 plan + 每步 concept_output + final_response，放第一层。
    # 早期轮次只留错误，供看 repair 历史 / 无效 repair（各轮 plan 逐轮重复又大又噪，略去）。
    # topology / reference_patterns 是给 batch 因果分析的，这里略去。
    execution = record["execution"]
    plans = record["plans_by_round"]
    final_round = plans[-1]["round"] if plans else None

    step_outputs = [
        {
            "step_id": s["step_id"],
            "goal": s["goal"],
            "resolved_inputs": s["resolved_inputs"],
            "concept_output": s[
                "concept_output"
            ],  # 该步经 concept 投影后的实际产出 —— 判达成的关键证据
            "unmet": s["unmet"],
            "process_error": s["process_error"],
        }
        for s in execution["step_done"]
        if s["round"] == final_round
    ]
    rounds = [
        {
            "round": p["round"],
            "static_errors": p["static_errors"],
            "runtime_errors": [
                e for e in execution["runtime_errors"] if e.get("round") == p["round"]
            ],
            "skipped": [
                s for s in execution["skipped"] if s.get("round") == p["round"]
            ],
        }
        for p in plans
    ]
    evidence = {
        "query": case.query,
        # ── 第一层：最终一轮的结果（判达成率的主证据）──
        "final_round": final_round,
        "final_plan": record["plan"]["final_plan"],
        "step_outputs": step_outputs,  # 最终一轮每步实际产出
        "final_response": record["final_response"],
        "forced": execution["forced"],
        "unresolved_errors": execution["unresolved_errors"],
        # ── 各轮概览：只给错误 / 跳过，用于看 repair 历史与无效 repair（不含完整 plan）──
        "rounds": rounds,
        "round_count": execution["round_count"],
        "repair_count": execution["repair_count"],
        "finish_reason": reason,
    }
    prompt = (
        "你是 plan-and-act 端到端评测的达成率归因器。基于原始 query、最终采用的 plan、执行结果与最终回答，"
        "判定该 query 的达成率，并对每个未达成/错误给出根因归因（映射到可执行的优化 lever）。\n\n"
        + _LEVER_GUIDE
        + "\n只依据下面呈现的最终结果判定（尤其看每个 step 的 concept_output 是否满足了对应需求）；"
        "已被后续 repair 修复的历史问题视为已解决。请只输出符合 FulfillmentAttribution schema 的 JSON。\n\n"
        + f"评测材料：\n{_truncate(evidence, max_chars=400000)}"
    )
    try:
        result = await attrib_model_api.structured_output(
            UserMessage(text=prompt),
            output_type=FulfillmentAttribution,
            state=attrib_model_api.initial_state(),
            params=params,
        )
        if result.parsed is None:
            return {
                "error": "attribution returned no parsed output",
                "raw_text": result.text,
            }
        return result.parsed.model_dump(mode="json")
    except Exception as exc:
        return {"error": str(exc)}


# ───────────────────────────────── 构造（供批量脚本复用）─────────────────────────────────


def build_tools() -> list[Any]:
    return get_default_tools(chat_id="User")


def build_model_apis(args: argparse.Namespace) -> tuple[Any, Any | None]:
    model_api = create_model_api(model=args.model, backend=args.backend)
    attrib_model_api = None
    if not args.skip_attribution:
        attrib_model_api = create_model_api(
            model=getattr(args, "attrib_model", None) or args.model,
            backend=getattr(args, "attrib_backend", None) or args.backend,
        )
    return model_api, attrib_model_api


# ─────────────────────────────────── CLI 入口 ───────────────────────────────────


def _add_common_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=ModelName.SEED_2_1_PRO_260628.value)
    parser.add_argument("--backend", choices=["chat", "responses"], default="responses")
    parser.add_argument("--attrib-model", default=None)
    parser.add_argument("--attrib-backend", choices=["chat", "responses"], default=None)
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument(
        "--thinking", choices=["enabled", "disabled", "auto"], default="disabled"
    )
    parser.add_argument("--skip-attribution", action="store_true")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="单 case 达成率归因（test_plact 扩展版）。"
    )
    parser.add_argument(
        "query", nargs="?", default=None, help="要评测的 query；缺省用内置示例。"
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="把单 case record 落成 JSON。"
    )
    _add_common_model_args(parser)
    return parser.parse_args()


_GRADE_LABEL = {
    "perfect": "完美解决",
    "imperfect_honest": "不完美但如实回复",
    "imperfect_flawed": "不完美且遗漏需求/捏造事实",
}
_GRADE_COLOR = {
    "perfect": "green",
    "imperfect_honest": "yellow",
    "imperfect_flawed": "red",
}


def _print_record(record: dict[str, Any]) -> None:
    # 过程已在 verbose 流式打印，这里不再重复过程 trace。
    rprint(f"\n[bold]=== query ===[/bold]\n{record['query']}")

    plan = record["plan"]
    rprint("\n[bold]=== plan 模式 / 引用模式 ===[/bold]")
    rprint(f"  topology={plan['topology']}  features={plan['graph_features']}")
    rprint(f"  reference_patterns={plan['reference_patterns']}")
    if record["static_errors"]:
        rprint(
            f"  [red]static_errors={len(record['static_errors'])}[/red] "
            + ", ".join(f"{e['source']}/{e['kind']}" for e in record["static_errors"])
        )

    rprint("\n[bold]=== 最终回答 ===[/bold]")
    rprint(record["final_response"])

    attribution = record.get("attribution")
    if isinstance(attribution, dict) and "error" not in attribution:
        grade = attribution.get("grade")
        color = _GRADE_COLOR.get(str(grade), "white")
        rprint("\n[bold]=== 达成率归因 ===[/bold]")
        rprint(
            f"  评级：[{color}]{grade} — {_GRADE_LABEL.get(str(grade), grade)}[/{color}]"
        )
        for a in attribution.get("attributions", []):
            flag_text = " [已告知]" if a.get("disclosed_in_answer") else ""
            rprint(
                f"  [cyan]{a['lever']}[/cyan]"
                f"{('(' + a['component'] + ')') if a.get('component') else ''}"
                f" <{a['confidence']}>{flag_text}: {a['root_cause']}"
            )
            rprint(f"      [dim]issue: {a.get('issue', '')}[/dim]")
    elif isinstance(attribution, dict):
        rprint(f"\n[red]attribution error:[/red] {attribution.get('error')}")


async def _amain(args: argparse.Namespace) -> None:
    case = EvalCase(case_id="adhoc", query=args.query or DEFAULT_QUERY)
    tools = build_tools()
    model_api, attrib_model_api = build_model_apis(args)
    params = ModelCallParams(thinking=args.thinking)
    record = await run_single_case(
        case,
        model_api=model_api,
        attrib_model_api=attrib_model_api,
        tools=tools,
        params=params,
        max_turns=args.max_turns,
        skip_attribution=args.skip_attribution,
        verbose=True,
    )
    _print_record(record)

    # 详细事件 trace（含 concept_output / 原始输出）落 JSON，控制台只打印路径。
    if args.output is not None:
        out_path = args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        fd, tmp_name = tempfile.mkstemp(prefix="plact_single_", suffix=".json")
        os.close(fd)
        out_path = Path(tmp_name)
    out_path.write_text(
        json.dumps(_jsonable(record), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rprint(f"\n[bold]详细事件 trace →[/bold] {out_path}")


def _main() -> None:
    anyio.run(_amain, _parse_args(), backend="asyncio")


if __name__ == "__main__":
    _main()
