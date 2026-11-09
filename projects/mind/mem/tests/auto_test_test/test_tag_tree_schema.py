import pytest
import json
from pathlib import Path

from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree, TagTreeNode


def build_demo_tag_tree() -> TagTree:
    return TagTree(
        root=TagTreeNode(
            name="测试用例标签",
            children=[
                TagTreeNode(
                    name="能力维度",
                    children=[
                        TagTreeNode(name="导航"),
                        TagTreeNode(name="多媒体控制"),
                    ],
                ),
                TagTreeNode(
                    name="对话维度",
                    children=[
                        TagTreeNode(name="单轮对话"),
                        TagTreeNode(name="多轮对话"),
                    ],
                ),
            ],
        )
    )


def test_build_and_print_tag_tree(capsys: pytest.CaptureFixture[str]) -> None:
    tree = build_demo_tag_tree()
    assert tree.get_leaf_tag_names() == ["导航", "多媒体控制", "单轮对话", "多轮对话"]

    pretty = tree.to_pretty_string()
    print(pretty)
    captured = capsys.readouterr()

    assert "测试用例标签" in captured.out
    assert "├── 能力维度" in captured.out
    assert "└── 对话维度" in captured.out
    assert "导航 [leaf]" in captured.out
    assert "多轮对话 [leaf]" in captured.out


def test_duplicate_node_names_not_allowed() -> None:
    with pytest.raises(ValueError, match="重名节点"):
        TagTree(
            root=TagTreeNode(
                name="根",
                children=[
                    TagTreeNode(name="重复标签"),
                    TagTreeNode(
                        name="一级节点",
                        children=[TagTreeNode(name="重复标签")],
                    ),
                ],
            )
        )


def test_add_node_success_and_duplicate_check() -> None:
    tree = build_demo_tag_tree()
    tree.add_node(parent_name="能力维度", node=TagTreeNode(name="车控"))
    assert "车控" in tree.get_leaf_tag_names()

    with pytest.raises(ValueError, match="已存在"):
        tree.add_node(parent_name="能力维度", node=TagTreeNode(name="导航"))


def test_delete_node_success() -> None:
    tree = build_demo_tag_tree()
    tree.delete_node("多轮对话")
    assert "多轮对话" not in tree.get_leaf_tag_names()

    with pytest.raises(ValueError, match="不允许删除根节点"):
        tree.delete_node("测试用例标签")


def test_move_subtree_success_and_invalid_cases() -> None:
    tree = build_demo_tag_tree()
    tree.move_subtree(source_name="能力维度", target_parent_name="对话维度")

    pretty = tree.to_pretty_string()
    assert "对话维度" in pretty
    assert "能力维度" in pretty

    with pytest.raises(ValueError, match="不允许将节点移动到其自身子树下"):
        tree.move_subtree(source_name="对话维度", target_parent_name="导航")


def test_update_node_info_success_and_duplicate_check() -> None:
    tree = build_demo_tag_tree()

    tree.update_node_info("能力维度", new_name="能力分类", new_description="能力标签一级分类")
    renamed_node = tree.get_node_by_name("能力分类")
    assert renamed_node.description == "能力标签一级分类"

    with pytest.raises(ValueError, match="重名节点"):
        tree.update_node_info("多媒体控制", new_name="导航")

    with pytest.raises(ValueError, match="new_name 不能为空"):
        tree.update_node_info("导航", new_name="   ")


def test_import_tag_tree_from_json_and_file() -> None:
    json_dict = {
        "tagging_guideline": "这是测试打标思路",
        "root": {
            "name": "测试用例标签",
            "children": [
                {"name": "能力维度", "children": [{"name": "导航"}, {"name": "车控"}]},
                {"name": "对话维度", "children": [{"name": "单轮对话"}]},
            ],
        }
    }
    tree_from_dict = TagTree.from_json(json_dict)
    assert tree_from_dict.root.name == "测试用例标签"
    assert tree_from_dict.root.description == ""
    assert len(tree_from_dict.root.children) == 2
    assert tree_from_dict.root.children[0].description == ""
    assert set(tree_from_dict.get_leaf_tag_names()) == {"导航", "车控", "单轮对话"}
    assert tree_from_dict.tagging_guideline == "这是测试打标思路"

    tree_from_str = TagTree.from_json(json.dumps(json_dict, ensure_ascii=False))
    assert tree_from_str.root.name == "测试用例标签"
    assert set(tree_from_str.get_leaf_tag_names()) == {"导航", "车控", "单轮对话"}

    template_path = Path(
        "projects/mind/mem/auto_test_script/auto_tagger/tag_tree_template.json"
    )
    tree_from_file = TagTree.from_json_file(str(template_path))
    assert tree_from_file.root.name == "root"
    assert tree_from_file.root.description == "empty tag tree template root"
    assert tree_from_file.get_leaf_tag_names() == ["root"]
    assert tree_from_file.tagging_guideline != ""


def test_from_json_rejects_multi_root_payload() -> None:
    with pytest.raises(ValueError, match="最外层必须且只能提供一个 root 字段"):
        TagTree.from_json(
            {
                "roots": [
                    {"name": "根1", "children": []},
                    {"name": "根2", "children": []},
                ]
            }
        )

    with pytest.raises(ValueError, match="root 必须是对象"):
        TagTree.from_json(
            {
                "root": [
                    {"name": "根1", "children": []},
                    {"name": "根2", "children": []},
                ]
            }
        )

    with pytest.raises(ValueError, match="最外层必须且只能提供一个 root 字段"):
        TagTree.from_json(
            {
                "meta": {"tagging_guideline": "x"},
                "items": [
                    {"name": "根1", "children": []},
                    {"name": "根2", "children": []},
                ],
            }
        )


def test_from_json_rejects_cycle_and_shared_subtree() -> None:
    cycle_root: dict = {"name": "根", "children": []}
    cycle_root["children"].append(cycle_root)
    with pytest.raises(ValueError, match="环结构"):
        TagTree.from_json({"root": cycle_root})

    shared_leaf = {"name": "共享叶子", "children": []}
    shared_root = {
        "name": "根",
        "children": [
            {"name": "分支A", "children": [shared_leaf]},
            {"name": "分支B", "children": [shared_leaf]},
        ],
    }
    with pytest.raises(ValueError, match="重名节点"):
        TagTree.from_json({"root": shared_root})


def test_reject_dag_in_tag_tree_structure_validation() -> None:
    # 直接构造对象图层面的DAG（同一个子节点对象挂到两个父节点）
    shared_leaf = TagTreeNode(name="共享叶子")
    root = TagTreeNode(
        name="根",
        children=[
            TagTreeNode(name="分支A", children=[shared_leaf]),
            TagTreeNode(name="分支B", children=[shared_leaf]),
        ],
    )
    with pytest.raises(ValueError, match="多个父节点"):
        TagTree(root=root)


def test_export_tag_tree_to_json_file(tmp_path: Path) -> None:
    tree = build_demo_tag_tree()

    json_text = tree.to_json()
    assert "测试用例标签" in json_text
    assert "能力维度" in json_text

    output_path = tmp_path / "exported_tag_tree.json"
    tree.to_json_file(str(output_path))
    assert output_path.exists()

    loaded_tree = TagTree.from_json_file(str(output_path))
    assert set(loaded_tree.get_leaf_tag_names()) == set(tree.get_leaf_tag_names())


def test_import_complex_sample_tag_tree_from_json_file() -> None:
    sample_path = Path(
        "projects/mind/mem/tests/auto_test_test/sample_car_assistant_tag_tree.json"
    )
    tree = TagTree.from_json_file(str(sample_path))

    assert tree.root.name == "车机助手测试标签树"
    assert tree.root.description == "车机助手自动化测试标签根节点"
    assert tree.tagging_guideline.startswith("请根据case的 expected_script")

    # 三层结构检查：root -> 一级 -> 二级 -> 叶子（至少一条链）
    level1 = tree.get_node_by_name("能力域")
    level2 = tree.get_node_by_name("导航能力")
    leaf = tree.get_node_by_name("回家导航")
    assert level1.description == "按业务能力维度划分"
    assert level2.description.startswith("与路线规划")
    assert leaf.description == "回家/回公司等默认地点导航能力"

    expected_leaf_tags = {
        "回家导航",
        "POI检索导航",
        "空调控制",
        "座椅控制",
        "单轮对话",
        "多轮对话",
        "跨多轮对话",
        "长期记忆",
        "音乐偏好",
        "skill创建",
        "skill复用",
    }
    assert set(tree.get_leaf_tag_names()) == expected_leaf_tags
