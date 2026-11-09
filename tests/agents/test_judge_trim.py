"""判定输入裁剪层（:mod:`aicore.agents.plan.trim`）的单测。

这一层是 Jev 与 LLM 两条判定路径**共用**的输入面，所以必须是可以断言其行为的纯函数：
- 确定性：同输入同输出（A/B 的可比性依赖它）；
- 有界：任何畸形输入都压进预算（否则 Jev 的 32k 上限会直接报错）；
- 保线索：工具返回里的失败线索不被裁掉（诊断判 replan/unsolvable 全靠它）；
- 记账：丢了什么写在 ``_trim`` 里（否则"判定变差了"无法归因到裁剪）。
"""

from __future__ import annotations

import json

from aicore.agents.plan.errors import InputRefErrorDetail, PlanError
from aicore.agents.plan import trim as T
from aicore.agents.plan.criterion import jq_expr


def _policy(**kw) -> T.TrimPolicy:
    base = dict(max_text=40, max_list_items=2, max_depth=4, max_total_chars=600)
    base.update(kw)
    return T.DEFAULT_TRIM.__class__(**base)


# ────────────────────────────── 基础裁剪 ──────────────────────────────


def test_trim_text_truncates_and_reports_length():
    out = T.trim_text("x" * 100, 10)
    assert out.startswith("x" * 10)
    assert "已截断" in out and "100" in out
    assert T.trim_text("short", 10) == "short"


def test_trim_value_is_deterministic_and_bounded():
    policy = _policy()
    raw = {"a": "y" * 500, "b": [1, 2, 3, 4, 5], "c": {"d": {"e": {"f": {"g": 1}}}}}
    first = T.trim_value(raw, policy)
    assert first == T.trim_value(raw, policy)
    assert len(first["b"]) == 3  # 2 项 + 1 条省略说明
    assert "已省略" in first["b"][-1]
    assert "嵌套过深" in json.dumps(first["c"], ensure_ascii=False)


def test_trim_value_keeps_scalars_untouched():
    policy = _policy()
    assert T.trim_value({"n": 3, "f": 1.5, "t": True, "z": None}, policy) == {
        "n": 3,
        "f": 1.5,
        "t": True,
        "z": None,
    }


def test_enforce_budget_passes_through_when_under_budget():
    policy = _policy(max_total_chars=10_000)
    state = T.enforce_budget({"a": "small"}, policy)
    assert state["a"] == "small"
    assert state[T.BUDGET_KEY]["shrunk"] is False
    assert state[T.BUDGET_KEY]["dropped_fields"] == []


def test_enforce_budget_shrinks_in_place_when_ladder_suffices():
    policy = _policy(max_total_chars=300)
    state = {"huge": "z" * 5000, "big": {"k": "w" * 5000}, "small": 1}
    out = T.enforce_budget(state, policy)
    assert T.estimate_chars({k: v for k, v in out.items() if k != T.BUDGET_KEY}) <= 300
    meta = out[T.BUDGET_KEY]
    # 降档（压文本长度）已足够时不丢字段，且小字段原样保留
    assert meta["shrunk"] is True
    assert meta["dropped_fields"] == []
    assert out["small"] == 1


def test_enforce_budget_drops_fields_when_shrinking_is_not_enough():
    # 降档下限是 max_text=60（阶梯最末档），字段够多时总仍超预算 → 必须开始丢字段。
    policy = _policy(max_total_chars=600)
    state = {f"f{i}": {"a": "v" * 3000, "b": "w" * 3000} for i in range(30)}
    out = T.enforce_budget(state, policy)
    body = {k: v for k, v in out.items() if k != T.BUDGET_KEY}
    assert T.estimate_chars(body) <= 600
    meta = out[T.BUDGET_KEY]
    assert meta["shrunk"] is True
    assert len(meta["dropped_fields"]) >= 1
    assert set(meta["dropped_fields"]) <= set(state)
    # 丢字段是确定性的：同输入同结果
    assert T.enforce_budget(state, policy)[T.BUDGET_KEY] == meta


def test_compact_tool_output_hoists_failure_signals():
    policy = _policy(max_text=200)
    raw = {"z": 1, "status": "fail", "message": "查不到", "error_msg": "empty result"}
    out = T.compact_tool_output(raw, policy)
    assert list(out)[:3] == ["status", "message", "error_msg"]
    assert out["message"] == "查不到"


def test_compact_tool_output_wraps_non_mapping():
    out = T.compact_tool_output("一段 markdown 文本", _policy())
    assert out == {"text": "一段 markdown 文本"}


# ────────────────────────────── 领域构造器 ──────────────────────────────


def _plan():
    from aicore.agents.plan.experiment.plan_schema_v1 import (
        ConceptOutput,
        PlanStepV1,
        StructuredPlanV1,
    )
    from aicore.utils._concepts.meta import (
        PrimitiveAttribute,
        PrimitiveAttributeType,
        SimpleConcept,
    )

    concept = SimpleConcept(
        name="WeatherInfo",
        definition="天气",
        attributes=[
            PrimitiveAttribute(
                name="temperature",
                title="温度",
                description="desc " * 50,
                is_required=True,
                type=PrimitiveAttributeType.STRING,
            )
        ],
    )
    step = PlanStepV1(
        step_goal="查天气" * 50,
        step_id="s1",
        op="weather",
        depends_on=[],
        inputs={"city": "北京"},
        outputs=ConceptOutput(is_list=False, concept=concept),
        success_check=jq_expr(".s1.outputs.WeatherInfo.temperature != null"),
    )
    return StructuredPlanV1(goal="目标" * 50, steps=[step])


def test_compact_plan_keeps_structure_and_drops_attribute_descriptions():
    policy = _policy()
    compact = T.compact_plan(_plan(), policy)
    step = compact["steps"][0]
    assert step["step_id"] == "s1" and step["op"] == "weather"
    assert step["outputs"] == {
        "concept": "WeatherInfo",
        "is_list": False,
        "attributes": ["temperature"],
    }
    # 概念属性的描述文本（很长）不应进 state
    assert "desc" not in json.dumps(compact, ensure_ascii=False)
    # 长文本被截断
    assert len(step["step_goal"]) < 120


def test_build_diagnosis_state_carries_evidence_within_budget():
    policy = _policy(max_total_chars=4000)
    state = T.build_diagnosis_state(
        query="查北京天气",
        step=_plan().steps[0],
        failure_message="success_check evaluated to false",
        outputs_snapshot={"WeatherInfo": {"temperature": None}},
        tool_output={"status": "fail", "message": "city not found", "dump": "x" * 3000},
        process_error_kind=None,
        policy=policy,
    )
    assert state["judge_point"] == "diagnosis"
    assert state["failure_message"].startswith("success_check")
    assert state["tool_raw_output"]["message"] == "city not found"
    assert T.estimate_chars({k: v for k, v in state.items() if k != T.BUDGET_KEY}) <= (
        policy.max_total_chars
    )


def test_build_round_gate_state_includes_history():
    errors = [
        PlanError(
            source="step.input_ref",
            detail=InputRefErrorDetail(step_id="s2", ref=".s1.outputs.X.a", message="boom"),
        )
    ]
    state = T.build_round_gate_state(
        query="q",
        round_no=1,
        max_turns=5,
        errors=errors,
        failures=[{"round": 0, "step_id": "s1", "source": "step.remediation", "detail": "同"}],
        policy=_policy(max_total_chars=10_000),
    )
    assert state["round"] == 1 and state["rounds_used"] == 2
    assert state["current_errors"][0]["kind"] == "input_ref"
    assert state["failure_history"][0]["step_id"] == "s1"


def test_render_state_is_json():
    state = T.build_plan_audit_state(query="q", plan=_plan(), policy=_policy())
    rendered = json.loads(T.render_state(state))
    assert rendered["judge_point"] == "plan_audit"
