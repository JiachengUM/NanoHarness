"""DAG 模块统一 Issue 体系

集中定义全链路 Issue/检查/异常的 Pydantic BaseModel，按职责分三层：
- 生成合法性：ContradictionIssue（check_contradictions 产出）、SafetyIssue（SafetyScanner 产出）
- 执行失败：ExecutionIssue（DAGExecutor 硬失败产出）、ExceptionIssue（未预期异常，替代 try-except 拼接）
- 执行问题：SearchStrategyIssue / StepGoalIssue / PlanOptimizationIssue
  → 如实记录执行过程中观察到的现象和上下文，供外层消费方自行判断应对策略

设计要点：
1. BaseIssue 继承 BaseSchema（frozen=True），保证 issue 创建后不可变，符合 issue 的不可变性语义
2. 子类通过 Field default 强制 category 字段，保证类型安全
3. IssueReport 继承 BaseModel（非 frozen），作为可变容器在各阶段间通过引用共享，
   符合 AGENTS.md 第 4 条"中间状态驱动多层抽象"——IssueReport 是唯一中间状态，仅需一层抽象
4. 所有 Issue 通过 IssueReport 单一出口汇聚，替代原本分散的 4 个出口
5. Issue 仅记录问题现象和上下文背景，不包含任何建议或优化方案——优化策略由消费方（如 NodeParamOptimizer、外层 LLM）根据现象自行决定
"""

import functools
import inspect
import logging
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aicore.tools.dag.operator_models import BaseSchema


class IssueSeverity(str, Enum):
    """Issue 严重级别 — 与原 SafetyIssue.severity 保持一致"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueCategory(str, Enum):
    """Issue 类别 — 对应产生阶段，用于按类别查询和过滤

    分三层：
    - 生成合法性（contradiction/safety）：Plan/DAG IR 结构与安全检查
    - 执行失败（execution/exception）：硬失败与未预期异常
    - 执行问题（search_strategy/step_goal/plan_optimization）：记录执行过程中观察到的现象，供消费方自行判断策略
    """

    # --- Plan 生成合法性（多维度检查）---
    CONTRADICTION = "contradiction"  # Plan 结构合法性（plan_generator.py）
    SAFETY = "safety"  # DAG IR 安全合法性（safety_scanner.py）

    # --- Plan 执行失败 ---
    EXECUTION = "execution"  # DAG 执行硬失败（dag_executor.py）
    EXCEPTION = "exception"  # 未预期异常（替代 try-except 拼接）

    # --- Plan 执行问题（记录现象，不包含建议）---
    SEARCH_STRATEGY = "search_strategy"  # 记录搜索结果质量问题（空/少/不相关）
    STEP_GOAL = "step_goal"  # 记录步骤目标未达成现象
    PLAN_OPTIMIZATION = "plan_optimization"  # 记录 Plan 结构问题现象


class BaseIssue(BaseSchema):
    """所有 Issue 的公共基类

    字段说明：
    - issue_id: 唯一标识，未提供时由 IssueReport.add 自动生成（uuid 前8位）
    - category: 类别，子类通过 Field default 强制
    - severity: 严重级别，由调用方按检查项语义填充
    - stage: 产生阶段（validation/dag_build/safety_scan/execution/exception）
    - message: 人类可读的问题描述
    - node_id: 相关节点ID（safety/execution 类常用）
    - operator_type: 相关算子类型（safety/execution 类常用）
    - check_name: 检查项名称（contradiction 类用，如 step_id_uniqueness）

    注：原 suggestion / detail 字段已移除，修复建议与扩展详情统一记录在
    `suggestion_readme.md` 中，调用方按 category / check_name / message 自行映射。
    """

    issue_id: str = Field(
        default="", description="唯一标识，未提供时由 IssueReport.add 自动生成"
    )
    category: IssueCategory
    severity: IssueSeverity
    stage: str
    message: str
    node_id: Optional[str] = None
    operator_type: Optional[str] = None
    check_name: Optional[str] = None


class ContradictionIssue(BaseIssue):
    """Plan 矛盾检查 Issue — 由 StructuredPlan.check_contradictions 产出

    强制 category = CONTRADICTION，stage = validation
    """

    category: IssueCategory = IssueCategory.CONTRADICTION
    stage: str = "validation"


class SafetyIssue(BaseIssue):
    """安全扫描 Issue — 由 SafetyScanner.scan 产出

    强制 category = SAFETY，stage = safety_scan
    """

    category: IssueCategory = IssueCategory.SAFETY
    stage: str = "safety_scan"


class ExecutionIssue(BaseIssue):
    """DAG 执行错误 Issue — 由 DAGExecutor 产出

    强制 category = EXECUTION，stage = execution
    扩展字段：
    - status: 节点执行状态（failed/skipped/partial）
    - retry_count: 已重试次数
    - trace_id: 追踪ID
    """

    category: IssueCategory = IssueCategory.EXECUTION
    stage: str = "execution"
    status: str = "failed"
    retry_count: int = 0
    trace_id: Optional[str] = None


class ExceptionIssue(BaseIssue):
    """未预期异常 Issue — 替代原 try-except 的 message 字符串拼接

    强制 category = EXCEPTION，stage = exception
    扩展字段：
    - exception_type: 异常类型名（如 ValueError、TimeoutError）
    - traceback: 完整堆栈字符串
    """

    category: IssueCategory = IssueCategory.EXCEPTION
    stage: str = "exception"
    exception_type: str
    traceback: str = ""


class SearchStrategyIssue(BaseIssue):
    """搜索策略问题 Issue — 记录搜索结果质量问题现象

    强制 category = SEARCH_STRATEGY，stage = execution
    由 DAGExecutor._record_node_result 在结果质量差（空 / 少量 / 不相关）时产出。
    仅记录事实现象（算子类型、结果质量、当时入参），不包含任何优化建议——
    消费方（如 NodeParamOptimizer）根据 result_quality 等事实字段自行决定应对策略。

    扩展字段：
    - tool_type: 使用的算子类型
    - result_quality: 结果质量（none/few/irrelevant/insufficient）
    - current_params: 当时使用的入参快照
    - retry_count: 已重试次数
    """

    category: IssueCategory = IssueCategory.SEARCH_STRATEGY
    stage: str = "execution"
    tool_type: str
    result_quality: str
    current_params: Dict[str, Any] = {}
    retry_count: int = 0


class StepGoalIssue(BaseIssue):
    """步骤目标问题 Issue — 记录步骤目标未达成现象

    强制 category = STEP_GOAL，stage = execution
    由 DAGExecutor._record_node_result 在 step_goal 未达成（partial）时产出，
    替代原 ExecutionIssue(status="partial")。仅记录事实（step_goal 原文），
    不包含优化建议——消费方自行判断应对策略。

    扩展字段：
    - step_goal: 步骤目标原文

    注：原 achievement_status / matched_segments / unmatched_segments / output_preview
    字段已移除，相关语义由消费方自行分析。
    """

    category: IssueCategory = IssueCategory.STEP_GOAL
    stage: str = "execution"
    step_goal: str


class PlanOptimizationIssue(BaseIssue):
    """Plan 结构问题 Issue — 记录 Plan 结构问题现象

    强制 category = PLAN_OPTIMIZATION，stage = execution
    捕获执行过程中发现的 Plan 结构性问题现象。仅记录事实（受影响步骤、问题类型），
    不包含重构建议——消费方自行判断应对策略。

    注：本次仅定义数据模型，产出逻辑（跨节点分析）留后续迭代。

    扩展字段：
    - affected_steps: 受影响的 step_id 列表
    - plan_issue_type: Plan 问题类型
    """

    category: IssueCategory = IssueCategory.PLAN_OPTIMIZATION
    stage: str = "execution"
    affected_steps: List[str] = []
    plan_issue_type: str


class SerializationIssue(BaseIssue):
    """序列化失败 Issue — 替代 _safe_json 等 CSV/日志序列化处的 try-except

    强制 category = EXCEPTION，stage = serialization
    当 json.dumps / model_dump 等序列化操作失败时抛出，外层可据此记录而非静默吞掉。
    扩展字段：
    - target_type: 被序列化对象的类型名
    - serializer: 使用的序列化器（如 json.dumps / model_dump_json）
    """

    category: IssueCategory = IssueCategory.EXCEPTION
    stage: str = "serialization"
    exception_type: str
    target_type: str = ""
    serializer: str = ""
    traceback: str = ""


class ToolOutputParseIssue(BaseIssue):
    """工具输出解析失败 Issue — 替代 _parse_tool_output 等 tool output 还原处的 try-except

    强制 category = EXCEPTION，stage = tool_output_parse
    当 tool output 无法还原为 PlanExecutionOutput 时抛出，外层可据此记录而非返回 None。
    扩展字段：
    - raw_type: 原始输出的类型名（str / dict / 其他）
    - parse_stage: 解析阶段（json_loads / model_validate）
    """

    category: IssueCategory = IssueCategory.EXCEPTION
    stage: str = "tool_output_parse"
    exception_type: str
    raw_type: str = ""
    parse_stage: str = ""
    traceback: str = ""


class IssueReport(BaseModel):
    """统一 Issue 容器 — 全链路单一出口

    作为各阶段（plan_generator → plan_processor → dag_executor）间传递的中间状态，
    通过引用共享，各阶段调用 add/extend 追加 issue，最终从 PlanExecutionOutput.issue_report 出口抛出。

    设计说明：
    - 非 frozen：作为可变容器需要频繁追加 issues
    - 不继承 BaseSchema：BaseSchema 是 frozen，与可变容器语义冲突
    - add() 自动填充 issue_id（如果未提供），用 uuid 前8位保证唯一性
    - 提供 has_critical/by_category/by_severity/summary 等查询方法，便于上层程序化处理
    """

    model_config = ConfigDict(extra="ignore")

    issues: List[BaseIssue] = Field(default_factory=list, description="全部 Issue 列表")

    def add(self, issue: BaseIssue) -> None:
        """追加单个 issue，若 issue_id 为空则自动生成 uuid 前8位"""
        if not issue.issue_id:
            issue = issue.model_copy(update={"issue_id": uuid.uuid4().hex[:8]})
        self.issues.append(issue)

    def extend(self, issues: List[BaseIssue]) -> None:
        """批量追加 issues，逐个调用 add 以保证 issue_id 填充"""
        for issue in issues:
            self.add(issue)

    def has_critical(self) -> bool:
        """是否存在 critical 级别 issue"""
        return any(issue.severity == IssueSeverity.CRITICAL for issue in self.issues)

    def by_category(self, category: IssueCategory) -> List[BaseIssue]:
        """按类别过滤 issue"""
        return [issue for issue in self.issues if issue.category == category]

    def by_severity(self, severity: IssueSeverity) -> List[BaseIssue]:
        """按严重级别过滤 issue"""
        return [issue for issue in self.issues if issue.severity == severity]

    def is_empty(self) -> bool:
        """是否无任何 issue"""
        return len(self.issues) == 0

    def execution_issues(self) -> List[BaseIssue]:
        """返回所有执行问题类 Issue（SEARCH_STRATEGY + STEP_GOAL + PLAN_OPTIMIZATION）

        供消费方获取执行过程中记录的问题现象，区别于生成合法性 / 执行失败类 Issue。
        """
        execution_categories = {
            IssueCategory.SEARCH_STRATEGY,
            IssueCategory.STEP_GOAL,
            IssueCategory.PLAN_OPTIMIZATION,
        }
        return [
            issue for issue in self.issues if issue.category in execution_categories
        ]

    def contradiction_issues(self) -> List[BaseIssue]:
        """返回所有 Plan 矛盾类 Issue（CONTRADICTION）

        供 Harness 修复闭环消费：check_contradictions 产出的结构性矛盾
        （step_id_uniqueness / depends_on_integrity / ref_step_existence /
        ref_field_declared / params_type_match / params_field_validity /
        cycle_detection 等），与 execution_issues 并列作为 LLM step 替换的输入。
        """
        return self.by_category(IssueCategory.CONTRADICTION)

    def issues_by_category(self) -> Dict[str, List[BaseIssue]]:
        """按类别分组返回，供消费方自行判断应对策略

        Returns:
            {
                "search_strategy": [...],
                "step_goal": [...],
                "plan": [...],
            }
        """
        return {
            "search_strategy": self.by_category(IssueCategory.SEARCH_STRATEGY),
            "step_goal": self.by_category(IssueCategory.STEP_GOAL),
            "plan": self.by_category(IssueCategory.PLAN_OPTIMIZATION),
        }

    def has_execution_issues(self) -> bool:
        """是否存在任何执行问题类 Issue"""
        return len(self.execution_issues()) > 0

    def summary(self) -> str:
        """生成问题摘要，按类别分组，用于 PlanExecutionOutput.message

        格式示例：
        [contradiction] 2 个问题
          - [HIGH] step_id_uniqueness: step_id 重复: s1 出现了 2 次
          - [CRITICAL] cycle_detection: 步骤之间存在循环依赖: s1 → s2 → s1
        [safety] 1 个问题
          - [CRITICAL] 节点 s1 使用了未知算子类型

        注：原 suggestion 字段已移除，修复建议统一参考 `suggestion_readme.md`。
        """
        if not self.issues:
            return "无问题"
        grouped: Dict[IssueCategory, List[BaseIssue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.category, []).append(issue)

        parts: List[str] = []
        for category, issues in grouped.items():
            parts.append(f"[{category.value}] {len(issues)} 个问题")
            for issue in issues:
                check_prefix = f" {issue.check_name}:" if issue.check_name else ""
                node_prefix = f" (node={issue.node_id})" if issue.node_id else ""
                parts.append(
                    f"  - [{issue.severity.value.upper()}]{check_prefix} {issue.message}{node_prefix}"
                )
        return "\n".join(parts)


# =============================================================================
# 装饰器基础设施 — 无 raise / 无 try-except，纯结果聚合
# =============================================================================

# Issue 捕获的 ContextVar — 复用 observer.py 的 ContextVar + contextmanager 模式
# with 块内所有 @capture_issues 装饰的函数自动汇聚 issues 到当前 IssueReport
_current_issue_report: ContextVar[Optional["IssueReport"]] = ContextVar(
    "dag_issue_report",
    default=None,
)


class CheckResult(BaseModel):
    """检查结果通用包装 — 所有被 @capture_issues 装饰的检查函数的统一返回类型

    被装饰函数检查到问题时构造 Issue 放入 issues 字段（不 raise），
    装饰器从本字段提取 Issue 汇入 ContextVar 中的 IssueReport。
    passed 表示检查是否通过（无 CRITICAL/HIGH issue）。

    继承 BaseModel（非 frozen）：需 add_issue 原地追加，与 IssueReport 可变语义一致。
    """

    model_config = ConfigDict(extra="ignore")

    issues: List[BaseIssue] = Field(
        default_factory=list, description="检查产出的 Issue 列表"
    )
    passed: bool = Field(default=True, description="是否通过（无 critical/high issue）")

    def add_issue(self, issue: BaseIssue) -> None:
        """追加 issue 并更新 passed 状态"""
        self.issues.append(issue)
        if issue.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH):
            self.passed = False


class IssueUtils(BaseModel):
    """Issue 工具节点 — 持有装饰器与上下文管理器

    符合 AGENTS.md 第 9.2 节"函数归属 BaseModel"：装饰器与上下文管理器
    作为 IssueUtils 的方法，输入主参为 self，输出 BaseModel 或 Callable。

    装饰器机制：无 raise / 无 try-except，纯结果聚合。
    被装饰函数返回 CheckResult（或含 issues 字段的对象），装饰器提取 issues
    汇入 _current_issue_report ContextVar 指向的 IssueReport。
    """

    model_config = ConfigDict(extra="ignore")

    report: IssueReport = Field(
        default_factory=lambda: IssueReport(), description="持有的 IssueReport 容器"
    )

    def capture_issues(self) -> Callable:
        """转换：IssueUtils → Callable（装饰器工厂）

        返回装饰器：从被装饰函数返回值提取 issues 汇入 _current_issue_report。
        不捕获异常（异常自然抛出，由上层处理或 logging 记录，符合 AGENTS.md 第 3.1 节）。
        自动适配同步/异步函数。
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                result = await func(*args, **kwargs)
                self._collect(result)
                return result

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                self._collect(result)
                return result

            return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

        return decorator

    def _collect(self, result: Any) -> None:
        """从返回值提取 issues 汇入当前 IssueReport（内部辅助）

        支持三种返回形态：
        - CheckResult：提取 .issues
        - List[BaseIssue]：直接汇入
        - 含 issues 字段的对象：提取 .issues
        """
        report = _current_issue_report.get()
        if report is None:
            return
        if isinstance(result, CheckResult):
            report.extend(result.issues)
        elif isinstance(result, list) and result and isinstance(result[0], BaseIssue):
            report.extend(result)
        elif hasattr(result, "issues") and isinstance(getattr(result, "issues"), list):
            report.extend(result.issues)

    @contextmanager
    def issue_scope(self) -> Iterator[None]:
        """转换：IssueUtils → Iterator（上下文管理器）

        将 self.report 设置到 _current_issue_report，with 块内所有 @capture_issues
        装饰的函数自动汇聚 issues 到 self.report。
        退出 with 块后恢复原值，保证作用域隔离。
        """
        token = _current_issue_report.set(self.report)
        yield
        _current_issue_report.reset(token)


# 模块级单例 — 供装饰器 @ 语法使用（实例引用，非模块级函数，符合第 9.2 节）
_issue_utils = IssueUtils()


class IssueStrategyPrompt(BaseSchema):
    """策略提示词节点 — 从配置文件读取提示词，供 PlanTool description 使用

    配置文件为纯文本（.md），内容是针对不同 issue 现象的应对策略提示词，
    读取后拼接到 PlanTool 的 description 中，指导 LLM 根据 issue 现象自行判断优化策略。
    （策略提示词本身不属于 Issue 数据，是 PlanTool 消费 Issue 时的辅助配置）

    符合 AGENTS.md 第 9 节 DAG 节点边关系：load 方法输入只有 self，输出 IssueStrategyPrompt。
    """

    path: str = Field(default="", description="策略提示词配置文件路径")
    content: str = Field(default="", description="读取到的提示词内容")

    def load(self) -> "IssueStrategyPrompt":
        """转换：IssueStrategyPrompt → IssueStrategyPrompt（从 self.path 读取提示词）

        读取 self.path 的文本文件，填充 content，返回新实例。
        文件不存在时返回原实例（content 为空），不 raise（符合第 3.1 节）。
        """
        if not self.path:
            return self
        if not os.path.exists(self.path):
            logging.getLogger(__name__).warning(f"策略提示词文件不存在: {self.path}")
            return self
        with open(self.path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.model_copy(update={"content": content})

def load_strategy_prompt() -> str:
    """加载默认策略提示词内容（issue_strategy_prompt.md）。

    模块级工具函数（符合 §9.2 例外：pure utils 可为模块级），
    消除 harness.py / plan_worker.py 两处重复的 path 计算 + load() 调用。
    """
    _STRATEGY_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "issue_strategy_prompt.md")
    return IssueStrategyPrompt(path=_STRATEGY_PROMPT_PATH).load().content
