"""手动验证 _format_repair_message 的输出。

Run directly:
    uv run python aicore/agents/plan/test_repair_message.py
"""

from rich.console import Console

console = Console()

from aicore.agents.plan.core import _format_repair_message
from aicore.agents.plan.errors import (
    PlanError,
    PlanRepairContext,
    RepairPolicy,
    SchemaErrorDetail,
    LogicDupStepIdError,
    LogicSelfDepError,
    LogicUnknownDepError,
    LogicUnknownOpError,
    LogicCycleError,
    LogicUndeclaredRefError,
    ParamsErrorDetail,
    ExecutionErrorDetail,
    ProjectionErrorDetail,
)

CASES: list[tuple[str, PlanRepairContext]] = [
    (
        "REGENERATE_PLAN / plan.schema 单条错误（LLM 输出无法解析）",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.schema",
                    detail=SchemaErrorDetail(
                        message="1 validation error for StructuredPlanV1\nsteps -> 0 -> op\n  field required (type=value_error.missing)",
                    ),
                )
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=1,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic 单条错误（unknown op）",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicUnknownOpError(step_id="s3", op="weather_search"),
                )
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=1,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic — undeclared_ref（引用了前序步骤但未在 depends_on 声明）",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicUndeclaredRefError(step_id="s3", ref_step_id="s1"),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=1,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic — undeclared_ref + unknown_dep 混合",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicUndeclaredRefError(step_id="s3", ref_step_id="s1"),
                ),
                PlanError(
                    source="plan.logic",
                    detail=LogicUnknownDepError(step_id="s3", dep_id="s_missing"),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=1,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic — self_dep",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicSelfDepError(step_id="s2"),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=1,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic — unknown_dep",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicUnknownDepError(step_id="s3", dep_id="s_weather"),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=1,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic — 混合多类型错误（dup + unknown_dep + unknown_op + cycle）",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicDupStepIdError(step_id="s2", count=3),
                ),
                PlanError(
                    source="plan.logic",
                    detail=LogicUnknownDepError(step_id="s3", dep_id="s_missing"),
                ),
                PlanError(
                    source="plan.logic",
                    detail=LogicUnknownOpError(step_id="s4", op="weather_search"),
                ),
                PlanError(
                    source="plan.logic",
                    detail=LogicCycleError(members=["s1", "s3", "s5"]),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=2,
        ),
    ),
    (
        "REGENERATE_PLAN / plan.logic 多条错误（cycle + dup step_id）",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="plan.logic",
                    detail=LogicCycleError(members=["s1", "s2", "s3"]),
                ),
                PlanError(
                    source="plan.logic",
                    detail=LogicDupStepIdError(step_id="s2", count=2),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_PLAN,
            round=2,
        ),
    ),
    (
        "REGENERATE_STEP / 单个 step，单条 step.params 错误",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="step.params",
                    detail=ParamsErrorDetail(
                        step_id="s3",
                        tool_name="navigate",
                        message="1 validation error for NavigateArgs\ndestination\n  field required (type=value_error.missing)",
                    ),
                )
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_STEP,
            round=1,
        ),
    ),
    (
        "REGENERATE_STEP / 单个 step，params + execution 多条错误",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="step.params",
                    detail=ParamsErrorDetail(
                        step_id="s2",
                        tool_name="poi_search",
                        message="extra field 'radius' not allowed",
                    ),
                ),
                PlanError(
                    source="step.execution",
                    detail=ExecutionErrorDetail(
                        step_id="s2",
                        tool_name="poi_search",
                        message="POI API returned 429 Too Many Requests after 3 retries",
                    ),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_STEP,
            round=1,
        ),
    ),
    (
        "REGENERATE_STEP / 多个 step 各有错误",
        PlanRepairContext(
            errors=[
                PlanError(
                    source="step.params",
                    detail=ParamsErrorDetail(
                        step_id="s2",
                        tool_name="websearch",
                        message="field 'query' expected str, got NoneType",
                    ),
                ),
                PlanError(
                    source="step.execution",
                    detail=ExecutionErrorDetail(
                        step_id="s4",
                        tool_name="navigate",
                        message="destination address could not be resolved",
                    ),
                ),
                PlanError(
                    source="step.projection",
                    detail=ProjectionErrorDetail(
                        step_id="s1",
                        concept_name="WeatherInfo",
                        message="projection returned empty result",
                    ),
                ),
            ],
            failed_plan=None,
            policy=RepairPolicy.REGENERATE_STEP,
            round=2,
        ),
    ),
]


def main() -> None:
    for label, ctx in CASES:
        console.print(f"\n[bold]{label}[/bold]")
        console.rule(style="dim")
        console.print(_format_repair_message(ctx), markup=False)
        console.print()


if __name__ == "__main__":
    main()
