"""DAG 执行器 — 拓扑调度、依赖注入、并行执行

本模块是 DAG 系统的核心执行引擎，职责：
1. 按拓扑序调度就绪节点（依赖全部成功的节点优先执行）
2. 将节点入参中的 $step_id.field / $step_id 占位符替换为上游输出（依赖注入）
3. 同一 dep 多字段按下标配对（zip），不同 dep 之间做笛卡尔积展开参数
4. 并行执行就绪节点（asyncio.Task + FIRST_COMPLETED 策略）
5. 执行后校验 step_goal 是否达成，未达成标记为 partial
6. 失败节点自动重试（最多 MAX_RETRIES 次），上游失败则下游标记 skipped

典型调用：executor = DAGExecutor(dag_ir); result = await executor.execute(context)
"""

import asyncio
import anyio
import json
import logging
import re
import traceback as traceback_module
from itertools import product
from typing import Dict, Any, Optional, List, Tuple, Union

import yaml
from pydantic import ValidationError

from .base_classes import (
    CurrentStepInfo,
    StepHistoryEntry,
    ExecutionContext,
    ExecutionTrace,
    DAGIR,
    DAGNode,
    OperatorType,
    _REF_PATTERN,
)
from .operator_registry import OperatorRegistry, OperatorContext, OperatorResult
from .operator_models import ValidatorOutput
from .observer import DAGRenderFrame, build_dag_render_graph, emit_dag_frame
from .dag_metrics import DagMetrics, NodeMetrics
from .issues import (
    BaseIssue,
    ExecutionIssue,
    ExceptionIssue,
    IssueSeverity,
    IssueReport,
    PlanOptimizationIssue,
    SearchStrategyIssue,
    SerializationIssue,
    StepGoalIssue,
    ToolOutputParseIssue,
)

logger = logging.getLogger(__name__)

# _REF_PATTERN 已迁移至 base_classes.py（跨模块共享，plan_generator 静态校验也用）
# field 路径允许 [N] 索引访问，如 $s9.songs[0].song_name
_SINGLE_REF = re.compile(
    r"^\$(\w+)\.([\w.\[\]]+)$"
)  # 精确匹配单个 $step_id.field（含嵌套多层与索引）
# bare ref: $step_id 无 .field，step_id 仅匹配 s+数字 格式，避免吃掉后续中文
_BARE_REF_PATTERN = re.compile(r"\$(s\d+)(?!\.)")
_SINGLE_BARE_REF = re.compile(r"^\$(s\d+)$")  # 精确匹配单个 $step_id
# 字段路径 token 化：'songs[0].song_name' → [('key','songs'), ('index',0), ('key','song_name')]
_FIELD_PATH_TOKEN = re.compile(r"\[(\d+)\]|([^\[\].]+)")


class DAGExecutor:
    """DAG 执行器 — 核心调度引擎

    接收 DAGIR（静态 DAG），按拓扑序并行执行节点，支持：
    - 依赖注入：将 $step_id.field / $step_id 占位符替换为上游实际输出
    - 笛卡尔积展开：不同 dep 的多值参数做组合展开
    - step_goal 校验：执行后检查步骤目标是否达成
    - 失败重试：失败节点最多重试 MAX_RETRIES 次
    """

    MAX_RETRIES = 2  # 失败节点最大重试次数
    MAX_PARAM_COMBINATIONS = 50  # 笛卡尔积展开上限

    def __init__(self, dag_ir: DAGIR):
        """初始化执行器

        Args:
            dag_ir: DAG 中间表示（静态快照）
        """
        self.dag_ir = dag_ir
        self._topo_order: List[str] = dag_ir.topological_order  # 缓存拓扑序
        self.traces: Dict[str, ExecutionTrace] = {}
        self.results: Dict[str, Any] = {}
        self.step_goals: Dict[str, str] = {}  # {node_id: step_goal}
        self.step_outputs: Dict[str, List[str]] = {}  # {node_id: step_output 字段列表}
        self.step_deps: Dict[str, List[str]] = {}  # {node_id: dependencies}
        self.step_history: List[
            StepHistoryEntry
        ] = []  # M3：增量维护，避免 O(n²) 全量重建
        self.metrics: DagMetrics = DagMetrics(
            node_count=len(dag_ir.nodes)
        )  # D3：全链路 metrics 容器，由 _record_node_metrics 填充

    # ---------- helpers ----------

    @staticmethod
    def _deduplicate_records(
        data: List[Dict[str, Any]],
        key_fields: Optional[List[str]] = None,
        max_records: int = 10,
    ) -> List[Dict[str, Any]]:
        """记录去重：支持按关键字段去重和整条记录去重，结果截断到 max_records 条。

        Args:
            data: 待去重的记录列表
            key_fields: 用于去重的关键字段列表（None 则按整条记录去重）
            max_records: 最大返回条数
        """

        def _make_hashable(v: Any) -> Any:
            if isinstance(v, dict):
                return json.dumps(v, sort_keys=True, ensure_ascii=False)
            if isinstance(v, list):
                return json.dumps(v, ensure_ascii=False)
            return v

        seen_keys = set()
        seen_full = set()
        result = []

        for record in data:
            if not isinstance(record, dict):
                result.append(record)
                continue

            key_tuple = None
            use_key_dedup = False

            if key_fields:
                if all(field in record for field in key_fields):
                    key_tuple = tuple(
                        _make_hashable(record[field]) for field in key_fields
                    )
                    use_key_dedup = True

            full_key = tuple(sorted((k, _make_hashable(v)) for k, v in record.items()))

            if use_key_dedup and key_tuple in seen_keys:
                continue
            if full_key in seen_full:
                continue

            if use_key_dedup:
                seen_keys.add(key_tuple)
            seen_full.add(full_key)
            result.append(record)

            if len(result) >= max_records:
                break

        return result

    def _compute_node_priority(self) -> Dict[str, Tuple[int, int]]:
        """计算每个节点的优先级元组 (chain_length, fan_out)。

        - chain_length: 该节点到叶节点的最长路径长度（关键路径长度）
        - fan_out: 直接依赖该节点的下游节点数量

        排序时按 chain_length 降序为主键，fan_out 降序为次键。
        关键路径节点优先执行，同链长时高扇出节点优先（释放更多下游并行窗口）。
        """
        # 1. fan_out: 反向邻接统计
        fan_out: Dict[str, int] = {nid: 0 for nid in self.dag_ir.nodes}
        for nid, node in self.dag_ir.nodes.items():
            for dep in node.dependencies:
                if dep in fan_out:
                    fan_out[dep] += 1

        # 2. chain_length: 拓扑逆序计算（从叶节点回溯）
        chain_length: Dict[str, int] = {}
        for nid in reversed(self._topo_order):
            if nid not in self.dag_ir.nodes:
                chain_length[nid] = 0
                continue
            downstream = [
                d for d in self.dag_ir.nodes if nid in self.dag_ir.nodes[d].dependencies
            ]
            if not downstream:
                chain_length[nid] = 0
            else:
                chain_length[nid] = 1 + max(chain_length.get(d, 0) for d in downstream)

        return {nid: (chain_length[nid], fan_out[nid]) for nid in self.dag_ir.nodes}

    def _pick_ready_nodes(
        self, issue_report: Optional[IssueReport] = None
    ) -> List[str]:
        """返回当前所有可执行的节点列表（依赖全部成功、自身未完成）。

        同时跳过已在运行中的节点，避免重复调度。
        上游依赖失败的节点直接标记为 skipped，并同步记入 issue_report（若提供）。
        """
        topo_order = self._topo_order

        ready = []
        for node_id in topo_order:
            if node_id not in self.dag_ir.nodes:
                continue
            trace = self.traces.get(node_id)
            if trace is not None:
                if trace.status in ("success", "partial", "skipped"):
                    continue
                if trace.status == "failed" and trace.retry_count >= self.MAX_RETRIES:
                    continue
                if trace.status == "running":
                    continue
            # 检查依赖
            deps = self.dag_ir.nodes[node_id].dependencies
            failed_deps = []
            pending_deps = []
            for dep in deps:
                dep_trace = self.traces.get(dep)
                if dep_trace is None:
                    pending_deps.append(dep)
                    continue
                if dep_trace.status in ("failed", "skipped"):
                    failed_deps.append(dep)
                elif dep_trace.status != "success":
                    pending_deps.append(dep)
            if failed_deps:
                # 依赖已失败，本节点直接标记为 skipped
                op_type = (
                    self.dag_ir.nodes[node_id].operator.value
                    if self.dag_ir.nodes[node_id].operator
                    else "unknown"
                )
                self.traces[node_id] = ExecutionTrace(
                    node_id=node_id,
                    operator_type=op_type,
                    params=self.dag_ir.nodes[node_id].params,
                ).model_copy(
                    update={
                        "status": "skipped",
                        "error": f"上游依赖节点失败: {', '.join(failed_deps)}",
                    }
                )
                # 同步记入 issue_report（skipped 属于 MEDIUM 级别，不影响整体但需记录）
                if issue_report is not None:
                    issue_report.add(
                        ExecutionIssue(
                            severity=IssueSeverity.MEDIUM,
                            message=f"节点 {node_id} 因上游依赖失败而跳过: {', '.join(failed_deps)}",
                            node_id=node_id,
                            operator_type=op_type,
                            status="skipped",
                            trace_id=node_id,
                        )
                    )
                continue
            if pending_deps:
                continue
            ready.append(node_id)
        # 按 (chain_length 降序, fan_out 降序) 排序：关键路径优先，同链长时高扇出优先
        priority = self._compute_node_priority()
        ready.sort(key=lambda nid: priority.get(nid, (0, 0)), reverse=True)
        return ready

    @staticmethod
    def _extract_match_text(data: Any) -> str:
        """从结构化输出提取文本用于 step_goal 匹配，避免字段名噪声

        搜索类算子输出形态：
        - list[dict]：POI 列表（取每个 dict 的 str 值拼接）
        - dict：WebSearch 单结果 / SongSearch|PlaylistSearch|AlbumSearch 聚合
        - BaseModel：算子输出模型（model_dump 后按 dict 处理）
        - str：直接返回
        - 其他：str() 转换

        提取策略：递归收集所有 str 类型字段值，跳过 None / 数值 / 字段名，
        避免字段名（如 "poi"/"address"）成为 2-gram 噪声导致误判达成。
        """

        def _collect_str_values(obj: Any) -> List[str]:
            if obj is None:
                return []
            if isinstance(obj, str):
                return [obj] if obj.strip() else []
            if hasattr(obj, "model_dump"):
                return _collect_str_values(obj.model_dump())
            if isinstance(obj, dict):
                values: List[str] = []
                for v in obj.values():
                    values.extend(_collect_str_values(v))
                return values
            if isinstance(obj, (list, tuple)):
                values = []
                for item in obj:
                    values.extend(_collect_str_values(item))
                return values
            return []  # 数值/布尔等非文本类型跳过

        return " ".join(_collect_str_values(data)).lower()

    def _get_downstream_nodes(self, node_id: str) -> List[Dict[str, Any]]:
        """获取节点的下游后继节点列表（依赖当前节点输出的节点）。

        遍历 self.dag_ir.nodes，收集 node_id 出现在其他节点 dependencies 中的节点。
        返回 dict 列表（与 ValidatorParams.downstream_nodes 序列化形态对齐），
        每项含 node_id / operator_type / step_goal / step_output。
        """
        downstream: List[Dict[str, Any]] = []
        for nid, node in self.dag_ir.nodes.items():
            if node_id in node.dependencies:
                downstream.append(
                    {
                        "node_id": nid,
                        "operator_type": node.operator.value if node.operator else "",
                        "step_goal": node.step_goal or "",
                        "step_output": list(node.step_output or []),
                    }
                )
        return downstream

    @staticmethod
    def _describe_available_keys(data: Any) -> str:
        """描述 data 的可用字段，用于 ref 解析失败时的 issue 诊断。

        覆盖三种常见 dep 输出形态：
        - list[dict]：取首元素的 keys（POI/WebSearch 输出的典型形态）
        - dict：取自身 keys（Condition 输出的典型形态）
        - 其他：返回类型名（标量或空 list）
        """
        if isinstance(data, list) and data:
            if isinstance(data[0], dict):
                keys = ", ".join(list(data[0].keys())[:5])
                return f"可用: {keys}"
            return f"list[{type(data[0]).__name__}, len={len(data)}]"
        if isinstance(data, dict):
            keys = ", ".join(list(data.keys())[:5])
            return f"可用: {keys}"
        return f"类型: {type(data).__name__}"

    @staticmethod
    def _resolve_with_diagnosis(
        data: Any, field_path: str
    ) -> Tuple[List[Any], Optional[str]]:
        """严格按 field_path 多层路径解析，返回 (values, failure_reason)。

        支持两种索引写法（等价，均不做穿透，单值返回）：
        - [N] 显式索引：'songs[0].song_name' → songs → [0] → song_name
        - N 数字 key：'0.url' → list[0] → url（兼容 $step_id.0.field 写法）

        每段路径都按直接 key 索引（不深度搜索同名 key），支持 list 穿透：
        若 current 元素是 list，遍历其中每个 dict 按 key 索引（key token）。
        index token（[N] 或数字 key token）显式索引 list 的第 N 个元素，不做穿透。

        成功时 failure_reason 为 None，values 为解析值列表（可能含多元素，
        对应 dep_data 中的多条记录）。
        失败时 values 为空列表，failure_reason 描述失败位置和可用字段，
        供 _build_unresolved_ref_issues 产出可操作的 PlanOptimizationIssue。

        解析策略：
        - 初始 current = [data]，逐段按 key 或 index 索引
        - key token: 非数字 → list 穿透 + dict key 索引；数字 → 按 list 整数索引
        - index token: 显式索引 list 第 N 个元素
        - 任一段无匹配即失败，返回具体失败原因：
          * 第一段 key 不存在 → 列出 dep_data 顶层可用字段
          * 第一段 index 应用于非 list 根 → 指出根类型
          * 中间 key 段遇到标量 → 指出父字段是 str/int 等标量，无法继续索引
          * 中间 key 段在 dict 内不存在 → 列出该 dict 的可用字段
          * 中间 index 段遇到非 list → 指出父字段类型，无法用索引访问
          * 中间 index 段越界 → 指出 list 长度与请求索引
        """
        # token 化：'songs[0].song_name' → [('key','songs'), ('index',0), ('key','song_name')]
        tokens: List[Tuple[str, Union[str, int]]] = []
        for m in _FIELD_PATH_TOKEN.finditer(field_path):
            if m.group(1) is not None:
                tokens.append(("index", int(m.group(1))))
            else:
                tokens.append(("key", m.group(2)))

        current: List[Any] = [data]
        path_so_far = ""

        for i, (kind, token) in enumerate(tokens):
            is_index = kind == "index"
            next_current: List[Any] = []
            for item in current:
                if is_index:
                    # index token：显式索引 list 第 N 个元素，不做穿透
                    if isinstance(item, list) and 0 <= token < len(item):
                        next_current.append(item[token])
                else:
                    # key token：list 穿透 + dict key 索引
                    # 兼容 $step_id.0.field：数字 key token 应用于 list 时按整数索引
                    # （等价于 [N] 显式索引，不做穿透，单值返回）
                    if isinstance(item, list):
                        if token.isdigit():
                            idx = int(token)
                            if 0 <= idx < len(item):
                                next_current.append(item[idx])
                        else:
                            for sub_item in item:
                                if isinstance(sub_item, dict) and token in sub_item:
                                    next_current.append(sub_item[token])
                    elif isinstance(item, dict) and token in item:
                        next_current.append(item[token])

            if not next_current:
                # 解析失败在这一段 — 收集诊断信息
                if i == 0:
                    if is_index:
                        return [], (
                            f"索引 [{token}] 无法应用于根数据"
                            f"（类型: {type(data).__name__}）"
                        )
                    # 数字 key token 应用于 list 根但越界
                    if token.isdigit() and isinstance(data, list):
                        return [], (
                            f"索引 {token} 越界（根数据是 list，长度 {len(data)}）"
                        )
                    # 提示根数据可用字段，供 LLM 据此修正 $ref 路径
                    # （如 $s2.genre 未解析时提示"可用: songs, playlists, albums"，
                    # LLM 可改为 $s2.songs[0].genre 或 $s2.songs.genre）
                    hint = DAGExecutor._describe_available_keys(data)
                    return [], f"字段 '{token}'（{hint}）"

                # 中间段失败
                if is_index:
                    non_list_items = [
                        item for item in current if not isinstance(item, list)
                    ]
                    if non_list_items:
                        sample = non_list_items[0]
                        sample_repr = str(sample)[:30]
                        return [], (
                            f"字段 '{path_so_far}' 是 {type(sample).__name__}"
                            f"（值: {sample_repr}），无法用索引 [{token}] 访问"
                        )
                    # 所有 item 都是 list 但都越界
                    sample_list = next(
                        item for item in current if isinstance(item, list)
                    )
                    return [], (
                        f"索引 [{token}] 越界（'{path_so_far}' 是 list"
                        f"，长度 {len(sample_list)}）"
                    )

                # key token 失败 — 数字 token 应用于 list 但越界（等价于 [N] 越界）
                if token.isdigit():
                    list_items = [item for item in current if isinstance(item, list)]
                    if list_items:
                        sample_list = list_items[0]
                        return [], (
                            f"索引 {token} 越界（'{path_so_far}' 是 list"
                            f"，长度 {len(sample_list)}）"
                        )
                # 非数字 key token 或数字 key token 应用于非 list 类型 — 区分标量 / dict 无此键
                non_dict_items = [
                    item for item in current if not isinstance(item, dict)
                ]
                if non_dict_items:
                    # 父字段是标量（如 business='龙华' 是 str），无法继续按 key 索引
                    sample = non_dict_items[0]
                    sample_repr = str(sample)[:30]
                    return [], (
                        f"字段 '{path_so_far}' 是 {type(sample).__name__}"
                        f"（值: {sample_repr}），无法继续解析 '{token}'"
                    )
                # 所有 item 都是 dict 但都没有 token 键
                sample_dict = next(item for item in current if isinstance(item, dict))
                available = ", ".join(list(sample_dict.keys())[:5])
                return (
                    [],
                    f"字段 '{path_so_far}.{token}' 不存在（{path_so_far} 内可用: {available}）",
                )

            # 更新 path_so_far（用于失败诊断）
            if is_index:
                path_so_far += f"[{token}]"
            else:
                path_so_far = f"{path_so_far}.{token}" if path_so_far else token
            current = next_current

        return current, None

    @staticmethod
    def _resolve_nested_field(data: Any, field_path: str) -> List[Any]:
        """解析多层 field 路径（如 result.action），逐层穿透 dict/list。

        向后兼容包装：调用 _resolve_with_diagnosis 并仅返回 values。
        新代码应直接调用 _resolve_with_diagnosis 以获取失败诊断。
        """
        values, _ = DAGExecutor._resolve_with_diagnosis(data, field_path)
        return values

    @staticmethod
    def _collect_refs(obj: Any, dep_outputs: Dict[str, Any]) -> Dict[str, List[Any]]:
        """扫描 obj 中所有 $step_id.field 和 $step_id 占位符，返回 {ref_str: [val1, val2, ...]}。

        同一 ref 只解析一次；dep 缺失或字段缺失时保留占位符原文。
        失败诊断信息（_resolve_with_diagnosis 返回的 failure_reason）不在此处保留，
        交由 _build_unresolved_ref_issues 在产出 issue 时按需重新诊断，避免在
        成功路径上携带无用信息。

        两种模式：
        - $step_id.field → 取 dep_outputs[step_id] 中 field 对应的值
        - $step_id（无 .field）→ 取 dep_outputs[step_id] 的所有字段，展开为 dict
        """
        seen: set = set()
        ref_values: Dict[str, List[Any]] = {}
        seen_dep_ids: set = (
            set()
        )  # M7：记录已被 $step_id.field 模式匹配的 dep_id，O(1) 跳过

        def _walk(v: Any) -> None:
            if isinstance(v, str):
                # 先匹配 $step_id.field（优先级高，避免被 $step_id 先吃掉）
                for m in _REF_PATTERN.finditer(v):
                    ref_str, dep_id, field = m.group(0), m.group(1), m.group(2)
                    if ref_str in seen:
                        continue
                    seen.add(ref_str)
                    seen_dep_ids.add(dep_id)  # M7：记录 field ref 已覆盖的 dep_id
                    dep_data = dep_outputs.get(dep_id)
                    if dep_data is None:
                        logger.warning(
                            f"占位符 {ref_str} 引用的依赖节点 {dep_id} 无输出"
                        )
                        ref_values[ref_str] = [ref_str]
                    else:
                        # M16：调用 _resolve_with_diagnosis 获取 (values, failure_reason)
                        # M18 修订：字段值为 None 是上游数据正常缺值（如 POI 无评分），
                        # 不应视为"未解析"触发 Plan 重试。区分三种情况：
                        # - 过滤 None 后有值 → 正常注入
                        # - failure_reason 为空但值全 None → 字段路径正确，用 [""] 替换
                        # - failure_reason 非空 → 字段路径不存在，保留占位符原文交 issue 诊断
                        values, failure_reason = DAGExecutor._resolve_with_diagnosis(
                            dep_data, field
                        )
                        non_none = [x for x in values if x is not None]
                        if non_none:
                            ref_values[ref_str] = non_none
                        elif failure_reason is None:
                            # 字段存在但值为 None：用空字符串替换，避免 List[str] 收到 None
                            # 触发 ValidationError，同时不产出 PlanOptimizationIssue（Plan 正确）
                            ref_values[ref_str] = [""]
                        else:
                            ref_values[ref_str] = [ref_str]

                # 再匹配 $step_id（无 .field），跳过已被 $step_id.field 匹配的
                for m in _BARE_REF_PATTERN.finditer(v):
                    ref_str, dep_id = m.group(0), m.group(1)
                    if ref_str in seen:
                        continue
                    # M7：O(1) 检查 — 该 dep_id 是否已被 field ref 覆盖（替代 O(n) 的 any+startswith）
                    if dep_id in seen_dep_ids:
                        continue
                    seen.add(ref_str)
                    dep_data = dep_outputs.get(dep_id)
                    if dep_data is None:
                        logger.warning(
                            f"占位符 {ref_str} 引用的依赖节点 {dep_id} 无输出"
                        )
                        ref_values[ref_str] = [ref_str]
                    else:
                        # 无 field 时，取 dep_data 整体作为单个值
                        ref_values[ref_str] = [dep_data]

            elif isinstance(v, dict):
                for x in v.values():
                    _walk(x)
            elif isinstance(v, list):
                for x in v:
                    _walk(x)

        _walk(obj)
        return ref_values

    @staticmethod
    def _build_unresolved_ref_issues(
        ref_values: Dict[str, List[Any]],
        node_id: Optional[str],
        dep_outputs: Dict[str, Any],
    ) -> List[PlanOptimizationIssue]:
        """从 _collect_refs 的输出检测未解析占位符，产出 PlanOptimizationIssue 列表

        判定规则：ref_values[ref] == [ref] 表示占位符被保留原文
        （_collect_refs 在 dep 缺失 / 字段路径导航失败 / 字段值为 None 时走 `or [ref_str]` 分支）。
        对每个未解析占位符，调用 _resolve_with_diagnosis 重新诊断失败原因，
        构造 HIGH 级 PlanOptimizationIssue（plan_issue_type=unresolved_placeholder），
        message 携带具体失败位置（哪一段字段不存在 / 中间值是标量无法继续 / dict 内无此键 / 字段值为 None）。

        M16：诊断细化 — 替代原"列出 dep_data 顶层 keys"的粗粒度描述：
        - 第一段不存在 → 列出 dep_data 顶层可用字段
        - 中间段遇到标量 → 指出父字段是 str/int 等标量及其值，无法继续索引
        - 中间段在 dict 内不存在 → 列出该 dict 的可用字段
        - 依赖无输出 → 记录依赖节点无输出的事实
        - 字段存在但值为 None → 明确记录"字段存在但值为 None"

        注：Issue 仅记录问题现象和上下文事实，不包含任何解决建议——
        应对策略由消费方（NodeParamOptimizer、外层 LLM）根据现象自行决定。
        """
        issues: List[PlanOptimizationIssue] = []
        for ref_str, values in ref_values.items():
            # 未解析：值列表仅含占位符原文
            if not (len(values) == 1 and values[0] == ref_str):
                continue
            dot_match = _REF_PATTERN.match(ref_str)
            if dot_match:
                dep_id, field_path = dot_match.group(1), dot_match.group(2)
                dep_data = dep_outputs.get(dep_id)
                if dep_data is None:
                    message = f"{ref_str} 未解析：依赖节点 {dep_id} 无输出"
                else:
                    _, failure_reason = DAGExecutor._resolve_with_diagnosis(
                        dep_data, field_path
                    )
                    if failure_reason is not None:
                        message = f"{ref_str} 未解析：{failure_reason}"
                    else:
                        message = (
                            f"{ref_str} 未解析：字段 '{field_path}' 存在但值为 None"
                        )
            else:
                bare_match = _SINGLE_BARE_REF.match(ref_str)
                if not bare_match:
                    continue
                dep_id = bare_match.group(1)
                message = f"{ref_str} 未解析：依赖节点 {dep_id} 无输出"
            issues.append(
                PlanOptimizationIssue(
                    severity=IssueSeverity.HIGH,
                    message=message,
                    node_id=node_id,
                    plan_issue_type="unresolved_placeholder",
                    affected_steps=[node_id] if node_id else [],
                )
            )
        return issues

    def _inject_deps(
        self,
        params: Dict[str, Any],
        dep_outputs: Dict[str, Any],
        node_id: Optional[str] = None,
        issue_report: Optional[IssueReport] = None,
    ) -> List[Dict[str, Any]]:
        """将节点入参中的 $step_id.field 和 $step_id 占位符替换为依赖节点的实际输出值。

        展开规则：
        - $step_id.field：同 dep 多字段按下标配对（zip），不同 dep 之间笛卡尔积；
        - $step_id（无 .field）：
          - 整个值就是 $step_id → 替换为 dep 输出的 dict；
          - $step_id 嵌入在字符串中 → 将 dep 输出的值拼接为可读字符串替换；
        - dep 缺失 / 字段缺失时保留占位符原文。

        支持的 $ref 写法（由 _resolve_with_diagnosis 统一解析）：
        - $step_id.field：取 dep 输出中所有记录的 field 字段（list 穿透）
        - $step_id：取 dep 输出整体
        - $step_id.[N].field：显式索引 list 第 N 个元素再取 field
        - $step_id.0.field：数字 key token 等价于 [N]，取 list 第 0 个元素再取 field

        Issue 产出（M14）：当传入 issue_report 时，检测保留原文的占位符，逐个产出
        PlanOptimizationIssue（plan_issue_type=unresolved_placeholder，severity=HIGH）
        汇入 issue_report。message 简短携带关键事实（占位符 / dep_id / 期望字段路径 / 实际可用字段）。
        node_id 与 issue_report 均为可选，未传时仅保留占位符原文（向后兼容现有测试）。

        注：Issue 仅记录问题现象，不包含解决建议。
        """
        ref_values = self._collect_refs(params, dep_outputs)
        if not ref_values:
            return [params]

        # M14：检测未解析占位符并产出 PlanOptimizationIssue，交 harness 层优化重试
        if issue_report is not None:
            for issue in self._build_unresolved_ref_issues(
                ref_values, node_id, dep_outputs
            ):
                issue_report.add(issue)

        # 所有 ref 统一走 _substitute_refs 替换
        # 按 dep_id 分组：{dep_id: [ref_str, ...]}
        dep_groups: Dict[str, List[str]] = {}
        for ref_str in ref_values:
            dot_match = _REF_PATTERN.match(ref_str)
            if dot_match:
                dep_id = dot_match.group(1)
            else:
                bare_match = _SINGLE_BARE_REF.match(ref_str)
                if not bare_match:
                    logger.warning(f"无法解析占位符引用: {ref_str}")
                    continue
                dep_id = bare_match.group(1)
            dep_groups.setdefault(dep_id, []).append(ref_str)

        # 为每个 dep_id 构建一个"轴"
        def build_axis(dep_id: str, ref_strs: List[str]) -> List[Dict[str, Any]]:
            max_len = max(len(ref_values[r]) for r in ref_strs)
            return [
                {
                    r: ref_values[r][i] if i < len(ref_values[r]) else ref_values[r][-1]
                    for r in ref_strs
                }
                for i in range(max_len)
            ]

        dep_axes = [build_axis(did, refs) for did, refs in dep_groups.items()]

        # 检查笛卡尔积总组合数是否超过上限
        total_combinations = 1
        for axis in dep_axes:
            total_combinations *= len(axis)
        if total_combinations > self.MAX_PARAM_COMBINATIONS:
            logger.warning(
                "参数笛卡尔积组合数超过上限 %d (当前 %d)，按贪心策略截断各轴",
                self.MAX_PARAM_COMBINATIONS,
                total_combinations,
            )
            # M6：贪心分配——按轴长度降序，从最长轴开始截断
            # 每个轴最多取 MAX_PARAM_COMBINATIONS // 其余轴乘积 个元素
            # 这样能保证最终总组合数 ≤ MAX_PARAM_COMBINATIONS，且尽量保留长轴的多样性
            indexed = sorted(enumerate(dep_axes), key=lambda x: len(x[1]), reverse=True)
            result_axes: List[Dict[str, Any]] = [None] * len(dep_axes)  # type: ignore
            for i, (orig_idx, ax) in enumerate(indexed):
                remaining_product = 1
                for j in range(i + 1, len(indexed)):
                    remaining_product *= len(indexed[j][1])
                max_take = max(
                    1, self.MAX_PARAM_COMBINATIONS // max(1, remaining_product)
                )
                take = min(len(ax), max_take)
                result_axes[orig_idx] = ax[:take]
            dep_axes = result_axes

        # 不同 dep 之间笛卡尔积，每组合并成完整 replacement 映射后替换
        return [
            self._substitute_refs(params, {k: v for m in combo for k, v in m.items()})
            for combo in product(*dep_axes)
        ]

    @staticmethod
    def _substitute_refs(
        params: Dict[str, Any], replacement: Dict[str, Any]
    ) -> Dict[str, Any]:
        """替换 params 中的 $ref 占位符

        - $step_id.field：直接替换为对应值
        - $step_id（bare ref）：若整个值就是 bare ref 且值为 dict，展开为 dict；
          若 bare ref 出现在字符串中间，将 dict 的值拼接为可读字符串替换
        """

        def _sub(value: Any) -> Any:
            if isinstance(value, str):
                # 整个值就是单个 bare ref，且值为 dict → 展开为 dict
                bare_match = _SINGLE_BARE_REF.match(value)
                if bare_match and value in replacement:
                    val = replacement[value]
                    if isinstance(val, dict):
                        return val
                    return val
                # 整个值就是单个 field ref → 直接替换
                if _SINGLE_REF.match(value) and value in replacement:
                    return replacement[value]
                # 字符串中包含 ref → 字符串替换
                result = value
                for ref, val in replacement.items():
                    if isinstance(val, dict):
                        # bare ref 在字符串中间，拼接为可读字符串
                        result = result.replace(
                            ref,
                            " ".join(
                                str(v)
                                for v in val.values()
                                if v is not None and v != "" and v != [] and v != {}
                            ),
                        )
                    else:
                        result = result.replace(ref, str(val))
                return result
            if isinstance(value, list):
                return [_sub(item) for item in value]
            if isinstance(value, dict):
                return {k: _sub(v) for k, v in value.items()}
            return value

        return {k: _sub(v) for k, v in params.items()}

    def _merge_condition_params(
        self,
        resolved_params: List[Dict[str, Any]],
        node_params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """合并 Condition 节点的笛卡尔积 resolved_params 为单条，facts 转为 List[Dict] 保留引用名。

        背景：_inject_deps 对多值占位符做笛卡尔积展开，Condition 节点会产生 N 条
        仅 facts 不同的 resolved_params。ConditionExecutor.execute 只取 params[0]，
        丢失 N-1 条数据。规则如"选评分最高的地面停车场"需要看到全部候选，因此合并。

        CONDITION 算子的 rules / default 不含 $ref 占位符，_inject_deps 只转换 facts
        中的占位符，因此所有条目的 rules / default 必然相同（不参与展开），无需校验，
        直接用首条即可；仅 facts 因笛卡尔积展开而不同，按位置配对合并为 List[Dict]。

        facts 转换：用 node_params["facts"] 中的 $ref 占位符提取引用名（去 $ 前缀），
        将每条 facts: List[str] 按位置配对为 Dict[str, str]，合并为 List[Dict]。
        单条 resolved_params 也转换，保证 facts 始终为 List[Dict]。

        引用名提取规则（优先级递降，按位置一一对应）：
        - 纯 field ref（$s1.weather.temperature）→ "s1.weather.temperature"
        - 纯 bare ref（$s1）→ "s1"
        - 标签 + ref（"气温: $s1.weather_temperature"）→ 取首个 ref 名 "s1.weather_temperature"
        - 无 ref 的字面量 → "fact_{index}" 兜底

        Args:
            resolved_params: _inject_deps 输出的已解析参数列表
            node_params: 原始 node.params（含 $ref 占位符，未解析）

        Returns:
            合并后的单元素列表 [merged_params]，保持 List[Dict] 接口不变
        """
        if not resolved_params:
            return resolved_params

        # 从原始 facts（含 $ref 占位符）提取引用名作为 dict key（位置一一对应）
        raw_facts = node_params.get("facts", [])
        ref_names: List[str] = []
        for idx, item in enumerate(raw_facts):
            if isinstance(item, str):
                m = _SINGLE_REF.match(item)
                if m:
                    ref_names.append(item[1:])
                    continue
                m = _SINGLE_BARE_REF.match(item)
                if m:
                    ref_names.append(item[1:])
                    continue
                m = _REF_PATTERN.search(item)
                if m:
                    ref_names.append(f"{m.group(1)}.{m.group(2)}")
                    continue
                m = _BARE_REF_PATTERN.search(item)
                if m:
                    ref_names.append(m.group(1))
                    continue
            ref_names.append(f"fact_{idx}")

        # rules / default 不含占位符，所有条目必然相同，直接用首条；仅 facts 按位置配对合并
        first = resolved_params[0]
        merged_facts: List[Dict[str, str]] = []
        for rp in resolved_params:
            facts_values = rp.get("facts", [])
            fact_dict: Dict[str, str] = {
                name: (str(val) if val is not None else "")
                for name, val in zip(ref_names, facts_values)
            }
            merged_facts.append(fact_dict)

        merged = {**first, "facts": merged_facts}
        return [merged]

    async def _execute_node(
        self,
        node: DAGNode,
        resolved_params: List[Dict[str, Any]],
        context: OperatorContext,
    ) -> OperatorResult:
        """执行单个 DAG 节点

        1. 从 OperatorRegistry 获取算子实例
        2. 构造 ExecutionContext（当前步骤信息 + 历史步骤摘要 + 全图状态）
        3. 调用算子 execute 方法（支持超时控制，anyio.fail_after）
        4. 异常不在此处捕获，自然抛出由 execute 循环的 Task 边界统一处理
           （符合 AGENTS.md 第 3 条"无捕获·全记录·直抛出"）
        """
        t0 = anyio.current_time()

        if node.operator is None:
            return OperatorResult(
                success=False,
            ).model_copy(
                update={
                    "error": f"节点 {node.node_id} 使用了未知算子类型",
                    "execution_time": round(anyio.current_time() - t0, 3),
                    "node_id": node.node_id,
                }
            )

        operator = OperatorRegistry.get_operator(node.operator.value)
        if not operator:
            return OperatorResult(
                success=False,
            ).model_copy(
                update={
                    "error": f"算子 {node.operator.value} 不在白名单中或未注册",
                    "execution_time": round(anyio.current_time() - t0, 3),
                    "node_id": node.node_id,
                }
            )

        # M3：用增量维护的 step_history，替代 O(n²) 的全量重建
        history = self.step_history

        exec_ctx = ExecutionContext(
            current_step=CurrentStepInfo(
                node_id=node.node_id,
                operator_type=node.operator.value,
            ).model_copy(
                update={
                    "step_goal": node.step_goal or "",
                    "step_output": list(node.step_output or []),
                    "dependencies": list(node.dependencies),
                    "params": list(resolved_params),
                }
            ),
        ).model_copy(
            update={
                "step_history": history,
                "step_goals": dict(self.step_goals),
                "results": dict(self.results),
                "snapshot_version": len(self.traces),
            }
        )

        node_context = context.model_copy(
            update={
                "metadata": {**context.metadata, "node_id": node.node_id},
                "execution_context": exec_ctx,
            }
        )

        # 异常不在此处捕获，自然抛出由 execute 循环的 Task 边界统一处理
        # anyio.fail_after 替代 asyncio.wait_for，超时抛 TimeoutError（asyncio.TimeoutError 别名）
        timeout = context.timeout.total_seconds() if context.timeout else None
        if timeout is not None:
            with anyio.fail_after(timeout):
                return await operator.execute(resolved_params, node_context)
        return await operator.execute(resolved_params, node_context)

    def _record_node_metrics(self, node_id: str, op_type: str) -> None:
        """D3：同步单节点执行统计到 self.metrics

        从 self.traces 读取最新 trace，构造 NodeMetrics 调用 self.metrics.add_node。
        覆盖语义：相同 node_id 多次记录以最后一次为准（DAGExecutor 重试时同一 node_id 会多次更新）。
        在 _record_node_result 末尾（成功/失败路径）和 execute 异常分支调用。
        """
        trace = self.traces.get(node_id)
        if trace is None:
            return
        duration = (
            trace.end_time - trace.start_time
            if trace.start_time is not None and trace.end_time is not None
            else 0.0
        )
        self.metrics.add_node(
            NodeMetrics(
                node_id=node_id,
                operator_type=op_type,
                duration_seconds=round(duration, 3),
                retry_count=trace.retry_count,
                status=trace.status,
            )
        )

    @staticmethod
    def _classify_exception_issue(
        exc: BaseException,
        tb_str: str,
        node_id: str,
        op_type: str,
        is_timeout: bool,
    ) -> BaseIssue:
        """C3：按异常类型分类产出合适的 Issue 子类

        asyncio.Task 异常边界的统一分类入口，替代原直接构造 ExceptionIssue 的逻辑。
        按 异常类型 + traceback 源模块 分派：

        - asyncio.TimeoutError → ExceptionIssue（保留 is_timeout 标识）
        - json.JSONDecodeError → ToolOutputParseIssue(parse_stage="json_loads")
        - pydantic.ValidationError → ToolOutputParseIssue(parse_stage="model_validate")
        - yaml.YAMLError → ToolOutputParseIssue(parse_stage="yaml_load")
        - TypeError/ValueError 且 traceback 含 "json" → SerializationIssue(serializer="json.dumps")
        - 其他 → ExceptionIssue（默认未预期异常）

        严重级别均为 HIGH（节点执行失败，不阻断 DAG 其他节点）。
        """
        # 超时异常优先保留 is_timeout 标识（原行为）
        if is_timeout:
            return ExceptionIssue(
                severity=IssueSeverity.HIGH,
                message=f"节点 {node_id} 执行超时: {type(exc).__name__}: {exc}",
                node_id=node_id,
                operator_type=op_type,
                exception_type=type(exc).__name__,
                traceback=tb_str,
            )

        # 工具输出解析失败 — JSON 解析
        if isinstance(exc, json.JSONDecodeError):
            return ToolOutputParseIssue(
                severity=IssueSeverity.HIGH,
                message=f"节点 {node_id} 工具输出 JSON 解析失败: {exc}",
                node_id=node_id,
                operator_type=op_type,
                exception_type=type(exc).__name__,
                raw_type="str",
                parse_stage="json_loads",
                traceback=tb_str,
            )

        # 工具输出解析失败 — Pydantic 模型校验
        if isinstance(exc, ValidationError):
            return ToolOutputParseIssue(
                severity=IssueSeverity.HIGH,
                message=f"节点 {node_id} 模型校验失败: {exc}",
                node_id=node_id,
                operator_type=op_type,
                exception_type=type(exc).__name__,
                raw_type="dict",
                parse_stage="model_validate",
                traceback=tb_str,
            )

        # 工具输出解析失败 — YAML 解析
        if isinstance(exc, yaml.YAMLError):
            return ToolOutputParseIssue(
                severity=IssueSeverity.HIGH,
                message=f"节点 {node_id} YAML 解析失败: {exc}",
                node_id=node_id,
                operator_type=op_type,
                exception_type=type(exc).__name__,
                raw_type="str",
                parse_stage="yaml_load",
                traceback=tb_str,
            )

        # 序列化失败 — TypeError/ValueError 且 traceback 源自 json 模块
        if isinstance(exc, (TypeError, ValueError)) and "json" in tb_str.lower():
            return SerializationIssue(
                severity=IssueSeverity.HIGH,
                message=f"节点 {node_id} 序列化失败: {exc}",
                node_id=node_id,
                operator_type=op_type,
                exception_type=type(exc).__name__,
                target_type="unknown",
                serializer="json.dumps",
                traceback=tb_str,
            )

        # 默认：未预期异常（保留原 ExceptionIssue 行为）
        return ExceptionIssue(
            severity=IssueSeverity.HIGH,
            message=f"节点 {node_id} 执行异常: {type(exc).__name__}: {exc}",
            node_id=node_id,
            operator_type=op_type,
            exception_type=type(exc).__name__,
            traceback=tb_str,
        )

    def _record_node_result(
        self,
        node_id: str,
        result: OperatorResult,
        issue_report: Optional[IssueReport] = None,
    ) -> None:
        """记录节点执行结果到 traces 和 results

        成功时：
        - 列表类型结果按算子元数据 dedup_fields 决定去重策略（M12：替代硬编码 op_type 判断）
        - 搜索类算子（is_search_operator=True）结果为空时产出 SearchStrategyIssue
          （M13：替代 endswith("_search") 判断）
        失败时：递增 retry_count，并产出 ExecutionIssue（若提供 issue_report）

        注：step_goal 校验已迁移至 `_validate_node_goal`（异步 LLM Validator，
        在本方法返回后由 `_validate_and_emit` 后台并行调用）。本方法不再做本地
        2-gram 校验，避免双重判定；trace 的 partial 状态由 `_validate_node_goal`
        在判定 goal_achieved=False 时降级设置。

        M5：node 和 op_type 在方法开头获取一次，复用，避免 4 次重复查找
        """
        # M5：方法开头获取一次 node / op_type / operator，复用
        node = self.dag_ir.nodes.get(node_id)
        op_type = node.operator.value if node and node.operator else "unknown"
        operator = (
            OperatorRegistry.get_operator(op_type) if node and node.operator else None
        )

        self.traces[node_id] = self.traces[node_id].model_copy(
            update={
                "end_time": anyio.current_time(),
                "output_data": result.data if result.success else None,
                "error": result.error if not result.success else None,
                "status": "success" if result.success else "failed",
                "retry_count": self.traces[node_id].retry_count
                + (0 if result.success else 1),
            }
        )

        # 失败时记入 issue_report（硬失败仍用 ExecutionIssue）
        if not result.success and issue_report is not None:
            issue_report.add(
                ExecutionIssue(
                    severity=IssueSeverity.HIGH,
                    message=f"节点 {node_id} 执行失败: {result.error or '未知错误'}",
                    node_id=node_id,
                    operator_type=op_type,
                    status="failed",
                    retry_count=self.traces[node_id].retry_count,
                    trace_id=node_id,
                )
            )

        if result.success and result.data is not None:
            # 写入时去重+截断，下游消费无需再处理
            # M12：由算子元数据 dedup_fields 决定去重策略，None 表示不去重（搜索类算子）
            if isinstance(result.data, list):
                dedup_fields = operator.dedup_fields if operator else ["address"]
                if dedup_fields is None:
                    self.results[node_id] = result.data
                else:
                    self.results[node_id] = self._deduplicate_records(
                        result.data, dedup_fields
                    )
            else:
                self.results[node_id] = result.data

            # 搜索结果质量检查：搜索类算子（is_search_operator=True）结果为空时产出 SearchStrategyIssue
            # step_goal 校验已迁移至 _validate_node_goal（异步 LLM 结构化校验，由 _validate_and_emit 后台并行调用），
            # 此处不再做本地 2-gram 校验，避免双重判定
            # M13：优先由算子元数据 is_search_operator 判断；
            # operator 缺失时回退到 op_type 后缀匹配（兜底，覆盖未注册算子）
            # 仅对 list 类型结果且搜索类算子生效，不混淆"失败"与"结果少"
            if issue_report is not None and isinstance(result.data, list):
                is_search = (
                    operator.is_search_operator
                    if operator is not None
                    else op_type.endswith("_search")
                )
                if is_search:
                    result_count = len(result.data)
                    if result_count == 0:
                        issue_report.add(
                            SearchStrategyIssue(
                                severity=IssueSeverity.MEDIUM,
                                message=f"节点 {node_id} 搜索结果为空",
                                node_id=node_id,
                                operator_type=op_type,
                                tool_type=op_type,
                                result_quality="none",
                                current_params=dict(node.params) if node else {},
                                retry_count=self.traces[node_id].retry_count,
                            )
                        )
        # M3：节点完成后增量追加到 step_history，避免每次 _execute_node 全量重建
        trace = self.traces[node_id]
        if trace.status in ("success", "partial", "failed"):
            entry = StepHistoryEntry(
                node_id=trace.node_id,
                operator_type=trace.operator_type,
            ).model_copy(
                update={
                    "step_goal": self.step_goals.get(node_id, ""),
                    "step_output": self.step_outputs.get(node_id, []),
                    "dependencies": list(self.step_deps.get(node_id, [])),
                    "status": trace.status,
                    "goal_achieved": (trace.status == "success"),
                    "output": self.results.get(node_id),
                }
            )
            self.step_history.append(entry)

        # D3：同步节点 metrics 到 self.metrics（成功/失败/partial 三种路径统一覆盖，
        # 异常路径在 execute 异常分支单独调用）。复用方法开头获取的 op_type，避免重复查找。
        self._record_node_metrics(node_id, op_type)

    async def _validate_node_goal(
        self,
        node_id: str,
        result: OperatorResult,
        issue_report: Optional[IssueReport] = None,
    ) -> None:
        """动态调用 Validator 算子，对搜索类算子节点做结构化目标验证。

        仅对 is_search_operator=True 且 trace.status="success" 的算子调用。
        用 ValidatorOutput BaseModel 做类型安全访问（符合 §7），缺必填字段
        goal_achieved 自然抛 ValidationError，由 _validate_and_emit Task 边界
        捕获为 ExceptionIssue，不再用 dict.get(goal_achieved, True) 静默当作达成。

        流程：
        1. 守卫：issue_report 为空 / trace 非成功 / 非搜索算子 → 直接返回
        2. 构造 ValidatorParams（downstream_nodes 从 DAGIR 计算）
        3. 构造 ExecutionContext（直接构造，无 model_copy）
        4. 通过 OperatorRegistry.get_operator("Validator") 动态获取算子
        5. 调用 operator.execute，ValidatorOutput.model_validate 重构 dict → BaseModel
        6. 按 goal_achieved 更新 trace.status（False → partial）
        7. ValidatorOutput 现象透传到 issue_report（→ harness 层），仅记录现象：
           仅 reasoning，不透传 confidence / improvements（符合 issues.py 设计原则）：
           - goal_achieved=False → StepGoalIssue（message 含 step_goal + reasoning）
           - goal_achieved=True 但 current_improvements 非空 → PlanOptimizationIssue
             （目标达成但产出有改进空间，message 含 reasoning）
           - downstream_improvements → 按 target node_id 分组产出 PlanOptimizationIssue
             （message 含受影响下游节点 + reasoning）

        异常不捕获，自然抛出由 execute 的 asyncio.Task 边界处理（符合第 3 节）。
        """
        # 守卫 1：issue_report 为空时无需产出 Issue，提前返回避免后续重复判空
        if issue_report is None:
            return
        # 守卫 2：仅对成功节点验证（失败节点已产出 ExecutionIssue）
        trace = self.traces.get(node_id)
        if trace is None or trace.status != "success":
            return
        # 守卫 3：仅搜索类算子需要 Validator 介入
        node = self.dag_ir.nodes.get(node_id)
        if node is None or node.operator is None:
            return
        op_type = node.operator.value
        operator = OperatorRegistry.get_operator(op_type)
        if operator is None or not operator.is_search_operator:
            return

        downstream_nodes = self._get_downstream_nodes(node_id)
        validator_params = [{"downstream_nodes": downstream_nodes}]

        exec_ctx = ExecutionContext(
            current_step=CurrentStepInfo(
                node_id=node.node_id,
                operator_type=op_type,
                step_goal=node.step_goal or "",
                step_output=list(node.step_output or []),
                dependencies=list(node.dependencies),
                params=list(trace.resolved_params or []),
            ),
            step_history=self.step_history,
            step_goals=dict(self.step_goals),
            results=dict(self.results),
            snapshot_version=len(self.traces),
        )
        validator_context = OperatorContext(
            request_id=node_id,
            metadata={"node_id": node_id},
            execution_context=exec_ctx,
        )

        validator = OperatorRegistry.get_operator("Validator")
        if validator is None:
            return
        validator_result = await validator.execute(validator_params, validator_context)
        validator_output = validator_result.data
        if validator_output is None:
            return

        # 用 ValidatorOutput BaseModel 做类型安全访问（符合 §7）。
        # validator_output 经 extract_data → _model_dump_by_title 转为 dict，
        # 此处 model_validate 重构为 BaseModel；缺必填字段 goal_achieved 自然抛
        # ValidationError，由 _validate_and_emit Task 边界捕获为 ExceptionIssue，
        # 不再用 dict.get(goal_achieved, True) 静默当作达成
        validated = (
            validator_output
            if isinstance(validator_output, ValidatorOutput)
            else ValidatorOutput.model_validate(validator_output)
        )

        reasoning = validated.reasoning
        # 构造现象描述（仅 reasoning），不透传 confidence / improvements
        # 符合 issues.py 设计原则：Issue 仅记录现象，不包含建议或优化方案
        phenomenon_desc = f"判断依据={reasoning}" if reasoning else ""

        # goal_achieved=False → 标记 partial 并产出 StepGoalIssue
        # message 仅记录未达成现象（step_goal + reasoning），不透传 confidence / 改进点
        if not validated.goal_achieved:
            self.traces[node_id] = self.traces[node_id].model_copy(
                update={
                    "status": "partial",
                    "error": f"步骤目标未达成(Validator): {self.step_goals.get(node_id, '')}",
                }
            )
            unmet_goal = self.step_goals.get(node_id, "")
            msg_parts = [f"节点 {node_id} 步骤目标未达成(Validator): {unmet_goal}"]
            if phenomenon_desc:
                msg_parts.append(phenomenon_desc)
            issue_report.add(
                StepGoalIssue(
                    severity=IssueSeverity.MEDIUM,
                    message=" | ".join(msg_parts),
                    node_id=node_id,
                    operator_type=op_type,
                    step_goal=unmet_goal,
                )
            )
        elif validated.current_improvements:
            # goal_achieved=True 但 improvements 非空 → PlanOptimizationIssue
            # message 仅记录现象（reasoning），不透传 confidence / 改进点描述
            msg_parts = [f"节点 {node_id} 目标达成但产出有改进空间"]
            if phenomenon_desc:
                msg_parts.append(phenomenon_desc)
            issue_report.add(
                PlanOptimizationIssue(
                    severity=IssueSeverity.MEDIUM,
                    message=" | ".join(msg_parts),
                    node_id=node_id,
                    operator_type=op_type,
                    affected_steps=[node_id],
                    plan_issue_type="output_improvement",
                )
            )

        # downstream_improvements → 按 node_id 分组产出 PlanOptimizationIssue
        # message 仅记录下游节点 + 现象（reasoning），不透传 confidence / 改进点
        if validated.downstream_improvements:
            grouped: Dict[str, List[Any]] = {}
            for imp in validated.downstream_improvements:
                target_nid = imp.node_id
                if target_nid:
                    grouped.setdefault(target_nid, []).append(imp)
            for target_nid in grouped:
                msg_parts = [f"节点 {node_id} 产出影响下游节点 {target_nid}"]
                if phenomenon_desc:
                    msg_parts.append(phenomenon_desc)
                issue_report.add(
                    PlanOptimizationIssue(
                        severity=IssueSeverity.MEDIUM,
                        message=" | ".join(msg_parts),
                        node_id=node_id,
                        operator_type=op_type,
                        affected_steps=[target_nid],
                        plan_issue_type="downstream_blocker",
                    )
                )

    @staticmethod
    def _node_progress_percent(status: str) -> int:
        if status in ("success", "partial", "failed", "skipped", "cancelled"):
            return 100
        if status == "running":
            return 45
        if status == "cancelling":
            return 88
        return 0

    def _render_graph_statuses(self) -> Dict[str, str]:
        return {nid: trace.status for nid, trace in self.traces.items()}

    def _render_graph_results(self) -> Dict[str, Any]:
        return {
            nid: trace.output_data
            if trace.output_data is not None
            else self.results.get(nid)
            for nid, trace in self.traces.items()
            if (
                trace.output_data
                if trace.output_data is not None
                else self.results.get(nid)
            )
            is not None
        }

    def _render_graph_errors(self) -> Dict[str, str | None]:
        return {nid: trace.error for nid, trace in self.traces.items() if trace.error}

    def _render_graph_progress(self) -> Dict[str, int]:
        return {
            nid: self._node_progress_percent(trace.status)
            for nid, trace in self.traces.items()
        }

    def _render_graph_arguments(self) -> Dict[str, Any]:
        arguments: Dict[str, Any] = {}
        for node_id, trace in self.traces.items():
            if trace.resolved_params:
                arguments[node_id] = trace.resolved_params
            elif trace.params:
                arguments[node_id] = trace.params
        return arguments

    def render_graph_snapshot(self) -> Dict[str, Any]:
        """聚合渲染图快照（公开接口，替代外部访问 _render_graph_* 私有方法）。

        返回 build_dag_render_graph 所需的全部字段：
        statuses / results / errors / progress_per_node / arguments
        """
        return {
            "statuses": self._render_graph_statuses(),
            "results": self._render_graph_results(),
            "errors": self._render_graph_errors(),
            "progress_per_node": self._render_graph_progress(),
            "arguments": self._render_graph_arguments(),
        }

    async def _emit_node_snapshot(self, node_id: str) -> None:
        trace = self.traces.get(node_id)
        if trace is None:
            return

        await emit_dag_frame(
            DAGRenderFrame(
                phase="execution",
                message=f"DAG节点 {node_id} 状态: {trace.status}",
                progress_percent=self._execution_progress_percent(),
                graph=build_dag_render_graph(
                    self.dag_ir,
                    statuses=self._render_graph_statuses(),
                    results=self._render_graph_results(),
                    errors=self._render_graph_errors(),
                    progress_per_node=self._render_graph_progress(),
                    arguments=self._render_graph_arguments(),
                ),
                active_node_id=node_id,
                status=trace.status,
            )
        )

    async def execute(
        self, context: OperatorContext, issue_report: Optional[IssueReport] = None
    ) -> Dict[str, Any]:
        """并行执行 DAG 中所有节点的执行循环（anyio 结构化并发）。

        调度策略：
        1. 收集所有就绪节点（依赖全部成功、自身未完成），按链长+fan-out 优先级排序
        2. 在 anyio.create_task_group 内为就绪节点启动并行 worker
        3. 通过 anyio.create_memory_object_stream 事件驱动接收节点完成通知
        4. 处理结果/异常后，启动新就绪节点（增量调度）
        5. 重复直到所有节点完成或达到 max_loops

        异常隔离：worker 内 Task 边界捕获异常存入 _task_exceptions（与 amap.py 一致），
        不抛出以避免 anyio TaskGroup 取消其他任务；主循环从 _task_exceptions 读取并记入 IssueReport。

        Args:
            context: 算子执行上下文
            issue_report: 统一 Issue 报告容器，各阶段产生的 ExecutionIssue 通过引用汇入此容器。
                          若为 None 则内部创建（调用方无法获取，建议显式传入）。
        """
        # 确保 issue_report 可用（调用方未提供时内部创建）
        if issue_report is None:
            issue_report = IssueReport()

        # 为每个 node 初始化一条 pending trace
        for node_id in list(self.dag_ir.nodes.keys()):
            if node_id not in self.traces:
                node = self.dag_ir.nodes[node_id]
                self.traces[node_id] = ExecutionTrace(
                    node_id=node_id,
                    operator_type=node.operator.value if node.operator else "unknown",
                    params=node.params,
                ).model_copy(
                    update={
                        "status": "pending",
                    }
                )

        # anyio 事件流：节点完成通知（0 缓冲，保证即时通知）
        send_stream, receive_stream = anyio.create_memory_object_stream(0)
        # Task 边界异常与结果隔离容器（单线程 asyncio 内无竞态）
        task_exceptions: Dict[str, BaseException] = {}
        task_results: Dict[str, OperatorResult] = {}
        started_nodes: set = set()  # 已启动节点集合，替代 running_tasks 的去重作用
        running_count = 0
        # max_loops 与节点数动态关联：每个节点最多执行 (1 + MAX_RETRIES) 次，再加 2 轮余量
        max_loops = max(len(self.dag_ir.nodes) * (1 + self.MAX_RETRIES) + 2, 10)
        loops = 0

        async def run_node(
            node_id: str, node: DAGNode, resolved_params: List[Dict[str, Any]]
        ) -> None:
            """Task 边界 worker：发送 running 快照 → 执行节点 → 存结果/异常 → 通知主循环。

            异常隔离与 aicore/utils/anyio/amap.py worker 一致：捕获后存入 task_exceptions，
            不抛出（避免 anyio TaskGroup 取消其他任务）。
            """
            try:
                # 发送 running 状态快照（trace 已在 _prepare_and_start 内更新为 running）
                await self._emit_node_snapshot(node_id)
                result = await self._execute_node(node, resolved_params, context)
                task_results[node_id] = result
            except BaseException as exc:  # noqa: BLE001 — Task 边界，非业务捕获
                task_exceptions[node_id] = exc
            finally:
                await send_stream.send(node_id)

        def _prepare_and_start(node_id: str, tg: anyio.abc.TaskGroup) -> bool:
            """构造 resolved_params 并启动 worker。返回是否实际启动。"""
            if node_id in started_nodes:
                return False
            node = self.dag_ir.nodes[node_id]

            # 缓存元信息，用于 step_history 构造
            if node.step_goal:
                self.step_goals[node_id] = node.step_goal
            if node.step_output:
                self.step_outputs[node_id] = list(node.step_output)
            if node.dependencies:
                self.step_deps[node_id] = list(node.dependencies)

            dep_outputs = {
                dep_id: self.results[dep_id]
                for dep_id in node.dependencies
                if dep_id in self.results
            }
            # 传入 node_id 与 issue_report：未解析占位符由 _inject_deps 产出
            # PlanOptimizationIssue（M14），交 harness 层与外层 React Agent 优化重试
            resolved_params = self._inject_deps(
                node.params,
                dep_outputs,
                node_id=node_id,
                issue_report=issue_report,
            )

            # Condition 节点：合并笛卡尔积 resolved_params 为单条，facts 转为 List[Dict]
            # 保留引用名（如 s1.weather.weather_temperature），让 LLM 看到全部候选
            if node.operator == OperatorType.CONDITION:
                resolved_params = self._merge_condition_params(
                    resolved_params, node.params
                )

            # 兜底日志：resolved_params 仍含未替换 $ 占位符时记录（Issue 已由 _inject_deps 产出）
            if any(
                isinstance(v, str) and _BARE_REF_PATTERN.search(v)
                for pd in resolved_params
                for v in pd.values()
            ):
                logger.warning(
                    "resolved_params 包含未替换的 $ 占位符 | node_id=%s | node.params=%s | dep_outputs=%s | resolved_params=%s",
                    node_id,
                    node.params,
                    dep_outputs,
                    resolved_params,
                )
            self.traces[node_id] = self.traces[node_id].model_copy(
                update={
                    "status": "running",
                    "start_time": anyio.current_time(),
                    "resolved_params": resolved_params,
                }
            )
            started_nodes.add(node_id)
            tg.start_soon(run_node, node_id, node, resolved_params)
            return True

        async def _validate_and_emit(
            node_id: str, result: OperatorResult, issue_report: IssueReport
        ) -> None:
            """Task 边界 worker：并行执行 Validator 验证 + emit 快照，不阻塞主循环。

            将 _validate_node_goal + _emit_node_snapshot 从主循环 await 改为后台并行，
            避免 Validator LLM 调用（1-3 秒）阻塞主循环接收其他节点完成通知。

            安全性：
            - _record_node_result（同步）已设 trace.status="success"，
              下游 _pick_ready_nodes 据此判定可调度
            - _validate_node_goal 可能将 "success" 降级为 "partial"，
              但 "partial" 同样视为"完成"，不影响下游调度
            - IssueReport.add 是同步方法（无 await），单线程 asyncio 下并发安全

            异常隔离与 run_node 一致：捕获后记录到 issue_report + logger，不抛出
            （避免 anyio TaskGroup 取消其他任务）。Validator 异常不阻断 DAG 流程
            （节点已成功），作为 ExceptionIssue 汇入统一出口。
            """
            try:
                await self._validate_node_goal(node_id, result, issue_report)
                await self._emit_node_snapshot(node_id)
            except BaseException as exc:  # noqa: BLE001 — Task 边界，非业务捕获
                tb_str = "".join(
                    traceback_module.format_exception(type(exc), exc, exc.__traceback__)
                )
                logger.error(f"节点 {node_id} Validator 验证异常: {exc}\n{tb_str}")
                exc_type_name = type(exc).__name__
                exc_msg = f"节点 {node_id} Validator 异常: {exc_type_name}: {exc}"
                issue_report.add(
                    ExceptionIssue(
                        severity=IssueSeverity.MEDIUM,
                        message=exc_msg,
                        node_id=node_id,
                        operator_type="Validator",
                        exception_type=exc_type_name,
                        traceback=tb_str,
                    )
                )

        async with anyio.create_task_group() as tg:
            # 启动初始就绪节点
            for node_id in self._pick_ready_nodes(issue_report):
                if _prepare_and_start(node_id, tg):
                    running_count += 1

            # 事件驱动调度循环
            while running_count > 0 and loops < max_loops:
                loops += 1
                node_id = await receive_stream.receive()
                running_count -= 1

                # 处理异常（Task 边界已隔离）
                exc = task_exceptions.pop(node_id, None)
                if exc is not None:
                    tb_str = "".join(
                        traceback_module.format_exception(
                            type(exc), exc, exc.__traceback__
                        )
                    )
                    logger.error(f"节点 {node_id} 执行异常: {exc}\n{tb_str}")
                    exc_node = self.dag_ir.nodes.get(node_id)
                    op_type = (
                        exc_node.operator.value
                        if exc_node and exc_node.operator
                        else "unknown"
                    )
                    # 超时异常单独标识（anyio.fail_after 抛 TimeoutError，asyncio.TimeoutError 别名）
                    is_timeout = isinstance(exc, asyncio.TimeoutError)
                    # C3：按异常类型分类产出 Issue 子类
                    issue_report.add(
                        self._classify_exception_issue(
                            exc=exc,
                            tb_str=tb_str,
                            node_id=node_id,
                            op_type=op_type,
                            is_timeout=is_timeout,
                        )
                    )
                    # 记录失败的 trace
                    if node_id in self.traces:
                        self.traces[node_id] = self.traces[node_id].model_copy(
                            update={
                                "status": "failed",
                                "error": str(exc),
                                "end_time": anyio.current_time(),
                                "retry_count": self.traces[node_id].retry_count + 1,
                            }
                        )
                    # D3：同步异常路径的节点 metrics
                    self._record_node_metrics(node_id, op_type)
                    await self._emit_node_snapshot(node_id)
                else:
                    # 正常完成：取出结果并记录
                    result = task_results.pop(node_id, None)
                    # 仅当节点仍在当前 DAG 中时记录结果（可能被重建移除）
                    if node_id in self.dag_ir.nodes:
                        # _record_node_result 同步完成（trace.status → success），
                        # 下游 _pick_ready_nodes 据此判定可调度
                        self._record_node_result(node_id, result, issue_report)
                        # Validator + emit 后台并行，不阻塞主循环
                        # 接收其他节点完成通知
                        # Validator 仅将 success 降级为 partial，
                        # 同样视为完成，不影响下游调度
                        tg.start_soon(_validate_and_emit, node_id, result, issue_report)
                    else:
                        self.traces.pop(node_id, None)
                        logger.info(f"节点 {node_id} 已不在当前 DAG 中，跳过结果记录")

                # 启动新就绪节点（增量调度）
                for new_node_id in self._pick_ready_nodes(issue_report):
                    if _prepare_and_start(new_node_id, tg):
                        running_count += 1

        if loops >= max_loops:
            logger.warning(
                f"DAGExecutor.execute 达到最大循环次数 {max_loops}，可能有 executor 持续修改 plan。"
            )
        return self.results

    def _execution_progress_percent(self) -> int:
        total = max(len(self.dag_ir.nodes), 1)
        completed = sum(
            1
            for trace in self.traces.values()
            if trace.status in ("success", "partial", "skipped", "failed")
        )
        return min(95, 40 + int(completed / total * 55))
