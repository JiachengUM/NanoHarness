#!/usr/bin/env python3
"""Export cases under each first-level subtree of「产品视角标签子树」.

A case is included in bucket L1 if any of its ``tags`` is a leaf tag that belongs
to that L1's subtree (under 产品视角标签子树). Cases with tags spanning multiple
product domains appear in multiple bucket files.

Usage (cwd=datasets/):
  python export_product_L1_cases.py
  python export_product_L1_cases.py --out-dir product_perspective_L1_export

Writes:
  - ``<out-dir>/*.json`` + ``README.md``
  - ``product_subtree_<一级子树>_cases.json`` (7 files next to this script)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


PRODUCT_ROOT = "产品视角标签子树"


def collect_leaves(node: dict, out: list[str]) -> None:
    name = node.get("name")
    ch = node.get("children") or []
    if not ch:
        if name:
            out.append(name)
        return
    for c in ch:
        collect_leaves(c, out)


def find_child_by_name(node: dict, name: str) -> dict | None:
    for c in node.get("children") or []:
        if c.get("name") == name:
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: <datasets>/product_perspective_L1_export)",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    out_dir = args.out_dir or (root / "product_perspective_L1_export")
    out_dir.mkdir(parents=True, exist_ok=True)

    tree = json.loads((root / "vehicle_assistant_case_tag_tree.json").read_text(encoding="utf-8"))
    product = find_child_by_name(tree["root"], PRODUCT_ROOT)
    if product is None:
        raise SystemExit(f"tag tree missing {PRODUCT_ROOT!r}")

    l1_nodes = product.get("children") or []
    l1_names = [n["name"] for n in l1_nodes]

    leaf_to_l1: dict[str, str] = {}
    l1_to_leaves: dict[str, list[str]] = {}
    for n in l1_nodes:
        l1 = n["name"]
        leaves: list[str] = []
        collect_leaves(n, leaves)
        l1_to_leaves[l1] = leaves
        for leaf in leaves:
            if leaf in leaf_to_l1 and leaf_to_l1[leaf] != l1:
                raise SystemExit(f"leaf {leaf!r} maps to both {leaf_to_l1[leaf]!r} and {l1!r}")
            leaf_to_l1[leaf] = l1

    cases = json.loads((root / "vehicle_assistant_leaf_cases.json").read_text(encoding="utf-8"))

    buckets: dict[str, list[dict]] = {name: [] for name in l1_names}
    seen_in_bucket: dict[str, set[str]] = {name: set() for name in l1_names}
    no_product: list[dict] = []

    for case in cases:
        cid = str(case.get("id", ""))
        tags = case.get("tags") or []
        matched_l1: set[str] = set()
        for t in tags:
            l1 = leaf_to_l1.get(t)
            if l1 is not None:
                matched_l1.add(l1)
        if not matched_l1:
            no_product.append(case)
            continue
        for l1 in matched_l1:
            if cid not in seen_in_bucket[l1]:
                seen_in_bucket[l1].add(cid)
                buckets[l1].append(case)

    def split_counts(rows: list[dict]) -> tuple[int, int, int]:
        leaf_n = sum(1 for r in rows if str(r.get("id", "")).startswith("leaf-"))
        comp_n = sum(1 for r in rows if str(r.get("id", "")).startswith("composite-"))
        other = len(rows) - leaf_n - comp_n
        return leaf_n, comp_n, other

    lines: list[str] = [
        "# 产品视角：一级子树用例导出摘要",
        "",
        f"- 数据源：`vehicle_assistant_leaf_cases.json`（共 **{len(cases)}** 条）",
        f"- 标签树：`vehicle_assistant_case_tag_tree.json` → `{PRODUCT_ROOT}` 下 **{len(l1_names)}** 个一级子树",
        "- 归类规则：若用例的任一 `tags` 叶子属于某一级子树，则该用例计入该子树；跨域多标签可重复出现在多个子树文件中。",
        "- 上表「用例数」按子树分别计数，**加总可大于**总用例数（同一条会进多个桶）；未命中产品叶子的条数见下节。",
        "",
        "## 一级子树 case 数",
        "",
        "| 一级子树 | 用例数 | leaf-* | composite-* | 其它 id | 子树叶子数 |",
        "|----------|--------|--------|---------------|---------|------------|",
    ]
    for l1 in l1_names:
        rows = buckets[l1]
        ln, cn, on = split_counts(rows)
        lines.append(
            f"| {l1} | {len(rows)} | {ln} | {cn} | {on} | {len(l1_to_leaves[l1])} |"
        )
    np_leaf, np_comp, np_other = split_counts(no_product)
    lines.extend(
        [
            "",
            "## 未命中任何产品视角叶子",
            "",
            f"- **{len(no_product)}** 条用例的 `tags` 中没有任何标签落在「{PRODUCT_ROOT}」子树的叶子集合内（可能仅为通用 Agent / 结构类标签）。",
            f"  - 其中 leaf-*：**{np_leaf}**，composite-*：**{np_comp}**，其它 id：**{np_other}**。",
            "",
            "## 产出文件",
            "",
            f"- 本目录下各 `*.json`：该一级子树下命中的完整用例对象列表（与源文件结构一致）。",
            f"- 同级目录另写 `product_subtree_<一级子树>_cases.json`（七份），便于旧脚本或外部工具按固定文件名引用。",
        ]
    )
    summary_path = out_dir / "README.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for l1, rows in buckets.items():
        safe = l1.replace("/", "／").replace("\\", "＼")
        payload = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
        (out_dir / f"{safe}.json").write_text(payload, encoding="utf-8")
        # 与历史命名对齐：datasets/product_subtree_<一级子树>_cases.json
        legacy_name = f"product_subtree_{l1}_cases.json"
        (root / legacy_name).write_text(payload, encoding="utf-8")

    print(f"Wrote {out_dir}/")
    print(f"  {summary_path.name}")
    for l1 in l1_names:
        safe = l1.replace("/", "／").replace("\\", "＼")
        print(f"  {safe}.json  ({len(buckets[l1])} cases)")
    print("Also wrote datasets/product_subtree_<L1>_cases.json (7 files)")
    print(f"no_product_leaf_hit: {len(no_product)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
