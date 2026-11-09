"""verify_* 脚本共用的构造与报告 helper。

被 verify_dag_checker.py 与 verify_step_diagnosis.py 共用（两者都要构造 PlanStepV1 / DAG）。
verify_ref_resolution.py 直接喂 runtime_state、不构造 step，不用本模块。
"""

from typing import Any

from rich.console import Console

from aicore.agents.plan.criterion import jq_expr, nature_assertion
from aicore.agents.plan.dag_runner import BareDag
from aicore.agents.plan.experiment.plan_schema_v1 import (
    ConceptOutput,
    PlanStepV1,
    StructuredPlanV1,
    plan_spec_v1,
)
from aicore.utils._concepts.meta import PrimitiveAttribute, PrimitiveAttributeType, SimpleConcept


def outputs(
    name: str = "Out", *, is_list: bool = True, attributes: list[str] | None = None
) -> ConceptOutput:
    attrs = attributes if attributes is not None else ["field"]
    return ConceptOutput(
        is_list=is_list,
        concept=SimpleConcept(
            name=name,
            definition="test concept",
            attributes=[
                PrimitiveAttribute(
                    name=a, title=a, description="test attr",
                    is_required=True, type=PrimitiveAttributeType.STRING,
                )
                for a in attrs
            ],
        ),
    )


def step(
    step_id: str,
    *,
    op: str = "op",
    depends_on: list[str] | None = None,
    inputs: dict[str, Any] | None = None,
    step_outputs: ConceptOutput | None = None,
    condition: str | None = None,
    success_check: str | None = None,
    assertion: list[str] | None = None,
) -> PlanStepV1:
    """构造一个 PlanStepV1（默认判据是 jq 形态）。

    success_check 是 schema 必填字段，且 check_dag 第 7 项要求 jq 形态的判据「自约束」
    （至少引用一次自身 outputs）。默认给一个自引用的合法 jq，使不测判据的用例不额外触发
    success_check_not_self_constrained。传 ``assertion`` 则构造自然语言断言形态的判据。
    """
    criterion = (
        nature_assertion(assertion)
        if assertion is not None
        else jq_expr(
            success_check
            if success_check is not None
            else f"((.{step_id}.outputs.Out // []) | length) >= 0"
        )
    )
    return PlanStepV1(
        step_goal=f"goal for {step_id}",
        step_id=step_id,
        op=op,
        depends_on=depends_on or [],
        inputs=inputs or {},
        outputs=step_outputs or outputs(),
        condition=condition,
        success_check=criterion,
    )


def build(steps: list[PlanStepV1]) -> BareDag[PlanStepV1]:
    plan = StructuredPlanV1(goal="test goal", steps=steps)
    return plan_spec_v1.build_dag(plan)


def emit(console: Console, label: str, actual: Any, expected: Any, extra: Any = None) -> bool:
    """打印单条用例结果并返回是否匹配（actual == expected）。"""
    console.print(f"\n[bold]{label}[/bold]")
    console.rule(style="dim")
    if extra is not None:
        console.print(extra, markup=False)
    ok = actual == expected
    status = "[green]OK[/green]" if ok else "[red]MISMATCH[/red]"
    console.print(f"expected={expected!r}", markup=False)
    console.print(f"actual  ={actual!r} ", markup=False, end="")
    console.print(status)
    return ok


def finish(console: Console, all_ok: bool) -> int:
    console.print()
    console.print(
        "[bold green]all cases matched[/bold green]"
        if all_ok
        else "[bold red]some cases mismatched[/bold red]"
    )
    return 0 if all_ok else 1
