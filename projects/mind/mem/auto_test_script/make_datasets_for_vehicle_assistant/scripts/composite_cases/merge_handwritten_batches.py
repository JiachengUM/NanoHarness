#!/usr/bin/env python3
"""Merge datasets/handwritten_batches/*.json into vehicle_assistant_leaf_cases.json.

Synthetic cases use ids composite-<n>. The next id is inferred from the **maximum**
composite-* serial already present in the leaf file (not necessarily the last array element).

Each batch file must be a JSON array of cases with sequential ids composite-251, …
Run anytime; appends batches whose first id == max(composite-*) + 1.
Usage (repo root):
  python projects/mind/mem/auto_test_script/datasets/merge_handwritten_batches.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _leaf_tags(tree_path: Path) -> set[str]:
    data = json.loads(tree_path.read_text(encoding="utf-8"))

    def walk(node: object):
        if isinstance(node, dict):
            children = node.get("children")
            name = node.get("name")
            if children:
                for ch in children:
                    yield from walk(ch)
            elif name:
                yield name
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    return set(walk(data["root"]))


def main() -> int:
    root = Path(__file__).resolve().parent
    batches_dir = root / "handwritten_batches"
    tree_path = root / "vehicle_assistant_case_tag_tree.json"
    leaf_path = root / "vehicle_assistant_leaf_cases.json"

    leaves = _leaf_tags(tree_path)
    comp = json.loads(leaf_path.read_text(encoding="utf-8"))
    if not comp:
        print("Leaf JSON is empty.", file=sys.stderr)
        return 1

    max_serial = 0
    for c in comp:
        m = re.fullmatch(r"composite-(\d+)", c.get("id", ""))
        if m:
            max_serial = max(max_serial, int(m.group(1)))
    if max_serial == 0:
        print(
            "No composite-* cases in vehicle_assistant_leaf_cases.json; cannot infer next id.",
            file=sys.stderr,
        )
        return 1

    paths = sorted(batches_dir.glob("*.json"))
    if not paths:
        print(f"No JSON files in {batches_dir}", file=sys.stderr)
        return 1

    seen: set[str] = set(c["id"] for c in comp)
    next_num = max_serial + 1
    total_added = 0

    for bp in paths:
        chunk = json.loads(bp.read_text(encoding="utf-8"))
        if not isinstance(chunk, list):
            print(f"{bp.name}: must be a JSON array", file=sys.stderr)
            return 1
        for case in chunk:
            cid = case.get("id", "")
            m = re.fullmatch(r"composite-(\d+)", cid)
            if not m:
                print(f"{bp.name}: bad id {cid!r}", file=sys.stderr)
                return 1
            num = int(m.group(1))
            if num != next_num:
                print(f"{bp.name}: expected id composite-{next_num}, got {cid}", file=sys.stderr)
                return 1
            if cid in seen:
                print(f"duplicate id {cid}", file=sys.stderr)
                return 1
            for tag in case.get("tags", []):
                if tag not in leaves:
                    print(f"{cid}: invalid leaf tag {tag!r}", file=sys.stderr)
                    return 1
            seen.add(cid)
            comp.append(case)
            next_num += 1
            total_added += 1

    leaf_path.write_text(json.dumps(comp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = batches_dir / "merged"
    archive.mkdir(exist_ok=True)
    for bp in paths:
        dest = archive / bp.name
        if dest.exists():
            dest.unlink()
        bp.rename(dest)
    print(
        f"merged {total_added} handwritten cases from {len(paths)} file(s); "
        f"vehicle_assistant_leaf_cases.json total {len(comp)}"
    )
    print(f"archived batch files to {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
