"""判定输入的统一裁剪与压缩（Jev / LLM 两条判定路径共用）。

设计动机
--------
本目录下所有"判定点"（preflight / plan audit / 语义验收 / step 诊断 / 轮次闸门 / 收尾评估）
都要求把当前执行状态交给一个判定器。判定器可以是 Jev（``system_one``，state + 最长问题
≤ 32k token）或 LLM（prompt）。**两条路径必须看到同一份压缩后的结构化状态**，否则 A/B 对比
不成立——被测的差异只应来自"谁来判"，而不是"看到了什么"。

因此本模块只做一件事：**raw 执行事实 → 有预算上限的结构化 state dict**。性质：

- JSON-safe：可直接作为 Jev 的 ``state``，也可经 :func:`render_state` 渲染成 LLM 提示文本；
- 确定性：同样输入必产出同样 state（便于回归与快照测试）；
- 有损但记账：超预算时按固定顺序降档，且丢掉了什么、压缩到多少都写进 state 的 ``_trim`` 字段；
- 保关键线索：工具返回里的 ``status`` / ``message`` / ``error_msg`` 等失败线索优先保留
  （它们常被 concept 投影丢弃，却是判 replan / unsolvable 的关键证据）。

裁剪粒度与其对应的读取方
------------------------
====================  ============================================
构造器                 用途
====================  ============================================
build_preflight_state 入口分流
build_plan_audit_state 计划语义审计
build_step_assert_state step 断言验收（含补救裁决）
build_diagnosis_state step 失败补救诊断
build_round_gate_state 轮次继续/止损
build_finish_state    收尾达成率与置信度
====================  ============================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Sequence

from pydantic import BaseModel

from aicore.agents.plan.criterion import (
    KIND_JQ,
    JqExprCriterion,
    NatureAssertionCriterion,
)
from aicore.agents.plan.errors import PlanError
from aicore.tools.concept_outputs import _normalize
from aicore.utils.nl_repr import nl_repr

__all__ = [
    "TrimPolicy",
    "DEFAULT_TRIM",
    "BUDGET_KEY",
    "trim_text",
    "trim_value",
    "estimate_chars",
    "enforce_budget",
    "render_state",
    "compact_plan",
    "compact_criterion",
    "compact_step",
    "compact_outputs",
    "compact_tool_output",
    "compact_errors",
    "compact_unmet",
    "build_preflight_state",
    "build_plan_audit_state",
    "build_step_assert_state",
    "build_diagnosis_state",
    "build_round_gate_state",
    "build_finish_state",
]

# state 里记录裁剪元信息的保留键（以 _ 开头，与业务字段区分）。
BUDGET_KEY = "_trim"

# enforce_budget 的降档阶梯：先按比例缩小文本/列表，仍超预算再丢顶层字段。
_SHRINK_LADDER: tuple[float, ...] = (0.5, 0.25, 0.1)

# 工具原始返回里最该保留的失败线索键（优先展示、不易被裁掉）。
_SIGNAL_KEYS: tuple[str, ...] = ("status", "message", "error", "error_msg", "code", "reason")


@dataclass(frozen=True)
class TrimPolicy:
    """裁剪预算。max_total_chars 是最终闸门，其余是单值裁剪参数。"""

    max_text: int = 300
    """单个字符串超过此长度即截断。"""

    max_list_items: int = 5
    """列表最多保留的元素个数（超出记一条省略说明）。"""

    max_depth: int = 6
    """递归深度上限，防止畸形嵌套把 state 撑爆。"""

    max_total_chars: int = 8000
    """state 序列化后的字符上限；超出即降档，最后按字段体积丢弃。"""

    max_step_results: int = 24
    """step_results 最多保留条数（收尾评估用）。"""

    max_tools: int = 40
    """工具目录最多列出几个工具。"""


DEFAULT_TRIM = TrimPolicy()


# ────────────────────────────── 基础裁剪 ──────────────────────────────


def trim_text(value: Any, max_text: int) -> str:
    """把任意值渲染成受长度约束的文本。

    非字符串值经 ``str`` 粗渲染——这里只服务于判定器的可读性，
    不承担任何结构化语义（结构化部分由 :func:`trim_value` 负责）。
    """
    text = value if isinstance(value, str) else nl_repr(value)
    if len(text) <= max_text:
        return text
    return text[:max_text] + f"…（已截断，原文 {len(text)} 字符）"


def _opt_text(value: Any, max_text: int) -> str | None:
    """可选文本字段：None/空 → None（不给判定器看 "None" 这种噪声）。"""
    if value is None:
        return None
    return trim_text(value, max_text).strip() or None


def compact_criterion(check: Any, policy: TrimPolicy) -> dict[str, Any] | None:
    """达成判据 → 判定器可读的紧凑表示（kind 显式保留）。

    两种形态共用同一个键名（``success_check``），judge 侧不再有第二个别名：形态靠 ``kind``
    分辨，判定点自己按 kind 取字段（见 :mod:`aicore.agents.plan.judge_points`）。
    历史 schema 的裸字符串判据（v0/v2）按 jq 形态渲染。
    """
    if check is None:
        return None
    if isinstance(check, NatureAssertionCriterion):
        return {
            "kind": check.kind,
            "assertions": [trim_text(a, policy.max_text) for a in check.assertions],
        }
    if isinstance(check, JqExprCriterion):
        return {"kind": check.kind, "expression": trim_text(check.expression, policy.max_text)}
    return {"kind": KIND_JQ, "expression": trim_text(check, policy.max_text)}


def trim_value(value: Any, policy: TrimPolicy = DEFAULT_TRIM, *, depth: int = 0) -> Any:
    """递归裁剪任意 JSON 兼容值：字符串截断、列表截断、深度封顶。

    dict 的 key 保留原样（key 本身是判定器的语义标签，截断会引入歧义）。
    """
    if depth > policy.max_depth:
        return "…（嵌套过深已省略）"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return trim_text(value, policy.max_text)
    if isinstance(value, dict):
        return {
            str(k): trim_value(v, policy, depth=depth + 1) for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        head = [trim_value(v, policy, depth=depth + 1) for v in items[: policy.max_list_items]]
        omitted = len(items) - policy.max_list_items
        if omitted > 0:
            head.append(f"…（共 {len(items)} 项，已省略 {omitted} 项）")
        return head
    if isinstance(value, BaseModel):
        return trim_value(value.model_dump(mode="json"), policy, depth=depth)
    return trim_text(value, policy.max_text)


def estimate_chars(value: Any) -> int:
    """state 的近似体积（JSON 字符数），用于预算判定。"""
    return len(json.dumps(value, ensure_ascii=False, default=str))


def enforce_budget(
    state: dict[str, Any], policy: TrimPolicy = DEFAULT_TRIM
) -> dict[str, Any]:
    """把 state 压进 ``policy.max_total_chars``，并记录裁剪元信息到 ``_trim``。

    两级策略，都是确定性的：
    1. 按 :data:`_SHRINK_LADDER` 逐级收紧文本与列表预算（保留全部字段名，只压值）；
    2. 仍超预算则按"序列化后体积"从大到小丢弃顶层字段（同体积按 key 名排序，保证可复现）。
    """
    if estimate_chars(state) <= policy.max_total_chars:
        return _with_meta(state, policy, dropped=[], shrunk=False)

    for ratio in _SHRINK_LADDER:
        smaller = trim_value(
            state,
            replace(
                policy,
                max_text=max(60, int(policy.max_text * ratio)),
                max_list_items=max(1, policy.max_list_items // 2),
            ),
        )
        if estimate_chars(smaller) <= policy.max_total_chars:
            return _with_meta(smaller, policy, dropped=[], shrunk=True)

    # 最后一档：丢最大的顶层字段（_trim 自身不参与，避免自我引用）
    body = {k: v for k, v in state.items() if k != BUDGET_KEY}
    dropped: list[str] = []
    while body and estimate_chars(body) > policy.max_total_chars:
        ranked = sorted(
            body.items(),
            key=lambda kv: (-len(json.dumps(kv[1], ensure_ascii=False, default=str)), kv[0]),
        )
        key = ranked[0][0]
        body.pop(key)
        dropped.append(key)
    return _with_meta(body, policy, dropped=dropped, shrunk=True)


def _with_meta(
    state: dict[str, Any], policy: TrimPolicy, *, dropped: list[str], shrunk: bool
) -> dict[str, Any]:
    out = dict(state)
    out[BUDGET_KEY] = {
        "budget_chars": policy.max_total_chars,
        "chars": estimate_chars(state),
        "shrunk": shrunk,
        "dropped_fields": dropped,
    }
    return out


def render_state(state: dict[str, Any]) -> str:
    """把 state 渲染成 LLM 判定器可读的文本（JSON 缩进，字段顺序稳定）。"""
    return json.dumps(state, ensure_ascii=False, indent=2, default=str)


# ────────────────────────────── 领域构造器 ──────────────────────────────


def compact_plan(plan: Any, policy: TrimPolicy = DEFAULT_TRIM) -> dict[str, Any]:
    """计划 → 紧凑表示。

    只保留判定"这个计划能不能满足用户"所需的字段：步骤目标、算子、依赖、条件、验收判据、
    以及输出概念的**属性名**（属性定义文本对判定无价值，去掉可省大量字符）。

    达成判据只有一个字段（``success_check``），形态由 ``kind`` 分辨——判定点不需要知道
    计划 schema 长什么样，只看这一个键。
    """
    steps: list[dict[str, Any]] = []
    for s in getattr(plan, "steps", []) or []:
        out = getattr(s, "outputs", None)
        outputs: dict[str, Any] | None = None
        if out is not None:
            concept = getattr(out, "concept", None)
            outputs = {
                "concept": getattr(concept, "name", None),
                "is_list": getattr(out, "is_list", None),
                "attributes": [
                    getattr(a, "name", str(a))
                    for a in (getattr(concept, "attributes", None) or [])
                ],
            }
        steps.append(
            {
                "step_id": s.step_id,
                "step_goal": trim_text(s.step_goal, policy.max_text),
                "op": s.op,
                "depends_on": list(s.depends_on),
                "condition": trim_text(s.condition, policy.max_text) if s.condition else None,
                "success_check": compact_criterion(
                    getattr(s, "success_check", None), policy
                ),
                "outputs": outputs,
            }
        )
    return {
        "goal": trim_text(getattr(plan, "goal", ""), policy.max_text),
        "steps": steps,
    }


def compact_step(step: Any, policy: TrimPolicy = DEFAULT_TRIM) -> dict[str, Any]:
    """单个 step → 紧凑表示（达成验收 / 诊断用）。判据只有 ``success_check`` 一个键。"""
    return {
        "step_id": step.step_id,
        "step_goal": trim_text(step.step_goal, policy.max_text),
        "op": step.op,
        "depends_on": list(step.depends_on),
        "success_check": compact_criterion(getattr(step, "success_check", None), policy),
    }


def compact_outputs(proj: Any, policy: TrimPolicy = DEFAULT_TRIM) -> Any:
    """concept 投影后的 outputs →（裁剪后的）可判定形态。"""
    return trim_value(_normalize(proj), policy)


def compact_tool_output(raw: Any, policy: TrimPolicy = DEFAULT_TRIM) -> Any:
    """工具原始返回 → 裁剪并保留失败线索。

    先按 :data:`_SIGNAL_KEYS` 把 ``status/message/error_msg`` 之类的线索提到前面，
    保证它们不会因为在 dict 里靠后而被顶层字段丢弃策略连带牺牲。
    """
    normalized = _normalize(raw)
    if not isinstance(normalized, (dict, list)):
        normalized = {"text": normalized}
    if isinstance(normalized, dict):
        ordered: dict[str, Any] = {}
        for key in _SIGNAL_KEYS:
            if key in normalized:
                ordered[key] = normalized[key]
        for key, value in normalized.items():
            if key not in ordered:
                ordered[key] = value
        normalized = ordered
    return trim_value(normalized, policy)


def compact_errors(
    errors: Sequence[PlanError], policy: TrimPolicy = DEFAULT_TRIM
) -> list[dict[str, Any]]:
    """错误列表 → 紧凑表示（轮次闸门 / repair 摘要用）。"""
    return [
        {
            "source": e.source,
            "kind": getattr(e.detail, "kind", None),
            "detail": trim_text(e.nl_repr(), policy.max_text * 2),
        }
        for e in errors
    ]


def compact_unmet(unmet: Any, policy: TrimPolicy = DEFAULT_TRIM) -> Any:
    """unmet_goals（``{step_id: {step_goal, verdict, reason}}``）→ 裁剪后原样透出。"""
    return trim_value(unmet, policy)


def compact_tool_catalog(
    tools: Sequence[Any], policy: TrimPolicy = DEFAULT_TRIM
) -> dict[str, str]:
    """工具清单 → ``{name: 一句话描述}``，供入口分流判定"该不该走 plan"。"""
    catalog: dict[str, str] = {}
    for t in list(tools)[: policy.max_tools]:
        catalog[getattr(t, "name", str(t))] = trim_text(
            getattr(t, "description", ""), policy.max_text
        )
    return catalog


# ────────────────────────────── state 构造器 ──────────────────────────────


def build_preflight_state(
    *, query: str, tools: Sequence[Any], policy: TrimPolicy = DEFAULT_TRIM
) -> dict[str, Any]:
    """入口分流状态：用户请求 + 候选工具目录。"""
    return enforce_budget(
        {
            "judge_point": "preflight",
            "query": trim_text(query, policy.max_text * 2),
            "available_tools": compact_tool_catalog(tools, policy),
        },
        policy,
    )


def build_plan_audit_state(
    *, query: str, plan: Any, policy: TrimPolicy = DEFAULT_TRIM
) -> dict[str, Any]:
    """计划语义审计状态：用户请求 + 完整计划（尚未执行，无任何执行事实）。"""
    return enforce_budget(
        {
            "judge_point": "plan_audit",
            "query": trim_text(query, policy.max_text * 2),
            "plan": compact_plan(plan, policy),
        },
        policy,
    )


def build_step_assert_state(
    *,
    query: str,
    step: Any,
    concept_output: Any,
    tool_output: Any,
    process_error_kind: str | None = None,
    all_step_outputs: Any = None,
    policy: TrimPolicy = DEFAULT_TRIM,
) -> dict[str, Any]:
    """step 断言验收状态：该步声明的断言 + 实际产出 + 工具原始返回。

    信息面与 :func:`build_diagnosis_state` 刻意对齐（都带 ``tool_raw_output``）：验收与补救
    是**同一次判定**，证据必须一次给全——否则"断言不成立"与"该不该重规划"会基于不同事实，
    出现「产出明明可用却判 replan」那类自相矛盾的裁决。

    ``all_step_outputs`` 是 runner 的 runtime_state 快照（``{step_id: {inputs, outputs}}``）。
    断言里大量是**跨步比对**（"目的地与**上一步返回的**地址一致"、"引用了上一步的名称"），
    只看本步产出时这类断言既不能成立也不能被证伪，判定器只能落"无证据"——产出完全正确
    也会走降级，最终回答被迫加一句"无法确认…"。带上快照才能真的验它、否则真的证伪它。
    """
    return enforce_budget(
        {
            "judge_point": "step_assert",
            "query": trim_text(query, policy.max_text * 2),
            "step": compact_step(step, policy),
            "actual_output": compact_outputs(concept_output, policy),
            "all_step_outputs": (
                compact_outputs(all_step_outputs, policy)
                if all_step_outputs is not None
                else None
            ),
            "tool_raw_output": compact_tool_output(tool_output, policy),
            "process_error_kind": process_error_kind,
        },
        policy,
    )


def build_diagnosis_state(
    *,
    query: str,
    step: Any,
    failure_message: str,
    outputs_snapshot: Any,
    tool_output: Any,
    process_error_kind: str | None,
    policy: TrimPolicy = DEFAULT_TRIM,
) -> dict[str, Any]:
    """补救诊断状态：失败步骤的声明、实际产出、工具原始返回、过程错误类型。

    与原 ``diagnosis._build_user_message`` 的信息面一致，差别只在**体积**：原实现把
    tool_output 全量 JSON 塞进 prompt，这里统一过裁剪 + 失败线索前置。
    """
    return enforce_budget(
        {
            "judge_point": "diagnosis",
            "query": trim_text(query, policy.max_text * 2),
            "failed_step": compact_step(step, policy),
            "failure_message": trim_text(failure_message, policy.max_text * 2),
            "process_error_kind": process_error_kind,
            "actual_output": compact_outputs(outputs_snapshot, policy),
            "tool_raw_output": compact_tool_output(tool_output, policy),
        },
        policy,
    )


def build_round_gate_state(
    *,
    query: str,
    round_no: int,
    max_turns: int,
    errors: Sequence[PlanError],
    failures: Sequence[dict[str, Any]],
    policy: TrimPolicy = DEFAULT_TRIM,
) -> dict[str, Any]:
    """轮次闸门状态：本轮错误 + 跨轮失败记忆（后者是"证据门槛"的依据）。

    ``failures`` 是 core 持有的、跨轮累积的失败记录（runner 每轮新建，故必须由编排层记）。
    没有它，就无法判断"同一 goal 换 approach 后仍失败"，也就无法把 skip_unsolvable
    从"单次判定"升级为"有证据门槛的判定"。
    """
    return enforce_budget(
        {
            "judge_point": "round_gate",
            "query": trim_text(query, policy.max_text * 2),
            "round": round_no,
            "max_turns": max_turns,
            "rounds_used": round_no + 1,
            "current_errors": compact_errors(errors, policy),
            "failure_history": trim_value(list(failures), policy),
        },
        policy,
    )


def build_finish_state(
    *,
    query: str,
    plan: Any | None,
    step_outputs: Any,
    step_results: Sequence[str],
    unmet: Any,
    final_response: str | None,
    forced: bool,
    reason: str | None,
    policy: TrimPolicy = DEFAULT_TRIM,
) -> dict[str, Any]:
    """收尾评估状态：最终计划 + 每步实际产出 + 最终回答 + 未达成清单。

    这是"答案到底达成到什么程度、有没有虚构"的唯一证据面，也是产出 confidence 的输入。
    """
    rows = [trim_text(line, policy.max_text * 2) for line in step_results]
    if len(rows) > policy.max_step_results:
        omitted = len(rows) - policy.max_step_results
        rows = rows[: policy.max_step_results] + [f"…（另有 {omitted} 条步骤结果已省略）"]
    return enforce_budget(
        {
            "judge_point": "finish",
            "query": trim_text(query, policy.max_text * 2),
            "final_plan": compact_plan(plan, policy) if plan is not None else None,
            "step_outputs": compact_outputs(step_outputs, policy),
            "step_results": rows,
            "unmet_goals": compact_unmet(unmet, policy),
            "final_response": trim_text(final_response or "", policy.max_text * 3),
            "execution": {"forced": forced, "reason": trim_text(reason or "", policy.max_text)},
        },
        policy,
    )
