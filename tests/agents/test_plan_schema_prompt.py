"""达成判据（success_check）的接缝护栏：**一份 schema、一份提示词、一个自变量**。

判据形态（jq 表达式 / 自然语言断言）是整个 plact 里唯一允许存在的自变量，本文件钉住这条线：

1. 提示词只有判据段随形态变化——两形态的提示词**除判据段外逐字节相同**，且共用段不提
   任何形态专名（success_check / jq_expr / nature_assertion），否则模型会照着共用段的字样
   去填另一种形态（旧版踩过：共用段残留 success_check，JEV 臂的计划里就带上了 jq 判据）；
2. schema 里 CriterionKind 直接可见且必填（`kind` 是 const、在 required 里），两种形态各只有
   自己那份字段；
3. 静态校验两形态**等强度**：判据非空与引用闭包两边都查，形态特有项各自补齐
   （jq 的可编译/自约束、断言的条数上限）。
"""

from __future__ import annotations

import json

import pytest

from aicore.agents.plan.criterion import (
    MAX_ASSERTIONS,
    KIND_ASSERTION,
    KIND_JQ,
    CriterionKind,
    bind_criterion,
    rules,
)
from aicore.agents.plan.dag_checker import check_dag
from aicore.agents.plan.experiment.plan_schema_v1 import (
    CONDITION_RULES,
    PlanSpecV1,
    PlanStepV1,
    StructuredPlanV1,
    plan_spec_v1,
)
from tests.agents._plan_verify_helpers import step as make_step

_CONDITION_RULES = CONDITION_RULES


def _prompt(criterion: CriterionKind) -> str:
    """判据形态经 with_criterion 绑定（core 注入用的就是这条路径）。"""
    return PlanSpecV1().with_criterion(criterion).build_sys_prompt([])


# ══════════════════════════════════════════════════════════════════════
# 提示词：唯一变化段
# ══════════════════════════════════════════════════════════════════════


def test_two_criteria_differ_only_in_the_criterion_section():
    """两形态提示词除了判据段，逐字节相同（这是"一个自变量"的可执行定义）。"""
    jq = _prompt(KIND_JQ)
    assertion = _prompt(KIND_ASSERTION)

    assert jq.replace(rules(KIND_JQ), "§CRITERION§") == assertion.replace(
        rules(KIND_ASSERTION), "§CRITERION§"
    )


def test_shared_sections_do_not_mention_any_criterion_form():
    """共用段不许出现形态专名与字段名——否则模型会照着填错形态。"""
    shared = _prompt(KIND_JQ).replace(rules(KIND_JQ), "")
    shared += _prompt(KIND_ASSERTION).replace(rules(KIND_ASSERTION), "")

    for forbidden in ("success_check", "jq_expr", "nature_assertion"):
        assert forbidden not in shared, f"共用段不该出现 {forbidden!r}：它是形态专名"


def test_prompt_keeps_its_sections_in_order():
    """拆段护栏：condition 规则、控制流、达成校验、工具指南四段都在且顺序不变。"""
    prompt = _prompt(KIND_JQ)

    for section in ("### 运行状态与引用", "### 控制流", "### 达成校验", "## TOOL GUIDELINES"):
        assert section in prompt, f"提示词缺了 {section!r} 段"
    assert prompt.count(_CONDITION_RULES) == 1
    assert prompt.count(rules(KIND_JQ)) == 1
    assert (
        prompt.index("### 运行状态与引用")
        < prompt.index("### 控制流")
        < prompt.index("### 达成校验")
        < prompt.index("## TOOL GUIDELINES")
    )
    # condition 规则只讲 condition；判据规则只讲判据（别再混着写）
    assert "condition" in _CONDITION_RULES
    assert "success_check" not in _CONDITION_RULES
    assert "success_check" in rules(KIND_JQ)
    assert "success_check" in rules(KIND_ASSERTION)


# ══════════════════════════════════════════════════════════════════════
# schema：CriterionKind 在 schema 里可见且必填
# ══════════════════════════════════════════════════════════════════════


def test_schema_exposes_the_criterion_kind_enum_and_required_field():
    schema = StructuredPlanV1.model_json_schema()
    union = schema["properties"]["steps"]["items"]["$ref"]
    assert union.startswith("#/$defs/")
    step_def = schema["$defs"][union.split("/")[-1]]
    assert "success_check" in step_def["required"]

    kinds = {
        name: definition["properties"]["kind"]
        for name, definition in schema["$defs"].items()
        if name.endswith("Criterion")
    }
    assert sorted(kinds) == ["JqExprCriterion", "NatureAssertionCriterion"]
    assert kinds["JqExprCriterion"]["const"] == KIND_JQ
    assert kinds["NatureAssertionCriterion"]["const"] == KIND_ASSERTION
    # kind 必填：模型必须自己说清这是哪种形态
    for name, definition in schema["$defs"].items():
        if name.endswith("Criterion"):
            assert "kind" in definition["required"], name


def test_both_forms_parse_and_unknown_form_is_rejected():
    jq_step = make_step("s1", success_check=".s1.outputs.Out.field != null")
    ast_step = make_step("s1", assertion=["至少返回 3 家"])

    assert jq_step.success_check.kind == KIND_JQ
    assert ast_step.success_check.kind == KIND_ASSERTION

    with pytest.raises(Exception):
        # 裸字符串（旧形态）不再合法：kind 必须显式
        PlanStepV1.model_validate(
            {**jq_step.model_dump(), "success_check": ".s1.outputs.Out.field != null"}
        )


# ══════════════════════════════════════════════════════════════════════
# 静态校验：两形态等强度
# ══════════════════════════════════════════════════════════════════════


def _errors(steps: list[PlanStepV1]) -> list[str]:
    dag = plan_spec_v1.build_dag(StructuredPlanV1(goal="g", steps=steps))
    return [str(getattr(e.detail, "kind", "?")) for e in check_dag(dag, {"op"})]


def test_empty_criterion_is_an_error_in_both_forms():
    """判据非空：两形态都查（旧实现里 jq 空串会被静默跳过，是个洞）。"""
    jq_empty = make_step("s1", success_check="")
    ast_empty = make_step("s1", assertion=[""])

    assert "logic.invalid_success_check" in _errors([jq_empty])
    assert "logic.invalid_success_check" in _errors([ast_empty])


def test_invalid_jq_and_too_many_assertions_are_both_rejected():
    bad_jq = make_step("s1", success_check=".s1.outputs.Out.field ==")
    too_many = make_step(
        "s1", assertion=[f"断言{i}" for i in range(MAX_ASSERTIONS + 1)]
    )

    assert "logic.invalid_success_check" in _errors([bad_jq])
    assert "logic.invalid_success_check" in _errors([too_many])


def test_self_constraint_is_checked_for_jq_only():
    """jq 形态必须自约束；断言形态没有这一项（自然语言断言天然约束本步产出）。"""
    upstream = make_step("s9")
    jq_not_self = make_step(
        "s1", depends_on=["s9"], success_check=".s9.outputs.Out.field != null"
    )
    ast_ = make_step("s1", assertion=["拿到了结果"])

    assert "logic.success_check_not_self_constrained" in _errors([upstream, jq_not_self])
    assert _errors([ast_]) == []


def test_upstream_reference_must_be_declared_in_both_forms():
    """引用闭包两形态都查：jq 里写引用、断言里写引用，同样要求列进 depends_on。"""
    sibling = make_step("s9")  # 已声明，但没被列进 depends_on
    jq_ref = make_step("s1", success_check=".s9.outputs.Out.field != null")
    ast_ref = make_step("s1", assertion=["地址等于 .s9.outputs.Out.field"])

    assert "logic.undeclared_ref" in _errors([sibling, jq_ref])
    assert "logic.undeclared_ref" in _errors([sibling, ast_ref])


def test_assertion_form_passes_static_check_like_jq_form():
    """等强度：同一个合法计划换成断言形态，静态校验结果一样（都是"没有错误"）。"""
    jq_steps = [make_step("s1", success_check='(.s1.outputs.Out.field // "") != ""')]
    ast_steps = [make_step("s1", assertion=["拿到了 field", "值不为空"])]

    assert _errors(jq_steps) == []
    assert _errors(ast_steps) == []


def test_criterion_is_json_serializable_in_judge_state():
    """判定器 state 里判据是带 kind 的纯数据（judge 侧只看这一个键）。"""
    from aicore.agents.plan import trim

    state = trim.compact_step(make_step("s1", assertion=["a", "b"]))
    assert json.loads(json.dumps(state["success_check"], ensure_ascii=False)) == {
        "kind": KIND_ASSERTION,
        "assertions": ["a", "b"],
    }
    assert (
        trim.compact_step(make_step("s1", success_check=".s1.outputs.Out.field != null"))[
            "success_check"
        ]["kind"]
        == KIND_JQ
    )


def test_create_plan_injects_the_criterion_into_the_prompt():
    """注入点：create_plan 用 bind_criterion 取"绑好形态的 spec"，历史 spec 原样返回。"""

    class _LegacySpec:
        name = "legacy"
        plan_type = StructuredPlanV1

        def build_sys_prompt(self, tools: list[object]) -> str:
            return "frozen prompt"

        def build_dag(self, plan: StructuredPlanV1):  # pragma: no cover - 不被本用例调用
            raise NotImplementedError

    bound = bind_criterion(PlanSpecV1(), KIND_ASSERTION)
    assert isinstance(bound, PlanSpecV1)
    assert bound.criterion == KIND_ASSERTION
    assert "nature_assertion" in bound.build_sys_prompt([])

    legacy = _LegacySpec()
    assert bind_criterion(legacy, KIND_ASSERTION) is legacy
