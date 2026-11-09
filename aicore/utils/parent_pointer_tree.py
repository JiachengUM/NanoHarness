"""Parent-pointer tree utilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import uuid4


__all__ = [
    "NodeId",
    "ParentPointerTree",
    "ParentPointerTreeNode",
]

type NodeId = str


@dataclass(frozen=True, slots=True)
class ParentPointerTreeNode[T]:
    """One immutable node in a parent-pointer tree."""

    id: NodeId
    value: T
    parent_id: NodeId | None = None
    depth: int = 0


class ParentPointerTree[T]:
    """Append-only multi-branch tree backed by parent pointers.

    Each append creates a new leaf. Different children can share the same
    parent, and existing paths are never modified.
    """

    def __init__(
        self,
        *,
        id_factory: Callable[[], NodeId] | None = None,
    ) -> None:
        self._nodes: dict[NodeId, ParentPointerTreeNode[T]] = {}
        self._id_factory = id_factory or (lambda: uuid4().hex)

    @property
    def nodes(self) -> Mapping[NodeId, ParentPointerTreeNode[T]]:
        """Read-only view of nodes keyed by node id."""

        return MappingProxyType(self._nodes)

    def __contains__(self, node_id: NodeId) -> bool:
        return node_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    def append(
        self,
        value: T,
        *,
        parent_id: NodeId | None = None,
    ) -> NodeId:
        """Append a value under parent_id and return the new node id."""

        if parent_id is not None and parent_id not in self._nodes:
            raise KeyError(f"Unknown parent node id: {parent_id}")

        new_id = self._new_node_id()
        depth = self._nodes[parent_id].depth + 1 if parent_id is not None else 0
        self._nodes[new_id] = ParentPointerTreeNode(
            id=new_id,
            value=value,
            parent_id=parent_id,
            depth=depth,
        )
        return new_id

    def get(self, node_id: NodeId) -> ParentPointerTreeNode[T]:
        """Return a node by id."""

        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node id: {node_id}") from exc

    def root_id(self, node_id: NodeId) -> NodeId:
        """Return the root node id for the path ending at node_id."""

        current = self.get(node_id)
        while current.parent_id is not None:
            current = self.get(current.parent_id)
        return current.id

    def path_nodes(self, node_id: NodeId) -> list[ParentPointerTreeNode[T]]:
        """Return nodes from root to node_id."""

        nodes: list[ParentPointerTreeNode[T]] = []
        current: ParentPointerTreeNode[T] | None = self.get(node_id)

        while current is not None:
            nodes.append(current)
            current = (
                self.get(current.parent_id)
                if current.parent_id is not None
                else None
            )

        nodes.reverse()
        return nodes

    def path(self, node_id: NodeId) -> list[T]:
        """Return values from root to node_id."""

        return [node.value for node in self.path_nodes(node_id)]

    def _new_node_id(self) -> NodeId:
        for _ in range(100):
            node_id = self._id_factory()
            if node_id not in self._nodes:
                return node_id
        raise RuntimeError("Unable to generate a unique parent-pointer tree node id")
