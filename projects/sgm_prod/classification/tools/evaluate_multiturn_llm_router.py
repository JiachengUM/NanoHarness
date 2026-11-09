from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from projects.sgm_prod.classification.llm import llm_multiturn_route
from projects.sgm_prod.classification.models import IntentType

DEFAULT_WORKBOOK = Path("/Users/WayneYu/Downloads/SGM多轮验证用例-0604.xlsx")


@dataclass(frozen=True)
class MultiturnCase:
    sheet_name: str
    row_number: int
    turn_index: int
    domain: str
    query: str
    expected: IntentType
    history: list[dict[str, str]]


@dataclass(frozen=True)
class MultiturnResult:
    case: MultiturnCase
    actual: IntentType
    correct: bool
    latency_ms: float


@dataclass(frozen=True)
class TurnSummary:
    total: int
    correct: int
    accuracy: float


@dataclass(frozen=True)
class LatencySummary:
    avg_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def _query_column(turn_index: int) -> str:
    return f"Query{turn_index}"


def _label_column(turn_index: int) -> str:
    return "预期落域" if turn_index == 1 else f"预期落域.{turn_index - 1}"


def _normalize_label(value: str, *, sheet_name: str, row_number: int, turn_index: int) -> IntentType:
    label = value.strip().lower()
    if label in {"简单", "simple"}:
        return "simple"
    if label in {"复杂", "complex"}:
        return "complex"
    raise ValueError(
        f"{sheet_name}: row {row_number} turn {turn_index} has invalid label {value!r}"
    )


def _domain_from_sheet(sheet_name: str) -> str:
    if "导航" in sheet_name:
        return "navigation"
    if "音乐" in sheet_name or "多媒体" in sheet_name:
        return "music"
    return "unknown"


def _row_turns(
    row: pd.Series,
    *,
    sheet_name: str,
    row_number: int,
    max_turns: int,
) -> list[tuple[int, str, IntentType]]:
    turns: list[tuple[int, str, IntentType]] = []
    for turn_index in range(1, max_turns + 1):
        query = str(row.get(_query_column(turn_index), "") or "").strip()
        raw_label = str(row.get(_label_column(turn_index), "") or "").strip()
        if not query and not raw_label:
            continue
        if not query or not raw_label:
            raise ValueError(
                f"{sheet_name}: row {row_number} turn {turn_index} has incomplete query/label"
            )
        turns.append(
            (
                turn_index,
                query,
                _normalize_label(
                    raw_label,
                    sheet_name=sheet_name,
                    row_number=row_number,
                    turn_index=turn_index,
                ),
            )
        )
    return turns


def load_multiturn_cases(
    workbook: Path,
    *,
    sheets: list[str] | None = None,
    max_turns: int = 5,
    limit: int = 0,
) -> list[MultiturnCase]:
    if max_turns < 2:
        raise ValueError("max_turns must be >= 2")

    xls = pd.ExcelFile(workbook)
    sheet_names = sheets if sheets is not None else xls.sheet_names
    cases: list[MultiturnCase] = []
    for sheet_name in sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=str).fillna("")
        domain = _domain_from_sheet(sheet_name)
        for index, row in df.iterrows():
            row_number = index + 2
            turns = _row_turns(
                row,
                sheet_name=sheet_name,
                row_number=row_number,
                max_turns=max_turns,
            )
            if len(turns) < 2:
                continue
            for offset, (turn_index, query, expected) in enumerate(turns[1:], start=1):
                history = [
                    {"query": prev_query, "route": prev_label}
                    for _, prev_query, prev_label in turns[:offset]
                ]
                cases.append(
                    MultiturnCase(
                        sheet_name=sheet_name,
                        row_number=row_number,
                        turn_index=turn_index,
                        domain=domain,
                        query=query,
                        expected=expected,
                        history=history,
                    )
                )
                if limit and len(cases) >= limit:
                    return cases
    return cases


def summarize_by_turn(
    rows: list[tuple[int, IntentType, IntentType]],
) -> dict[int, TurnSummary]:
    grouped: dict[int, list[tuple[IntentType, IntentType]]] = {}
    for turn_index, expected, actual in rows:
        grouped.setdefault(turn_index, []).append((expected, actual))

    return {
        turn_index: TurnSummary(
            total=len(items),
            correct=sum(1 for expected, actual in items if expected == actual),
            accuracy=(
                sum(1 for expected, actual in items if expected == actual) / len(items)
                if items
                else 0.0
            ),
        )
        for turn_index, items in sorted(grouped.items())
    }


def _write_cases_csv(path: Path, cases: list[MultiturnCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sheet_name",
                "row_number",
                "turn_index",
                "domain",
                "query",
                "expected",
                "history_json",
            ],
        )
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "sheet_name": case.sheet_name,
                    "row_number": case.row_number,
                    "turn_index": case.turn_index,
                    "domain": case.domain,
                    "query": case.query,
                    "expected": case.expected,
                    "history_json": json.dumps(case.history, ensure_ascii=False),
                }
            )


def _write_results_csv(path: Path, results: list[MultiturnResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sheet_name",
                "row_number",
                "turn_index",
                "domain",
                "query",
                "expected",
                "actual",
                "correct",
                "latency_ms",
                "history_json",
            ],
        )
        writer.writeheader()
        for result in results:
            case = result.case
            writer.writerow(
                {
                    "sheet_name": case.sheet_name,
                    "row_number": case.row_number,
                    "turn_index": case.turn_index,
                    "domain": case.domain,
                    "query": case.query,
                    "expected": case.expected,
                    "actual": result.actual,
                    "correct": result.correct,
                    "latency_ms": f"{result.latency_ms:.3f}",
                    "history_json": json.dumps(case.history, ensure_ascii=False),
                }
            )


async def evaluate_cases(
    cases: list[MultiturnCase],
    *,
    concurrency: int,
    progress_every: int = 50,
) -> list[MultiturnResult]:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[MultiturnResult] = []
    started_at = time.perf_counter()

    async def evaluate_one(case: MultiturnCase) -> MultiturnResult:
        async with semaphore:
            started = time.perf_counter()
            actual = await llm_multiturn_route(case.query, history=case.history)
            latency_ms = (time.perf_counter() - started) * 1000
        return MultiturnResult(
            case=case,
            actual=actual,
            correct=actual == case.expected,
            latency_ms=latency_ms,
        )

    tasks = [evaluate_one(case) for case in cases]
    for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
        result = await task
        results.append(result)
        if progress_every and (completed % progress_every == 0 or completed == len(tasks)):
            correct = sum(1 for item in results if item.correct)
            elapsed_s = time.perf_counter() - started_at
            print(
                f"[progress] {completed}/{len(tasks)} "
                f"accuracy={correct / completed if completed else 0:.6f} "
                f"elapsed_s={elapsed_s:.1f}"
            )
    return results


def _print_case_summary(cases: list[MultiturnCase]) -> None:
    by_sheet = Counter(case.sheet_name for case in cases)
    by_turn = Counter(case.turn_index for case in cases)
    by_label = Counter(case.expected for case in cases)
    print(f"cases={len(cases)}")
    print(f"history_source=golden")
    print(f"by_sheet={dict(by_sheet)}")
    print(f"by_turn={dict(sorted(by_turn.items()))}")
    print(f"by_label={dict(by_label)}")


def _print_result_summary(
    results: list[MultiturnResult],
    *,
    wall_time_ms: float | None = None,
) -> None:
    print(format_result_summary(results, wall_time_ms=wall_time_ms))


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _sheet_short_name(sheet_name: str) -> str:
    if "导航" in sheet_name:
        return "导航"
    if "音乐" in sheet_name or "多媒体" in sheet_name:
        return "音乐"
    return sheet_name


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def summarize_latency(results: list[MultiturnResult]) -> LatencySummary:
    latencies = [result.latency_ms for result in results]
    return LatencySummary(
        avg_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        p50_ms=_percentile(latencies, 0.50),
        p90_ms=_percentile(latencies, 0.90),
        p95_ms=_percentile(latencies, 0.95),
        p99_ms=_percentile(latencies, 0.99),
        max_ms=max(latencies) if latencies else 0.0,
    )


def format_result_summary(
    results: list[MultiturnResult],
    *,
    wall_time_ms: float | None = None,
) -> str:
    total = len(results)
    correct = sum(1 for result in results if result.correct)
    false_simple = sum(
        1 for result in results if result.case.expected == "complex" and result.actual == "simple"
    )
    false_complex = sum(
        1 for result in results if result.case.expected == "simple" and result.actual == "complex"
    )
    accuracy = correct / total if total else 0.0

    lines = [
        "=== Multiturn LLM Router Evaluation ===",
        "",
        "Overall",
        f"  total          : {total}",
        f"  correct        : {correct}",
        f"  accuracy       : {_pct(accuracy)} ({accuracy:.6f})",
        f"  False simple   : {false_simple}  # expected complex, predicted simple",
        f"  False complex  : {false_complex}  # expected simple, predicted complex",
        "",
        "By Turn",
        "  turn  total  correct  accuracy",
    ]
    rows = [(r.case.turn_index, r.case.expected, r.actual) for r in results]
    for turn_index, summary in summarize_by_turn(rows).items():
        lines.append(
            f"  Q{turn_index:<3} {summary.total:>5} {summary.correct:>8}  "
            f"{_pct(summary.accuracy):>8} ({summary.accuracy:.6f})"
        )

    lines.extend(["", "By Sheet", "  sheet  total  correct  accuracy  false_simple  false_complex"])
    sheet_names = sorted({result.case.sheet_name for result in results})
    for sheet_name in sheet_names:
        subset = [result for result in results if result.case.sheet_name == sheet_name]
        sheet_total = len(subset)
        sheet_correct = sum(1 for result in subset if result.correct)
        sheet_accuracy = sheet_correct / sheet_total if sheet_total else 0.0
        sheet_false_simple = sum(
            1
            for result in subset
            if result.case.expected == "complex" and result.actual == "simple"
        )
        sheet_false_complex = sum(
            1
            for result in subset
            if result.case.expected == "simple" and result.actual == "complex"
        )
        lines.append(
            f"  {_sheet_short_name(sheet_name):<4} {sheet_total:>5} {sheet_correct:>8}  "
            f"{_pct(sheet_accuracy):>8} ({sheet_accuracy:.6f})"
            f" {sheet_false_simple:>13} {sheet_false_complex:>14}"
        )

    latency = summarize_latency(results)
    lines.extend(
        [
            "",
            "Latency",
            f"  avg_ms   : {latency.avg_ms:.3f}",
            f"  p50_ms   : {latency.p50_ms:.3f}",
            f"  p90_ms   : {latency.p90_ms:.3f}",
            f"  p95_ms   : {latency.p95_ms:.3f}",
            f"  p99_ms   : {latency.p99_ms:.3f}",
            f"  max_ms   : {latency.max_ms:.3f}",
        ]
    )
    if wall_time_ms is not None:
        wall_time_s = wall_time_ms / 1000
        throughput = total / wall_time_s if wall_time_s > 0 else 0.0
        lines.extend(
            [
                "",
                "Run",
                f"  wall_time_s       : {wall_time_s:.3f}",
                f"  throughput_qps    : {throughput:.3f}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Run",
                "  wall_time_s       : n/a",
                "  throughput_qps    : n/a",
            ]
        )

    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the minimal multi-turn LLM router on the SGM navigation/music "
            "workbook. Previous-turn history labels always come from golden labels."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help=f"Input xlsx workbook. Default: {DEFAULT_WORKBOOK}",
    )
    parser.add_argument(
        "--sheet",
        action="append",
        help="Optional sheet name. Repeat to evaluate multiple sheets. Defaults to all sheets.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional case limit.")
    parser.add_argument("--max-turns", type=int, default=5, help="Maximum QueryN columns.")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent LLM calls.")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Print progress every N completed LLM calls. Use 0 to disable.",
    )
    parser.add_argument(
        "--export-cases-csv",
        type=Path,
        help="Write converted cases with golden history and labels.",
    )
    parser.add_argument("--output-csv", type=Path, help="Write per-case prediction results.")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Only convert/export cases; do not call the LLM.",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.max_turns < 2:
        parser.error("--max-turns must be >= 2")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.progress_every < 0:
        parser.error("--progress-every must be >= 0")
    return args


async def _main_async() -> None:
    args = _parse_args()
    cases = load_multiturn_cases(
        args.workbook,
        sheets=args.sheet,
        max_turns=args.max_turns,
        limit=args.limit,
    )
    _print_case_summary(cases)
    if args.export_cases_csv:
        _write_cases_csv(args.export_cases_csv, cases)
        print(f"export_cases_csv={args.export_cases_csv}")
    if args.skip_llm:
        return

    evaluation_started = time.perf_counter()
    results = await evaluate_cases(
        cases,
        concurrency=args.concurrency,
        progress_every=args.progress_every,
    )
    wall_time_ms = (time.perf_counter() - evaluation_started) * 1000
    _print_result_summary(results, wall_time_ms=wall_time_ms)
    if args.output_csv:
        _write_results_csv(args.output_csv, results)
        print(f"output_csv={args.output_csv}")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
