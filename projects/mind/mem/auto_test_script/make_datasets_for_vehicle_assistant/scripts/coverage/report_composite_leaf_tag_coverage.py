#!/usr/bin/env python3
"""Report per-leaf tag coverage: composite-* cases in vehicle_assistant_leaf_cases.json vs the tag tree.

Usage (cwd=datasets/):
  python report_composite_leaf_tag_coverage.py
  python report_composite_leaf_tag_coverage.py --min 8
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def collect_leaves(node: dict, out: list[str]) -> None:
    name = node.get("name")
    ch = node.get("children") or []
    if not ch:
        if name:
            out.append(name)
        return
    for c in ch:
        collect_leaves(c, out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--min",
        type=int,
        default=8,
        metavar="N",
        help="Flag leaves with fewer than N case hits (default: 8)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print deficit summary as JSON to stdout",
    )
    args = ap.parse_args()
    min_hits = args.min

    root = Path(__file__).resolve().parent
    tree = json.loads((root / "vehicle_assistant_case_tag_tree.json").read_text(encoding="utf-8"))
    leaves: list[str] = []
    collect_leaves(tree["root"], leaves)
    leaf_set = set(leaves)

    all_cases = json.loads((root / "vehicle_assistant_leaf_cases.json").read_text(encoding="utf-8"))
    data = [c for c in all_cases if str(c.get("id", "")).startswith("composite-")]
    cnt: Counter[str] = Counter()
    for case in data:
        for t in case.get("tags") or []:
            cnt[t] += 1

    bad = [t for t in cnt if t not in leaf_set]
    missing = sorted(leaf_set - set(cnt))
    low = sorted((t, cnt[t]) for t in leaf_set if cnt.get(t, 0) < min_hits)
    deficit = sum(max(0, min_hits - cnt.get(t, 0)) for t in leaf_set)

    if args.json:
        out = {
            "composite_case_count": len(data),
            "leaf_file_total_cases": len(all_cases),
            "leaf_count_in_tree": len(leaf_set),
            "leaves_never_used": len(missing),
            "leaves_below_min": len(low),
            "deficit_to_min": deficit,
            "min_hits": min_hits,
            "non_leaf_tags_in_composite": bad,
            "leaves_with_zero": missing,
            "below_min": [{"tag": t, "count": n} for t, n in low],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print(f"Tree leaves: {len(leaf_set)}")
    print(f"Composite-* cases (subset of vehicle_assistant_leaf_cases.json): {len(data)}")
    print(f"Tags in composite-* cases (distinct): {len(cnt)}")
    print(f"Non-leaf tags in composite-* cases: {len(bad)}")
    if bad:
        print("  ", bad)
    print(f"Leaves with 0 cases: {len(missing)}")
    for t in missing:
        print(f"  - {t}")
    print(f"Leaves with count < {min_hits}: {len(low)}")
    print(
        f"Total 'slots' to add if each case contributed only one tag "
        f"(rough lower bound to reach {min_hits} per leaf): {deficit}"
    )
    print()
    for t, n in sorted(low, key=lambda x: (x[1], x[0])):
        print(f"{n:3d}  {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
