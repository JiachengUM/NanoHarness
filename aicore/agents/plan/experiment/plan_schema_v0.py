"""Plan schema 对比实验 v0：纯 list 形式的 inputs/outputs。

自包含、无外部依赖，不继承任何其它 schema。inputs/outputs 都是字段名列表，
模型只需从工具字段里挑名字，不需要填具体值或类型。
"""

from typing import Any, Sequence

from pydantic import BaseModel, Field

from aicore.tools import ToolProtocol

from aicore.agents.plan.plan_spec import PlanSpec, generate_tools_description


class PlanStepV0(BaseModel):
    step_goal: str = Field(description="本步骤的小目标")
    step_id: str = Field(description="步骤标识，如 s1, s2。每个步骤调用一个工具。")
    op: str = Field(description="工具名称")
    depends_on: list[str] = Field(description="直接依赖的前序步骤ID列表")
    inputs: list[str] = Field(
        description="本步骤入参列表（从工具的输入字段中选择，选择时考虑给依赖步骤提供依赖）"
    )
    outputs: list[str] = Field(
        description="本步骤出参列表（从工具的输出字段中选择，选择时考虑给下游步骤提供依赖）"
    )


class StructuredPlanV0(BaseModel):
    goal: str = Field(description="任务目标")
    steps: list[PlanStepV0] = Field(description="详细步骤列表")


class PlanSpecV0:
    name = "v0"
    plan_type = StructuredPlanV0

    def build_sys_prompt(self, tools: Sequence[ToolProtocol[Any]]) -> str:
        return f"""
将用户输入转换成结构化Plan，基于Plan获取任务目标所需的信息；
Plan生成策略：一步一步将目标分解成最小可执行单元；
优化Plan时必须输出完整的steps列表；

可以使用的工具如下：
{generate_tools_description(tools)}
"""


plan_spec_v0: PlanSpec[StructuredPlanV0] = PlanSpecV0()
