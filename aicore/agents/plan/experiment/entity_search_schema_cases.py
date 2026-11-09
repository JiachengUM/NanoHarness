from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

from aicore.tools.dag.operator_models import (
    MusicSearchOutput,
    POISearchOutput,
    WebSearchOutput,
)
from aicore.tools.experiments.entity_search_tool import full_output_schema_payload


SearchOp = Literal["poi_search", "web_search", "music_search"]


OP_OUTPUT_MODELS: dict[SearchOp, type[BaseModel]] = {
    "poi_search": POISearchOutput,
    "web_search": WebSearchOutput,
    "music_search": MusicSearchOutput,
}


@dataclass(frozen=True)
class PlanCase:
    case_id: str
    plan_index: int
    step_id: str
    source_user_query: str
    schema_query: str
    op: SearchOp
    inputs: dict[str, Any]
    reference_output_schema: dict[str, Any]
    reference_paths: list[str]
    output_model: type[BaseModel]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "plan_index": self.plan_index,
            "step_id": self.step_id,
            "source_user_query": self.source_user_query,
            "schema_query": self.schema_query,
            "op": self.op,
            "input": self.inputs,
            "reference_output_schema": self.reference_output_schema,
            "reference_paths": self.reference_paths,
            "full_output_schema": full_output_schema_payload(self.output_model),
        }


def extract_plan_cases(
    path: Path,
    *,
    full_schema_threshold: float = 2.0,
) -> list[PlanCase]:
    """从 plan JSON 提取 eval case。

    Args:
        full_schema_threshold: reference 叶子覆盖率 ≥ 此值时视为全量模板并跳过。
            默认 2.0（禁用全量过滤）。设为 1.0 可过滤 100% 覆盖的 case。
    """
    rows = json.loads(path.read_text(encoding="utf-8"))
    cases: list[PlanCase] = []
    skipped_mismatch = 0
    skipped_full = 0

    for item in rows:
        if not item.get("success", False):
            continue
        plan_index = int(item.get("index", len(cases)))
        source_user_query = str(item.get("query", ""))
        steps = item.get("plan", {}).get("steps") or []

        for step in steps:
            op = normalize_search_op(str(step.get("op", "")))
            if op is None:
                continue
            inputs = step.get("inputs") or {}
            if not isinstance(inputs, dict):
                continue
            if step.get("depends_on") or contains_step_ref(inputs):
                continue

            step_id = str(step.get("step_id", ""))
            output_schema = step.get("outputs") or {}
            if not isinstance(output_schema, dict):
                output_schema = {"value": output_schema}

            output_model = OP_OUTPUT_MODELS[op]
            ref_paths = extract_reference_paths(output_schema)

            # 过滤：reference 顶级字段与 model 完全不匹配（数据集错误）
            if not _reference_matches_model(ref_paths, output_model):
                skipped_mismatch += 1
                continue
            # 过滤：reference 覆盖全部叶子字段（非有效子集选择）
            if _leaf_coverage(ref_paths, output_model) >= full_schema_threshold:
                skipped_full += 1
                continue

            cases.append(
                PlanCase(
                    case_id=f"p{plan_index}_{step_id}_{op}",
                    plan_index=plan_index,
                    step_id=step_id,
                    source_user_query=source_user_query,
                    schema_query=str(step.get("step_goal", "")),
                    op=op,
                    inputs=inputs,
                    reference_output_schema=output_schema,
                    reference_paths=ref_paths,
                    output_model=output_model,
                )
            )

    if skipped_mismatch or skipped_full:
        print(
            f"[extract_plan_cases] skipped {skipped_mismatch} mismatch + "
            f"{skipped_full} full-schema cases, kept {len(cases)}"
        )

    return cases


def write_case_file(cases: list[PlanCase], output_path: Path, *, source: Path | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": str(source) if source is not None else None,
        "cases": [case.to_json_dict() for case in cases],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_case_file(path: Path) -> list[PlanCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["cases"] if isinstance(payload, dict) and "cases" in payload else payload
    if not isinstance(rows, list):
        raise ValueError(f"case file must contain a list or a dict with cases: {path}")
    return [_case_from_json(row) for row in rows]


def load_cases_from_excel(path: Path) -> list[PlanCase]:
    sheets = pd.read_excel(path, sheet_name=None)
    if "cases" not in sheets:
        raise ValueError(f"Excel workbook must contain a 'cases' sheet: {path}")
    case_rows = sheets["cases"].to_dict(orient="records")
    return [_case_from_excel_row(row) for row in case_rows]


def normalize_search_op(op: str) -> SearchOp | None:
    lowered = op.lower()
    if lowered in {"poisearch", "poi_search"}:
        return "poi_search"
    if lowered in {"websearch", "web_search"}:
        return "web_search"
    if lowered in {"musicsearch", "music_search"}:
        return "music_search"
    return None


def contains_step_ref(value: Any) -> bool:
    if isinstance(value, str):
        return "$" in value
    if isinstance(value, dict):
        return any(contains_step_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_step_ref(v) for v in value)
    return False


def extract_reference_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(extract_reference_paths(value[key], child_prefix))
        return paths or ([prefix] if prefix else [])
    if isinstance(value, list):
        if not value:
            return [prefix] if prefix else []
        paths: list[str] = []
        for item in value:
            paths.extend(extract_reference_paths(item, f"{prefix}[]"))
        return sorted(set(paths))
    return [prefix] if prefix else []


def _case_from_json(row: dict[str, Any]) -> PlanCase:
    op = normalize_search_op(str(row["op"]))
    if op is None:
        raise ValueError(f"unsupported search op: {row.get('op')}")
    reference_schema = row.get("reference_output_schema") or {}
    if not isinstance(reference_schema, dict):
        reference_schema = {"value": reference_schema}
    return PlanCase(
        case_id=str(row["case_id"]),
        plan_index=int(row.get("plan_index", 0)),
        step_id=str(row.get("step_id", "")),
        source_user_query=str(row.get("source_user_query", "")),
        schema_query=str(row.get("schema_query", "")),
        op=op,
        inputs=dict(row.get("input") or row.get("inputs") or {}),
        reference_output_schema=reference_schema,
        reference_paths=list(row.get("reference_paths") or extract_reference_paths(reference_schema)),
        output_model=OP_OUTPUT_MODELS[op],
    )


def _case_from_excel_row(row: dict[str, Any]) -> PlanCase:
    op = normalize_search_op(str(row["op"]))
    if op is None:
        raise ValueError(f"unsupported search op: {row.get('op')}")
    inputs = _loads_json_cell(row.get("input_json") or row.get("input") or "{}")
    reference_schema = _loads_json_cell(row.get("reference_schema_json") or "{}")
    reference_paths = _split_paths(row.get("reference_paths"))
    if not reference_paths:
        reference_paths = extract_reference_paths(reference_schema)
    return PlanCase(
        case_id=str(row["case_id"]),
        plan_index=int(row.get("plan_index") or 0),
        step_id=str(row.get("step_id") or ""),
        source_user_query=str(row.get("source_user_query") or ""),
        schema_query=str(row.get("schema_query") or ""),
        op=op,
        inputs=inputs if isinstance(inputs, dict) else {},
        reference_output_schema=reference_schema if isinstance(reference_schema, dict) else {},
        reference_paths=reference_paths,
        output_model=OP_OUTPUT_MODELS[op],
    )


def _loads_json_cell(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        return json.loads(value)
    return value


def _split_paths(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).splitlines() if part.strip()]


def _reference_matches_model(ref_paths: list[str], model: type[BaseModel]) -> bool:
    """至少有一个 reference 路径的顶级字段存在于 model 中，否则视为 op/reference 不匹配。"""
    if not ref_paths:
        return False
    top_level_fields = set(model.model_fields.keys())
    ref_top_level = {p.split(".")[0].split("[")[0] for p in ref_paths}
    return bool(ref_top_level & top_level_fields)


def _leaf_coverage(ref_paths: list[str], model: type[BaseModel]) -> float:
    """计算 reference 路径对 model 全部叶子字段的覆盖率（含前缀展开）。

    返回 0.0~1.0。当接近 1.0 时说明 reference 是全量模板，不是有意义的子集选择。
    """
    from aicore.tools.experiments.entity_search_tool import collect_schema_attributes

    all_leaves = set(collect_schema_attributes(model).keys())
    if not all_leaves:
        return 0.0
    covered: set[str] = set()
    for ref in ref_paths:
        for leaf in all_leaves:
            if leaf == ref or leaf.startswith(ref + ".") or leaf.startswith(ref + "["):
                covered.add(leaf)
    return len(covered) / len(all_leaves)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build fixed entity-search case JSON.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--input-format",
        choices=["plan-json", "excel"],
        default=None,
        help="Defaults to excel for .xlsx inputs, otherwise plan-json.",
    )
    parser.add_argument(
        "--full-schema-threshold",
        type=float,
        default=2.0,
        help="Reference leaf coverage >= threshold is filtered. Default 2.0 (disabled). Set 1.0 to filter full-schema cases.",
    )
    return parser.parse_args()


def _main() -> None:
    args = _parse_args()
    input_format = args.input_format
    if input_format is None:
        input_format = "excel" if args.input.suffix.lower() in {".xlsx", ".xls"} else "plan-json"
    if input_format == "excel":
        cases = load_cases_from_excel(args.input)
    else:
        cases = extract_plan_cases(
            args.input,
            full_schema_threshold=args.full_schema_threshold,
        )
    write_case_file(cases, args.output, source=args.input)
    print(f"wrote {len(cases)} cases -> {args.output}")


if __name__ == "__main__":
    _main()
