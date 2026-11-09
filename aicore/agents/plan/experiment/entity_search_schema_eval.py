from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import anyio
import pandas as pd
from pydantic import BaseModel

from aicore.agents.plan.experiment.entity_search_schema_cases import (
    PlanCase,
    load_case_file,
)
from aicore.models.credentials import ModelName
from aicore.models.model_api import create_model_api
from aicore.tools import TaskToolTypeGeneral
from aicore.tools.experiments.entity_search_tool import (
    EntitySearchSchemaWorker,
    EntitySearchToolInput,
    collect_schema_attributes,
    compact_output_schema,
    concept_to_schema,
    create_entity_search_tool,
    flatten_concept_paths,
    full_output_schema_payload,
)
from aicore.tools.experiments.entity_search_tool_v2 import (
    EntitySearchSchemaWorkerV2,
    EntitySearchToolInputV2,
    attributes_to_field_types,
    attributes_to_fields,
    build_prompt_v2,
    create_entity_search_tool_v2,
    flatten_simple_concept_paths,
    simple_concept_to_schema,
)
from aicore.tools.runner.task_tool_runner import TaskToolRunner
from aicore.utils._concepts.meta import Concept, SimpleConcept


ConceptGenerator = Callable[["PlanCase"], Awaitable[Concept | SimpleConcept]]


@dataclass(frozen=True)
class EvaluationResult:
    case: PlanCase
    generated_concept: dict[str, Any] | None
    generated_paths: list[str]
    invalid_generated_paths: list[str]
    generated_schema: dict[str, Any] | None
    error: str | None
    duration_s: float | None
    input_chars: int
    total_leaf_count: int
    generated_leaf_count: int
    compression_rate: float | None
    prompt_text: str


ToolVersion = Literal["v1", "v2"]


async def run_eval(
    cases: list[PlanCase],
    generator: ConceptGenerator,
    *,
    concurrency: int = 50,
    schema_mode: SchemaMode = "full",
    tool_version: ToolVersion = "v1",
) -> list[EvaluationResult]:
    results: list[EvaluationResult | None] = [None] * len(cases)
    sem = anyio.Semaphore(concurrency)

    async def _run(idx: int, case: PlanCase) -> None:
        async with sem:
            results[idx] = await _evaluate_case(
                case, generator, schema_mode=schema_mode, tool_version=tool_version,
            )

    async with anyio.create_task_group() as tg:
        for idx, case in enumerate(cases):
            tg.start_soon(_run, idx, case)

    return results  # type: ignore[return-value]


def write_excel(results: list[EvaluationResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    case_rows = [_case_row(result) for result in results]
    schema_rows = [_schema_row(result) for result in results]
    summary_rows = _summary_rows(results)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(case_rows).to_excel(writer, sheet_name="cases", index=False)
        pd.DataFrame(schema_rows).to_excel(writer, sheet_name="schemas", index=False)
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="summary", index=False)


async def _evaluate_case(
    case: PlanCase,
    generator: ConceptGenerator,
    *,
    schema_mode: SchemaMode = "full",
    tool_version: ToolVersion = "v1",
) -> EvaluationResult:
    prompt_text = _build_prompt_text(case, schema_mode=schema_mode, tool_version=tool_version)
    input_chars = len(prompt_text)
    try:
        t0 = time.monotonic()
        output = await generator(case)
        duration_s = time.monotonic() - t0

        # 根据输出类型分派 flatten / schema 函数
        if isinstance(output, SimpleConcept):
            generated_paths = flatten_simple_concept_paths(output)
            generated_schema = simple_concept_to_schema(output)
        else:
            generated_paths = flatten_concept_paths(output)
            generated_schema = concept_to_schema(output)

        allowed_fields = collect_schema_attributes(case.output_model)
        invalid_paths = [p for p in generated_paths if p not in allowed_fields]
        total_leaves = len(allowed_fields)
        gen_leaf_count = len(generated_paths)
        compression = 1.0 - gen_leaf_count / total_leaves if total_leaves else None
        return EvaluationResult(
            case=case,
            generated_concept=output.model_dump(),
            generated_paths=generated_paths,
            invalid_generated_paths=invalid_paths,
            generated_schema=generated_schema,
            error=None,
            duration_s=duration_s,
            input_chars=input_chars,
            total_leaf_count=total_leaves,
            generated_leaf_count=gen_leaf_count,
            compression_rate=compression,
            prompt_text=prompt_text,
        )
    except Exception as exc:
        total_leaves = len(collect_schema_attributes(case.output_model))
        return EvaluationResult(
            case=case,
            generated_concept=None,
            generated_paths=[],
            invalid_generated_paths=[],
            generated_schema=None,
            error=f"{type(exc).__name__}: {exc}",
            duration_s=None,
            input_chars=input_chars,
            total_leaf_count=total_leaves,
            generated_leaf_count=0,
            compression_rate=None,
            prompt_text=prompt_text,
        )


SchemaMode = Literal["full", "compact"]


def _get_output_schema(model: type[BaseModel], mode: SchemaMode) -> dict[str, Any]:
    if mode == "compact":
        return compact_output_schema(model)
    return model.model_json_schema()


def _make_live_generator(
    *,
    model: str,
    backend: Literal["chat", "responses"],
    schema_mode: SchemaMode = "full",
    tool_version: ToolVersion = "v1",
) -> ConceptGenerator:
    model_api = create_model_api(backend=backend, model=model)
    if tool_version == "v2":
        worker = EntitySearchSchemaWorkerV2(model_api)
        tool = create_entity_search_tool_v2(worker)
        return _make_tool_generator_v2(tool)
    schema_worker = EntitySearchSchemaWorker(model_api)
    tool = create_entity_search_tool(schema_worker)
    return _make_tool_generator(tool, schema_mode=schema_mode)


def _make_tool_generator(
    tool: TaskToolTypeGeneral,
    *,
    schema_mode: SchemaMode = "full",
) -> ConceptGenerator:
    async def run_entity_search_tool(case: PlanCase) -> Concept:
        runner = TaskToolRunner()
        runner.add_tool(
            tool,
            EntitySearchToolInput(
                query=case.schema_query,
                tool_name=case.op,
                output_schema=_get_output_schema(case.output_model, schema_mode),
            ),
        )
        async for _ in runner.run():
            pass

        if not runner.results:
            raise RuntimeError("entity_search_tool returned no result")

        result = runner.results[0]
        if not result.is_success:
            raise RuntimeError(result.error or "entity_search_tool failed")

        concept = result.data
        if not isinstance(concept, Concept):
            raise TypeError(
                f"entity_search_tool returned {type(concept).__name__}, expected Concept"
            )
        return concept

    return run_entity_search_tool


def _make_tool_generator_v2(
    tool: TaskToolTypeGeneral,
) -> ConceptGenerator:
    """V2 generator：使用 flat-path 工具，输出 SimpleConcept。"""

    async def run_entity_search_tool_v2(case: PlanCase) -> SimpleConcept:
        all_attrs = collect_schema_attributes(case.output_model)
        runner = TaskToolRunner()
        runner.add_tool(
            tool,
            EntitySearchToolInputV2(
                query=case.schema_query,
                tool_name=case.op,
                fields=attributes_to_fields(all_attrs),
                field_types=attributes_to_field_types(all_attrs),
            ),
        )
        async for _ in runner.run():
            pass

        if not runner.results:
            raise RuntimeError("entity_search_tool_v2 returned no result")

        result = runner.results[0]
        if not result.is_success:
            raise RuntimeError(result.error or "entity_search_tool_v2 failed")

        sc = result.data
        if not isinstance(sc, SimpleConcept):
            raise TypeError(
                f"entity_search_tool_v2 returned {type(sc).__name__}, expected SimpleConcept"
            )
        return sc

    return run_entity_search_tool_v2


# ---------------------------------------------------------------------------
# 行级指标
# ---------------------------------------------------------------------------


def _case_row(result: EvaluationResult) -> dict[str, Any]:
    case = result.case
    p = _precision(result)
    r = _recall(result)
    missing = [
        ref for ref in case.reference_paths
        if not any(_paths_match(ref, gen) for gen in result.generated_paths)
    ]
    extra = [
        gen for gen in result.generated_paths
        if not any(_paths_match(ref, gen) for ref in case.reference_paths)
    ]
    return {
        "case_id": case.case_id,
        "plan_index": case.plan_index,
        "step_id": case.step_id,
        "source_user_query": case.source_user_query,
        "schema_query": case.schema_query,
        "op": case.op,
        "input_json": _json(case.inputs),
        "reference_paths": "\n".join(case.reference_paths),
        "generated_paths": "\n".join(result.generated_paths),
        "missing_vs_reference": "\n".join(sorted(missing)),
        "extra_vs_reference": "\n".join(sorted(extra)),
        "invalid_generated_paths": "\n".join(result.invalid_generated_paths),
        "total_leaf_count": result.total_leaf_count,
        "generated_leaf_count": result.generated_leaf_count,
        "compression_rate": result.compression_rate,
        "precision": p,
        "recall": r,
        "f1": _f1(p, r),
        "duration_s": result.duration_s,
        "input_chars": result.input_chars,
        "error_type": _classify_error(result.error),
        "error": result.error,
    }


def _schema_row(result: EvaluationResult) -> dict[str, Any]:
    case = result.case
    return {
        "case_id": case.case_id,
        "prompt_text": result.prompt_text,
        "full_output_schema_json": _json(full_output_schema_payload(case.output_model)),
        "reference_schema_json": _json(case.reference_output_schema),
        "generated_concept_json": _json(result.generated_concept),
        "generated_schema_json": _json(result.generated_schema),
    }


# ---------------------------------------------------------------------------
# 汇总指标：precision / recall / F1
# ---------------------------------------------------------------------------


def _summary_rows(results: list[EvaluationResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for op in sorted({result.case.op for result in results}):
        op_results = [result for result in results if result.case.op == op]
        precisions = [_precision(r) for r in op_results]
        recalls = [_recall(r) for r in op_results]
        f1s = [_f1(p, r) for p, r in zip(precisions, recalls)]
        durations = [r.duration_s for r in op_results]
        total_duration = sum(d for d in durations if d is not None)
        input_chars_list = [r.input_chars for r in op_results]
        rows.append(
            {
                "op": op,
                "case_count": len(op_results),
                "success_count": sum(1 for r in op_results if r.error is None),
                "invalid_path_count": sum(
                    len(r.invalid_generated_paths) for r in op_results
                ),
                "error_count": sum(1 for r in op_results if r.error is not None),
                "avg_precision": _safe_mean(precisions),
                "avg_recall": _safe_mean(recalls),
                "avg_f1": _safe_mean(f1s),
                "total_duration_s": total_duration,
                "avg_duration_s": _safe_mean(durations),
                "avg_input_chars": _safe_mean(input_chars_list),
                "avg_compression_rate": _safe_mean(
                    [r.compression_rate for r in op_results]
                ),
                "avg_generated_leaves": _safe_mean(
                    [float(r.generated_leaf_count) for r in op_results if r.error is None]
                ),
                "avg_total_leaves": _safe_mean(
                    [float(r.total_leaf_count) for r in op_results]
                ),
            }
        )
    return rows


def _paths_match(ref: str, gen: str) -> bool:
    """判断 reference 路径和 generated 路径是否语义匹配。

    支持三种情况：
    - 精确匹配: "business.rating" == "business.rating"
    - ref 是容器前缀: ref="songs" 匹配 gen="songs[].song_name"
    - gen 是容器前缀: gen="business" 匹配 ref="business.rating"
    """
    if ref == gen:
        return True
    # ref 是 gen 的前缀 (ref="songs", gen="songs[].song_name")
    if gen.startswith(ref) and len(gen) > len(ref) and gen[len(ref)] in (".", "["):
        return True
    # gen 是 ref 的前缀 (gen="business", ref="business.rating")
    if ref.startswith(gen) and len(ref) > len(gen) and ref[len(gen)] in (".", "["):
        return True
    return False


def _precision(result: EvaluationResult) -> float | None:
    """生成的路径中，有多少能被 reference 中的某条路径匹配。

    error case（generated_paths 为空）返回 0.0 而非 None，确保被纳入统计。
    """
    if result.error is not None:
        return 0.0
    if not result.generated_paths:
        return None
    matched = sum(
        1 for g in result.generated_paths
        if any(_paths_match(r, g) for r in result.case.reference_paths)
    )
    return matched / len(result.generated_paths)


def _recall(result: EvaluationResult) -> float | None:
    """reference 中的路径，有多少被 LLM 生成的路径覆盖。

    error case 返回 0.0 而非 None。
    """
    if result.error is not None:
        return 0.0
    if not result.case.reference_paths:
        return None
    matched = sum(
        1 for r in result.case.reference_paths
        if any(_paths_match(r, g) for g in result.generated_paths)
    )
    return matched / len(result.case.reference_paths)


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def _safe_mean(values: list[float | None]) -> float:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else 0.0


def _classify_error(error: str | None) -> str | None:
    """将原始错误文本分类为可读的错误类型。"""
    if error is None:
        return None
    if "$defs" in error and "Field required" in error:
        return "输出了JSON Schema定义而非Concept实例"
    if "Concept" in error and "Field required" in error and "$defs" not in error:
        return "多包了一层{Concept:{...}}"
    if "is_required" in error and "Field required" in error:
        return "children中漏掉is_required字段"
    if "Invalid JSON" in error:
        return "JSON截断/格式错误"
    if "Field required" in error:
        return "缺少必填字段"
    return "其他错误"


def _build_prompt_text(
    case: PlanCase,
    *,
    schema_mode: SchemaMode = "full",
    tool_version: ToolVersion = "v1",
) -> str:
    """构造完整 prompt 文本，用于记录和估算输入字符数。"""
    if tool_version == "v2":
        all_attrs = collect_schema_attributes(case.output_model)
        return build_prompt_v2(
            case.schema_query, case.op,
            attributes_to_fields(all_attrs),
            attributes_to_field_types(all_attrs),
        )
    from aicore.tools.experiments.entity_search_tool import _build_prompt

    return _build_prompt(EntitySearchToolInput(
        query=case.schema_query,
        tool_name=case.op,
        output_schema=_get_output_schema(case.output_model, schema_mode),
    ))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _parse_model_name(raw: str) -> str:
    if raw in ModelName.__members__:
        return ModelName[raw].value
    try:
        return ModelName(raw).value
    except ValueError:
        return raw


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate entity_search_tool output schemas.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("entity_search_schema_cases_doubao-seed-1-6-251015_v2.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("entity_search_schema_review_doubao-seed-1-6-251015_v2.xlsx"),
    )
    parser.add_argument("--model", default="SEED_1_6_251015")
    parser.add_argument("--backend", choices=["chat", "responses"], default="chat")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument(
        "--schema-mode",
        choices=["full", "compact"],
        default="full",
        help="Schema format: full (Pydantic JSON Schema) or compact (name→description only). V1 only.",
    )
    parser.add_argument(
        "--tool-version",
        choices=["v1", "v2"],
        default="v1",
        help="Tool version: v1 (nested Concept output) or v2 (flat-path selection).",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    cases = load_case_file(args.input)
    if args.limit is not None:
        cases = cases[: args.limit]
    generator = _make_live_generator(
        model=_parse_model_name(args.model),
        backend=args.backend,
        schema_mode=args.schema_mode,
        tool_version=args.tool_version,
    )
    results = await run_eval(
        cases, generator,
        concurrency=args.concurrency,
        schema_mode=args.schema_mode,
        tool_version=args.tool_version,
    )
    write_excel(results, args.output)
    _print_summary(results, schema_mode=args.schema_mode, tool_version=args.tool_version)
    print(f"\nwrote {len(results)} rows -> {args.output}")


def _print_summary(
    results: list[EvaluationResult],
    *,
    schema_mode: str = "full",
    tool_version: str = "v1",
) -> None:
    summary = _summary_rows(results)
    error_count = sum(1 for r in results if r.error is not None)
    total = len(results)

    # 计算 valid path rate（不依赖 reference，衡量 LLM 输出质量）
    all_gen = sum(len(r.generated_paths) for r in results)
    all_invalid = sum(len(r.invalid_generated_paths) for r in results)
    valid_rate = (all_gen - all_invalid) / all_gen if all_gen else 0.0

    # 汇总耗时
    all_durations = [r.duration_s for r in results if r.duration_s is not None]
    total_duration = sum(all_durations) if all_durations else 0.0
    avg_duration = total_duration / len(all_durations) if all_durations else 0.0
    total_input_chars = sum(r.input_chars for r in results)

    # 错误类型分布
    from collections import Counter
    error_type_counts = Counter(
        _classify_error(r.error) for r in results if r.error is not None
    )

    print(f"\n{'='*105}")
    print(f"  Entity Search Schema Eval  ({total} cases, {error_count} errors, "
          f"{total - error_count} success)  tool={tool_version}  schema_mode={schema_mode}")
    # 压缩率汇总
    success_results = [r for r in results if r.error is None]
    compressions = [r.compression_rate for r in success_results if r.compression_rate is not None]
    avg_compression = sum(compressions) / len(compressions) if compressions else 0.0
    avg_gen_leaves = sum(r.generated_leaf_count for r in success_results) / len(success_results) if success_results else 0

    print(f"  Valid path rate: {valid_rate:.1%} ({all_gen - all_invalid}/{all_gen})")
    print(f"  Avg compression: {avg_compression:.1%} (avg {avg_gen_leaves:.1f} leaves selected)")
    print(f"  Total duration: {total_duration:.1f}s | Avg: {avg_duration:.2f}s/case")
    print(f"  Total input chars: {total_input_chars:,} | Avg: {total_input_chars // max(total, 1):,}/case")
    if error_type_counts:
        print(f"  Error breakdown:")
        for etype, count in error_type_counts.most_common():
            print(f"    {count:>3}x  {etype}")
    print(f"{'='*105}")
    print(
        f"{'op':<15} {'count':>5} {'ok':>4} {'err':>4} {'invalid':>7} "
        f"{'prec':>7} {'recall':>7} {'F1':>7} "
        f"{'compress':>8} {'leaves':>6} "
        f"{'total_s':>8} {'avg_s':>7} {'avg_chars':>10}"
    )
    print(
        f"{'-'*15} {'-'*5} {'-'*4} {'-'*4} {'-'*7} "
        f"{'-'*7} {'-'*7} {'-'*7} "
        f"{'-'*8} {'-'*6} "
        f"{'-'*8} {'-'*7} {'-'*10}"
    )
    for row in summary:
        print(
            f"{row['op']:<15} {row['case_count']:>5} {row['success_count']:>4} "
            f"{row['error_count']:>4} "
            f"{row['invalid_path_count']:>7} {row['avg_precision']:>7.3f} "
            f"{row['avg_recall']:>7.3f} {row['avg_f1']:>7.3f} "
            f"{row['avg_compression_rate']:>7.1%} "
            f"{row['avg_generated_leaves']:>6.1f} "
            f"{row['total_duration_s']:>8.1f} {row['avg_duration_s']:>7.2f} "
            f"{row['avg_input_chars']:>10.0f}"
        )
    print(f"{'='*105}")


if __name__ == "__main__":
    anyio.run(_main, backend="asyncio")
