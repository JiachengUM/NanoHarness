"""算子基类定义 - V2

集中管理所有算子和执行器的基类，避免循环依赖
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
import anyio
import logging
import re
from typing import Dict, Any, Type, Optional, List, Tuple, Callable
from functools import wraps

from pydantic import BaseModel, Field, ConfigDict

from aicore.tools.dag.operator_models import BaseSchema
from aicore.tools.dag.issues import (
    SafetyIssue,  # noqa: F401 — re-export for __init__.py backward compat
    IssueReport,
    ContradictionIssue,
    IssueSeverity,
)
from aicore.tools.dag.dag_metrics import DagMetrics

logger = logging.getLogger(__name__)

# $ref 占位符正则 — 匹配 $step_id.field 或 $step_id.field[N].subfield 嵌套路径
# 跨模块共享：dag_executor（运行时依赖注入）+ plan_generator（静态 $ref 校验）
_REF_PATTERN = re.compile(r"\$(\w+)\.([\w.\[\]]+)")


# ── DAG IR 模型 ──────────────────────────────────────────────────────────


class OperatorType(str, Enum):
    """算子类型枚举 — 所有已注册的原子能力标识（PascalCase 命名，与 LLM 自然输出对齐）"""

    POI_SEARCH = "POISearch"
    SONG_SEARCH = "SongSearch"
    PLAYLIST_SEARCH = "PlaylistSearch"
    ALBUM_SEARCH = "AlbumSearch"
    WEB_SEARCH = "WebSearch"
    NAVIGATION = "Navigation"
    CAR_CONTROL = "CarControl"
    AUDIO_PLAY = "AudioPlay"
    CONDITION = "Condition"
    MEMORY_RECALL = "MemoryRecall"
    VALIDATOR = "Validator"


def _normalize_step_output(raw: Any) -> List[str]:
    """把 step_output 归一化为 List[str]。

    支持以下来源：
    - None / 空字符串 -> []
    - str（可能是逗号/分号/空白分隔的多个字段） -> 按分隔符拆分并去空格
    - list / tuple -> 逐项做 str() / Enum.value 规范化
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        if not raw.strip():
            return []
        tokens: List[str] = []
        for part in raw.replace(";", ",").split(","):
            token = part.strip()
            if token:
                tokens.append(token)
        return tokens
    if isinstance(raw, (list, tuple)):
        result: List[str] = []
        for item in raw:
            if item is None:
                continue
            if isinstance(item, Enum):
                token = str(item.value)
            else:
                token = str(item)
            token = token.strip()
            if token:
                result.append(token)
        return result
    return _normalize_step_output(str(raw))


def _collect_nested_field_paths(raw: Any, prefix: str = "") -> List[str]:
    """从 step_output 序列化结构中递归提取所有字段路径（含嵌套路径）。

    嵌套 dict（对应嵌套 BaseModel）会被递归展开，同时保留父路径（如 business）
    和嵌套路径（如 business.parking_type），让下游 $ref 既能引用整个嵌套对象
    （$s2.business），也能引用嵌套子字段（$s2.business.parking_type）。

    支持三种来源：
    - dict：递归提取所有字段路径（顶层 + 嵌套）
    - list：兼容 LLM 偶尔生成 list 的情况，逐项提取（dict 递归 / str 直接保留）
    - str：直接作为单个路径保留
    - None / 其他：返回空列表
    """
    paths: List[str] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            current_path = f"{prefix}.{k}" if prefix else k
            paths.append(current_path)  # 保留父路径，让 $ref 能引用整个嵌套对象
            if isinstance(v, dict):
                paths.extend(_collect_nested_field_paths(v, current_path))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                paths.extend(_collect_nested_field_paths(item))
            elif isinstance(item, str):
                paths.append(item)
    elif isinstance(raw, str):
        paths.append(raw)
    return paths


def detect_cycle(adj: Dict[str, List[str]]) -> List[str]:
    """DFS 三色标记法检测有向图中的循环依赖

    Args:
        adj: 邻接表 {node_id: [dep_id, ...]}

    Returns:
        若存在循环，返回构成环的节点列表（如 [s2, s3, s1, s2]）；
        无环时返回空列表。

    说明：
        - WHITE (0): 未访问
        - GRAY (1): 当前 DFS 路径中
        - BLACK (2): 已完成访问
        - 若在 GRAY 状态的节点上遇到 GRAY 依赖，则存在环
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {nid: WHITE for nid in adj}
    path: List[str] = []

    def _dfs(node_id: str) -> List[str]:
        color[node_id] = GRAY
        path.append(node_id)
        for dep in adj.get(node_id, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == WHITE:
                cycle = _dfs(dep)
                if cycle:
                    return cycle
        color[node_id] = BLACK
        path.pop()
        return []

    for nid in adj:
        if color[nid] == WHITE:
            cycle = _dfs(nid)
            if cycle:
                return cycle
    return []


class DAGNode(BaseSchema):
    """DAG 节点 — 对应 Plan 中的一个步骤

    每个节点绑定一个算子（operator），携带入参（params）和依赖列表（dependencies）。
    step_goal 用于执行后校验步骤是否达成预期；step_output 声明本节点输出的字段名列表，
    供下游节点通过 $step_id.field 占位符引用。
    """

    node_id: str = Field(description="节点唯一标识")
    operator: Optional[OperatorType] = Field(default=None, description="算子类型")
    params: Dict[str, Any] = Field(default_factory=dict, description="算子参数")
    dependencies: List[str] = Field(default_factory=list, description="依赖的节点ID")
    step_goal: Optional[str] = Field(
        default=None,
        description="本步骤的小目标，是总goal的子集，用于后续检查步骤是否达成",
    )
    step_output: List[str] = Field(
        default_factory=list,
        description="本步骤的出参列表（从算子输出字段中选择，可以多个）",
    )


class DAGIR(BaseSchema):
    """DAG 中间表示 — 从 Plan 构建的可执行有向无环图

    nodes: 全部节点的字典 {node_id: DAGNode}
    entry_nodes: 无依赖的入口节点（拓扑排序起点）
    exit_nodes: 无下游的出口节点（最终结果产出者）
    topological_order: 属性方法，Kahn 算法计算拓扑序，循环依赖时抛异常
    from_plan: 类方法，从 Plan 字典构建 DAGIR 实例
    """

    goal: str = Field(description="目标描述")
    nodes: Dict[str, DAGNode] = Field(default_factory=dict, description="节点集合")
    entry_nodes: List[str] = Field(default_factory=list, description="入口节点ID列表")
    exit_nodes: List[str] = Field(default_factory=list, description="出口节点ID列表")

    @classmethod
    def from_plan(cls, plan: Dict[str, Any]) -> "DAGIR":
        """从 Plan 字典构建 DAGIR 实例

        遍历 plan.steps，将每个 step 映射为 DAGNode，
        同时计算 entry_nodes（无依赖）和 exit_nodes（无下游）。

        结构错误（缺 step_id / 缺 op）自然抛出 ValueError，保持底层快速失败语义。
        如需 issue 化处理，请使用 from_plan_with_issues。
        """
        dag_ir, issues = cls._build_plan(plan)
        if issues:
            # 结构错误自然抛出，保持 from_plan 的原有契约（底层快速失败）
            raise ValueError("; ".join(i.message for i in issues))
        return dag_ir

    @classmethod
    def from_plan_with_issues(
        cls, plan: Dict[str, Any]
    ) -> Tuple[Optional["DAGIR"], List[ContradictionIssue]]:
        """从 Plan 字典构建 DAGIR 实例，结构错误转为 ContradictionIssue 而非 raise

        供 plan_processor._build_dag_ir 调用，将 dag_build 阶段的结构错误
        通过 IssueReport 统一出口返回，与 validation/safety_scan/execution 阶段一致。

        Returns:
            (dag_ir, issues): 无错误时 dag_ir 为有效实例、issues 为空；
                              有错误时 dag_ir 为 None、issues 非空。
        """
        return cls._build_plan(plan)

    @classmethod
    def _build_plan(
        cls, plan: Dict[str, Any]
    ) -> Tuple[Optional["DAGIR"], List[ContradictionIssue]]:
        """Plan 字典构建 DAGIR 的核心逻辑，结构错误收集为 ContradictionIssue

        被 from_plan 和 from_plan_with_issues 共同复用，避免逻辑重复。
        """
        goal = plan.get("goal", "")
        nodes: Dict[str, DAGNode] = {}
        entry_nodes: List[str] = []
        issues: List[ContradictionIssue] = []

        for step in plan.get("steps", []):
            step_id = step.get("step_id")
            if not step_id:
                issues.append(
                    ContradictionIssue(
                        severity=IssueSeverity.CRITICAL,
                        stage="dag_build",
                        message=f"步骤缺少 step_id 字段（原始 step: {step}）",
                        check_name="missing_step_id",
                    )
                )
                continue

            operator_type = step.get("op") or step.get("operator")
            if not operator_type:
                issues.append(
                    ContradictionIssue(
                        severity=IssueSeverity.CRITICAL,
                        stage="dag_build",
                        message=f"步骤 {step_id} 缺少 op 或 operator 字段（原始 step: {step}）",
                        check_name="missing_operator",
                        node_id=step_id,
                    )
                )
                continue

            operator_enum = None
            if operator_type in OperatorType._value2member_map_:
                operator_enum = OperatorType(operator_type)

            # step_input（step_input 序列化后的 dict）转为 DAGNode.params（dict）
            # 供 DAGExecutor._inject_deps 做 $ref 占位符替换
            step_input_raw = step.get("step_input", {})
            params: Dict[str, Any] = {}
            if isinstance(step_input_raw, dict):
                params = step_input_raw
            elif isinstance(step_input_raw, list):
                # 兼容 LLM 偶尔生成 list 的情况
                for inp in step_input_raw:
                    if isinstance(inp, dict):
                        params.update(inp)

            # step_output（step_output 序列化后的 dict）提取字段路径列表
            # 递归提取嵌套路径（如 business.parking_type），让下游 $ref 能按多层路径引用
            # 供 DAGExecutor 构建 CurrentStepInfo / StepHistoryEntry（LLM prompt 展示 + 依赖声明）
            step_output_raw = step.get("step_output", {})
            step_output_fields: List[str] = _collect_nested_field_paths(step_output_raw)

            node = DAGNode(
                node_id=step_id,
            ).model_copy(
                update={
                    "operator": operator_enum,
                    "params": params,
                    "dependencies": list(step.get("depends_on", []) or []),
                    "step_goal": step.get("step_goal"),
                    "step_output": step_output_fields,
                }
            )
            nodes[step_id] = node

            if not step.get("depends_on"):
                entry_nodes.append(step_id)

        # 有结构错误时不构建 DAGIR，避免下游处理不完整数据
        if issues:
            return None, issues

        all_dependencies: set = set()
        for node in nodes.values():
            all_dependencies.update(node.dependencies)
        exit_nodes = [node_id for node_id in nodes if node_id not in all_dependencies]

        return cls(
            goal=goal,
            nodes=nodes,
            entry_nodes=entry_nodes,
            exit_nodes=exit_nodes,
        ), []

    @property
    def topological_order(self) -> List[str]:
        """Kahn 算法计算拓扑排序。若存在循环依赖则抛出 ValueError。"""
        from collections import deque

        in_degree = {
            node_id: len(node.dependencies) for node_id, node in self.nodes.items()
        }
        # 预建邻接表：dep_id -> [依赖它的节点列表]
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep in adj:
                    adj[dep].append(nid)
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            for target in adj[node_id]:
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)

        if len(result) != len(self.nodes):
            raise ValueError("DAG存在循环依赖")
        return result


# ── 执行轨迹 ─────────────────────────────────────────────────────────────


class ExecutionTrace(BaseSchema):
    """DAG 节点执行轨迹"""

    node_id: str = Field(description="节点ID")
    operator_type: str = Field(description="算子类型")
    params: Dict[str, Any] = Field(default_factory=dict, description="输入参数")
    resolved_params: List[Dict[str, Any]] = Field(
        default_factory=list, description="解析后的参数列表（占位符多值展开）"
    )
    output_data: Any = Field(default=None, description="输出数据")
    error: Optional[str] = Field(default=None, description="错误信息")
    start_time: Optional[float] = Field(default=None, description="开始时间")
    end_time: Optional[float] = Field(default=None, description="结束时间")
    status: str = Field(
        default="pending",
        description="执行状态: pending/running/success/failed/partial（partial表示执行成功但未达成步骤目标）",
    )
    retry_count: int = Field(default=0, description="已重试次数")


class CurrentStepInfo(BaseSchema):
    """当前正在执行的步骤信息 - 字段命名与 PlanStep / DAGNode 保持同步

    字段映射：
    - node_id         ↔ PlanStep.step_id / DAGNode.node_id
    - operator_type   ↔ PlanStep.op      / DAGNode.operator
    - step_goal       ↔ PlanStep.step_goal / DAGNode.step_goal
    - step_output     ↔ PlanStep.step_output / DAGNode.step_output（List[str]，字段列表）
    - dependencies    ↔ PlanStep.depends_on / DAGNode.dependencies
    - params          ↔ PlanStep.step_input / DAGNode.params（占位符展开后的实参）
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    node_id: str = Field(description="当前节点ID")
    operator_type: str = Field(description="算子类型")
    step_goal: str = Field(default="", description="本步骤的小目标")
    step_output: List[str] = Field(
        default_factory=list,
        description="本步骤的出参列表（从算子输出字段中选择，可以多个）",
    )
    dependencies: List[str] = Field(default_factory=list, description="依赖节点ID列表")
    params: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="实参列表（占位符展开后），与 _inject_deps 输出对齐",
    )


class StepHistoryEntry(BaseSchema):
    """已完成步骤的执行摘要，供下游算子感知上下文

    字段与 PlanStep / CurrentStepInfo 保持完全同步，新增 status / output / goal_achieved。
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    node_id: str = Field(description="节点ID")
    operator_type: str = Field(description="算子类型")
    step_goal: str = Field(default="", description="步骤小目标")
    step_output: List[str] = Field(default_factory=list, description="本步骤的出参列表")
    dependencies: List[str] = Field(default_factory=list, description="依赖节点ID列表")
    status: str = Field(default="", description="success/failed/skipped/partial")
    goal_achieved: bool = Field(default=False, description="step_goal 是否达成")
    output: Optional[Any] = Field(
        default=None,
        description="节点输出数据（与算子 output_model 对齐的实际形态，POI/WebSearch 为 list，其他为 dict）",
    )


class ExecutionContext(BaseSchema):
    """步骤执行上下文，与 OperatorContext 解耦，仅承载步骤/历史信息"""

    model_config = ConfigDict(frozen=True, extra="ignore")

    current_step: CurrentStepInfo = Field(description="当前步骤信息")
    step_history: List[StepHistoryEntry] = Field(
        default_factory=list, description="已执行步骤摘要"
    )
    step_goals: Dict[str, str] = Field(
        default_factory=dict, description="全图 step_goal 映射 {node_id: goal}"
    )
    results: Dict[str, Any] = Field(
        default_factory=dict, description="全图已执行节点的输出 {node_id: output}"
    )
    snapshot_version: int = Field(default=0, description="快照版本，单调递增")


class OperatorContext(BaseSchema):
    """算子执行上下文，承载调度元信息（步骤历史、依赖输出、共享状态等）"""

    model_config = ConfigDict(frozen=True, extra="ignore")

    request_id: str = Field(description="请求ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    current_location: Optional[Dict[str, float]] = Field(
        default=None, description="当前位置"
    )
    timestamp: Optional[datetime] = Field(
        default_factory=datetime.now, description="时间戳"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, description="对话历史"
    )
    timeout: Optional[timedelta] = Field(default=None, description="超时时间")
    execution_context: Optional[ExecutionContext] = Field(
        default=None, description="步骤执行上下文（独立于会话上下文）"
    )


def _get_field_display_name(field_info: Any) -> str:
    """返回字段的展示名称：优先用 title，否则用字段名本身。

    用于：输出字段描述给 LLM、step_output 校验时的名称匹配。
    """
    title = getattr(field_info, "title", None)
    if title:
        return str(title)
    name = getattr(field_info, "alias", None)
    if name:
        return str(name)
    return ""


def _get_output_field_map(model_class: Type[BaseModel]) -> Dict[str, str]:
    """构建 {Python字段名: title或字段名} 的映射表。

    递归处理嵌套模型，各层字段独立命名，不拼接父路径（如
    nested_field.inner_name → inner_name）。
    """
    if not model_class or not hasattr(model_class, "model_fields"):
        return {}
    mapping: Dict[str, str] = {}
    for param_name, field_info in model_class.model_fields.items():
        display_name = _get_field_display_name(field_info)
        key = display_name if display_name else param_name
        mapping[param_name] = key
        # 递归处理嵌套 BaseModel
        nested_models = _extract_nested_model_types(field_info.annotation)
        for inner in nested_models:
            inner_map = _get_output_field_map(inner)
            # 去掉父路径，只用嵌套模型自身字段名
            for inner_k, inner_v in inner_map.items():
                mapping[inner_k] = inner_v
    return mapping


def _extract_nested_model_types(field_type: Any) -> List[type[BaseModel]]:
    """从类型注解中提取所有 BaseModel 子类，用于递归处理嵌套模型。

    支持：直接类型（BaseModel 子类）、List[X]、Optional[X]、Union[...]。
    """
    if field_type is None:
        return []
    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
        return [field_type]
    origin = getattr(field_type, "__origin__", None)
    args = getattr(field_type, "__args__", None) or []
    results: List[type[BaseModel]] = []
    if origin is not None:
        for arg in args:
            results.extend(_extract_nested_model_types(arg))
    return results


def _model_dump_by_title(obj: BaseModel) -> Dict[str, Any]:
    """将 BaseModel 对象转为 dict，key 使用 field title（若存在）。

    这使得下游（step_output 声明、依赖注入、LLM 展示）可以统一使用
    语义化名称（如 address/province/city/district）而非 Python 字段名
    （name/pname/cityname/adname）。

    嵌套的 BaseModel 对象也递归做相同处理。
    """
    raw = obj.model_dump()
    mapping = _get_output_field_map(type(obj))
    if not mapping:
        return raw
    result: Dict[str, Any] = {}
    for k, v in raw.items():
        new_key = mapping.get(k, k)
        if isinstance(v, dict):
            # 若该字段对应一个嵌套模型，也递归处理（简单启发式：字段名匹配嵌套模型）
            nested_field_info = obj.model_fields.get(k)
            if nested_field_info:
                nested_types = _extract_nested_model_types(nested_field_info.annotation)
                if nested_types and v:
                    # 取第一个匹配类型做转换
                    # A2：异常自然向上抛出（符合第 3.1 节），由调用方决定是否捕获产出 SerializationIssue
                    nested_cls = nested_types[0]
                    nested_obj = nested_cls.model_validate(v)
                    v = _model_dump_by_title(nested_obj)
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            # list[BaseModel] → 递归转换
            nested_field_info = obj.model_fields.get(k)
            if nested_field_info:
                nested_types = _extract_nested_model_types(nested_field_info.annotation)
                if nested_types:
                    nested_cls = nested_types[0]
                    # A2：异常自然向上抛出（符合第 3.1 节），由调用方决定是否捕获产出 SerializationIssue
                    v = [_model_dump_by_title(nested_cls.model_validate(x)) for x in v]
        result[new_key] = v
    return result


class OperatorResult(BaseSchema):
    """算子执行结果 — 承载 BaseOperator.execute 的返回值

    success: 是否执行成功
    data: 结果数据（可能是 dict / list / FilterAndStructureOutput / BaseModel）
    error: 失败时的错误信息
    execution_time: 执行耗时（秒）
    node_id: 对应的 DAG 节点 ID
    trace_id: 追踪 ID
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    success: bool = Field(description="是否成功")
    data: Any = Field(default=None, description="执行结果数据")
    error: Optional[str] = Field(default=None, description="错误信息")
    execution_time: float = Field(default=0, description="执行时间(秒)")
    node_id: str = Field(default="", description="对应的节点ID")
    trace_id: Optional[str] = Field(default=None, description="追踪ID")

    def is_failed(self) -> bool:
        """检查算子是否执行失败：success=False 或 data 为 None 均视为失败"""
        return not self.success or self.data is None

    def extract_data(self) -> Any:
        """从 data 中提取结构化输出，应对算子输出类型的不确定性。

        output_model 的字段一律优先用 title 作为键名（如 POISearchOutput.name →
        title="address" 时输出为 {"address": ..., ...}），与 LLM 生成的 step_output
        声明保持一致。

        处理策略：
        - FilterAndStructureOutput → 取 structured_output
        - list → 逐项转换：BaseModel 调 _model_dump_by_title，dict 原样保留
        - BaseModel → _model_dump_by_title（用 title 做键名）
        - dict → 尝试取 structured_output 键，否则原样返回
        - None → 空字典
        """
        if self.data is None:
            return {}
        if isinstance(self.data, FilterAndStructureOutput):
            return self.data.structured_output or {}
        if isinstance(self.data, list):
            return [
                _model_dump_by_title(item) if isinstance(item, BaseModel) else item
                for item in self.data
            ]
        if isinstance(self.data, BaseModel):
            return _model_dump_by_title(self.data)
        if isinstance(self.data, dict):
            return self.data.get("structured_output", self.data)
        return {}


class BaseOperator(ABC):
    """算子基类 — 定义算子的标准接口

    子类必须实现：
    - operator_type: 算子类型标识字符串

    可选覆盖：
    - execute: 异步执行方法，接收参数列表和上下文，返回 OperatorResult
      （默认实现已提供统一执行模板，子类通常只需覆盖 _process_success_result）
    - _process_success_result: 成功结果处理钩子，用于定制特殊业务逻辑
    - input_model / output_model: 参数模型类，用于 schema 生成
    - description: 算子描述文本
    - dedup_fields: 去重字段列表（None 表示不去重，搜索类算子默认不去重；
      其他算子按指定字段去重，如 ["address"]）。由 DAGExecutor._record_node_result 读取
    - is_search_operator: 是否为搜索类算子（结果可能为空或少量，需产出 SearchStrategyIssue）
    """

    async def execute(
        self, params_list: List[Dict[str, Any]], context: OperatorContext
    ) -> "OperatorResult":
        """统一执行模板：计时 → 调用执行器 → 包装结果 → 失败快速返回 → 成功后处理。

        子类通常无需覆盖此方法，只需覆盖 _process_success_result 钩子处理特殊业务逻辑。
        """
        from .operator_executors import execute_operator

        result, elapsed, node_id = await self._timed(
            execute_operator(self.operator_type, params_list, context), context
        )

        op_result = OperatorResult(
            success=result.success,
            data=result.data,
            error=result.error,
            execution_time=elapsed,
            node_id=node_id,
        )
        if op_result.is_failed():
            return op_result

        processed_data = self._process_success_result(op_result)
        return OperatorResult(success=True).model_copy(
            update={
                "data": processed_data,
                "execution_time": elapsed,
                "node_id": node_id,
            }
        )

    def _process_success_result(self, op_result: "OperatorResult") -> Any:
        """成功结果处理钩子：默认调用 extract_data() 提取结构化输出。

        子类可覆盖此方法以处理特殊业务逻辑（如 CarControlOperator 需从 results 列表取首项）。
        """
        return op_result.extract_data()

    @property
    @abstractmethod
    def operator_type(self) -> str:
        pass

    @property
    def input_model(self) -> Type[BaseModel]:
        return BaseModel

    @property
    def output_model(self) -> Type[BaseModel]:
        return BaseModel

    @property
    def description(self) -> str:
        return "未定义描述"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """去重字段列表，None 表示不去重。搜索类算子应覆盖为 None，其他算子按需指定字段。"""
        return ["address"]

    @property
    def is_search_operator(self) -> bool:
        """是否为搜索类算子（结果可能为空或少量时产出 SearchStrategyIssue）"""
        return False

    @staticmethod
    async def _timed(coro: Any, context: "OperatorContext") -> Tuple[Any, float, str]:
        """执行协程并计时，返回 (result, elapsed_seconds, node_id)。

        统一 6 个算子 execute 方法中的 timing + node_id 提取逻辑（M10），
        使用 anyio.current_time() 替代 loop.time()，兼容 anyio 结构化并发。
        """
        t0 = anyio.current_time()
        result = await coro
        elapsed = round(anyio.current_time() - t0, 3)
        node_id = context.metadata.get("node_id", context.request_id)
        return result, elapsed, node_id


class ExecutorResult(BaseSchema):
    """执行器执行结果 - 承载 BaseExecutor.execute 的返回值"""

    model_config = ConfigDict(frozen=True, extra="ignore")

    success: bool = Field(description="是否成功")
    data: Optional[Any] = Field(
        default=None, description="执行结果数据（具体类型由各执行器决定）"
    )
    error: Optional[str] = Field(default=None, description="错误信息")


class BaseExecutor(ABC):
    """执行器基类 — 定义执行器的标准接口

    每个执行器绑定一个外部工具实例（self.tool），由 initialize() 注入。
    子类必须实现 execute() 方法和 params_model 属性。
    validate_params 装饰器自动将 dict 参数转为 BaseModel 实例。
    execute() 返回各自业务类型（FilterAndStructureOutput / List[...]），
    由 execute_operator 统一包装为 ExecutorResult；异常不捕获，自然向上抛出。
    """

    def __init__(self):
        self.tool = None

    def initialize(self, tool):
        """使用真实工具实例初始化，使执行器可用"""
        self.tool = tool

    @property
    def params_model(self) -> Type[BaseModel]:
        """参数模型类 - 子类应覆盖此属性以返回具体的 BaseModel 类型"""
        return BaseModel

    @abstractmethod
    async def execute(
        self,
        params: List[BaseModel],
        context: Optional[OperatorContext] = None,
    ) -> Any:
        """执行算子逻辑

        Args:
            params: 参数列表，元素类型为子类 params_model 指定的 BaseModel
            context: 算子执行上下文

        Returns:
            各执行器业务类型（FilterAndStructureOutput / List[BaseModel] 等），
            由 execute_operator 统一包装为 ExecutorResult。
            异常不捕获，自然向上抛出。
        """
        pass

    @property
    def available(self) -> bool:
        """检查执行器是否可用"""
        return self.tool is not None


def validate_params(func: Callable) -> Callable:
    """参数验证装饰器 - 将 Dict 列表转换为对应 BaseModel 列表。

    从 self.params_model 获取目标模型类，逐项将 dict 转为 BaseModel 实例。
    若参数已是 BaseModel 则保留原样。
    """

    @wraps(func)
    async def wrapper(self, *args, **kwargs) -> Any:
        params: Optional[List[Any]] = None
        if len(args) > 0:
            if isinstance(args[0], list):
                params = args[0]
            elif len(args) > 1 and isinstance(args[1], list):
                params = args[1]
        if params is None and "params" in kwargs:
            params = kwargs["params"]

        if params is None:
            raise ValueError("未找到params参数")

        # 获取参数模型类
        model_class: Type[BaseModel] = getattr(self, "params_model", BaseModel)

        # 转换参数：dict -> BaseModel
        converted: List[BaseModel] = []
        for p in params:
            if isinstance(p, BaseModel):
                converted.append(p)
            elif isinstance(p, dict):
                converted.append(model_class.model_validate(p))
            else:
                raise ValueError(
                    f"参数类型错误，期望 dict 或 BaseModel，收到 {type(p).__name__}"
                )

        if len(args) > 0 and isinstance(args[0], list):
            args = (converted,) + args[1:]
        elif len(args) > 1 and isinstance(args[1], list):
            args = (args[0], converted) + args[2:]
        else:
            kwargs["params"] = converted

        return await func(self, *args, **kwargs)

    return wrapper


class BuildPromptInput(BaseSchema):
    """构造 LLM 提示词的输入"""

    all_results: List[Dict[str, Any]] = Field(description="候选结果列表")
    step_goal: str = Field(description="步骤目标")
    step_output: List[str] = Field(default_factory=list, description="步骤出参列表")


class FilterAndStructureInput(BaseSchema):
    """筛选与结构化输入"""

    all_results: List[Dict[str, Any]] = Field(description="原始检索结果列表")
    context: Optional[OperatorContext] = Field(
        default=None, description="算子执行上下文"
    )


class FilterAndStructureOutput(BaseSchema):
    """筛选与结构化输出"""

    results: List[Dict[str, Any]] = Field(
        default_factory=list, description="原始结果列表"
    )
    total_count: int = Field(default=0, description="结果总数")
    step_goal: Optional[str] = Field(default=None, description="步骤目标")
    step_output: Optional[List[str]] = Field(default=None, description="步骤出参列表")
    structured_output: Optional[Any] = Field(
        default=None, description="结构化输出（LLM 筛选后的 JSON）"
    )
    error: Optional[str] = Field(default=None, description="错误信息")


class BuildConditionPromptInput(BaseSchema):
    """条件算子-提示词输入：构造 LLM 提示词的数据载体

    rules 用 List[Any] 而非 List[ConditionRule]，避免 base_classes 与
    operator_models 产生循环依赖；实际元素为 ConditionRule 实例。
    facts 为引用名→值映射列表（_merge_condition_params 合并后），
    每条 dict 的 key 为引用名（如 s1.weather.weather_temperature），value 为解析值。
    """

    facts: List[Dict[str, str]] = Field(
        description="上游信息（引用名→值映射列表，_merge_condition_params 合并后）"
    )
    rules: List[Any] = Field(description="条件规则表（ConditionRule 列表）")
    step_goal: str = Field(default="", description="步骤目标")


class ConditionJudgeInput(BaseSchema):
    """条件算子-判断输入：judge_condition 的入参

    rules 用 List[Any] 规避循环依赖，实际元素为 ConditionRule 实例。
    facts 为引用名→值映射列表（_merge_condition_params 合并后），
    每条 dict 的 key 为引用名（如 s1.weather.weather_temperature），value 为解析值。
    """

    facts: List[Dict[str, str]] = Field(
        description="上游信息（引用名→值映射列表，_merge_condition_params 合并后）"
    )
    rules: List[Any] = Field(description="条件规则表")
    default: Dict[str, Any] = Field(description="兜底输出")
    context: Optional[OperatorContext] = Field(
        default=None, description="算子执行上下文"
    )


class BuildValidatorPromptInput(BaseSchema):
    """目标验证-提示词输入：构造 LLM 提示词的数据载体

    downstream_nodes / step_history 用 List[Any] 规避循环依赖，
    实际元素为 DownstreamNodeRef / StepHistoryEntry 序列化形态。
    """

    step_goal: str = Field(default="", description="当前步骤目标")
    step_output: List[str] = Field(
        default_factory=list, description="当前步骤出参字段列表"
    )
    current_output: Any = Field(default=None, description="当前节点产出数据")
    step_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="已执行步骤摘要(StepHistoryEntry序列化)"
    )
    downstream_nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="下游后继节点(DownstreamNodeRef序列化)"
    )


class ValidatorJudgeInput(BaseSchema):
    """目标验证-判断输入：validate_goal 的入参

    params 为 ValidatorParams 序列化形态（含 downstream_nodes）。
    context 携带 ExecutionContext（current_step / step_history / results）。
    """

    params: Any = Field(description="ValidatorParams(含downstream_nodes)")
    context: Optional[OperatorContext] = Field(
        default=None, description="算子执行上下文(含ExecutionContext)"
    )


class BuildMemoryMockPromptInput(BaseSchema):
    """记忆召回-Mock答案提示词输入：构造 LLM 提示词的数据载体

    根据 query 和 memory_type，由 LLM mock 出一条符合要求的记忆事实文本，
    供下游算子正常消费，使 Plan 链路在无真实记忆接口时跑通。
    """

    query: str = Field(description="记忆查询描述")
    memory_type: str = Field(description="记忆类型: preference/history/context/profile")
    step_goal: str = Field(
        default="", description="当前步骤目标，辅助 LLM 理解查询上下文"
    )


class MemoryMockJudgeInput(BaseSchema):
    """记忆召回-Mock答案编排输入：generate_memory_mock 的入参

    params 为 MemoryRecallParams 序列化形态。
    context 携带 ExecutionContext（提取 step_goal）。
    """

    params: Any = Field(description="MemoryRecallParams 序列化形态")
    context: Optional[OperatorContext] = Field(
        default=None, description="算子执行上下文(含ExecutionContext)"
    )


class ProcessResult(BaseSchema):
    """处理结果封装

    安全问题统一通过 issue_report.by_category(IssueCategory.SAFETY) 查询，
    不再保留独立的 safety_issues 字段（已合并到 issue_report 单一出口）。
    """

    success: bool = Field(default=False, description="是否成功")
    stage: str = Field(default="", description="执行阶段")
    message: str = Field(default="", description="执行消息")
    dag_ir: Optional[DAGIR] = Field(default=None, description="DAG IR 实例")
    execution_result: Optional[Dict[str, Any]] = Field(
        default=None, description="执行结果"
    )
    trace: Dict[str, ExecutionTrace] = Field(
        default_factory=dict, description="执行轨迹"
    )
    issue_report: Optional[IssueReport] = Field(
        default=None,
        description="统一 Issue 报告（全链路单一出口，安全问题通过 by_category(SAFETY) 查询）",
    )
    metrics: Optional[DagMetrics] = Field(
        default=None,
        description="D5：全链路 metrics 容器，从 DAGExecutor.metrics 透传（D3），供下游量化分析",
    )


class PlanExecutionOutput(BaseSchema):
    """Plan执行输出 - 包含完整的处理结果

    字段与 ProcessResult 保持一一对应，避免在跨层传递时类型退化。
    issue_report 作为统一出口，汇聚全链路所有阶段的 Issue。
    安全问题统一通过 issue_report.by_category(IssueCategory.SAFETY) 查询，
    不再保留独立的 safety_issues / safety_issue_list 字段。
    """

    success: bool = Field(title="success", description="执行是否成功")
    stage: str = Field(default="", title="stage", description="执行阶段")
    message: str = Field(default="", title="message", description="执行消息")
    goal: str = Field(default="", title="goal", description="任务目标")
    steps: int = Field(default=0, title="steps", description="步骤数量")
    dag_nodes: int = Field(default=0, title="dag_nodes", description="DAG节点数量")
    execution_result: Optional[Dict[str, Any]] = Field(
        default=None, title="execution_result", description="执行结果"
    )
    trace: Dict[str, ExecutionTrace] = Field(
        default_factory=dict,
        title="trace",
        description="执行轨迹（node_id -> ExecutionTrace）",
    )
    issue_report: Optional[IssueReport] = Field(
        default=None,
        title="issue_report",
        description="统一 Issue 报告（全链路单一出口，汇聚 contradiction/safety/execution/exception 四类 Issue）",
    )
    metrics: Optional[DagMetrics] = Field(
        default=None,
        title="metrics",
        description="全链路 metrics 聚合字段，由 harness 终止时附加，含 NodeMetrics/total_duration/issue_distribution，供外层量化分析",
    )


class PlanRuntimeState(dict):
    """Plan 运行时状态，本质是对 plan dict 的薄封装。

    由 plan_processor._execute_dag 构造，注入 OperatorContext.metadata["plan_state"]，
    供算子在执行期间访问完整的 plan 结构信息。
    """


class AvailableOperator(BaseSchema):
    """可用算子信息（用于LLM结构化生成）"""

    operator_type: str = Field(description="算子类型标识")
    description: str = Field(default="", description="算子描述")
    input_schema: Dict[str, Any] = Field(
        default_factory=dict, description="输入参数schema"
    )
    output_schema: Dict[str, Any] = Field(
        default_factory=dict, description="输出参数schema"
    )
