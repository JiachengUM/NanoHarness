from __future__ import annotations

import argparse
import asyncio
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from projects.sgm_prod.classification import arbitrate_simple_complex_decision
from projects.sgm_prod.classification.tools._asset_dir import use_router_asset_dir

Label = Literal["simple", "complex"]
EXPECTED_EXACT_SOURCE: dict[Label, str] = {
    "simple": "exact_simple",
    "complex": "exact_complex",
}


@dataclass(frozen=True)
class Case:
    path: Path
    line_number: int
    query: str
    expected_label: Label
    asset_source: str


@dataclass(frozen=True)
class Failure:
    case: Case
    actual_label: str
    decision_source: str
    failure_type: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate router exact-case assets.")
    parser.add_argument(
        "--asset-dir",
        type=Path,
        required=True,
        help="Directory containing data/simple.csv and data/complex.csv.",
    )
    return parser.parse_args()


def _read_cases(path: Path, expected_label: Label) -> list[Case]:
    cases: list[Case] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):
            query = (row.get("query") or "").strip()
            label = (row.get("label") or "").strip()
            if label not in {"simple", "complex"}:
                raise ValueError(f"{path}: row {line_number} has invalid label {label!r}")
            if label != expected_label:
                raise ValueError(
                    f"{path}: row {line_number} expected label {expected_label}, got {label!r}"
                )
            if not query:
                raise ValueError(f"{path}: row {line_number} missing query")
            cases.append(
                Case(
                    path=path,
                    line_number=line_number,
                    query=query,
                    expected_label=cast(Label, label),
                    asset_source=(row.get("source") or "").strip(),
                )
            )
    return cases


def _load_cases(asset_dir: Path) -> list[Case]:
    return [
        *_read_cases(_case_csv_path(asset_dir, "simple"), "simple"),
        *_read_cases(_case_csv_path(asset_dir, "complex"), "complex"),
    ]


def _case_csv_path(asset_dir: Path, label: Label) -> Path:
    return asset_dir / "data" / f"{label}.csv"


async def _evaluate(cases: list[Case]) -> tuple[Counter[str], list[Failure]]:
    source_counts: Counter[str] = Counter()
    failures: list[Failure] = []
    for case in cases:
        decision = await arbitrate_simple_complex_decision(
            case.query,
            use_exact_match=True,
        )
        source_counts[decision.source] += 1
        expected_source = EXPECTED_EXACT_SOURCE[case.expected_label]
        if decision.label != case.expected_label or decision.source != expected_source:
            failure_type = (
                "label_mismatch" if decision.label != case.expected_label else "non_exact_source"
            )
            failures.append(
                Failure(
                    case=case,
                    actual_label=decision.label,
                    decision_source=decision.source,
                    failure_type=failure_type,
                )
            )
    return source_counts, failures


def _print_report(
    *,
    total: int,
    source_counts: Counter[str],
    failures: list[Failure],
) -> None:
    correct = total - len(failures)
    accuracy = correct / total if total else 0.0
    false_simple = sum(
        1
        for failure in failures
        if failure.case.expected_label == "complex" and failure.actual_label == "simple"
    )
    false_complex = sum(
        1
        for failure in failures
        if failure.case.expected_label == "simple" and failure.actual_label == "complex"
    )

    print(f"total: {total}")
    print(f"correct: {correct}")
    print(f"accuracy: {accuracy:.6f}")
    print(f"false_simple: {false_simple}")
    print(f"false_complex: {false_complex}")
    print("source_counts:")
    if source_counts:
        for source, count in sorted(source_counts.items()):
            print(f"  {source}: {count}")
    else:
        print("  <none>: 0")

    print("first_20_failures:")
    if not failures:
        print("  <none>")
        return

    for failure in failures[:20]:
        case = failure.case
        print(
            "  "
            f"{case.path.name}:{case.line_number} "
            f"expected={case.expected_label} "
            f"actual={failure.actual_label} "
            f"source={failure.decision_source} "
            f"failure_type={failure.failure_type} "
            f"asset_source={case.asset_source or '<empty>'} "
            f"query={case.query}"
        )


async def _amain(asset_dir: Path) -> int:
    with use_router_asset_dir(asset_dir):
        cases = _load_cases(asset_dir)
        source_counts, failures = await _evaluate(cases)
        _print_report(total=len(cases), source_counts=source_counts, failures=failures)
    return 0 if not failures else 1


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_amain(args.asset_dir)))


if __name__ == "__main__":
    main()
