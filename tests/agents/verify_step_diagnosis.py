"""手动验证 plan_dag_runner 的「统一验证尾段」+ diagnosis 的「规则前置层 / 裁决路由」。

覆盖 proposals/step-succ-check-diagnosis 的实现：非 skipped 的每个 step 执行后一律求值
success_check，失败（含 input_ref/params/condition/execution/projection 过程错误使 outputs 为空）即进诊断；
诊断三种裁决 replan / skip_unsolvable / accept_degraded 分别路由到
PlanRunnerErrorEvent(step.remediation) / PlanStepDoneEvent.unmet(+级联跳过) / unmet(不级联)。

放在 tests/ 下但文件名不以 test_ 开头，不参与 pytest 收集（pytest.ini python_files = test_*.py）。

Run directly:
    uv run python -m tests.agents.verify_step_diagnosis

分两组：
- A 组（8 例）：diagnosis._rule_based_diagnosis 纯函数——规则前置层的确定性裁决表。
- B 组（13 例）：PlanDAGRunner.run 的验证尾段路由——注入假诊断（不打模型），断言每个 step 的
  process_error / unmet / skipped 与 runner 上报的错误 source。
"""

import json
from typing import Any, get_args

import anyio
from pydantic import BaseModel, Field
from rich.console import Console

from aicore.models.model_api import ModelState, StructuredModelResponse
from aicore.tools import TaskTool
from aicore.agents.plan.plan_dag_runner import PlanDAGRunner
from aicore.agents.plan.diagnosis import (
    AcceptDegraded,
    DiagnosisResult,
    RemediationDiagnosis,
    Replan,
    SkipUnsolvable,
    _rule_based_diagnosis,
)
from aicore.agents.plan.events import (
    PlanStepDoneEvent,
    PlanRunnerErrorEvent,
    PlanStepSkippedEvent,
)
from tests.agents._plan_verify_helpers import outputs, step, build, emit, finish

console = Console()


# ── 工具 stub ────────────────────────────────────────────────────────────────
class _In(BaseModel):
    q: str = Field(...)


def _tool(
    name: str, *, value: Any = None, raises: bool = False
) -> TaskTool[_In, object, None, Any]:
    async def worker(q: str) -> object:
        if raises:
            raise RuntimeError("tool boom")
        return value

    return TaskTool[_In, object, None, Any](
        name=name,
        description="test tool",
        args_schema=_In,
        worker=worker,
    )


class _DeterministicProjectionModelAPI:
    """Drive Concept v2 extraction deterministically without an external model."""

    def initial_state(self, *, system_prompt: str | None = None) -> ModelState:
        return ModelState()

    async def structured_output(
        self,
        message: Any,
        *,
        output_type: type[Any],
        state: ModelState,
        params: Any = None,
    ) -> StructuredModelResponse[Any, ModelState]:
        raw_text = message.text.split("```json\n", 1)[1].split("\n```", 1)[0]
        raw = json.loads(raw_text)
        if "items" in output_type.model_fields:
            item_type = get_args(output_type.model_fields["items"].annotation)[0]
            empty_item = {name: None for name in item_type.model_fields}
            parsed = (
                None
                if isinstance(raw, dict)
                else output_type(items=[empty_item for _ in raw])
            )
        else:
            parsed = output_type(
                **{name: None for name in output_type.model_fields}
            )
        return StructuredModelResponse(parsed=parsed, state=state)


# ── A 组：规则前置层 ──────────────────────────────────────────────────────────
# (label, op, process_error_kind, failure_message, expected_outcome_or_None)
RULE_CASES: list[tuple[str, str, str | None, str, str | None]] = [
    (
        "A1 projection 空 list → replan",
        "op",
        "projection",
        "concept 'X' is_list output is empty",
        "replan",
    ),
    ("A2 params 错误 → replan", "op", "params", "missing required arg", "replan"),
    (
        "A3 input_ref 错误 → replan",
        "op",
        "input_ref",
        "jq evaluation returned null",
        "replan",
    ),
    ("A4 condition 错误 → replan", "op", "condition", "not a boolean", "replan"),
    ("A5 execution 错误 → replan", "op", "execution", "tool boom", "replan"),
    (
        "A6 音乐 op + projection 类型不符（非空 list）→ skip_unsolvable",
        "QQ音乐单曲搜索",
        "projection",
        "Input should be an object ... input_type=list",
        "skip_unsolvable",
    ),
    (
        "A7 音乐 op + 纯 success_check 失败（kind None）→ skip_unsolvable",
        "歌曲搜索",
        None,
        "success_check evaluated to false",
        "skip_unsolvable",
    ),
    (
        "A8 非音乐 op + 纯 success_check 失败 → 交 LLM 兜底（None）",
        "导航",
        None,
        "success_check evaluated to false",
        None,
    ),
]


def _run_rule_cases() -> bool:
    all_ok = True
    console.rule("[bold]A 组：diagnosis._rule_based_diagnosis 规则前置层")
    for label, op, kind, msg, expected in RULE_CASES:
        result = _rule_based_diagnosis(
            op=op, process_error_kind=kind, failure_message=msg
        )
        actual = result.outcome if result is not None else None
        all_ok = emit(console, label, actual, expected) and all_ok
    return all_ok


# ── B 组：runner 验证尾段路由 ─────────────────────────────────────────────────
def _make_fake_diagnose(diag_map: dict[str, str]):
    """注入到 runner 实例上，绕过真实（需模型的）诊断，按 step_id 给定裁决。

    未在 diag_map 中的 step 若仍被诊断，抛 KeyError——即"本不该失败的 step 却进了诊断"，
    正是要暴露的回归。签名对齐 run() 里的 self._diagnose_failure(step, sc, msg, snap, raw, pe)。
    """

    def _forced(outcome: str) -> RemediationDiagnosis:
        """把 diag_map 的 outcome 字符串映射成对应变体（字段值仅占位，本组只验路由）。"""
        if outcome == "replan":
            return Replan(failed_assumption="forced", retry_direction="forced")
        if outcome == "skip_unsolvable":
            return SkipUnsolvable(unsolvable_reason="forced")
        if outcome == "accept_degraded":
            return AcceptDegraded(limitation="forced")
        raise ValueError(f"unknown outcome: {outcome!r}")

    async def fake(step_, success_check, message, outputs_snapshot, tool_output, process_error=None):
        return DiagnosisResult(
            source="rule",
            decision=_forced(diag_map[step_.step_id]),
        )
    return fake


async def _run(
    tools: list[Any],
    steps: list[Any],
    diag_map: dict[str, str],
) -> dict[str, Any]:
    """跑一个 plan，归一化每个 step 的结果 + runner 错误 source。"""
    runner = PlanDAGRunner(
        tools,
        model_api=_DeterministicProjectionModelAPI(),  # type: ignore[arg-type]
        query="测试请求",
    )
    runner._diagnose_failure = _make_fake_diagnose(diag_map)  # type: ignore[method-assign]
    summary: dict[str, Any] = {"_errors": []}
    async for ev in runner.run(build(steps)):
        if isinstance(ev, PlanStepDoneEvent):
            summary[ev.step_id] = {
                "pe": ev.process_error.kind if ev.process_error is not None else None,
                "unmet": ev.unmet.verdict if ev.unmet is not None else None,
            }
        elif isinstance(ev, PlanStepSkippedEvent):
            summary[ev.step_id] = {"skipped": ev.reason}
        elif isinstance(ev, PlanRunnerErrorEvent):
            summary["_errors"].extend(e.source for e in ev.errors)
    return summary


def _done(pe: str | None = None, unmet: str | None = None) -> dict[str, Any]:
    return {"pe": pe, "unmet": unmet}


# 每条用例：(label, tools, steps, diag_map, expected_summary)
def _build_exec_cases() -> list[
    tuple[str, list[Any], list[Any], dict[str, str], dict[str, Any]]
]:
    R = lambda: outputs("R", is_list=True, attributes=["field"])  # noqa: E731
    R1 = lambda: outputs("R", is_list=False, attributes=["field"])  # noqa: E731
    len_gt0 = "((.s1.outputs.R // []) | length) > 0"
    len_gt5 = "((.s1.outputs.R // []) | length) > 5"

    return [
        (
            "B1 达成：tool+投影+success_check 均通过 → done，无 error/unmet",
            [_tool("search", value=[{}, {}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt0,
                )
            ],
            {},
            {"s1": _done(), "_errors": []},
        ),
        (
            "B2 success_check 判 false + 诊断 replan → step.remediation",
            [_tool("search", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt5,
                )
            ],
            {"s1": "replan"},
            {"s1": _done(unmet=None), "_errors": ["step.remediation"]},
        ),
        (
            "B3 success_check 判 false + 诊断 skip_unsolvable → unmet=unsolvable，无 error",
            [_tool("search", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt5,
                )
            ],
            {"s1": "skip_unsolvable"},
            {"s1": _done(unmet="unsolvable"), "_errors": []},
        ),
        (
            "B4 success_check 判 false + 诊断 accept_degraded → unmet=degraded，无 error",
            [_tool("search", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt5,
                )
            ],
            {"s1": "accept_degraded"},
            {"s1": _done(unmet="degraded"), "_errors": []},
        ),
        (
            "B5 Concept v2 list 提取连续解析失败 → pe=projection → skip_unsolvable",
            [_tool("search", value={"not": "a list"})],
            [step("s1", op="search", inputs={"q": "x"}, step_outputs=R())],
            {"s1": "skip_unsolvable"},
            {"s1": _done(pe="projection", unmet="unsolvable"), "_errors": []},
        ),
        (
            "B6 projection 空结果（is_list=True 返回 []）→ pe=projection → replan",
            [_tool("search", value=[])],
            [step("s1", op="search", inputs={"q": "x"}, step_outputs=R())],
            {"s1": "replan"},
            {"s1": _done(pe="projection"), "_errors": ["step.remediation"]},
        ),
        (
            "B7 execution 失败（工具抛异常）→ pe=execution → replan",
            [_tool("search", raises=True)],
            [step("s1", op="search", inputs={"q": "x"}, step_outputs=R1())],
            {"s1": "replan"},
            {"s1": _done(pe="execution"), "_errors": ["step.remediation"]},
        ),
        (
            "B8 params 校验失败（缺必填入参 q）→ 工具不跑 → pe=params → replan",
            [_tool("search", value=[{}])],
            [step("s1", op="search", inputs={}, step_outputs=R())],
            {"s1": "replan"},
            {"s1": _done(pe="params"), "_errors": ["step.remediation"]},
        ),
        (
            "B8b input ref 运行时为空（静态合法但下标越界返回 null）→ 工具不跑 → pe=input_ref → replan",
            [_tool("search", value=[{"field": "v"}]), _tool("play", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt0,
                ),
                step(
                    "s2",
                    op="play",
                    depends_on=["s1"],
                    inputs={"q": "{{ .s1.outputs.R[99].field }}"},
                    step_outputs=R(),
                    success_check="((.s2.outputs.R // []) | length) >= 0",
                ),
            ],
            {"s2": "replan"},
            {
                "s1": _done(),
                "s2": _done(pe="input_ref"),
                "_errors": ["step.remediation"],
            },
        ),
        (
            "B9 condition=false → 跳过（condition_false），不进诊断",
            [_tool("search", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    condition="false",
                )
            ],
            {},
            {"s1": {"skipped": "condition_false"}, "_errors": []},
        ),
        (
            "B10 condition 求值非布尔（jq 返回 1）→ 工具不跑 → pe=condition → replan",
            [_tool("search", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    condition="1",
                )
            ],
            {"s1": "replan"},
            {"s1": _done(pe="condition"), "_errors": ["step.remediation"]},
        ),
        (
            "B11 无解级联：s1 skip_unsolvable → s2(依赖) upstream_unsolvable → s3(依赖 s2) 传播 "
            "upstream_unsolvable；s4(独立) 仍达成",
            [
                _tool("search", value=[{}]),
                _tool("play", value=[{}]),
                _tool("more", value=[{}]),
                _tool("other", value=[{}]),
            ],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt5,
                ),
                step(
                    "s2",
                    op="play",
                    depends_on=["s1"],
                    inputs={"q": "x"},
                    step_outputs=outputs("R", is_list=True),
                    success_check="((.s2.outputs.R // []) | length) >= 0",
                ),
                step(
                    "s3",
                    op="more",
                    depends_on=["s2"],
                    inputs={"q": "x"},
                    step_outputs=outputs("R", is_list=True),
                    success_check="((.s3.outputs.R // []) | length) >= 0",
                ),
                step(
                    "s4",
                    op="other",
                    inputs={"q": "x"},
                    step_outputs=outputs("R", is_list=True),
                    success_check="((.s4.outputs.R // []) | length) > 0",
                ),
            ],
            {"s1": "skip_unsolvable"},
            {
                "s1": _done(unmet="unsolvable"),
                "s2": {"skipped": "upstream_unsolvable"},
                "s3": {"skipped": "upstream_unsolvable"},
                "s4": _done(),
                "_errors": [],
            },
        ),
        (
            "B11b condition_false 级联仍是 upstream_skipped（不被无解链污染）",
            [_tool("search", value=[{}]), _tool("play", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    condition="false",
                ),
                step(
                    "s2",
                    op="play",
                    depends_on=["s1"],
                    inputs={"q": "x"},
                    step_outputs=outputs("R", is_list=True),
                    success_check="((.s2.outputs.R // []) | length) >= 0",
                ),
            ],
            {},
            {
                "s1": {"skipped": "condition_false"},
                "s2": {"skipped": "upstream_skipped"},
                "_errors": [],
            },
        ),
        (
            "B12 降级不级联：s1 accept_degraded → s2(依赖) 照常执行并达成",
            [_tool("search", value=[{}]), _tool("play", value=[{}])],
            [
                step(
                    "s1",
                    op="search",
                    inputs={"q": "x"},
                    step_outputs=R(),
                    success_check=len_gt5,
                ),
                step(
                    "s2",
                    op="play",
                    depends_on=["s1"],
                    inputs={"q": "x"},
                    step_outputs=outputs("R", is_list=True),
                    success_check="((.s2.outputs.R // []) | length) > 0",
                ),
            ],
            {"s1": "accept_degraded"},
            {"s1": _done(unmet="degraded"), "s2": _done(), "_errors": []},
        ),
    ]


async def _run_exec_cases() -> bool:
    all_ok = True
    console.rule("[bold]B 组：PlanDAGRunner.run 验证尾段路由")
    for label, tools, steps, diag_map, expected in _build_exec_cases():
        actual = await _run(tools, steps, diag_map)
        all_ok = emit(console, label, actual, expected) and all_ok
    return all_ok


async def main() -> int:
    ok_a = _run_rule_cases()
    ok_b = await _run_exec_cases()
    return finish(console, ok_a and ok_b)


if __name__ == "__main__":
    raise SystemExit(anyio.run(main))
