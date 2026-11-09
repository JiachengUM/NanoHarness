from collections import defaultdict
from typing import Callable, Any, cast

from pydantic import BaseModel, Field


class Node[T](BaseModel):
    """DAG 节点。"""
    name: str = Field(description="节点名称")
    data: T = Field(description="节点数据")


class Edge[T](BaseModel):
    """DAG 边。source/target 为节点 ID，data 为附加数据。"""
    source: str = Field(description="源节点名称")
    target: str = Field(description="目标节点名称")
    data: T = Field(description="边数据")


class CycleDetected(Exception):
    """topo_levels 内部异常，携带环中所有节点 ID。"""

    def __init__(self, members: list[str]) -> None:
        self.members = members


class DAG[NT, ET]:
    """DAG 图。"""

    nodes: list[NT] = Field(description="节点列表")
    edges: list[ET] = Field(description="边列表")

    def __init__(self, nodes: list[NT] | None = None, edges: list[ET] | None = None):
        self.nodes = nodes or []
        self.edges = edges or []

    def topo_levels(self, key: Callable[[NT], str]) -> list[list[NT]]:
        """Kahn's BFS 拓扑排序，将节点按执行层分组，同层无相互依赖可并行。

        edges 须为 Edge[...] 实例（source/target 为节点 ID）。
        存在环时抛出 CycleDetected，members 为环中所有节点 ID。
        """
        in_degree: dict[str, int] = {key(n): 0 for n in self.nodes}
        dependents: dict[str, list[str]] = defaultdict(list)
        node_map: dict[str, NT] = {key(n): n for n in self.nodes}
        level_of: dict[str, int] = {}

        for edge in cast(list[Edge[Any]], self.edges):
            dependents[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        queue: list[str] = [nid for nid, d in in_degree.items() if d == 0]
        for nid in queue:
            level_of[nid] = 0

        head = 0
        while head < len(queue):
            nid = queue[head]; head += 1
            for child in dependents[nid]:
                in_degree[child] -= 1
                level_of[child] = level_of[nid] + 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(queue) != len(self.nodes):
            members = [nid for nid, d in in_degree.items() if d > 0]
            raise CycleDetected(members)

        max_level = max(level_of.values(), default=-1)
        levels: list[list[NT]] = [[] for _ in range(max_level + 1)]
        for nid, lv in level_of.items():
            levels[lv].append(node_map[nid])
        return levels
