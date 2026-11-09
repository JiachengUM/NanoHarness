"""projects.mind.toolset.dag — 递归 drop 空 leaf 的 dict 转换器

设计原则：
- drop：None / "" / 空 dict / 空 tuple / 空 set
- keep：False / 0 / 0.0 / True / 非空容器 / 空 list
    - 空 list 保留：让 LLM 看到 "key[0]:" 显式"0 results"信号
    - False / 数字零值保留：有语义（cost=0 免费、distance=0 在点上）
- bool 必须在 int 之前 isinstance（bool 是 int 的子类，否则会被误判）
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from projects.mind.toolset.dag.toon import to_toon


def _should_drop(v: Any) -> bool:
    """drop 规则：None / "" / 空 dict / 空 tuple / 空 set drop，其余保留。

    list 内的 items 走另一条路径（本函数只用于 dict/BaseModel 的 leaf 判断），
    不会在 list 中被调用。
    """
    if v is None:
        return True
    if isinstance(v, bool):  # 必须在 int 之前：bool 是 int 的子类
        return False
    if isinstance(v, (int, float)):
        return False
    if isinstance(v, str):
        return v == ""
    if isinstance(v, list):
        return False  # 空 list 保留：让 to_toon 输出 "key[0]:" 显式 0 results
    if isinstance(v, (dict, tuple, set)):
        return len(v) == 0
    return False


def _convert(v: Any) -> Any:
    """递归把 BaseModel / dict / list 转 dict，保留嵌套结构。"""
    if isinstance(v, BaseModel):
        converted = {k: _convert(item) for k, item in v.model_dump().items()}
        return {k: c for k, c in converted.items() if not _should_drop(c)}
    if isinstance(v, dict):
        converted = {k: _convert(item) for k, item in v.items()}
        return {k: c for k, c in converted.items() if not _should_drop(c)}
    if isinstance(v, list):
        return [_convert(item) for item in v]
    return v


def compact_dict(data: Any) -> dict:
    """把 BaseModel / dict / list 转 compact dict。

    - 顶层为 list 时包成 ``{"items": list}`` 并保留（即使空 list 也保留，
      体现"搜不到"的显式语义，model 可从 ``items: []`` 推断无结果）
    - dict/BaseModel 路径的 leaf 过滤在 ``_convert`` 内已完成，此处不再二次过滤
    - 顶层非 dict / list / BaseModel 时返回空 dict
    """
    converted = _convert(data)
    if isinstance(converted, list):
        return {"items": converted}
    if not isinstance(converted, dict):
        return {}
    return converted


def wrap_worker_with_compact(worker):
    """包装 worker：让它的输出走 compact_dict + to_toon（返回新 async function）。

    与 ``_compact_worker``（已删）的区别：
    - 这是纯函数：worker 进 → 包装后的新 worker 出，不修改输入
    - 调用方负责把返回的 worker 装回 tool（如 model_copy(update={"worker": ...})）
    - 不再包含 ``TOON_ENABLED`` 开关（已删 Smell α：当前只有 True 一种状态）
    """
    # 延迟 import 避免 compact ↔ toon 循环（toon 不依赖 compact，compact 依赖 toon）
    from projects.mind.toolset.dag.toon import to_toon

    async def wrapped(*args, **kwargs):
        result = compact_dict(await worker(*args, **kwargs))
        return to_toon(result)

    return wrapped


# 标记需要 compact 输出的 search tool 名字
# 妥协方案：v1 核心（aicore.tools.factory.create_tool + aicore.tools.task.TaskTool）不允许修改
# （58 个 caller 共享，添加字段/参数有连带影响），所以不能加声明式 ``compact_output: bool`` 字段。
# 退化为 frozenset 注册（位置从原 _common.py 搬到 compact.py 紧邻 compact_tool_output），
# 加新 search tool 时需要同步在这里加 1 个名字——成本仍低于 2 处分散硬编码（_common + __init__）。
_COMPACT_OUTPUT_TOOLS: frozenset[str] = frozenset(
    {"SongSearch", "PlaylistSearch", "AlbumSearch", "POISearch", "WebSearch"}
)


def compact_tool_output(tool):
    """返回 tool 副本：worker 走 compact 包装（不修改原 tool）。

    只处理 tool.name 在 ``_COMPACT_OUTPUT_TOOLS`` 内的 tool（注册式：frozenset 集中管理）。

    Args:
        tool: v1 TaskTool 实例（含 worker 字段）

    Returns:
        原 tool 副本（tool.name 不在注册表 或 无 worker 时）或 worker 被 wrap 后的 tool 副本

    Note:
        Pydantic v2 model_copy(update=...) 不触发 model_validator；
        wrapped 是 async function，静态看仍是 coroutine function，
        即使开了 ``validate_assignment`` 也能通过 ``is_task_aworker`` 校验。
    """
    if tool.name not in _COMPACT_OUTPUT_TOOLS:
        return tool
    original = getattr(tool, "worker", None)
    if original is None:
        return tool
    return tool.model_copy(update={"worker": wrap_worker_with_compact(original)})
