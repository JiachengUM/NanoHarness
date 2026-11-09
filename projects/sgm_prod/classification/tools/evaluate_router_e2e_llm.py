from __future__ import annotations

import argparse
import asyncio
import csv
import io
import time
import unicodedata
from contextlib import redirect_stdout
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from projects.sgm_prod.classification import arbitrate_simple_complex_decision
from projects.sgm_prod.classification.models import RouterDecision
from projects.sgm_prod.classification.tools._asset_dir import use_router_asset_dir

Label = Literal["simple", "complex"]
DomainFilter = Literal["all", "byd", "benz"]
TableAlign = Literal["left", "right"]
SECTION_WIDTH = 88


@dataclass(frozen=True)
class Case:
    path: Path
    line_number: int
    query: str
    expected_label: Label
    asset_source: str
    domain: str


@dataclass(frozen=True)
class EvalResult:
    case: Case
    actual_label: str
    decision_source: str
    correct: bool
    latency_ms: float
    llm_routed: bool
    decision_path: str
    normalized_query: str
    top_candidate_id: str
    top_missing_slots: str
    top_risk_flags: str
    top_unconsumed_text: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate all router cases end-to-end with exact match disabled "
            "and LLM fallback enabled."
        )
    )
    parser.add_argument(
        "--asset-dir",
        type=Path,
        required=True,
        help="Directory containing data/simple.csv and data/complex.csv.",
    )
    parser.add_argument(
        "--domain",
        choices=("all", "byd", "benz"),
        default="all",
        help="Evaluate all cases or only one domain.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Maximum concurrent router calls. LLM fallback calls are included.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional smoke-test limit. Default 0 means evaluate all cases.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print progress every N completed cases. Use 0 to disable.",
    )
    parser.add_argument(
        "--print-failures",
        type=int,
        default=20,
        help="Number of failures to print in the terminal report.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Optional path for all per-case predictions.",
    )
    parser.add_argument(
        "--failures-csv",
        type=Path,
        help="Optional path for only failed predictions.",
    )
    parser.add_argument(
        "--report-txt",
        type=Path,
        help=(
            "Optional path for a text report containing the terminal metric "
            "sections, excluding the first-N failure examples."
        ),
    )
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.progress_every < 0:
        parser.error("--progress-every must be >= 0")
    if args.print_failures < 0:
        parser.error("--print-failures must be >= 0")
    return args


def _case_csv_path(asset_dir: Path, label: Label) -> Path:
    return asset_dir / "data" / f"{label}.csv"


def _read_cases(
    path: Path,
    expected_label: Label,
    domain_filter: DomainFilter,
) -> list[Case]:
    cases: list[Case] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):
            query = (row.get("query") or "").strip()
            if not query:
                continue

            label = (row.get("label") or "").strip()
            if label and label != expected_label:
                raise ValueError(
                    f"{path}: row {line_number} expected label {expected_label}, got {label!r}"
                )

            domain = (row.get("domain") or "").strip()
            if domain_filter != "all" and domain.lower() != domain_filter:
                continue

            cases.append(
                Case(
                    path=path,
                    line_number=line_number,
                    query=query,
                    expected_label=cast(Label, label or expected_label),
                    asset_source=(row.get("source") or "").strip(),
                    domain=domain,
                )
            )
    return cases


def _load_cases(
    asset_dir: Path,
    domain_filter: DomainFilter = "all",
    limit: int = 0,
) -> list[Case]:
    cases = [
        *_read_cases(_case_csv_path(asset_dir, "simple"), "simple", domain_filter),
        *_read_cases(_case_csv_path(asset_dir, "complex"), "complex", domain_filter),
    ]
    return cases[:limit] if limit else cases


def _format_list(values: list[str]) -> str:
    return "|".join(values)


def _llm_routed(decision: RouterDecision) -> bool:
    return "llm_fallback:start" in decision.trace.decision_path


def _result_from_decision(
    case: Case,
    decision: RouterDecision,
    latency_ms: float,
) -> EvalResult:
    best = decision.trace.matched_candidates[0] if decision.trace.matched_candidates else None
    return EvalResult(
        case=case,
        actual_label=decision.label,
        decision_source=decision.source,
        correct=decision.label == case.expected_label,
        latency_ms=latency_ms,
        llm_routed=_llm_routed(decision),
        decision_path=" -> ".join(decision.trace.decision_path),
        normalized_query=decision.trace.normalized_query,
        top_candidate_id=best.capability_id if best else "",
        top_missing_slots=_format_list(best.missing_slots) if best else "",
        top_risk_flags=_format_list(best.risk_flags) if best else "",
        top_unconsumed_text=best.unconsumed_text if best else "",
    )


async def _evaluate_case(case: Case, semaphore: asyncio.Semaphore) -> EvalResult:
    async with semaphore:
        started_at = time.perf_counter()
        decision = await arbitrate_simple_complex_decision(
            case.query,
            use_exact_match=False,
            use_llm_fallback=True,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000
    return _result_from_decision(case, decision, latency_ms)


def _print_progress(completed: int, total: int, results: list[EvalResult], started_at: float) -> None:
    correct = sum(1 for result in results if result.correct)
    llm_routed = sum(1 for result in results if result.llm_routed)
    elapsed_s = time.perf_counter() - started_at
    print(
        f"[progress] {completed:>5}/{total:<5} | "
        f"accuracy={correct / completed if completed else 0:.6f} | "
        f"llm_routed={llm_routed:<5} | "
        f"elapsed_s={elapsed_s:.1f}"
    )


async def _evaluate(
    cases: list[Case],
    *,
    concurrency: int,
    progress_every: int,
) -> list[EvalResult]:
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [_evaluate_case(case, semaphore) for case in cases]
    results: list[EvalResult] = []
    started_at = time.perf_counter()
    total = len(tasks)

    for completed, future in enumerate(asyncio.as_completed(tasks), start=1):
        results.append(await future)
        if progress_every and (completed % progress_every == 0 or completed == total):
            _print_progress(completed, total, results, started_at)

    return results


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _accuracy(results: list[EvalResult]) -> float:
    if not results:
        return 0.0
    return sum(1 for result in results if result.correct) / len(results)


def _source_counts(results: list[EvalResult]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for result in results:
        counts[result.decision_source] += 1
    return counts


def _print_section(title: str) -> None:
    print()
    print("=" * SECTION_WIDTH)
    print(title)
    print("=" * SECTION_WIDTH)


def _print_subsection(title: str) -> None:
    print()
    print("-" * SECTION_WIDTH)
    print(title)
    print("-" * SECTION_WIDTH)


def _cell_text(value: object) -> str:
    return str(value).replace("\n", " ").strip()


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.category(char).startswith("C"):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def _truncate_display(text: str, max_width: int) -> str:
    if max_width <= 0 or _display_width(text) <= max_width:
        return text
    if max_width <= 3:
        return "." * max_width

    truncated = ""
    width = 0
    for char in text:
        char_width = 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
        if width + char_width > max_width - 3:
            break
        truncated += char
        width += char_width
    return truncated + "..."


def _pad_display(text: str, width: int, align: TableAlign) -> str:
    padding = max(0, width - _display_width(text))
    if align == "right":
        return " " * padding + text
    return text + " " * padding


def _print_table(
    headers: list[str],
    rows: list[list[object]],
    *,
    aligns: list[TableAlign] | None = None,
    max_widths: dict[int, int] | None = None,
) -> None:
    max_widths = max_widths or {}
    aligns = aligns or ["left"] * len(headers)
    normalized_rows = [
        [
            _truncate_display(_cell_text(cell), max_widths.get(idx, 0))
            for idx, cell in enumerate(row)
        ]
        for row in rows
    ]
    normalized_headers = [
        _truncate_display(_cell_text(header), max_widths.get(idx, 0))
        for idx, header in enumerate(headers)
    ]
    widths = [
        max(
            _display_width(normalized_headers[idx]),
            *(_display_width(row[idx]) for row in normalized_rows),
        )
        for idx in range(len(headers))
    ]
    border = "+-" + "-+-".join("-" * width for width in widths) + "-+"

    print(border)
    print(
        "| "
        + " | ".join(
            _pad_display(header, widths[idx], "left")
            for idx, header in enumerate(normalized_headers)
        )
        + " |"
    )
    print(border)
    for row in normalized_rows:
        print(
            "| "
            + " | ".join(
                _pad_display(row[idx], widths[idx], aligns[idx])
                for idx in range(len(headers))
            )
            + " |"
        )
    print(border)


def _print_kv_table(rows: list[tuple[object, object]]) -> None:
    _print_table(["metric", "value"], [[key, value] for key, value in rows])


def _print_counter_table(title: str, counts: Counter[str]) -> None:
    _print_subsection(title)
    if not counts:
        _print_table(["source", "count"], [["<none>", 0]], aligns=["left", "right"])
        return
    _print_table(
        ["source", "count"],
        [[source, count] for source, count in sorted(counts.items())],
        aligns=["left", "right"],
    )


def _artifact_rows(
    *,
    report_txt: Path | None = None,
    output_csv: Path | None = None,
    failures_csv: Path | None = None,
) -> list[list[object]]:
    rows: list[list[object]] = []
    if report_txt:
        rows.append(["report_txt", report_txt])
    if output_csv:
        rows.append(["output_csv", output_csv])
    if failures_csv:
        rows.append(["failures_csv", failures_csv])
    return rows


def _print_artifacts(artifact_rows: list[list[object]], *, max_path_width: int = 96) -> None:
    _print_subsection("Artifacts")
    _print_table(["artifact", "path"], artifact_rows, max_widths={1: max_path_width})


def _latency_row(scope: str, results: list[EvalResult]) -> list[object]:
    latencies = [result.latency_ms for result in results]
    if not latencies:
        return [scope, 0, "-", "-", "-", "-"]
    return [
        scope,
        len(latencies),
        f"{sum(latencies) / len(latencies):.1f}",
        f"{_percentile(latencies, 0.50):.1f}",
        f"{_percentile(latencies, 0.95):.1f}",
        f"{max(latencies):.1f}",
    ]


def _print_report(
    *,
    results: list[EvalResult],
    domain_filter: DomainFilter,
    print_failures: int,
    include_failure_examples: bool = True,
) -> None:
    total = len(results)
    failures = [result for result in results if not result.correct]
    false_simple = sum(
        1
        for result in failures
        if result.case.expected_label == "complex" and result.actual_label == "simple"
    )
    false_complex = sum(
        1
        for result in failures
        if result.case.expected_label == "simple" and result.actual_label == "complex"
    )
    llm_results = [result for result in results if result.llm_routed]
    parser_results = [result for result in results if not result.llm_routed]

    _print_section("E2E Router Evaluation")
    _print_subsection("Run Config")
    _print_kv_table(
        [
            ("mode", "use_exact_match=False, use_llm_fallback=True"),
            ("domain", domain_filter),
        ]
    )

    _print_subsection("Overall Metrics")
    _print_kv_table(
        [
            ("total", total),
            ("correct", total - len(failures)),
            ("accuracy", f"{_accuracy(results):.6f}"),
            ("false_simple", false_simple),
            ("false_complex", false_complex),
            ("llm_routed", len(llm_results)),
            ("llm_route_rate", f"{len(llm_results) / total if total else 0:.6f}"),
            ("llm_accuracy_on_routed", f"{_accuracy(llm_results):.6f}"),
            ("parser_accuracy_before_llm", f"{_accuracy(parser_results):.6f}"),
        ]
    )

    _print_subsection("Latency")
    _print_table(
        ["scope", "count", "avg_ms", "p50_ms", "p95_ms", "max_ms"],
        [
            _latency_row("overall", results),
            _latency_row("llm_routed", llm_results),
            _latency_row("parser_only", parser_results),
        ],
        aligns=["left", "right", "right", "right", "right", "right"],
    )

    _print_counter_table("Source Counts", _source_counts(results))
    _print_counter_table("LLM Source Counts", _source_counts(llm_results))

    by_domain: dict[str, list[EvalResult]] = defaultdict(list)
    by_asset_source: dict[str, list[EvalResult]] = defaultdict(list)
    for result in results:
        domain = result.case.domain or "<empty>"
        by_domain[domain].append(result)
        source_key = f"{result.case.expected_label}:{domain}:{result.case.asset_source or '<empty>'}"
        by_asset_source[source_key].append(result)

    _print_subsection("By Domain")
    domain_rows: list[list[object]] = []
    for domain, domain_results in sorted(by_domain.items()):
        domain_llm = [result for result in domain_results if result.llm_routed]
        domain_rows.append(
            [
                domain,
                len(domain_results),
                f"{_accuracy(domain_results):.6f}",
                len(domain_llm),
                f"{len(domain_llm) / len(domain_results) if domain_results else 0:.6f}",
                f"{_accuracy(domain_llm):.6f}",
            ]
        )
    _print_table(
        ["domain", "total", "accuracy", "llm_routed", "llm_route_rate", "llm_accuracy"],
        domain_rows or [["<none>", 0, "-", 0, "-", "-"]],
        aligns=["left", "right", "right", "right", "right", "right"],
    )

    _print_subsection("By Asset Source")
    asset_source_rows: list[list[object]] = []
    for source_key, source_results in sorted(by_asset_source.items()):
        source_llm = [result for result in source_results if result.llm_routed]
        counts = _source_counts(source_results)
        asset_source_rows.append(
            [
                source_key,
                len(source_results),
                f"{_accuracy(source_results):.6f}",
                len(source_llm),
                f"{_accuracy(source_llm):.6f}",
                counts["parser_simple"],
                counts["parser_veto"],
                counts["llm_simple"],
                counts["llm_complex"],
                counts["default_complex"],
            ]
        )
    _print_table(
        [
            "asset_source",
            "total",
            "accuracy",
            "llm_routed",
            "llm_accuracy",
            "parser_simple",
            "parser_veto",
            "llm_simple",
            "llm_complex",
            "default_complex",
        ],
        asset_source_rows or [["<none>", 0, "-", 0, "-", 0, 0, 0, 0, 0]],
        aligns=[
            "left",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
        ],
        max_widths={0: 42},
    )

    if not include_failure_examples:
        return

    _print_subsection(f"First {print_failures} Failures")
    failure_rows: list[list[object]] = []
    for idx, result in enumerate(failures[:print_failures], start=1):
        case = result.case
        failure_rows.append(
            [
                idx,
                f"{case.path.name}:{case.line_number}",
                case.query,
                case.expected_label,
                result.actual_label,
                result.decision_source,
                case.asset_source or "<empty>",
                case.domain or "<empty>",
                result.llm_routed,
                result.decision_path,
            ]
        )
    _print_table(
        [
            "#",
            "location",
            "query",
            "expected",
            "actual",
            "source",
            "asset_source",
            "domain",
            "llm",
            "path",
        ],
        failure_rows or [["<none>", "-", "-", "-", "-", "-", "-", "-", "-", "-"]],
        aligns=[
            "right",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
        ],
        max_widths={2: 42, 6: 24, 9: 58},
    )


def _render_report_text(
    *,
    results: list[EvalResult],
    domain_filter: DomainFilter,
    include_failure_examples: bool,
    artifact_rows: list[list[object]] | None = None,
    print_failures: int = 0,
) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _print_report(
            results=results,
            domain_filter=domain_filter,
            print_failures=print_failures,
            include_failure_examples=include_failure_examples,
        )
        if artifact_rows:
            _print_artifacts(artifact_rows, max_path_width=0)
    return buffer.getvalue()


def _write_report_txt(
    path: Path,
    *,
    results: list[EvalResult],
    domain_filter: DomainFilter,
    artifact_rows: list[list[object]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report_text = _render_report_text(
        results=results,
        domain_filter=domain_filter,
        include_failure_examples=False,
        artifact_rows=artifact_rows,
    )
    path.write_text(report_text, encoding="utf-8")


def _csv_row(result: EvalResult) -> dict[str, str]:
    case = result.case
    return {
        "case_file": case.path.name,
        "line_number": str(case.line_number),
        "query": case.query,
        "expected": case.expected_label,
        "actual": result.actual_label,
        "correct": str(result.correct),
        "decision_source": result.decision_source,
        "asset_source": case.asset_source,
        "domain": case.domain,
        "llm_routed": str(result.llm_routed),
        "latency_ms": f"{result.latency_ms:.1f}",
        "decision_path": result.decision_path,
        "normalized_query": result.normalized_query,
        "top_candidate_id": result.top_candidate_id,
        "top_missing_slots": result.top_missing_slots,
        "top_risk_flags": result.top_risk_flags,
        "top_unconsumed_text": result.top_unconsumed_text,
    }


def _write_results_csv(path: Path, results: list[EvalResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(_csv_row(results[0]).keys()) if results else [
        "case_file",
        "line_number",
        "query",
        "expected",
        "actual",
        "correct",
        "decision_source",
        "asset_source",
        "domain",
        "llm_routed",
        "latency_ms",
        "decision_path",
        "normalized_query",
        "top_candidate_id",
        "top_missing_slots",
        "top_risk_flags",
        "top_unconsumed_text",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(_csv_row(result))


async def _amain(args: argparse.Namespace) -> int:
    with use_router_asset_dir(args.asset_dir):
        cases = _load_cases(args.asset_dir, args.domain, args.limit)
        results = await _evaluate(
            cases,
            concurrency=args.concurrency,
            progress_every=args.progress_every,
        )

    results.sort(key=lambda result: (str(result.case.path), result.case.line_number))
    _print_report(
        results=results,
        domain_filter=args.domain,
        print_failures=args.print_failures,
    )

    artifact_rows = _artifact_rows(
        report_txt=args.report_txt,
        output_csv=args.output_csv,
        failures_csv=args.failures_csv,
    )
    if args.report_txt:
        _write_report_txt(
            args.report_txt,
            results=results,
            domain_filter=args.domain,
            artifact_rows=artifact_rows,
        )
    if args.output_csv:
        _write_results_csv(args.output_csv, results)
    if args.failures_csv:
        failures = [result for result in results if not result.correct]
        _write_results_csv(args.failures_csv, failures)
    if artifact_rows:
        _print_artifacts(artifact_rows)

    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
