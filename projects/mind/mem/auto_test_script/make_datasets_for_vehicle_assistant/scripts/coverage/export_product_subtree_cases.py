"""按标签子树导出命中叶子标签的用例。

默认：「产品视角标签子树」下一级子树（车控、导航等）→ product_subtree_<名>_cases.json

另含：「内容合规」中间节点下全部叶子 → product_subtree_内容合规_cases.json
（tags 与内容合规九叶有交集即收录，规则与产品子树相同。）

读取：
  vehicle_assistant_case_tag_tree.json — 树结构
  vehicle_assistant_leaf_cases.json — 评测用例（默认含 leaf + composite 合并结果）
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent


def find_product_subtree(node: dict) -> dict | None:
    if node.get("name") == "产品视角标签子树":
        return node
    for c in node.get("children") or []:
        r = find_product_subtree(c)
        if r is not None:
            return r
    return None


def leaves_under(node: dict) -> list[str]:
    ch = node.get("children")
    if not ch:
        if node.get("name"):
            return [node["name"]]
        return []
    out: list[str] = []
    for c in ch:
        out.extend(leaves_under(c))
    return out


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def find_node_by_name(node: dict, name: str) -> dict | None:
    if node.get("name") == name:
        return node
    for c in node.get("children") or []:
        r = find_node_by_name(c, name)
        if r is not None:
            return r
    return None


def write_subtree_cases(
    node: dict,
    cases: list[dict],
    out_dir: Path,
    *,
    prefix: str = "product_subtree",
) -> tuple[str, int, int, str]:
    """Export cases whose tags intersect leaves under ``node``."""
    st_name = node["name"]
    leaf_tags = set(leaves_under(node))
    picked = [c for c in cases if set(c.get("tags") or []) & leaf_tags]
    out_name = f"{prefix}_{safe_filename(st_name)}_cases.json"
    out_path = out_dir / out_name
    out_path.write_text(
        json.dumps(picked, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return st_name, len(leaf_tags), len(picked), out_name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cases",
        type=Path,
        default=BASE / "vehicle_assistant_leaf_cases.json",
        help="输入用例 JSON（数组）",
    )
    ap.add_argument(
        "--tree",
        type=Path,
        default=BASE / "vehicle_assistant_case_tag_tree.json",
        help="标签树 JSON",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=BASE,
        help="输出目录（默认与脚本同目录）",
    )
    ap.add_argument(
        "--only",
        type=str,
        default="",
        help="仅导出指定子树（产品一级名或「内容合规」）",
    )
    args = ap.parse_args()

    tree = json.loads(args.tree.read_text(encoding="utf-8"))
    pst = find_product_subtree(tree["root"])
    if pst is None:
        raise SystemExit("未找到节点：产品视角标签子树")
    subtrees = pst.get("children") or []

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    only = (args.only or "").strip()

    def should_export(name: str) -> bool:
        return not only or only == name

    for st in subtrees:
        st_name = st["name"]
        if not should_export(st_name):
            continue
        _, n_leaves, n_cases, out_name = write_subtree_cases(st, cases, args.out_dir)
        print(f"{st_name}\tleaves={n_leaves}\tcases={n_cases}\t-> {out_name}")

    cc = find_node_by_name(tree["root"], "内容合规")
    if cc is None:
        raise SystemExit("未找到节点：内容合规")
    if should_export("内容合规"):
        _, n_leaves, n_cases, out_name = write_subtree_cases(cc, cases, args.out_dir)
        print(f"内容合规\tleaves={n_leaves}\tcases={n_cases}\t-> {out_name}")


if __name__ == "__main__":
    main()
