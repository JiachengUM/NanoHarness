"""批量运行 test_plact_single，并产出「诱因分类 + 因果分析」summary。

用 aicore/utils/anyio/amap.py 的 amap 并发跑 test_plact_single.run_single_case，
然后：
  1) build_causal_table —— 确定性把每 case 拍成一行「可能承载因果关系」的原始数据（不下结论）；
  2) rank_levers —— 按 case 数与达成率加权影响给优化 lever 排优先级（两者都给）；
  3) analyze_causality —— 末尾一次 structured_output LLM，按不同维度 aggregate 做因果归纳。

直接运行：
    uv run python tests/agents/test_plact_with_eval_batch.py --input synthetic_complex_plan_queries.json --limit 3 --max-concurrent 3
    uv run python tests/agents/test_plact_with_eval_batch.py --input data.json --skip-causal --csv reports/table.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import anyio
from pydantic import BaseModel, Field
from rich import print as rprint

sys.path.insert(0, str(Path(__file__).resolve().parent))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aicore.models.credentials import ModelName
from aicore.models.model_api import ModelCallParams, UserMessage, create_model_api
from aicore.utils.anyio.amap import amap
from test_plact_with_eval import (
    EvalCase,
    build_model_apis,
    build_tools,
    load_eval_cases,
    run_single_case,
)

DEFAULT_DIMENSIONS = "lever,layer,component,topology,runtime_error_class"


# ───────────────────────────── 因果归纳 schema（LLM structured）─────────────────────────────


class DimensionGroup(BaseModel):
    group: str = Field(description="该维度下的一个取值分组，如 lever=model_plan、topology=conditional。")
    count: int = Field(description="落入该分组的 case 数。")
    weighted_impact: float = Field(description="该分组对达成率的加权影响（低达成率 case 权重更高）。")
    likely_cause: str = Field(description="这一组失败/未达成背后最可能的共同根因。")
    cause_to_effect: str = Field(description="从该根因到观测到的达成率下降/错误的因果链路说明。")
    evidence_cases: list[str] = Field(default_factory=list, description="支撑该判断的代表性 case_id。")


class DimensionFinding(BaseModel):
    dimension: str
    groups: list[DimensionGroup] = Field(default_factory=list)


class CausalAnalysis(BaseModel):
    dimensions: list[DimensionFinding] = Field(default_factory=list)
    overall_hypotheses: list[str] = Field(
        default_factory=list, description="跨维度的整体因果假设，按对整体达成率的影响排序。"
    )


# ─────────────────────────────── 确定性诱因分类 + 原始数据表 ───────────────────────────────


def _error_class(row: dict[str, Any]) -> str:
    """把静/动态错误按 source+kind 归成一个确定性诱因类。"""
    source = str(row.get("source") or "")
    kind = str(row.get("kind") or "")
    if source == "plan.schema":
        return "schema"
    if source == "plan.logic":
        if kind.startswith("logic.ref"):
            return "reference"
        if kind in {"logic.cycle", "logic.dup_step_id", "logic.self_dep", "logic.unknown_dep", "logic.unknown_op"}:
            return "structure"
        if kind in {"logic.invalid_condition", "logic.invalid_success_check", "logic.success_check_not_self_constrained"}:
            return "expression"
        return "logic_other"
    if source == "step.params":
        return "params"
    if source == "step.execution":
        return "tool_exec"
    if source == "step.projection":
        return "projection"
    if source == "step.condition":
        return "condition_runtime"
    if source == "step.remediation":
        return "remediation"
    return source or "unknown"


def _layer_of(lever: str) -> str:
    if lever == "tool":
        return "tool"
    if lever == "mechanism":
        return "mechanism"
    return "model"


def build_causal_table(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每 case 一行，抽取可能承载因果关系的扁平字段。仅分类，不下结论。"""
    table: list[dict[str, Any]] = []
    for record in records:
        if "error" in record and "plan" not in record:
            table.append({"case_id": record.get("case_id"), "run_error": record.get("error")})
            continue
        plan = record.get("plan") or {}
        execution = record.get("execution") or {}
        attribution = record.get("attribution") if isinstance(record.get("attribution"), dict) else {}
        attributions = attribution.get("attributions") or []
        levers = [a.get("lever") for a in attributions]
        table.append(
            {
                "case_id": record.get("case_id"),
                "topology": plan.get("topology"),
                "reference_patterns": plan.get("reference_patterns") or [],
                "static_error_classes": [_error_class(e) for e in (record.get("static_errors") or [])],
                "runtime_error_classes": [_error_class(e) for e in (execution.get("runtime_errors") or [])],
                "repair_count": execution.get("repair_count"),
                "forced": execution.get("forced"),
                "grade": attribution.get("grade"),
                "levers": levers,
                "layers": [_layer_of(str(lv)) for lv in levers if lv],
                "components": [a.get("component") for a in attributions if a.get("component")],
                "confidences": [a.get("confidence") for a in attributions],
            }
        )
    return table


_GRADE_WEIGHT = {"perfect": 1, "imperfect_honest": 2, "imperfect_flawed": 3}


def rank_levers(table: list[dict[str, Any]]) -> dict[str, Any]:
    """按 lever 聚合：case 数 与 达成率加权影响（评级越差权重越高），两种排序都给。"""
    agg: dict[str, dict[str, Any]] = {}
    for row in table:
        weight = _GRADE_WEIGHT.get(row.get("grade"), 2)  # 未知评级给中性权重
        for lever in set(lv for lv in (row.get("levers") or []) if lv):
            node = agg.setdefault(str(lever), {"lever": str(lever), "layer": _layer_of(str(lever)),
                                               "case_count": 0, "weighted_impact": 0.0, "cases": []})
            node["case_count"] += 1
            node["weighted_impact"] += weight
            node["cases"].append(row.get("case_id"))
    entries = list(agg.values())
    return {
        "by_case_count": sorted(entries, key=lambda e: (-e["case_count"], -e["weighted_impact"])),
        "by_weighted_impact": sorted(entries, key=lambda e: (-e["weighted_impact"], -e["case_count"])),
    }


# ─────────────────────────────── 末尾一次 LLM 因果归纳 ───────────────────────────────


async def analyze_causality(
    table: list[dict[str, Any]],
    lever_ranking: dict[str, Any],
    *,
    dimensions: list[str],
    model_api: Any,
    params: ModelCallParams,
) -> dict[str, Any]:
    payload = {
        "dimensions_to_aggregate": dimensions,
        "lever_ranking": lever_ranking,
        "raw_table": table,
    }
    prompt = (
        "你是 plan-and-act 批量评测的因果分析器。下面是一张每 case 一行的原始数据表（已做确定性诱因分类，"
        "但未下任何因果结论），以及按优化 lever 的确定性排名。\n"
        "请按 dimensions_to_aggregate 里给的每个维度分别聚合，找出每个分组背后最可能的共同根因，"
        "并说明从根因到达成率下降的因果链路；最后给出跨维度、按整体达成率影响排序的 overall_hypotheses。\n"
        "lever 含义：tool=工具能力/数据缺口；model_*=靠改提示词/schema description 提升模型表现；"
        "mechanism=必须动 runner/schema 结构。只依据表内数据推断，不要臆造表里没有的 case。\n"
        "请只输出符合 CausalAnalysis schema 的 JSON。\n\n"
        f"数据：\n{_truncate(payload, max_chars=48000)}"
    )
    try:
        result = await model_api.structured_output(
            UserMessage(text=prompt),
            output_type=CausalAnalysis,
            state=model_api.initial_state(),
            params=params,
        )
        if result.parsed is None:
            return {"error": "causal analysis returned no parsed output", "raw_text": result.text}
        return result.parsed.model_dump(mode="json")
    except Exception as exc:
        return {"error": str(exc)}


# ─────────────────────────────────── 序列化 / 落盘 ───────────────────────────────────


def _truncate(value: Any, *, max_chars: int) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... <truncated>"


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(f"{output_path.name}.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(output_path)


def write_csv(table: list[dict[str, Any]], csv_path: Path) -> None:
    if not table:
        return
    keys = list({k for row in table for k in row.keys()})
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for row in table:
            writer.writerow({k: ("|".join(map(str, v)) if isinstance(v, list) else v) for k, v in row.items()})


def _safe_name(case_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(case_id)) or "case"


# ─────────────────────────────────── CLI 入口 ───────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量达成率归因 + 因果 summary（amap）。")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/plact_complex_plan_eval.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--max-concurrent", type=int, default=4)
    parser.add_argument("--model", default=ModelName.SEED_2_0_PRO_260215.value)
    parser.add_argument("--backend", choices=["chat", "responses"], default="responses")
    parser.add_argument("--attrib-model", default=None)
    parser.add_argument("--attrib-backend", choices=["chat", "responses"], default=None)
    parser.add_argument("--causal-model", default=None)
    parser.add_argument("--causal-backend", choices=["chat", "responses"], default=None)
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--thinking", choices=["enabled", "disabled", "auto"], default="disabled")
    parser.add_argument("--skip-attribution", action="store_true")
    parser.add_argument("--skip-causal", action="store_true")
    parser.add_argument("--dimensions", default=DEFAULT_DIMENSIONS)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--no-per-case", action="store_true")
    return parser.parse_args()


def _select_cases(args: argparse.Namespace) -> list[EvalCase]:
    cases = load_eval_cases(args.input)
    if args.case_id:
        wanted = set(args.case_id)
        cases = [c for c in cases if c.case_id in wanted]
    if args.limit is not None:
        cases = cases[: args.limit]
    return cases


async def _amain(args: argparse.Namespace) -> None:
    cases = _select_cases(args)
    if not cases:
        raise SystemExit(f"no cases selected from {args.input}")

    tools = build_tools()
    model_api, attrib_model_api = build_model_apis(args)
    params = ModelCallParams(thinking=args.thinking)
    per_case_dir = args.output.parent / "cases"

    async def run_one(case: EvalCase) -> dict[str, Any]:
        record = await run_single_case(
            case,
            model_api=model_api,
            attrib_model_api=attrib_model_api,
            tools=tools,
            params=params,
            max_turns=args.max_turns,
            skip_attribution=args.skip_attribution,
        )
        if not args.no_per_case:
            per_case_dir.mkdir(parents=True, exist_ok=True)
            path = per_case_dir / f"{_safe_name(case.case_id)}.json"
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return record

    rprint(f"[dim]running {len(cases)} cases, max_concurrent={args.max_concurrent}[/dim]")
    results, stats = await amap(run_one, cases, max_concurrent=max(1, args.max_concurrent), progress=True)

    records: list[dict[str, Any]] = []
    for case, result in zip(cases, results):
        if isinstance(result, Exception):
            records.append({"case_id": case.case_id, "error": f"{type(result).__name__}: {result}"})
        else:
            records.append(result)

    table = build_causal_table(records)
    lever_ranking = rank_levers([r for r in table if "run_error" not in r])

    causal_analysis: dict[str, Any] | None = None
    if not args.skip_causal:
        causal_model_api = create_model_api(
            model=args.causal_model or args.model,
            backend=args.causal_backend or args.backend,
        )
        rprint("[dim]running causal analysis…[/dim]")
        causal_analysis = await analyze_causality(
            table,
            lever_ranking,
            dimensions=[d.strip() for d in args.dimensions.split(",") if d.strip()],
            model_api=causal_model_api,
            params=params,
        )

    report = {
        "version": 1,
        "run": {
            "input": str(args.input),
            "output": str(args.output),
            "model": args.model,
            "backend": args.backend,
            "case_count": len(cases),
            "max_concurrent": args.max_concurrent,
            "max_turns": args.max_turns,
            "thinking": args.thinking,
            "skip_attribution": args.skip_attribution,
            "skip_causal": args.skip_causal,
        },
        "causal_table": table,
        "lever_ranking": lever_ranking,
        "causal_analysis": causal_analysis,
        "records": records,
    }
    write_report(report, args.output)
    if args.csv is not None:
        write_csv(table, args.csv)

    _print_summary(report, stats)


def _print_summary(report: dict[str, Any], stats: Any) -> None:
    rprint(f"\n[bold]wrote[/bold] {report['run']['output']}")
    rprint("\n[bold]=== lever ranking (by weighted impact) ===[/bold]")
    for entry in report["lever_ranking"].get("by_weighted_impact", []):
        rprint(
            f"  [cyan]{entry['lever']}[/cyan] ({entry['layer']}) "
            f"cases={entry['case_count']} weighted_impact={entry['weighted_impact']:.0f}"
        )
    analysis = report.get("causal_analysis")
    if isinstance(analysis, dict) and "error" not in analysis:
        rprint("\n[bold]=== overall causal hypotheses ===[/bold]")
        for hypo in analysis.get("overall_hypotheses", []):
            rprint(f"  - {hypo}")
    elif isinstance(analysis, dict):
        rprint(f"\n[red]causal analysis error:[/red] {analysis.get('error')}")

    rprint("\n[bold]=== amap stats ===[/bold]")
    for line in stats.dump():
        rprint(f"  {line}")


def _main() -> None:
    anyio.run(_amain, _parse_args(), backend="asyncio")


if __name__ == "__main__":
    _main()
