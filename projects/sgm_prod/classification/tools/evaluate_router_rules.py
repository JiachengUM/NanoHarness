from __future__ import annotations

import argparse
import asyncio
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from projects.sgm_prod.classification import arbitrate_simple_complex_decision
from projects.sgm_prod.classification.tools._asset_dir import use_router_asset_dir

Label = Literal["simple", "complex"]
DomainFilter = Literal["all", "byd", "benz"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate parser/risk rules without exact cases or LLM.")
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
    return parser.parse_args()


def _read_cases(
    path: Path,
    expected_label: Label,
    domain_filter: DomainFilter,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            query = (row.get("query") or "").strip()
            domain = (row.get("domain") or "").strip()
            if domain_filter != "all" and domain.lower() != domain_filter:
                continue
            if query:
                rows.append(
                    {
                        "query": query,
                        "expected": expected_label,
                        "source": (row.get("source") or "").strip(),
                        "domain": domain,
                    }
                )
    return rows


def _load_cases(asset_dir: Path, domain_filter: DomainFilter = "all") -> list[dict[str, str]]:
    return [
        *_read_cases(_case_csv_path(asset_dir, "simple"), "simple", domain_filter),
        *_read_cases(_case_csv_path(asset_dir, "complex"), "complex", domain_filter),
    ]


def _case_csv_path(asset_dir: Path, label: Label) -> Path:
    return asset_dir / "data" / f"{label}.csv"


async def evaluate(asset_dir: Path, domain_filter: DomainFilter = "all") -> int:
    with use_router_asset_dir(asset_dir):
        cases = _load_cases(asset_dir, domain_filter)
        source_counts: Counter[str] = Counter()
        by_label: dict[str, Counter[str]] = defaultdict(Counter)
        by_asset_source: dict[str, Counter[str]] = defaultdict(Counter)
        by_domain: dict[str, Counter[str]] = defaultdict(Counter)
        failures: list[dict[str, str]] = []

        for case in cases:
            decision = await arbitrate_simple_complex_decision(
                case["query"],
                use_exact_match=False,
                use_llm_fallback=False,
            )
            source_counts[decision.source] += 1
            by_label[case["expected"]][decision.source] += 1
            domain = case["domain"] or "<empty>"
            by_domain[domain]["total"] += 1
            by_domain[domain][decision.source] += 1
            if decision.label == case["expected"]:
                by_domain[domain]["correct"] += 1
            source_key = f"{case['expected']}:{domain}:{case['source']}"
            by_asset_source[source_key]["total"] += 1
            by_asset_source[source_key][decision.source] += 1

            if decision.source in {"parser_simple", "parser_veto"}:
                by_asset_source[source_key]["rule_hit"] += 1
                if decision.label == case["expected"]:
                    by_asset_source[source_key]["rule_correct"] += 1

            if decision.label != case["expected"]:
                failures.append(
                    {
                        "query": case["query"],
                        "expected": case["expected"],
                        "actual": decision.label,
                        "source": decision.source,
                        "path": " | ".join(decision.trace.decision_path),
                    }
                )

    total = len(cases)
    rule_hits = source_counts["parser_simple"] + source_counts["parser_veto"]
    rule_correct = by_label["simple"]["parser_simple"] + by_label["complex"]["parser_veto"]
    correct = total - len(failures)
    simple_total = sum(by_label["simple"].values())
    complex_total = sum(by_label["complex"].values())

    print(f"total: {total}")
    print(f"domain: {domain_filter}")
    print(f"rule_hits: {rule_hits}")
    print(f"rule_coverage: {rule_hits / total:.6f}" if total else "rule_coverage: 0.000000")
    print(f"rule_correct_hits: {rule_correct}")
    print(
        f"rule_precision_on_hit: {rule_correct / rule_hits:.6f}"
        if rule_hits
        else "rule_precision_on_hit: 0.000000"
    )
    print(
        f"simple_correct_rule_coverage: {by_label['simple']['parser_simple'] / simple_total:.6f}"
        if simple_total
        else "simple_correct_rule_coverage: 0.000000"
    )
    print(
        f"complex_correct_rule_coverage: {by_label['complex']['parser_veto'] / complex_total:.6f}"
        if complex_total
        else "complex_correct_rule_coverage: 0.000000"
    )
    print(f"accuracy_if_unmatched_default_complex: {correct / total:.6f}" if total else "accuracy_if_unmatched_default_complex: 0.000000")

    print("source_counts:")
    for source, count in sorted(source_counts.items()):
        print(f"  {source}: {count}")

    print("by_domain:")
    for domain, counts in sorted(by_domain.items()):
        domain_total = counts["total"]
        print(
            f"  {domain}: "
            f"total={domain_total} "
            f"correct={counts['correct']} "
            f"accuracy={counts['correct'] / domain_total if domain_total else 0:.6f} "
            f"parser_simple={counts['parser_simple']} "
            f"parser_veto={counts['parser_veto']} "
            f"default_complex={counts['default_complex']}"
        )

    print("by_asset_source:")
    for source_key, counts in sorted(by_asset_source.items()):
        source_total = counts["total"]
        rule_hit = counts["rule_hit"]
        rule_correct_for_source = counts["rule_correct"]
        print(
            f"  {source_key}: "
            f"total={source_total} "
            f"rule_hit={rule_hit} "
            f"coverage={rule_hit / source_total:.6f} "
            f"rule_correct={rule_correct_for_source} "
            f"precision={rule_correct_for_source / rule_hit if rule_hit else 0:.6f} "
            f"parser_simple={counts['parser_simple']} "
            f"parser_veto={counts['parser_veto']} "
            f"default_complex={counts['default_complex']}"
        )

    print("first_20_failures:")
    if not failures:
        print("  <none>")
    for failure in failures[:20]:
        print(
            "  "
            f"[{failure['expected']}->{failure['actual']}] "
            f"source={failure['source']} "
            f"path={failure['path']} "
            f"query={failure['query']}"
        )

    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(evaluate(args.asset_dir, args.domain)))


if __name__ == "__main__":
    main()
