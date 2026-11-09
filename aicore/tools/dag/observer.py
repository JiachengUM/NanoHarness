"""Ambient DAG render observations.

The DAG core emits domain render frames through a context-local observer. v2
tool wrappers can collect those frames and expose them as TaskProgress without
threading progress-specific parameters through the DAG call chain.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aicore.tools.dag.base_classes import DAGIR


DAGRenderPhase = Literal["queued", "build", "execution", "completed", "failed"]
DAGRenderObserver = Callable[["DAGRenderFrame"], Awaitable[None] | None]

_current_observer: ContextVar[DAGRenderObserver | None] = ContextVar(
    "dag_render_observer",
    default=None,
)


class DAGRenderNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    label: str
    operator_type: str | None = None
    status: str = "pending"
    step_index: int | None = None
    goal: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    result: Any = None
    progress_percent: int = 0


class DAGRenderEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class DAGRenderGraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    goal: str = ""
    nodes: list[DAGRenderNode] = Field(default_factory=list)
    edges: list[DAGRenderEdge] = Field(default_factory=list)


class DAGRenderFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    component: Literal["dag"] = "dag"
    event: Literal["snapshot"] = "snapshot"
    phase: DAGRenderPhase
    message: str
    progress_percent: int | None = None
    graph: DAGRenderGraph | None = None
    active_node_id: str | None = None
    status: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


@contextmanager
def observe_dag_frames(observer: DAGRenderObserver) -> Iterator[None]:
    token = _current_observer.set(observer)
    try:
        yield
    finally:
        _current_observer.reset(token)


async def emit_dag_frame(frame: DAGRenderFrame) -> None:
    observer = _current_observer.get()
    if observer is None:
        return

    result = observer(frame)
    if inspect.isawaitable(result):
        await result


def _progress_for_status(status: str) -> int:
    if status in ("success", "done", "failed", "partial", "skipped", "cancelled"):
        return 100
    if status == "running":
        return 45
    if status == "cancelling":
        return 88
    return 0


def _safe_text(value: Any, *, max_len: int = 120) -> str:
    text = str(value).strip()
    if len(text) > max_len:
        return f"{text[:max_len]}..."
    return text


def _summarize_result(value: Any, *, max_len: int = 120) -> str:
    if value is None:
        return ""
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            if item is None:
                continue
            parts.append(f"{key}={_safe_text(item, max_len=26)}")
            if len(parts) >= 4:
                break
        return _safe_text("; ".join(parts), max_len=max_len)
    if isinstance(value, list):
        if not value:
            return "无结果"
        first = value[0]
        if isinstance(first, BaseModel):
            first = first.model_dump()
        if isinstance(first, dict):
            return _safe_text(f"共{len(value)}条结果: {_summarize_result(first, max_len=72)}", max_len=max_len)
        return _safe_text(f"共{len(value)}条结果: {_safe_text(first, max_len=72)}", max_len=max_len)
    return _safe_text(value, max_len=max_len)


def _result_summary_for_node(status: str, result: Any, error: str | None) -> str:
    if status in ("failed", "cancelled") and error:
        return _safe_text(error)
    summary = _summarize_result(result)
    if summary:
        return summary
    if status == "running":
        return "执行中"
    if status == "success":
        return "已完成"
    if status == "partial":
        return "部分完成"
    if status == "skipped":
        return "已跳过"
    if status in ("failed", "cancelled"):
        return "执行失败"
    return "等待执行"


def _arguments_for_node(raw: Any) -> dict[str, Any]:
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        if len(raw) == 1:
            return _arguments_for_node(raw[0])
        return {"items": raw}
    return {}


def _detail_value_for_node(raw: Any) -> Any:
    if isinstance(raw, BaseModel):
        return raw.model_dump(mode="json")
    if isinstance(raw, dict):
        return {str(key): _detail_value_for_node(value) for key, value in raw.items()}
    if isinstance(raw, (list, tuple)):
        return [_detail_value_for_node(value) for value in raw]
    if isinstance(raw, (str, int, float, bool)) or raw is None:
        return raw
    return str(raw)


def _topological_node_ids(dag_ir: DAGIR) -> list[str]:
    try:
        return list(dag_ir.topological_order)
    except Exception:
        return list(dag_ir.nodes.keys())


def build_dag_render_graph(
    dag_ir: DAGIR | None,
    *,
    statuses: dict[str, str] | None = None,
    results: dict[str, Any] | None = None,
    errors: dict[str, str | None] | None = None,
    progress_per_node: dict[str, int] | None = None,
    arguments: dict[str, Any] | None = None,
) -> DAGRenderGraph:
    if dag_ir is None:
        return DAGRenderGraph()

    statuses = statuses or {}
    results = results or {}
    errors = errors or {}
    progress_per_node = progress_per_node or {}
    arguments = arguments or {}
    nodes: list[DAGRenderNode] = []
    edges: list[DAGRenderEdge] = []
    ordered_node_ids = _topological_node_ids(dag_ir)
    step_index_by_id = {node_id: index + 1 for index, node_id in enumerate(ordered_node_ids)}
    for node_id in ordered_node_ids:
        node = dag_ir.nodes[node_id]
        operator_type = node.operator.value if node.operator else None
        status = statuses.get(node_id, "pending")
        node_goal = node.step_goal or operator_type or node_id
        nodes.append(
            DAGRenderNode(
                id=node_id,
                label=node_goal,
                operator_type=operator_type,
                status=status,
                step_index=step_index_by_id.get(node_id),
                goal=node_goal,
                tool_name=operator_type or "",
                arguments=_arguments_for_node(arguments.get(node_id, node.params)),
                result_summary=_result_summary_for_node(
                    status,
                    results.get(node_id),
                    errors.get(node_id),
                ),
                result=_detail_value_for_node(results.get(node_id)) if node_id in results else None,
                progress_percent=progress_per_node.get(node_id, _progress_for_status(status)),
            )
        )
        edges.extend(DAGRenderEdge(from_=dep_id, to=node_id) for dep_id in node.dependencies)

    return DAGRenderGraph(goal=dag_ir.goal, nodes=nodes, edges=edges)


__all__ = [
    "DAGRenderEdge",
    "DAGRenderFrame",
    "DAGRenderGraph",
    "DAGRenderNode",
    "DAGRenderObserver",
    "build_dag_render_graph",
    "emit_dag_frame",
    "observe_dag_frames",
]
