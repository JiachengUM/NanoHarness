from __future__ import annotations

from collections.abc import Callable

import pytest

from aicore.utils.parent_pointer_tree import NodeId, ParentPointerTree


def _id_factory() -> Callable[[], NodeId]:
    ids = iter(["A", "B", "C", "D", "E"])
    return lambda: next(ids)


def test_path_returns_values_from_root_to_leaf() -> None:
    tree = ParentPointerTree[str](id_factory=_id_factory())

    root = tree.append("root")
    child = tree.append("child", parent_id=root)
    leaf = tree.append("leaf", parent_id=child)

    assert tree.path(leaf) == ["root", "child", "leaf"]
    assert tree.root_id(leaf) == root
    assert [node.id for node in tree.path_nodes(leaf)] == ["A", "B", "C"]


def test_multiple_branches_share_parent_path() -> None:
    tree = ParentPointerTree[str](id_factory=_id_factory())

    root = tree.append("root")
    left = tree.append("left", parent_id=root)
    right = tree.append("right", parent_id=root)

    assert tree.path(left) == ["root", "left"]
    assert tree.path(right) == ["root", "right"]
    assert tree.get(left).parent_id == root
    assert tree.get(right).parent_id == root


def test_new_child_can_be_added_to_existing_branch_point() -> None:
    tree = ParentPointerTree[str](id_factory=_id_factory())

    root = tree.append("root")
    child = tree.append("child", parent_id=root)

    assert len(tree) == 2
    assert tree.path(child) == ["root", "child"]


def test_unknown_ids_are_rejected() -> None:
    tree = ParentPointerTree[str]()

    with pytest.raises(KeyError, match="Unknown parent node id"):
        tree.append("value", parent_id="missing")

    with pytest.raises(KeyError, match="Unknown node id"):
        tree.path("missing")


def test_append_generates_node_id_internally() -> None:
    tree = ParentPointerTree[str](id_factory=_id_factory())

    node_id = tree.append("value")

    assert node_id == "A"
    assert tree.get(node_id).id == node_id


def test_id_factory_collision_limit_is_reported() -> None:
    tree = ParentPointerTree[str](id_factory=lambda: "same")

    tree.append("first")

    with pytest.raises(RuntimeError, match="Unable to generate"):
        tree.append("second")
