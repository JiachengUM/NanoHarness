"""DAG 静态检查：输入一个 BareDag[PlanStepV1] 和已注册 tool 名称集合，返回所有潜在问题。

以下检查始终全部执行（不提前中断），以便 repair 层拿到尽可能完整的错误信息：
1. step_id 唯一性
2. depends_on 中每个 dep 存在且不是自身；每个 op 在已注册 tools 中可找到
3. 环检测（build_dag 已过滤未知 dep 和 self-dep，不会产生假阳性）
4. inputs 模板引用必须能在 depends_on 的传递闭包（祖先集合）中找到，
   即 A -> B -> C 时，C 只声明 depends_on: [B] 也可以直接 ref A
5. inputs 中每个 {{...}} 标记逐一校验（单次扫描，两层判断）：
   a) trim 后必须是受限 jq path（{{ .step_id.outputs.ConceptName[0].attr }} 或
      {{ .step_id.outputs.ConceptName[].attr }}）——inputs 不支持 Jinja 风格的 if/else/end
      等控制流写法，也不支持函数、管道、逻辑/比较运算、切片；写进 {{...}} 里的非 path
      内容一律按 LogicRefMalformedError 报告。
   b) 形状合法的 path，除 step_id 外的每一段还必须能对齐被引用 step 实际声明的
      outputs：outputs 字面量、ConceptName、is_list 决定的下标/数组迭代形状、
      attribute_name 是否已声明——分别对应 LogicRefMalformedError /
      LogicRefConceptMismatchError / LogicRefShapeMismatchError /
      LogicRefUnknownAttributeError。
   只覆盖 inputs 的 {{...}} 引用，不覆盖 condition 的 jq 引用（jq 是完整表达式语言，
   从中解析出线性路径前缀是单独的、更大的问题，这里不做）。
6. condition（若非 None）必须是合法可编译的 jq 表达式；
   condition 中引用的 step_id 同样必须落在 depends_on 传递闭包内，规则同第 4 项
"""

import re
from collections.abc import Container
from typing import Any

import jq

from aicore.agents.plan.dag import DAG, CycleDetected
from aicore.agents.plan.dag_runner import BareDag
from aicore.agents.plan.experiment.plan_schema_v1 import ConceptOutput, PlanStepV1
from aicore.agents.plan.criterion import MAX_ASSERTIONS, JqExprCriterion
from aicore.agents.plan.errors import (
    PlanError,
    PlanErrorDetail,
    LogicDupStepIdError,
    LogicSelfDepError,
    LogicUnknownDepError,
    LogicUnknownOpError,
    LogicCycleError,
    LogicUndeclaredRefError,
    LogicInvalidConditionError,
    LogicInvalidSuccessCheckError,
    LogicSuccessCheckNotSelfConstrainedError,
    LogicRefMalformedError,
    LogicRefConceptMismatchError,
    LogicRefShapeMismatchError,
    LogicRefUnknownAttributeError,
)

# 模板引用：{{ .step_id.outputs.ConceptName[0].attribute_name }}
# 也支持 jq 数组迭代投影：{{ .step_id.outputs.ConceptName[].attribute_name }}。
# 这个正则同时被 plan_dag_runner.py 导入用于运行时替换；路径语法本身由
# _parse_input_jq_path 做严格校验，正则只负责找出 {{...}} 边界。
_REF_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}", re.DOTALL)

# 宽松版本：只负责找出所有 {{...}} 标记的边界，不对内容做任何路径语法假设。
# 仅用于第 5 项检查；路径语法的唯一定义是 _parse_input_jq_path。
_ANY_TAG_RE = _REF_RE

# jq condition 中的 step 输出引用：.step_id.outputs.ConceptName.attribute_name
_CONDITION_REF_RE = re.compile(r"\.([A-Za-z_]\w*)\.outputs\b")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")

type _InputPathPart = str | int


def _iter_input_tags(inputs: dict[str, Any]) -> list[str]:
    """递归遍历 step inputs，收集每个 {{...}} 标记 trim 后的原始内容（不做任何合法性判断）。

    _extract_input_refs（只要合法 ref）和第 5 项检查（合法性判断本身）共用这一次树遍历，
    避免同一份递归 scan() 逻辑维护两份。
    """
    tags: list[str] = []

    def scan(v: Any) -> None:
        if isinstance(v, str) and "{{" in v:
            for m in _ANY_TAG_RE.finditer(v):
                tags.append(m.group(1).strip())
        elif isinstance(v, dict):
            d: dict[str, Any] = v  # type: ignore[assignment]
            for val in d.values():
                scan(val)
        elif isinstance(v, list):
            lst: list[Any] = v  # type: ignore[assignment]
            for item in lst:
                scan(item)

    scan(inputs)
    return tags


def _extract_input_refs(inputs: dict[str, Any]) -> list[str]:
    """从 step inputs 中提取所有形状合法的模板引用路径（如 .s1.outputs.Concept[].field）。

    形状不合法的标记（如误写的 if/else/end）不在这里报告，由第 5 项检查单独处理。
    """
    return [
        tag for tag in _iter_input_tags(inputs) if _parse_input_jq_path(tag) is not None
    ]


def _extract_input_ref_step_ids(inputs: dict[str, Any]) -> set[str]:
    """从 step inputs 中提取所有模板引用的 step_id（路径第一段）。"""
    step_ids: set[str] = set()
    for ref in _extract_input_refs(inputs):
        parts = _parse_input_jq_path(ref)
        if parts and isinstance(parts[0], str):
            step_ids.add(parts[0])
    return step_ids


def _parse_input_jq_path(expr: str) -> list[_InputPathPart] | None:
    """解析 inputs 模板中的受限 jq path。

    仅允许：
    - 对象键访问：.field
    - 数组下标：[0] 或 .[0]
    - 数组迭代：[] 或 .[]

    明确不支持切片、管道、函数、比较/逻辑运算、字符串 key 等完整 jq 语法。
    """
    expr = expr.strip()
    if not expr or any(ch.isspace() for ch in expr) or not expr.startswith("."):
        return None

    parts: list[_InputPathPart] = []
    i = 0
    n = len(expr)

    def parse_bracket(pos: int) -> tuple[_InputPathPart, int] | None:
        if pos + 1 < n and expr[pos : pos + 2] == "[]":
            return "*", pos + 2
        m = re.match(r"\[(\d+)\]", expr[pos:])
        if not m:
            return None
        return int(m.group(1)), pos + len(m.group(0))

    while i < n:
        ch = expr[i]
        if ch == ".":
            i += 1
            if i >= n:
                return None
            if expr[i] == "[":
                bracket = parse_bracket(i)
                if bracket is None:
                    return None
                part, i = bracket
                parts.append(part)
                continue
            m = _IDENT_RE.match(expr, i)
            if not m:
                return None
            parts.append(m.group(0))
            i = m.end()
            continue

        if ch == "[":
            bracket = parse_bracket(i)
            if bracket is None:
                return None
            part, i = bracket
            parts.append(part)
            continue

        return None

    return parts or None


def _validate_ref_against_schema(
    step_id: str,
    ref: str,
    outputs_by_step: dict[str, ConceptOutput],
) -> PlanErrorDetail | None:
    """校验 ref 路径除 step_id 外的每一段，是否对齐被引用 step 实际声明的 outputs。

    只处理 inputs 的 {{...}} 模板引用，不处理 condition 的 jq 引用（见模块 docstring 第 5 项）。
    这里针对的是当前固定使用扁平 SimpleConcept 的场景；一旦 ConceptOutput.concept 改用支持
    children 嵌套的 Concept，这里需要改成沿路径逐层递归校验，且"ConceptName 后只允许一个
    数组下标或 [] 迭代段"这条上游假设也需要一并重新评估（多层嵌套 list 场景下可能需要多个 []）。
    """
    parts = _parse_input_jq_path(ref)
    if not parts or not isinstance(parts[0], str):
        return LogicRefMalformedError(step_id=step_id, ref=ref, found_segment=None)

    ref_step_id = parts[0]
    co = outputs_by_step.get(ref_step_id)
    if co is None:
        return None  # 未知 / 非祖先 step，已由 unknown_dep / undeclared_ref 覆盖

    if len(parts) < 2 or parts[1] != "outputs":
        return LogicRefMalformedError(
            step_id=step_id,
            ref=ref,
            found_segment=str(parts[1]) if len(parts) >= 2 else None,
        )

    rest = parts[2:]
    if not rest:
        return LogicRefMalformedError(step_id=step_id, ref=ref, found_segment=None)

    actual_concept, rest = rest[0], rest[1:]
    if not isinstance(actual_concept, str):
        return LogicRefMalformedError(
            step_id=step_id, ref=ref, found_segment=str(actual_concept)
        )
    if actual_concept != co.concept.name:
        return LogicRefConceptMismatchError(
            step_id=step_id,
            ref=ref,
            ref_step_id=ref_step_id,
            expected_concept=co.concept.name,
            actual_concept=actual_concept,
        )

    expected_count = 2 if co.is_list else 1
    if len(rest) != expected_count:
        return LogicRefShapeMismatchError(
            step_id=step_id,
            ref=ref,
            ref_step_id=ref_step_id,
            is_list=co.is_list,
            reason="segment_count_mismatch",
            expected_segment_count=expected_count,
            actual_segment_count=len(rest),
        )

    if co.is_list:
        index_seg, attr_seg = rest
        if not (index_seg == "*" or isinstance(index_seg, int)):
            return LogicRefShapeMismatchError(
                step_id=step_id,
                ref=ref,
                ref_step_id=ref_step_id,
                is_list=co.is_list,
                reason="invalid_index_segment",
                expected_segment_count=expected_count,
                actual_segment_count=len(rest),
                found_index_segment=str(index_seg),
            )
    else:
        attr_seg = rest[0]

    known_attrs = {a.name for a in co.concept.attributes}
    if not isinstance(attr_seg, str) or attr_seg not in known_attrs:
        return LogicRefUnknownAttributeError(
            step_id=step_id,
            ref=ref,
            ref_step_id=ref_step_id,
            concept_name=co.concept.name,
            attribute=str(attr_seg),
            known_attributes=sorted(known_attrs),
        )

    return None


def _extract_condition_ref_step_ids(condition: str) -> set[str]:
    """从 jq condition 表达式中提取所有 `.step_id.outputs...` 形式引用的 step_id。"""
    return set(_CONDITION_REF_RE.findall(condition))


def _build_ancestors_map(
    steps: list[PlanStepV1], counts: dict[str, int]
) -> dict[str, set[str]]:
    """计算每个 step_id 的祖先集合（depends_on 的传递闭包）。

    只沿着合法边（dep 存在且不是自身）走；出现环时用 visiting 集合截断，
    避免死循环——环本身由第 3 项检查单独报告。
    """
    dep_map: dict[str, list[str]] = {}
    for step in steps:
        dep_map[step.step_id] = [
            dep for dep in step.depends_on if dep in counts and dep != step.step_id
        ]

    cache: dict[str, set[str]] = {}

    def ancestors_of(sid: str, visiting: set[str]) -> set[str]:
        if sid in cache:
            return cache[sid]
        if sid in visiting:
            return set()
        visiting.add(sid)
        result: set[str] = set()
        for dep in dep_map.get(sid, []):
            result.add(dep)
            result |= ancestors_of(dep, visiting)
        visiting.discard(sid)
        cache[sid] = result
        return result

    return {sid: ancestors_of(sid, set()) for sid in dep_map}


def check_dag(dag: BareDag[PlanStepV1], known_ops: Container[str]) -> list[PlanError]:
    """对 DAG 执行以下静态检查，收集并返回所有 PlanError（不提前中断）。"""
    errors: list[PlanError] = []
    steps = dag.nodes
    counts: dict[str, int] = {}

    for step in steps:
        counts[step.step_id] = counts.get(step.step_id, 0) + 1

    # 1. dup step_id（每个重复 id 只报一次）
    seen_dups: set[str] = set()
    for step in steps:
        if counts[step.step_id] > 1 and step.step_id not in seen_dups:
            seen_dups.add(step.step_id)
            errors.append(
                PlanError(
                    source="plan.logic",
                    detail=LogicDupStepIdError(
                        step_id=step.step_id, count=counts[step.step_id]
                    ),
                )
            )

    # 2. deps + op（所有 step 全量检查，不因 dup 跳过）
    for step in steps:
        for dep in step.depends_on:
            if dep == step.step_id:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicSelfDepError(step_id=step.step_id),
                    )
                )
            elif dep not in counts:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicUnknownDepError(step_id=step.step_id, dep_id=dep),
                    )
                )
        if step.op not in known_ops:
            errors.append(
                PlanError(
                    source="plan.logic",
                    detail=LogicUnknownOpError(step_id=step.step_id, op=step.op),
                )
            )

    # 3. 环检测（build_dag 已过滤未知 dep 和 self-dep，不会产生假阳性）
    # topo_levels 按 step_id 去重节点后判断「已排序节点数 == 节点总数」，
    # dup step_id 存在时节点总数 > 唯一 id 数，会被误判成一个 members 为空的环。
    # dup 本身已由第 1 项检查报告，这里先按 step_id 去重再检测，避免把 dup 的
    # 副作用错当成一个真实环重复上报给 repair 层。
    unique_steps = list({step.step_id: step for step in steps}.values())
    try:
        DAG(nodes=unique_steps, edges=dag.edges).topo_levels(lambda s: s.step_id)
    except CycleDetected as e:
        errors.append(
            PlanError(
                source="plan.logic",
                detail=LogicCycleError(members=e.members),
            )
        )

    # 4. inputs 模板引用必须能在 depends_on 传递闭包中找到
    ancestors_map = _build_ancestors_map(steps, counts)
    for step in steps:
        ancestors = ancestors_map.get(step.step_id, set())
        for ref_id in _extract_input_ref_step_ids(step.inputs):
            if ref_id == step.step_id:
                continue  # self-ref，已由 self_dep 检查覆盖
            if ref_id not in counts:
                continue  # 未知 step，已由 unknown_dep 检查覆盖
            if ref_id not in ancestors:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicUndeclaredRefError(
                            step_id=step.step_id, ref_step_id=ref_id
                        ),
                    )
                )

    # 5. inputs 中每个 {{...}} 标记：先判形状是否是合法受限 jq path（不合法直接 malformed，
    # 例如误写的 if/else/end），形状合法的再比对被引用 step 实际声明的 outputs。
    outputs_by_step = {s.step_id: s.outputs for s in unique_steps}
    for step in steps:
        for tag in _iter_input_tags(step.inputs):
            if _parse_input_jq_path(tag) is None:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicRefMalformedError(
                            step_id=step.step_id, ref=tag, found_segment=None
                        ),
                    )
                )
                continue
            if detail := _validate_ref_against_schema(
                step.step_id, tag, outputs_by_step
            ):
                errors.append(PlanError(source="plan.logic", detail=detail))

    # 6. condition 语法校验 + condition 引用必须落在 depends_on 传递闭包内
    for step in steps:
        if not step.condition:
            continue
        try:
            jq.compile(step.condition)  # type: ignore
        except Exception as e:
            errors.append(
                PlanError(
                    source="plan.logic",
                    detail=LogicInvalidConditionError(
                        step_id=step.step_id,
                        condition=step.condition,
                        message=str(e),
                    ),
                )
            )
            continue  # 语法都不合法，引用校验没有意义

        ancestors = ancestors_map.get(step.step_id, set())
        for ref_id in _extract_condition_ref_step_ids(step.condition):
            if ref_id == step.step_id or ref_id not in counts:
                continue  # 分别已由 self_dep / unknown_dep 覆盖
            if ref_id not in ancestors:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicUndeclaredRefError(
                            step_id=step.step_id, ref_step_id=ref_id
                        ),
                    )
                )

    # 7. 达成判据（success_check）的静态校验。判据有两种形态（见 criterion）：
    #    - jq_expr：可编译、**自约束**（至少引用一次自身 outputs，否则本 step 失败时它仍可能
    #      判 true 而漏判）、引用的其它 step_id 落在 depends_on 传递闭包内；
    #    - nature_assertion：非空、条数 ≤ MAX_ASSERTIONS、文本里出现的引用同样落在闭包内。
    #    「判据非空」与「引用落在闭包内」两形态共有；形态特有项各自实现（jq 的可编译/自约束、
    #    断言的条数上限）。_extract_condition_ref_step_ids 复用 `.step_id.outputs` 引用语法，
    #    所以两种形态共用同一条引用闭包检查。
    #
    #    谁来做达成判定由注入的把控决定（见 core.astream_plact）：规则层用 jq 求值，
    #    判定器读断言语义——静态检查这一层只管判据形态本身，不区分谁来判。
    for step in steps:
        check = step.success_check
        ancestors = ancestors_map.get(step.step_id, set())

        if isinstance(check, JqExprCriterion):
            expression = check.expression
            if not expression.strip():
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicInvalidSuccessCheckError(
                            step_id=step.step_id,
                            success_check="",
                            message="jq 表达式为空：达成判据不能留空（否则这步没有达成门）",
                        ),
                    )
                )
                continue
            try:
                jq.compile(expression)  # type: ignore
            except Exception as e:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicInvalidSuccessCheckError(
                            step_id=step.step_id,
                            success_check=expression,
                            message=str(e),
                        ),
                    )
                )
                continue

            ref_ids = _extract_condition_ref_step_ids(expression)
            if step.step_id not in ref_ids:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicSuccessCheckNotSelfConstrainedError(
                            step_id=step.step_id,
                            success_check=expression,
                        ),
                    )
                )
        else:
            # 联合是闭合的：走到这里只可能是 nature_assertion 形态
            assertions = [a for a in check.assertions if a.strip()]
            if not assertions:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicInvalidSuccessCheckError(
                            step_id=step.step_id,
                            success_check=str(check.assertions),
                            message="断言列表为空：达成判据不能留空（否则这步没有达成门）",
                        ),
                    )
                )
                continue
            if len(assertions) > MAX_ASSERTIONS:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicInvalidSuccessCheckError(
                            step_id=step.step_id,
                            success_check=str(check.assertions),
                            message=(
                                f"断言 {len(assertions)} 条，超过上限 {MAX_ASSERTIONS} 条："
                                "只断言真正要校验的，不要凑数"
                            ),
                        ),
                    )
                )
            # 断言本该是自然语言（不写引用路径）；真写了就按同一条闭包规则校验，
            # 免得"写了个引用上游的断言"绕过 depends_on 完备性。
            ref_ids = _extract_condition_ref_step_ids(" ".join(assertions))
        for ref_id in ref_ids:
            if ref_id == step.step_id or ref_id not in counts:
                continue  # self-ref（jq 形态下合法且必需）/ unknown_dep（已覆盖）
            if ref_id not in ancestors:
                errors.append(
                    PlanError(
                        source="plan.logic",
                        detail=LogicUndeclaredRefError(
                            step_id=step.step_id, ref_step_id=ref_id
                        ),
                    )
                )

    return errors
