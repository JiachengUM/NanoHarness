import argparse
import sys
from pathlib import Path

from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree


def main() -> None:
    parser = argparse.ArgumentParser(description="可视化打印标签树")
    parser.add_argument(
        "tag_tree_path",
        nargs="?",
        default=None,
        help="标签树 JSON 文件路径（默认：脚本同目录下 vehicle_assistant_case_tag_tree.json）",
    )
    parser.add_argument(
        "--leaves-only",
        action="store_true",
        help="仅打印叶子标签清单，不打印树形结构",
    )
    args = parser.parse_args()

    if args.tag_tree_path:
        tag_tree_path = Path(args.tag_tree_path).resolve()
    else:
        tag_tree_path = Path(__file__).resolve().parent.parent.parent / "artifacts" / "base" / "base_vehicle_assistant_case_tag_tree.json"

    if not tag_tree_path.exists():
        print(f"错误：文件不存在 {tag_tree_path}", file=sys.stderr)
        sys.exit(1)

    tag_tree = TagTree.from_json_file(str(tag_tree_path))

    if not args.leaves_only:
        print(f"=== {tag_tree_path.name}（树形）===")
        print(tag_tree.to_pretty_string(show_leaf_mark=True))
        print()

    leaf_tags = tag_tree.get_leaf_tag_names()
    print(f"=== 叶子标签总数: {len(leaf_tags)} ===")
    for index, tag in enumerate(leaf_tags, start=1):
        print(f"{index:02d}. {tag}")


if __name__ == "__main__":
    main()
