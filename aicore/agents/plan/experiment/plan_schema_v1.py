"""Plan schema v1：当前主线版本（也是 plact 使用的唯一 schema）。

dict 形式 inputs、声明式 outputs、jq condition，达成判据是 ``success_check``。
自包含，不继承其它 schema。

唯一自变量：达成判据的形态
--------------------------
``success_check`` 是"两个形态、一个字段"的强类型联合（见 :mod:`aicore.agents.plan.criterion`）：

- ``{"kind": "jq_expr", "expression": "..."}``：由规则层用 jq 确定性求值（不注入把控时）；
- ``{"kind": "nature_assertion", "assertions": [...]}``：由判定器（LLM / Jev）判定。

形态在调用时由依赖注入决定（``create_plan(..., criterion=...)``），并同时决定三件事——
提示词里唯一变化的那一段（:func:`criterion.rules`）、静态校验走哪一支
（:mod:`aicore.agents.plan.dag_checker` 第 7 项）、以及 runner 里谁来做达成判定。
**除这三处之外，schema、提示词、校验、事件载荷一律与形态无关**；所以本文件的提示词里，
共用段一律写"达成判据"而不写形态名与字段名，避免模型照着共用段的字样填另一种形态。
"""

from typing import Any, Sequence

from pydantic import BaseModel, Field

from aicore.tools import ToolProtocol

from aicore.agents.plan.criterion import (
    KIND_JQ,
    CriterionKind,
    SuccessCheck,
    rules,
)
from aicore.agents.plan.dag import DAG, Edge
from aicore.agents.plan.dag_runner import BareDag
from aicore.agents.plan.plan_spec import PlanSpec, generate_tools_description
from aicore.utils._concepts.meta import SimpleConcept

__all__ = [
    "ConceptOutput",
    "PlanStepV1",
    "StructuredPlanV1",
    "PlanSpecV1",
    "plan_spec_v1",
    "CONDITION_RULES",
]


class ConceptOutput(BaseModel):
    """Plan step 的一个输出槽：声明该槽的输出是否为列表及对应的 Concept 定义。"""

    is_list: bool = Field(
        description=(
            "本步骤输出是否为列表：True 产出同类元素的列表（每个元素对应一个 concept 实例），"
            "False 产出单个 concept 实例。"
        )
    )

    concept: SimpleConcept = Field(description="输出概念的定义。")


class PlanStepV1(BaseModel):
    step_goal: str = Field(description="本步骤的小目标")

    step_id: str = Field(description="步骤标识，如 s1, s2。")

    op: str = Field(description="工具名称")

    depends_on: list[str] = Field(description=("直接依赖的前序步骤 ID 列表。"))

    inputs: dict[str, Any] = Field(
        description=(
            "本步骤的工具入参，必须符合 op 对应工具的输入字段。只填写执行该工具需要的参数。"
        )
    )

    outputs: ConceptOutput = Field(description="本步骤的出参。")

    condition: str | None = Field(
        description=("本步骤的前置条件，jq 布尔表达式；为 null 表示无条件执行。"),
        default=None,
    )

    success_check: SuccessCheck = Field(
        description=(
            "判定 step_goal 是否真正达成的判据。kind 只有两种取值："
            "jq_expr（expression = jq 布尔表达式，由规则层确定性求值）或 "
            "nature_assertion（assertions = 1~3 条可判真假的自然语言断言，由判定器逐条判定，"
            "全部成立才算达成）。本次计划只接受其中一种形态，按系统提示词里「达成校验」一节的要求填写。"
        ),
    )


class StructuredPlanV1(BaseModel):
    goal: str = Field(description="任务目标")

    steps: list[PlanStepV1] = Field(description="详细步骤列表。")


# ── system prompt 的规则段 ────────────────────────────────────────────────
# 提示词按"可替换缝"切成段，好让**唯一**随判据形态变化的那一段（criterion.rules(kind)）
# 单独抽出来，其余段落与形态无关、逐字共用：
#
#   _RULES_HEAD → output_modeling_extra → _OUTPUT_ATTRS_RULE → _RULES_REFERENCES
#   → CONDITION_RULES（共用）→ _RULES_FLOW（共用）→ rules(kind)（唯一变量）→ _RULES_TAIL（共用）
#
# 共用段里**不出现** success_check / jq_expr / nature_assertion 这些形态专名，只说"达成判据"：
# 否则模型会照着共用段的字样填另一种形态（旧版本踩过：共用段残留 success_check 字样，
# 于是 JEV 臂的计划里会带上一个它本不该写的 jq 判据）。
# tests/agents/test_plan_schema_prompt.py 钉住"两形态提示词除判据段外逐字节相同"。
_RULES_HEAD = """将用户输入转换成结构化 Plan，基于 Plan 获取任务目标所需的信息。

## 策略
- 目标所需信息能通过确定性的工具调用步骤获得的，就转成 Plan 逐步收集。
- 并非所有需求都能转成 PlanStep，比如复杂决策；这类情况不要硬拆分支，
  只需在 Plan 中尽可能多地收集相关信息，交由 plan 完成后的模型统一整理，回答用户的原始问题。

## 计划构造规则

### 拆分
- 按可执行顺序把任务拆成最小工具调用单元，每个步骤只调用一个工具。
- 信息查询、筛选、导航、车控等不同动作应拆成独立步骤，通过 depends_on 连接。
- depends_on 必须完备：凡是本步骤 inputs、condition 或达成判据中引用到的步骤，
  都必须列入 depends_on；不要依赖后续步骤或自身。

### 输出建模
- concept.name 用 PascalCase 英文命名，是下游引用路径的第一段。
- concept 自身无 list 语义，某步输出是不是列表由该步的 is_list 显式声明。
- concept 不支持嵌套或复杂结构，attributes 尽量平铺：把一条信息里的多个维度拆成多个独立字段，
  而不是塞进一个字段（如天气的最低温、最高温拆成 min_temperature、max_temperature）。
"""

# 变体（如 v3）把额外的输出建模约束插在这里，从而不必复制整段提示词。
_OUTPUT_MODELING_EXTRA = ""

_OUTPUT_ATTRS_RULE = """- concept.attributes 只需枚举下游步骤、condition 或达成判据会引用到的字段——
  这些字段即引用路径的可用目标，用不到的不投影。

"""

_RULES_REFERENCES = """### 运行状态与引用
- 步骤间通过引用彼此的 outputs 传递数据。计划运行状态 JSON 的结构为
  {"s1":{"outputs":{"ConceptName":{"attribute_name":...}}},...}；当某步 outputs.is_list=true 时，
  ConceptName 对应值是对象数组，如 {"s1":{"outputs":{"ConceptName":[{"attribute_name":...}]}}}。
- 任何引用里的 step_id、ConceptName、attribute_name 都必须来自已声明的步骤与对应步骤 outputs 中
  的 concept.name / attribute.name。
- inputs 用模板占位符 {{ jq路径 }} 引用上游 outputs；只允许 jq 路径语法，禁止函数、管道、比较、
  and/or、if/then/else、变量、自然语言条件和切片。允许的路径段只有：
  · 对象字段：.field，例如 {{ .s1.outputs.WeatherInfo.weather_condition }}
  · 数组下标：[0]，例如 {{ .s1.outputs.RoastDuckShop[0].address }}
  · 数组迭代：[]，仅用于把上游 is_list=true 的列表字段批量取出，例如
    {{ .s1.outputs.LightMusicSong[].play_id }}，结果顺序和数量与上游列表一致。
- input 占位符是某入参字段的全部内容时，取值保持原始类型（如字符串或列表）；占位符嵌在更长字符串
  里时，列表会转成用「, 」连接的文本再拼入。
"""

# condition 的规则：与判据形态无关，两形态逐字共用（这里**只讲 condition**）。
CONDITION_RULES = """- condition 是完整 jq 布尔表达式，引用路径从
  .step_id.outputs.ConceptName.attribute_name 开始；禁止使用未定义变量如 $s1、$s2，禁止写自然语言条件。
- condition 由 runner 用 jq 实际编译并求值，结果必须为 true 或 false；语法错误或结果非
  true/false 都会被判定为错误，不是仅供参考的自然语言。
  数组长度判断示例：((.s2.outputs.PoiResult.poi_list // []) | length) > 0；
  复合条件示例：(.s1.outputs.WeatherInfo.min_temperature < 21) and
  (((.s2.outputs.PoiResult.poi_list // []) | length) > 0)。

"""

_RULES_FLOW = """### 控制流
- 当用户需求包含"如果/否则/满足条件才执行"等控制流时，必须拆成多个带 condition 的互斥分支步骤；
  不要把条件判断合并进某个步骤的 inputs 或自然语言描述（inputs 只是纯参数值，不支持 for/if/eq 等表达式）。
- 分支步骤的 condition 只能引用 depends_on 中前序步骤已声明的 outputs。
- condition 求值为 false 时，本步骤被跳过且不产生任何 outputs；任何 depends_on 直接或间接包含
  该步骤的下游步骤也会被级联跳过，不再单独判断自己的 condition。因此除非是故意设计的互斥分支
  （下游本就该随之跳过），不要让某个步骤依赖一个可能被跳过的步骤的 outputs。

"""

_RULES_TAIL = """## TOOL GUIDELINES
导航工具只需要输入地址名称即可，不需要详细经纬度坐标，但是导航工具只会返回成功与否，不会返回类似 ETA，距离，耗时等
media工具输入只需要音乐/歌单名称即可，不需要具体 id
"""


class PlanSpecV1:
    """v1 的 plan spec：schema + 提示词。

    ``criterion`` 是**注入的判据形态**（见 :mod:`aicore.agents.plan.criterion`），它只影响提示词里
    唯一那一段（:func:`criterion.rules`）。注入入口是 :func:`criterion.bind_criterion`：core 拿
    ``spec.with_criterion(kind)`` 得到的"绑好的那份"去建 system prompt，而 ``PlanSpec`` 协议本身
    不必为此改动（历史实验的 spec 不实现该能力，提示词照旧冻结）。
    """

    name = "v1"
    plan_type = StructuredPlanV1

    # 注入的判据形态（经 criterion.bind_criterion 绑定，见类 docstring）。
    criterion: CriterionKind

    def __init__(self, criterion: CriterionKind = KIND_JQ) -> None:
        self.criterion = criterion

    def with_criterion(self, criterion: CriterionKind) -> "PlanSpecV1":
        """返回一份绑定了该判据形态的 spec（原实例不变）。"""
        return type(self)(criterion=criterion)

    # 变体的可替换缝（都是"与判据形态无关"的扩展点）：
    # - output_modeling_extra：额外的输出建模约束（v3 用它要求执行类工具的 attribute 与工具输出字段同名）；
    # - tools_description：工具清单的渲染方式（v3 额外展示执行类工具的输出字段）。
    output_modeling_extra: str = _OUTPUT_MODELING_EXTRA

    def tools_description(self, tools: Sequence[ToolProtocol[Any]]) -> str:
        return generate_tools_description(tools)

    def build_dag(self, plan: StructuredPlanV1) -> BareDag[PlanStepV1]:
        known = {s.step_id for s in plan.steps}
        edges = [
            Edge(source=dep, target=s.step_id, data=None)
            for s in plan.steps
            for dep in s.depends_on
            if dep in known and dep != s.step_id
        ]
        return DAG(nodes=plan.steps, edges=edges)

    def build_sys_prompt(self, tools: Sequence[ToolProtocol[Any]]) -> str:
        """拼装系统提示词。

        唯一随判据形态变化的是 :func:`criterion.rules` 那一段（形态来自 ``self.criterion``，
        由 :func:`criterion.bind_criterion` 注入），其余段落逐字共用。
        """
        rules_text = (
            _RULES_HEAD
            + self.output_modeling_extra
            + _OUTPUT_ATTRS_RULE
            + _RULES_REFERENCES
            + CONDITION_RULES
            + _RULES_FLOW
            + rules(self.criterion)
            + _RULES_TAIL
        )
        return (
            f"{rules_text}\n## 可以使用的工具\n{self.tools_description(tools)}\n"
        )


plan_spec_v1: PlanSpec[StructuredPlanV1] = PlanSpecV1()
