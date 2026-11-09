from typing import Any, Sequence, Protocol, runtime_checkable

from pydantic import BaseModel

from aicore.tools import ToolProtocol
from aicore.utils.nl_repr.basemodel import nl_repr_base_model_type
from aicore.agents.plan.dag_runner import BareDag


def generate_tools_description[TT: ToolProtocol[BaseModel]](tools: Sequence[TT]) -> str:
    """动态生成算子类型及参数描述"""
    lines: list[str] = []
    for t in tools:
        lines.append("\n")
        lines.append(f"工具名字: {t.name}")
        lines.append(f"工具描述: {t.description}")
        lines.append(f"工具输入参数:\n {nl_repr_base_model_type(t.args_schema)}")
    return "\n".join(lines)


@runtime_checkable
class PlanSpec[PlanT: BaseModel](Protocol):
    """一个对比实验的策略：把会一起变化的 schema 与 prompt 绑在一起。

    - plan_type: 该实验的结构化 Plan schema（structured_output 的 output_type）
    - build_sys_prompt: 该实验的 system prompt。达成判据形态是**可选能力**：想跟随注入形态的
      spec 另外实现 :class:`~aicore.agents.plan.criterion.CriterionAware`（`plan_schema_v1`
      就是），core 用 :func:`~aicore.agents.plan.criterion.bind_criterion` 取"绑好的那份"；
      历史实验（v0 / v2 / v3）的提示词各自冻结，不吃形态注入。
    """

    name: str
    plan_type: type[PlanT]

    def build_sys_prompt(self, tools: Sequence[ToolProtocol[Any]]) -> str: ...

    def build_dag(self, plan: PlanT) -> BareDag[Any]: ...
