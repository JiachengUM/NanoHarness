"""Plan 矛盾检查器：适配 aicore/agents/plan 中的 StructuredPlan 和 PlanStep 结构

参考 aicore/tools/dag/plan_generator.py 的 check_contradictions 方法实现：
- 使用 @capture_issues 装饰器，检查结果自动汇入 IssueReport
- 移除 try-except，异常自然抛出（符合 AGENTS.md 第 3.1 节）
- 复用 base_classes.detect_cycle，消除重复代码
- 增强错误消息，添加修复建议
- 支持多种 $ref 格式：$s1.field / ${s1.field} / ${s1.field[index].subfield}
"""

import re
from typing import List, Dict, Any, Set, Tuple

from aicore.tools.dag.issues import ContradictionIssue, IssueSeverity, CheckResult, _issue_utils, BaseIssue
from aicore.tools.dag.base_classes import detect_cycle
from aicore.agents.plan.experiment.plan_schema_v0 import StructuredPlan


@_issue_utils.capture_issues()
def check_plan_contradictions(plan_data: Dict[str, Any]) -> CheckResult:
    """检查 Plan 中的矛盾与不一致，适配 aicore/agents/plan 的 StructuredPlan 结构。

    装饰器化：检查到问题时构造 ContradictionIssue 放入 CheckResult.issues（不 raise），
    装饰器自动从返回值提取 issues 汇入 _current_issue_report ContextVar 指向的 IssueReport。

    检查项：
    1. step_id_uniqueness     — step_id 唯一性
    2. depends_on_integrity   — depends_on 引用完整性
    3. ref_step_existence     — $ref 占位符引用的 step_id 存在性
    4. ref_field_declared     — $ref 引用的 field 在上游 outputs 中是否声明
    5. cycle_detection        — 循环依赖
    6. depends_on_usage       — depends_on 声明的依赖是否在 inputs 中实际引用
    7. empty_outputs_depended — 上游步骤 outputs 为空但下游声明了 depends_on
    8. ref_format_compatibility — $ref 格式兼容性（支持 $s1.field / ${s1.field}）
    """
    plan = StructuredPlan.model_validate(plan_data)
    issues: List[ContradictionIssue] = []
    step_ids = {s.step_id for s in plan.steps}

    # 1. step_id 唯一性
    seen: Dict[str, int] = {}
    for s in plan.steps:
        seen[s.step_id] = seen.get(s.step_id, 0) + 1
    for sid, cnt in seen.items():
        if cnt > 1:
            issues.append(ContradictionIssue(
                severity=IssueSeverity.HIGH,
                message=f"step_id 重复: {sid} 出现了 {cnt} 次，建议分配唯一 step_id（如 {sid}, {sid}_2, {sid}_3）",
                check_name="step_id_uniqueness",
            ))

    # 构建每个 step 的 outputs 字段集合（供 $ref 校验使用）
    step_output_map: Dict[str, Set[str]] = {}
    for s in plan.steps:
        step_output_map[s.step_id] = set(s.outputs)

    # 构建反向依赖映射：哪些步骤依赖了当前步骤
    depended_by_map: Dict[str, List[str]] = {s.step_id: [] for s in plan.steps}
    for s in plan.steps:
        for dep in s.depends_on:
            if dep in depended_by_map:
                depended_by_map[dep].append(s.step_id)

    # 2. depends_on 引用完整性
    for s in plan.steps:
        for dep in s.depends_on:
            if dep not in step_ids:
                issues.append(ContradictionIssue(
                    severity=IssueSeverity.CRITICAL,
                    message=f"步骤 {s.step_id} 的 depends_on 引用了不存在的步骤: {dep}，建议移除 '{dep}' 或新增步骤 '{dep}'（可用: {sorted(step_ids)}）",
                    check_name="depends_on_integrity",
                    node_id=s.step_id,
                ))

    # 收集所有 $ref 引用（支持多种格式）
    ref_patterns = [
        re.compile(r"\$(\w+)\.(\w+)"),
        re.compile(r"\$\{(\w+)\.(\w+)\}"),
        re.compile(r"\$\{(\w+)\.([^}]+)\}"),
        re.compile(r"\{\{(\w+)\.([^}]+)\}\}"),
        re.compile(r"\{(\w+)\.([^}]+)\}"),
    ]

    def extract_refs(inputs_str: str) -> List[Tuple[str, str]]:
        refs: List[Tuple[str, str]] = []
        for pattern in ref_patterns:
            matches = pattern.findall(inputs_str)
            for ref_step_id, ref_field in matches:
                refs.append((ref_step_id, ref_field))
        return refs

    # 3 & 4. $ref 占位符合法性（从 inputs 字段中扫描）
    for s in plan.steps:
        inputs_str = str(s.inputs)
        refs_in_params = extract_refs(inputs_str)
        for ref_step_id, ref_field in refs_in_params:
            base_field = ref_field.split("[")[0].split(".")[0]
            if ref_step_id not in step_ids:
                issues.append(ContradictionIssue(
                    severity=IssueSeverity.CRITICAL,
                    message=f"步骤 {s.step_id} 的参数 $ref 引用了不存在的步骤: ${ref_step_id}.{ref_field}，建议改为已存在的 step_id（可用: {sorted(step_ids)}）",
                    check_name="ref_step_existence",
                    node_id=s.step_id,
                ))
            elif ref_step_id not in step_output_map or not step_output_map[ref_step_id]:
                issues.append(ContradictionIssue(
                    severity=IssueSeverity.HIGH,
                    message=f"步骤 {s.step_id} 的参数 $ref 引用了步骤 {ref_step_id}，但该步骤未声明 outputs: ${ref_step_id}.{ref_field}，建议在步骤 {ref_step_id} 的 outputs 中声明输出字段",
                    check_name="ref_field_declared",
                    node_id=s.step_id,
                ))
            elif base_field not in step_output_map[ref_step_id]:
                issues.append(ContradictionIssue(
                    severity=IssueSeverity.HIGH,
                    message=f"步骤 {s.step_id} 的参数 $ref 引用了步骤 {ref_step_id} 未声明的输出字段: ${ref_step_id}.{ref_field}，建议改为 {sorted(step_output_map[ref_step_id])} 之一，或在步骤 {ref_step_id} 的 outputs 中声明 '{base_field}'",
                    check_name="ref_field_declared",
                    node_id=s.step_id,
                ))

    # 5. 循环依赖检测（复用 base_classes.detect_cycle，DFS 三色标记法）
    adj: Dict[str, List[str]] = {s.step_id: list(s.depends_on) for s in plan.steps}
    cycle = detect_cycle(adj)
    if cycle:
        cycle_str = " → ".join(cycle)
        issues.append(ContradictionIssue(
            severity=IssueSeverity.CRITICAL,
            message=f"步骤之间存在循环依赖: {cycle_str}（循环路径: {cycle}）",
            check_name="cycle_detection",
        ))

    # 6. depends_on_usage — depends_on 声明的依赖是否在 inputs 中实际引用
    for s in plan.steps:
        if not s.depends_on:
            continue
        inputs_str = str(s.inputs)
        refs_in_params = extract_refs(inputs_str)
        used_refs = {ref[0] for ref in refs_in_params}
        unused_deps = set(s.depends_on) - used_refs
        if unused_deps:
            issues.append(ContradictionIssue(
                severity=IssueSeverity.MEDIUM,
                message=f"步骤 {s.step_id} 声明了 depends_on={s.depends_on}，但 inputs 中未实际引用 {sorted(unused_deps)} 的输出，建议在 inputs 中添加 ${', '.join(f'{d}.field' for d in unused_deps)} 引用，或移除不必要的依赖",
                check_name="depends_on_usage",
                node_id=s.step_id,
            ))

    # 7. empty_outputs_depended — 上游步骤 outputs 为空但下游声明了 depends_on
    for s in plan.steps:
        if not s.outputs and depended_by_map[s.step_id]:
            issues.append(ContradictionIssue(
                severity=IssueSeverity.HIGH,
                message=f"步骤 {s.step_id} 的 outputs 为空，但步骤 {sorted(depended_by_map[s.step_id])} 声明了 depends_on 依赖它，建议在步骤 {s.step_id} 的 outputs 中声明输出字段",
                check_name="empty_outputs_depended",
                node_id=s.step_id,
            ))

    # 8. ref_format_compatibility — $ref 格式兼容性检查（${s1.field} 格式）
    for s in plan.steps:
        inputs_str = str(s.inputs)
        if "${" in inputs_str:
            issues.append(ContradictionIssue(
                severity=IssueSeverity.LOW,
                message=f"步骤 {s.step_id} 的 inputs 中使用了 ${{...}} 格式的占位符，建议统一使用 $step_id.field 格式（如 $s1.address）",
                check_name="ref_format_compatibility",
                node_id=s.step_id,
            ))

    # 构造 CheckResult：装饰器从 .issues 提取并汇入 IssueReport
    result = CheckResult()
    for issue in issues:
        result.add_issue(issue)
    return result


def format_issues(issues: List[BaseIssue]) -> str:
    """格式化 Issue 列表为可读字符串"""
    if not issues:
        return "无矛盾问题"

    lines: List[str] = []
    lines.append(f"共检测到 {len(issues)} 个问题:")
    for issue in issues:
        node_info = f" (节点: {issue.node_id})" if issue.node_id else ""
        check_prefix = f" [{issue.check_name}]" if issue.check_name else ""
        lines.append(f"  - [{issue.severity.value.upper()}]{check_prefix}{node_info}: {issue.message}")
    return "\n".join(lines)


def parse_error_detail(e: Exception) -> Dict[str, Any]:
    """解析 Plan 创建失败的错误详情"""
    error_detail = {
        "error_type": type(e).__name__,
        "missing_fields": [],
        "model_output_type": "未知",
        "error_message": str(e),
        "parsed_errors": [],
    }

    if hasattr(e, 'errors'):
        for err in e.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "")
            error_detail["parsed_errors"].append({"loc": loc, "msg": msg})

            if "Input should be a valid string" in msg and "input_type=dict" in str(e):
                error_detail["model_output_type"] = "inputs 为字典而非字符串"
            elif "missing" in msg.lower():
                error_detail["missing_fields"].append(loc)

    return error_detail

