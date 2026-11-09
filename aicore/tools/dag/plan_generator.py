"""Plan 生成器：验证结构化 Plan 并输出可执行的 PlanGeneratorOutput"""

import logging
import re

from typing import Annotated, List, Dict, Any, Optional, Type, Union, Literal
from aicore.tools.dag.operator_registry import OperatorRegistry
from pydantic import BaseModel, Field

from aicore.tools.dag.operator_models import (
    POISearchParams,
    POISearchOutput,
    NavigationParams,
    NavigationOutput,
    SongSearchParams,
    SongSearchOutput,
    PlaylistSearchParams,
    PlaylistSearchOutput,
    AlbumSearchParams,
    AlbumSearchOutput,
    AudioPlayParams,
    AudioPlayOutput,
    CarControlParams,
    CarControlOutput,
    WebSearchParams,
    WebSearchOutput,
    ConditionParams,
    ConditionOutput,
    MemoryRecallParams,
    MemoryRecallOutput,
    BaseSchema,
)
from aicore.tools.dag.base_classes import (
    AvailableOperator,
    detect_cycle,
    _REF_PATTERN,
    _extract_nested_model_types,
)
from aicore.tools.dag.issues import (
    ContradictionIssue,
    IssueSeverity,
    CheckResult,
    _issue_utils,
)

logger = logging.getLogger(__name__)

# Condition then 值含自然语言引用（如 $s2.poi_list中第一个符合条件的场所），
# _REF_PATTERN 的 \w 匹配 Unicode 会把中文后缀吞进 field 名导致误报；
# 此处用 re.ASCII 限定 field 段，仅匹配 $step_id.field 形式的 ASCII 占位符，
# 不影响 dag_executor 共享的 _REF_PATTERN（运行时靠 LLM 兜底解析自然语言引用）
_REF_ASCII_PATTERN = re.compile(r"\$(\w+)\.([\w.\[\]]+)", re.ASCII)


def _collect_all_field_names(
    model: Union[Type[BaseModel], BaseModel], prefix: str = ""
) -> set[str]:
    """递归收集 Pydantic 模型的所有字段路径（含嵌套路径，如 business.parking_type）。

    支持两种输入：
    - Pydantic 模型类：收集类定义的显式字段
    - Pydantic 模型实例：同时收集类定义字段 + 实例上通过 extra="allow" 添加的动态字段

    嵌套 BaseModel 字段会拼接父路径：business → business.parking_type。
    同时保留顶层字段名（如 business）和嵌套路径（如 business.parking_type），
    让 $ref 既能引用整个嵌套对象（$s2.business），也能引用嵌套子字段
    （$s2.business.parking_type）。

    output_model 一律优先用 title 作为字段名：当字段有 title 属性时，
    以 title 为主名，同时保留原 Python 字段名作为 fallback 别名，使 LLM
    生成的 step_output 声明（如 address/city）能正确匹配到实际字段
    （如 name/cityname）。
    """
    if not model:
        return set()

    model_class = model if isinstance(model, type) else type(model)
    if not hasattr(model_class, "model_fields"):
        return set()

    field_names = set()

    for param_name, field_info in model_class.model_fields.items():
        title = getattr(field_info, "title", None)
        param_path = f"{prefix}.{param_name}" if prefix else param_name
        if title:
            title_path = f"{prefix}.{title}" if prefix else str(title)
            field_names.add(title_path)
            field_names.add(param_path)
        else:
            field_names.add(param_path)
        nested_models = _extract_nested_model_types(field_info.annotation)
        for inner_type in nested_models:
            field_names.update(_collect_all_field_names(inner_type, param_path))
        if not isinstance(model, type):
            field_value = getattr(model, param_name, None)
            if isinstance(field_value, BaseModel):
                field_names.update(_collect_all_field_names(field_value, param_path))

    if not isinstance(model, type) and hasattr(model, "__pydantic_extra__"):
        extra_fields = model.__pydantic_extra__ or {}
        for extra_name in extra_fields:
            extra_path = f"{prefix}.{extra_name}" if prefix else extra_name
            field_names.add(extra_path)
            extra_value = extra_fields.get(extra_name)
            if isinstance(extra_value, BaseModel):
                field_names.update(_collect_all_field_names(extra_value, extra_path))

    return field_names


class PlanStepBase(BaseSchema):
    """PlanStep 公共字段基类：仅承载与 op 无关的通用字段。

    step_input / step_output 的具体类型由各 op 变体钉死，与算子
    input/output model 对齐，避免 Union 歧义。step_output 移至各子类为
    Optional[XxxOutput]，运行时由算子填充实际值；下游 $ref 引用的合法
    字段集统一由 _build_step_output_map 从算子 output_model 全量字段
    （含 title 别名与嵌套路径）推导，不再依赖 step_output 的声明。
    """

    step_id: str = Field(description="步骤标识，如 s1, s2")
    step_goal: str = Field(description="本步骤的可量化的具体目标")
    depends_on: List[str] = Field(description="直接依赖的步骤ID列表")


class POISearchStep(PlanStepBase):
    op: Literal["POISearch"] = "POISearch"
    step_input: List[POISearchParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[POISearchOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")

class NavigationStep(PlanStepBase):
    op: Literal["Navigation"] = "Navigation"
    step_input: List[NavigationParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[NavigationOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class SongSearchStep(PlanStepBase):
    op: Literal["SongSearch"] = "SongSearch"
    step_input: List[SongSearchParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[SongSearchOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class PlaylistSearchStep(PlanStepBase):
    op: Literal["PlaylistSearch"] = "PlaylistSearch"
    step_input: List[PlaylistSearchParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[PlaylistSearchOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class AlbumSearchStep(PlanStepBase):
    op: Literal["AlbumSearch"] = "AlbumSearch"
    step_input: List[AlbumSearchParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[AlbumSearchOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class AudioPlayStep(PlanStepBase):
    op: Literal["AudioPlay"] = "AudioPlay"
    step_input: List[AudioPlayParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[AudioPlayOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class CarControlStep(PlanStepBase):
    op: Literal["CarControl"] = "CarControl"
    step_input: List[CarControlParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[CarControlOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class WebSearchStep(PlanStepBase):
    op: Literal["WebSearch"] = "WebSearch"
    step_input: List[WebSearchParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[WebSearchOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class ConditionStep(PlanStepBase):
    op: Literal["Condition"] = "Condition"
    step_input: List[ConditionParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[Dict[str, Any]] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


class MemoryRecallStep(PlanStepBase):
    op: Literal["MemoryRecall"] = "MemoryRecall"
    step_input: List[MemoryRecallParams] = Field(description="本步骤入参，缺失信息引用属性链输出（$step_id.field）")
    step_output: List[MemoryRecallOutput] = Field(description="本步骤出参，值留空（字段供下游步骤通过属性链+占位符表达引用）")


# step_input 类型在 schema 层钉死，消除 smart Union 猜测导致的 op params 错配
PlanStep = Union[
        POISearchStep,
        NavigationStep,
        SongSearchStep,
        PlaylistSearchStep,
        AlbumSearchStep,
        AudioPlayStep,
        CarControlStep,
        WebSearchStep,
        ConditionStep,
        MemoryRecallStep
]


class StructuredPlan(BaseSchema):
    goal: str = Field(description="任务目标")
    steps: List[PlanStep] = Field(description="详细步骤列表")

    @_issue_utils.capture_issues()
    def check_contradictions(self) -> CheckResult:
        """检查 PlanStep 之间的矛盾与不一致，返回 CheckResult（含矛盾 Issue 列表）。

        装饰器化：检查到问题时构造 ContradictionIssue 放入 CheckResult.issues（不 raise），
        装饰器自动从返回值提取 issues 汇入 _current_issue_report ContextVar 指向的 IssueReport。

        编排方法：构造中间状态（step_ids / step_output_map / op 映射）后依次调用 8 个子检查，
        各子检查返回 List[ContradictionIssue]，主方法聚合到 CheckResult。

        检查项：
        1. step_id_uniqueness   — step_id 唯一性
        2. depends_on_integrity — depends_on 引用完整性
        3. ref_step_existence   — $ref 占位符引用的 step_id 存在性
        4. ref_field_declared   — $ref 引用的 field 在上游 step_output 中是否声明
        5. params_type_match    — params 类型与 op 对应的算子 input_model 是否一致
        6. params_field_validity — 必填字段非空校验（枚举/范围已由 Literal/Field 在实例化时校验）
        7. cycle_detection      — 循环依赖
        8. condition_then_ref_coverage — Condition then 中 $ref 必须在 facts 声明
        """
        step_ids = {s.step_id for s in self.steps}
        op_to_output_model = self._build_op_output_model_map()
        step_output_map = self._build_step_output_map(op_to_output_model)
        op_to_input_model = self._build_op_input_model_map()

        issues: List[ContradictionIssue] = []
        issues.extend(self._check_step_id_uniqueness())
        issues.extend(self._check_depends_on_integrity(step_ids))
        issues.extend(self._check_ref_validity(step_ids, step_output_map))
        issues.extend(self._check_params_type_match(op_to_input_model))
        issues.extend(self._check_params_field_validity(op_to_input_model))
        issues.extend(self._check_cycle_detection())
        issues.extend(self._check_condition_then_ref_coverage())

        result = CheckResult()
        for issue in issues:
            result.add_issue(issue)
        return result

    def _build_step_output_map(
        self, op_to_output_model: Dict[str, type]
    ) -> Dict[str, set[str]]:
        """构建每个 step 的 step_output 字段集合。

        字段集合来源于算子 output_model 全量字段（含 title 别名与嵌套路径如
        business.business_area），作为下游 $ref 的合法目标；不再读取 step_output
        声明。Condition 算子输出为动态字段（ConditionOutput extra="allow" 无静态
        字段），从 step_input 的 ConditionParams 中收集 rules[].then / default 的 key。
        """
        step_output_map: Dict[str, set[str]] = {}
        for s in self.steps:
            field_set: set[str] = set()
            # 来源：output_model 全量字段（含 title 别名与嵌套路径）
            output_model = op_to_output_model.get(s.op)
            # ConditionOutput 等动态输出模型（extra="allow" 无静态字段）跳过：
            # 输出字段由 rules[].then / default 动态决定，下方 Condition 分支补充收集
            if (
                output_model
                and hasattr(output_model, "model_fields")
                and output_model.model_fields
            ):
                field_set.update(_collect_all_field_names(output_model))
            # Condition 算子输出为动态字段（ConditionOutput extra="allow" 无静态字段），
            # 实际输出字段由 rules[].then 和 default 的 key 决定，
            # 需从 step_input 的 ConditionParams 中补充收集
            if s.op == "Condition":
                inps = s.step_input
                items = inps if isinstance(inps, list) else [inps]
                for item in items:
                    if isinstance(item, ConditionParams):
                        for rule in item.rules:
                            field_set.update(rule.then.keys())
                        field_set.update(item.default.keys())
                    elif isinstance(item, dict):
                        for rule in item.get("rules", []) or []:
                            then = (
                                rule.get("then", {}) if isinstance(rule, dict) else {}
                            )
                            field_set.update(then.keys())
                        field_set.update((item.get("default") or {}).keys())
            step_output_map[s.step_id] = field_set
        return step_output_map

    def _check_step_id_uniqueness(self) -> List[ContradictionIssue]:
        """检查项 1：step_id 唯一性。"""
        issues: List[ContradictionIssue] = []
        seen: Dict[str, int] = {}
        for s in self.steps:
            seen[s.step_id] = seen.get(s.step_id, 0) + 1
        for sid, cnt in seen.items():
            if cnt > 1:
                issues.append(
                    ContradictionIssue(
                        severity=IssueSeverity.HIGH,
                        message=f"step_id 重复: {sid} 出现了 {cnt} 次",
                        check_name="step_id_uniqueness",
                    )
                )
        return issues

    def _check_depends_on_integrity(
        self, step_ids: set[str]
    ) -> List[ContradictionIssue]:
        """检查项 2：depends_on 引用完整性。"""
        issues: List[ContradictionIssue] = []
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in step_ids:
                    issues.append(
                        ContradictionIssue(
                            severity=IssueSeverity.CRITICAL,
                            message=f"步骤 {s.step_id} 的 depends_on 引用了不存在的步骤: {dep}（可用: {sorted(step_ids)}）",
                            check_name="depends_on_integrity",
                            node_id=s.step_id,
                        )
                    )
        return issues

    def _check_ref_validity(
        self, step_ids: set[str], step_output_map: Dict[str, set[str]]
    ) -> List[ContradictionIssue]:
        """检查项 3 & 4：$ref 占位符合法性（step_id 存在 + field 声明）。

        遍历 step_input 各元素，合并字段到统一 dict 供 $ref 扫描。
        匹配 $step_id.field 或 $step_id.field[N].subfield 嵌套路径
        （与 dag_executor._REF_PATTERN 一致，支持 [N] 索引写法）。
        条件算子例外：仅检测 facts 的 $ref；rules 的 when/then 含自然语言与模板引用。
        """
        issues: List[ContradictionIssue] = []
        for s in self.steps:
            params_dict: Dict[str, Any] = {}
            inps = s.step_input
            if isinstance(inps, list):
                for item in inps:
                    if isinstance(item, ConditionParams):
                        params_dict["facts"] = item.facts
                    elif isinstance(item, BaseModel):
                        params_dict.update(item.model_dump())
                    elif isinstance(item, dict):
                        if s.op == "Condition" and "facts" in item:
                            params_dict["facts"] = item["facts"]
                        else:
                            params_dict.update(item)
            elif isinstance(inps, ConditionParams):
                params_dict["facts"] = inps.facts
            elif isinstance(inps, BaseModel):
                params_dict.update(inps.model_dump())
            elif isinstance(inps, dict):
                if s.op == "Condition" and "facts" in inps:
                    params_dict["facts"] = inps["facts"]
                else:
                    params_dict.update(inps)
            refs_in_params = _REF_PATTERN.findall(str(params_dict))
            for ref_step_id, ref_field in refs_in_params:
                if ref_step_id not in step_ids:
                    issues.append(
                        ContradictionIssue(
                            severity=IssueSeverity.CRITICAL,
                            message=f"步骤 {s.step_id} 的参数 $ref 引用了不存在的步骤: ${ref_step_id}.{ref_field}（可用: {sorted(step_ids)}）",
                            check_name="ref_step_existence",
                            node_id=s.step_id,
                        )
                    )
                elif (
                    ref_step_id not in step_output_map
                    or not step_output_map[ref_step_id]
                ):
                    issues.append(
                        ContradictionIssue(
                            severity=IssueSeverity.HIGH,
                            message=f"步骤 {s.step_id} 的参数 $ref 引用了步骤 {ref_step_id}，但该步骤未声明 step_output: ${ref_step_id}.{ref_field}",
                            check_name="ref_field_declared",
                            node_id=s.step_id,
                        )
                    )
                else:
                    # 归一化 ref_field 后与 step_output_map 比对：
                    # dag_executor 支持 songs[0].genre / songs.0.genre 写法，
                    # 归一化（移除 [N] 索引与数字段）为 songs.genre，与模型字段路径一致
                    normalized = re.sub(r"\[\d+\]", "", ref_field)
                    normalized = ".".join(
                        seg for seg in normalized.split(".") if not seg.isdigit()
                    )
                    if normalized not in step_output_map[ref_step_id]:
                        issues.append(
                            ContradictionIssue(
                                severity=IssueSeverity.HIGH,
                                message=f"步骤 {s.step_id} 的参数 $ref 引用了步骤 {ref_step_id} 未声明的输出字段: ${ref_step_id}.{ref_field}",
                                check_name="ref_field_declared",
                                node_id=s.step_id,
                            )
                        )
        return issues

    def _build_op_output_model_map(self) -> Dict[str, type]:
        """构建 op_type → output_model 映射。"""
        op_to_output_model: Dict[str, type] = {}
        for op_type, op_info in OperatorRegistry.get_registry_model().operators.items():
            op_to_output_model[op_type] = op_info.output_model
        return op_to_output_model

    def _build_op_input_model_map(self) -> Dict[str, type]:
        """构建 op_type → input_model 映射。"""
        op_to_input_model: Dict[str, type] = {}
        for op_type, op_info in OperatorRegistry.get_registry_model().operators.items():
            op_to_input_model[op_type] = op_info.input_model
        return op_to_input_model

    def _check_params_type_match(
        self, op_to_input_model: Dict[str, type]
    ) -> List[ContradictionIssue]:
        """检查项 5：params 类型与算子 input_model 匹配（阻断性检查）。

        step_input 为各算子对应的 input_model 列表（PlanStep discriminated union
        已按 op 钉死类型）。本检查按 op 期望的 input_model 做严格 isinstance 校验
        （列表中所有元素匹配即通过），类型不一致时产出 HIGH Issue 阻断执行。
        """
        issues: List[ContradictionIssue] = []
        for s in self.steps:
            expected_input_model = op_to_input_model.get(s.op)
            if not expected_input_model:
                continue
            inps = s.step_input
            if isinstance(inps, list):
                matched = all(isinstance(item, expected_input_model) for item in inps)
            else:
                matched = isinstance(inps, expected_input_model)
            if not matched:
                issues.append(
                    ContradictionIssue(
                        severity=IssueSeverity.HIGH,
                        message=(
                            f"步骤 {s.step_id} 的 step_input 类型 {type(inps).__name__} "
                            f"与算子 {s.op} 的入参模型 {expected_input_model.__name__} 不一致，"
                        ),
                        check_name="params_type_match",
                        node_id=s.step_id,
                    )
                )
        return issues

    def _check_params_field_validity(
        self, op_to_input_model: Dict[str, type]
    ) -> List[ContradictionIssue]:
        """检查项 6：必填字段非空校验。

        Pydantic 只检查必填字段「存在」，不检查「值非空」——query="" 也能通过实例化。
        本检查对 expected_input_model 中所有 required 字段做非空校验，
        允许值中包含 $ref 占位符（依赖注入阶段会替换），但纯空字符串/None 视为缺失。
        枚举值与数值范围已由 Literal / Field(ge=, le=) 在实例化时校验，此处不重复。
        """
        issues: List[ContradictionIssue] = []
        for s in self.steps:
            expected_input_model = op_to_input_model.get(s.op)
            if not expected_input_model:
                continue
            inps = s.step_input
            # 提取匹配 expected_input_model 的元素做字段校验
            # 类型不匹配由 #5 params_type_match 报告，此处仅校验匹配元素
            if isinstance(inps, list):
                matched_items = [
                    item for item in inps if isinstance(item, expected_input_model)
                ]
            elif isinstance(inps, expected_input_model):
                matched_items = [inps]
            else:
                matched_items = []

            for inp in matched_items:
                # 遍历 expected_input_model 的字段，检查 required 字段非空
                for field_name, field_info in expected_input_model.model_fields.items():
                    if not field_info.is_required():
                        continue
                    value = getattr(inp, field_name, None)
                    # 允许 $ref 占位符（字符串中含 $xxx.yyy），但纯空字符串/None 视为缺失
                    if value is None or (
                        isinstance(value, str) and value.strip() == ""
                    ):
                        issues.append(
                            ContradictionIssue(
                                severity=IssueSeverity.HIGH,
                                message=(
                                    f"步骤 {s.step_id} 的必填字段 '{field_name}' 为空，"
                                    f"算子 {s.op} 要求提供 {field_info.description or field_name}"
                                ),
                                check_name="params_field_validity",
                                node_id=s.step_id,
                            )
                        )
        return issues

    def _check_cycle_detection(self) -> List[ContradictionIssue]:
        """检查项 7：循环依赖检测（复用 base_classes.detect_cycle，DFS 三色标记法）。"""
        issues: List[ContradictionIssue] = []
        adj: Dict[str, List[str]] = {s.step_id: list(s.depends_on) for s in self.steps}
        cycle = detect_cycle(adj)
        if cycle:
            cycle_str = " → ".join(cycle)
            issues.append(
                ContradictionIssue(
                    severity=IssueSeverity.CRITICAL,
                    message=f"步骤之间存在循环依赖: {cycle_str}（循环路径: {cycle}）",
                    check_name="cycle_detection",
                )
            )
        return issues

    def _check_condition_then_ref_coverage(self) -> List[ContradictionIssue]:
        """检查项 8：condition_then_ref_coverage — Condition then 中 $ref 必须在 facts 声明。

        facts 是 Condition 算子声明的依赖字段列表，then 中若用 $ref 引用上游字段，
        该 $ref 必须出现在 facts 中，否则视为"未声明的依赖"。
        仅校验 then 的字符串值（default 不参与，按现有 ref 校验例外约定）。

        then 值常含自然语言引用（如 $s2.poi_list中第一个符合条件的场所），
        用 _REF_ASCII_PATTERN（re.ASCII）避免 \\w 匹配中文把后缀吞进 field 名。
        """
        issues: List[ContradictionIssue] = []
        for s in self.steps:
            if s.op != "Condition":
                continue
            inps = s.step_input
            if isinstance(inps, list):
                condition_params_list = [
                    i for i in inps if isinstance(i, ConditionParams)
                ]
            elif isinstance(inps, ConditionParams):
                condition_params_list = [inps]
            else:
                continue
            for inp in condition_params_list:
                facts_set = set(inp.facts)
                for rule_idx, rule in enumerate(inp.rules):
                    for field_name, value in rule.then.items():
                        if not isinstance(value, str):
                            continue
                        refs_in_value = _REF_ASCII_PATTERN.findall(value)
                        for ref_step_id, ref_field in refs_in_value:
                            ref_str = f"${ref_step_id}.{ref_field}"
                            if ref_str not in facts_set:
                                issues.append(
                                    ContradictionIssue(
                                        severity=IssueSeverity.HIGH,
                                        message=(
                                            f"步骤 {s.step_id} 的 Condition 规则 "
                                            f"rules[{rule_idx}].then.{field_name} "
                                            f"引用了 {ref_str}，"
                                            f"但该引用未在 facts 中声明"
                                        ),
                                        check_name="condition_then_ref_coverage",
                                        node_id=s.step_id,
                                    )
                                )
        return issues


def _get_available_operators() -> List[AvailableOperator]:
    """从算子注册表获取所有可用算子的详细信息"""
    registry_model = OperatorRegistry.get_registry_model()
    operators = []

    for op_type, op_info in registry_model.operators.items():
        input_schema = {}
        output_schema = {}

        if op_info.input_model:
            input_schema = op_info.input_model.model_json_schema()
        if op_info.output_model:
            output_schema = op_info.output_model.model_json_schema()

        operators.append(
            AvailableOperator(
                operator_type=op_type,
            ).model_copy(
                update={
                    "description": op_info.description,
                    "input_schema": input_schema,
                    "output_schema": output_schema,
                }
            )
        )

    return operators


def _generate_operator_description() -> str:
    """动态生成算子类型及参数描述"""
    registry_model = OperatorRegistry.get_registry_model()
    lines = []

    for op_info in registry_model.operators.values():
        input_params = _get_model_fields(op_info.input_model)
        output_params = _get_model_fields(op_info.output_model, use_title=True)

        input_str = ", ".join(input_params) if input_params else "无参数"
        output_str = ", ".join(output_params) if output_params else "无输出"

        lines.append(f"- {op_info.operator_type}: {op_info.description}")
        lines.append(f"  入参：{input_str}")
        lines.append(f"  出参：{output_str}")
    return "\n".join(lines)


def _get_model_fields(
    model_class: Type[BaseModel], use_title: bool = False, prefix: str = ""
) -> List[str]:
    """递归获取模型的字段描述，收集各层（含嵌套模型）字段作为嵌套路径列表。

    嵌套 BaseModel 字段会拼接父路径：business → business.parking_type。
    让 LLM 在算子描述中看到完整的嵌套字段路径，从而生成规范的
    $step_id.field.subfield 占位符。

    Args:
        model_class: Pydantic 模型类
        use_title: 若为 True，字段优先用 title 属性作为名称
                   （output_model 一律优先用 title）
        prefix: 父路径前缀（递归时拼接，如 "business"）
    """
    if not model_class:
        return []

    params = []
    for param_name, field_info in model_class.model_fields.items():
        field_type = field_info.annotation
        field_desc = field_info.description or ""

        # title 优先作为字段名
        if use_title and getattr(field_info, "title", None):
            display_name = str(field_info.title)
        else:
            display_name = param_name

        # 构建当前字段路径（含父路径前缀）
        current_path = f"{prefix}.{display_name}" if prefix else display_name

        nested_models = _extract_nested_model_types(field_type)

        if field_desc:
            field_str = f"{current_path}（{field_desc}）"
        else:
            field_str = current_path
        if not nested_models:
            params.append(field_str)

        for inner_type in nested_models:
            params.extend(
                _get_model_fields(inner_type, use_title=use_title, prefix=current_path)
            )

    return params


class PlanGeneratorInput(BaseSchema):
    structured_plan: StructuredPlan = Field(description="结构化Plan")


class PlanGeneratorOutput(BaseSchema):
    """Plan生成器输出（强类型）"""

    goal: str = Field(description="任务目标")
    steps: List[PlanStep] = Field(default_factory=list, description="步骤列表")
    issues: List[ContradictionIssue] = Field(
        default_factory=list, description="矛盾检查结果"
    )


async def _plan_generator_worker(
    structured_plan: StructuredPlan,
) -> PlanGeneratorOutput:
    """Plan生成器工作函数：接收结构化Plan，验证并返回处理后的Plan

    白名单检查与矛盾检查均产出 ContradictionIssue，不再 raise ValueError，
    与 dag_build/safety_scan/execution 阶段的 issue 化处理一致。
    """
    structured_plan = StructuredPlan.model_validate(structured_plan)
    available_ops = _get_available_operators()
    operator_types = {op.operator_type for op in available_ops}

    # 收集所有矛盾检查结果（含白名单检查）
    contradictions: List[ContradictionIssue] = []

    # 白名单检查：算子不在白名单中产出 CRITICAL Issue（替代原 raise ValueError）
    for step in structured_plan.steps:
        if step.op not in operator_types:
            contradictions.append(
                ContradictionIssue(
                    severity=IssueSeverity.CRITICAL,
                    message=f"步骤 {step.step_id} 的算子 '{step.op}' 不在白名单中，可用算子: {', '.join(sorted(operator_types))}",
                    check_name="operator_whitelist",
                    node_id=step.step_id,
                    operator_type=step.op,
                )
            )

    # 检查 PlanStep 矛盾（check_contradictions 返回 CheckResult，取 .issues）
    # @capture_issues 装饰器在 _current_issue_report 未设置时（_plan_generator_worker
    # 调用时机早于 plan_processor 的 issue_scope）不会自动汇入 IssueReport，故手动 extend。
    contradictions.extend(structured_plan.check_contradictions().issues)

    if contradictions:
        contradiction_msg = ";\n".join(
            f"[{c.check_name}] {c.message}" for c in contradictions
        )
        logger.error(f"Plan 存在矛盾:\n{contradiction_msg}")
    return PlanGeneratorOutput(
        goal=structured_plan.goal,
    ).model_copy(
        update={
            "steps": structured_plan.steps,
            "issues": contradictions,
        }
    )
