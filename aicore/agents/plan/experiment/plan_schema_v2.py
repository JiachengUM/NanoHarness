"""Plan schema 对比实验 v1：typed-union 形式的 inputs/outputs。

inputs/outputs 直接复用 aicore.tools.dag.operator_models 里的算子参数/输出模型，
用 Union 让模型按 op 选择对应的强类型入参，而不是自由字符串。
"""

from typing import Any, Sequence, Union

from pydantic import BaseModel, Field

from aicore.tools import ToolProtocol

from aicore.agents.plan.plan_spec import PlanSpec
from aicore.agents.plan.dag import DAG, Edge
from aicore.agents.plan.dag_runner import BareDag

from aicore.tools.dag.operator_models import (
    POISearchParams,
    NavigationParams,
    MusicSearchParams,
    AudioPlayParams,
    CarControlParams,
    WebSearchParams,
    POISearchOutput,
    NavigationOutput,
    MusicSearchOutput,
    AudioPlayOutput,
    CarControlOutput,
    WebSearchOutput,
)


OperatorInputParams = Union[
    POISearchParams,
    NavigationParams,
    MusicSearchParams,
    AudioPlayParams,
    CarControlParams,
    WebSearchParams,
]

OperatorOutputParams = Union[
    POISearchOutput,
    NavigationOutput,
    MusicSearchOutput,
    AudioPlayOutput,
    CarControlOutput,
    WebSearchOutput,
]


class PlanStepV2(BaseModel):
    step_id: str = Field(description="步骤标识，如 s1, s2")
    op: str = Field(description="算子类型")
    step_goal: str = Field(description="本步骤的小目标")
    depends_on: list[str] = Field(description="直接依赖的步骤ID列表")
    inputs: OperatorInputParams = Field(
        description="本步骤入参，缺失信息引用合法的依赖步骤输出（$step_id.出参）"
    )
    outputs: OperatorOutputParams = Field(
        description="本步骤出参，值留空（算子输出模型实例，其字段供下游步骤通过 $step_id.field 占位符引用）"
    )


class StructuredPlanV2(BaseModel):
    goal: str = Field(description="任务目标")
    steps: list[PlanStepV2] = Field(description="详细步骤列表")


class PlanSpecV2:
    name = "v2"
    plan_type = StructuredPlanV2

    def build_dag(self, plan: StructuredPlanV2) -> BareDag[PlanStepV2]:
        known = {s.step_id for s in plan.steps}
        edges = [
            Edge(source=dep, target=s.step_id, data=None)
            for s in plan.steps
            for dep in s.depends_on
            if dep in known and dep != s.step_id
        ]
        return DAG(nodes=plan.steps, edges=edges)


    def build_sys_prompt(self, tools: Sequence[ToolProtocol[Any]]) -> str:
        return f"""
        将用户输入转换成结构化Plan，基于Plan获取任务目标所需的信息；
        Plan生成策略：一步一步将目标分解成最小可执行单元；"""


plan_spec_v2: PlanSpec[StructuredPlanV2] = PlanSpecV2()
