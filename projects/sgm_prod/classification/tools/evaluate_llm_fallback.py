from __future__ import annotations

import argparse
import asyncio
import csv
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from projects.sgm_prod.classification.llm import llm_fallback
from projects.sgm_prod.classification.models import IntentType

Classifier = Callable[[str], Awaitable[IntentType]]


@dataclass(frozen=True)
class LLMFallbackCase:
    query: str
    expected: IntentType
    source: str = "builtin"
    domain: str = ""
    note: str = ""


@dataclass(frozen=True)
class LLMFallbackResult:
    case: LLMFallbackCase
    actual: IntentType
    correct: bool
    latency_ms: float


@dataclass(frozen=True)
class LLMFallbackSummary:
    total: int
    correct: int
    false_simple: int
    false_complex: int
    accuracy: float


def default_cases() -> list[LLMFallbackCase]:
    """Small smoke set for the conservative LLM fallback boundary."""
    return [
        LLMFallbackCase("开始导航", "simple", note="navigation_hard_control"),
        LLMFallbackCase("播放周杰伦的歌", "simple", note="single_media_search"),
        LLMFallbackCase("把空调调到二十二度", "simple", note="single_vehicle_control"),
        LLMFallbackCase("当前这首歌是谁唱的", "simple", note="single_media_query"),
        LLMFallbackCase("深圳本周五傍晚的天气，适合去海边吗？", "complex", note="weather_advice"),
        LLMFallbackCase("冻屁股帮我调下", "complex", note="vague_vehicle_comfort"),
        LLMFallbackCase("宝宝睡了，安静一点", "complex", note="scenario_without_explicit_action"),
        LLMFallbackCase("我不要去北京南站了，我要去首都机场", "complex", note="navigation_change_target"),
        LLMFallbackCase("置地C座能不能进去", "complex", note="poi_access_check"),
        LLMFallbackCase("你就给我唱吧，唱《爱心便利贴》", "complex", note="assistant_singing"),
    ]


def _normalize_label(value: str, *, row_number: int, path: Path) -> IntentType:
    normalized = value.strip().lower()
    if normalized in {"simple", "true", "1"}:
        return "simple"
    if normalized in {"complex", "false", "0"}:
        return "complex"
    raise ValueError(f"{path}: row {row_number} has invalid expected label {value!r}")


def _is_true(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "y"}


def load_cases(
    path: Path,
    *,
    limit: int = 0,
    only_llm_routed: bool = False,
    domain: str = "all",
) -> list[LLMFallbackCase]:
    cases: list[LLMFallbackCase] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            row_domain = (row.get("domain") or "").strip()
            if domain != "all" and row_domain.lower() != domain:
                continue
            if only_llm_routed and not _is_true(row.get("llm_routed") or ""):
                continue

            query = (row.get("query") or "").strip()
            if not query:
                continue

            label = (
                row.get("expected")
                or row.get("expected_label")
                or row.get("label")
                or ""
            )
            expected = _normalize_label(label, row_number=row_number, path=path)
            cases.append(
                LLMFallbackCase(
                    query=query,
                    expected=expected,
                    source=(row.get("source") or row.get("asset_source") or "").strip(),
                    domain=row_domain,
                    note=(row.get("note") or row.get("decision_path") or "").strip(),
                )
            )
            if limit and len(cases) >= limit:
                break
    return cases


async def evaluate_cases(
    cases: list[LLMFallbackCase],
    *,
    classifier: Classifier = llm_fallback,
    concurrency: int = 4,
) -> list[LLMFallbackResult]:
    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_one(case: LLMFallbackCase) -> LLMFallbackResult:
        async with semaphore:
            started_at = time.perf_counter()
            actual = await classifier(case.query)
            latency_ms = (time.perf_counter() - started_at) * 1000
        return LLMFallbackResult(
            case=case,
            actual=cast(IntentType, actual),
            correct=actual == case.expected,
            latency_ms=latency_ms,
        )

    return [await task for task in asyncio.as_completed([evaluate_one(case) for case in cases])]


def summarize_results(results: list[LLMFallbackResult]) -> LLMFallbackSummary:
    total = len(results)
    correct = sum(1 for result in results if result.correct)
    false_simple = sum(
        1
        for result in results
        if result.case.expected == "complex" and result.actual == "simple"
    )
    false_complex = sum(
        1
        for result in results
        if result.case.expected == "simple" and result.actual == "complex"
    )
    return LLMFallbackSummary(
        total=total,
        correct=correct,
        false_simple=false_simple,
        false_complex=false_complex,
        accuracy=correct / total if total else 0.0,
    )


def write_results(path: Path, results: list[LLMFallbackResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "query",
                "expected",
                "actual",
                "correct",
                "source",
                "domain",
                "latency_ms",
                "note",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "query": result.case.query,
                    "expected": result.case.expected,
                    "actual": result.actual,
                    "correct": result.correct,
                    "source": result.case.source,
                    "domain": result.case.domain,
                    "latency_ms": f"{result.latency_ms:.3f}",
                    "note": result.case.note,
                }
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate only the LLM fallback classifier on labeled cases."
    )
    parser.add_argument(
        "--cases-csv",
        type=Path,
        help="CSV with query and expected/expected_label/label columns. Defaults to built-in smoke cases.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional case limit.")
    parser.add_argument(
        "--domain",
        choices=("all", "byd", "benz"),
        default="all",
        help="Optional domain filter when the CSV has a domain column.",
    )
    parser.add_argument(
        "--only-llm-routed",
        action="store_true",
        help="When reading an e2e result CSV, evaluate only rows with llm_routed=True.",
    )
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent LLM calls.")
    parser.add_argument("--output-csv", type=Path, help="Optional per-case result CSV.")
    parser.add_argument(
        "--print-failures",
        type=int,
        default=20,
        help="Number of failed cases to print.",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.print_failures < 0:
        parser.error("--print-failures must be >= 0")
    return args


async def _main_async() -> None:
    args = _parse_args()
    cases = (
        load_cases(
            args.cases_csv,
            limit=args.limit,
            only_llm_routed=args.only_llm_routed,
            domain=args.domain,
        )
        if args.cases_csv
        else default_cases()
    )
    if args.limit and not args.cases_csv:
        cases = cases[: args.limit]

    results = await evaluate_cases(cases, concurrency=args.concurrency)
    summary = summarize_results(results)

    print(f"total={summary.total}")
    print(f"correct={summary.correct}")
    print(f"accuracy={summary.accuracy:.6f}")
    print(f"false_simple={summary.false_simple}")
    print(f"false_complex={summary.false_complex}")

    failures = [result for result in results if not result.correct]
    for result in failures[: args.print_failures]:
        print(
            "[failure] "
            f"expected={result.case.expected} actual={result.actual} "
            f"source={result.case.source} domain={result.case.domain} "
            f"query={result.case.query}"
        )

    if args.output_csv:
        write_results(args.output_csv, results)
        print(f"output_csv={args.output_csv}")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
