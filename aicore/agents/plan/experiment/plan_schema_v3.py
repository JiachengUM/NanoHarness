"""Plan schema v3：在 v1 基础上为执行类工具声明输出字段，约束 concept attribute 命名。

与 v1 的差异仅在 prompt：
- 工具描述中，执行类工具（CarControl / AudioPlay / navigation）额外展示可用的输出字段列表。
- 输出建模规则中新增约束：对声明了输出字段的工具，concept.attributes.name 必须从输出字段中选择。
- 这样 concept_tool_outputs_v3 的 passthrough 就能可靠命中，跳过 LLM 调用。

Plan schema（PlanStepV1 / StructuredPlanV1 / ConceptOutput）完全复用 v1，不重复定义。
"""

from typing import Any, Sequence

from pydantic import BaseModel

from aicore.tools import ToolProtocol
from aicore.utils.nl_repr.basemodel import nl_repr_base_model_type

from aicore.agents.plan.dag import DAG, Edge
from aicore.agents.plan.dag_runner import BareDag
from aicore.agents.plan.experiment.plan_schema_v1 import (
    PlanStepV1,
    StructuredPlanV1,
)
from aicore.agents.plan.plan_spec import PlanSpec


# ---------------------------------------------------------------------------
# 执行类工具的输出字段声明
# ---------------------------------------------------------------------------

# tool_name -> [(field_name, type, description), ...]
# 只列原始类型字段（string/integer/float/boolean），observation 等嵌套 dict 不列入。
# passthrough 的 _match_fields 按 key 匹配，这里的 field_name 必须与工具实际输出的 dict key 一致。
TOOL_OUTPUT_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "CarControl": [
        ("status", "string", "执行状态: success/error"),
        ("message", "string", "执行结果消息"),
        ("error_msg", "string", "错误信息"),
    ],
    "AudioPlay": [
        ("status", "string", "执行状态: success/error"),
        ("message", "string", "执行结果消息"),
        ("error_msg", "string", "错误信息"),
    ],
    "navigation": [
        ("status", "string", "执行状态: success/error"),
        ("message", "string", "执行结果消息"),
        ("error_msg", "string", "错误信息"),
    ],
    
}


def _format_output_fields(fields: list[tuple[str, str, str]]) -> str:
    """将输出字段列表格式化为 prompt 文本。"""
    return "\n".join(f"  {name} ({ftype}): {desc}" for name, ftype, desc in fields)


def _generate_tools_description_v3[TT: ToolProtocol[BaseModel]](
    tools: Sequence[TT],
) -> str:
    """生成工具描述，对声明了输出字段的工具额外展示可选输出字段。"""
    lines: list[str] = []
    for t in tools:
        lines.append("\n")
        lines.append(f"工具名字: {t.name}")
        lines.append(f"工具描述: {t.description}")
        lines.append(f"工具输入参数:\n {nl_repr_base_model_type(t.args_schema)}")
        if t.name in TOOL_OUTPUT_FIELDS:
            fields_text = _format_output_fields(TOOL_OUTPUT_FIELDS[t.name])
            lines.append(
                f"工具输出字段（concept.attributes.name 必须从中选取）:\n{fields_text}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PlanSpec v3
# ---------------------------------------------------------------------------

_OUTPUT_CONSTRAINT_RULE = """\
- 对于声明了「工具输出字段」的工具（如车控、媒体播放、导航等执行类工具），
  concept.attributes 的 name 必须与该工具输出字段的名称完全一致，不可自行命名。
  这些工具的输出是确定性的执行反馈，attribute 直接对应工具返回的字段 key。"""


class PlanSpecV3:
    name = "v3"
    plan_type = StructuredPlanV1

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
        rules = f"""将用户输入转换成结构化 Plan，基于 Plan 获取任务目标所需的信息。

## 策略
- 目标所需信息能通过确定性的工具调用步骤获得的，就转成 Plan 逐步收集。
- 并非所有需求都能转成 PlanStep，比如复杂决策；这类情况不要硬拆分支，
  只需在 Plan 中尽可能多地收集相关信息，交由 plan 完成后的模型统一整理，回答用户的原始问题。

## 计划构造规则

### 拆分
- 按可执行顺序把任务拆成最小工具调用单元，每个步骤只调用一个工具。
- 信息查询、筛选、导航、车控等不同动作应拆成独立步骤，通过 depends_on 连接。
- depends_on 必须完备：凡是本步骤 inputs、condition 或 success_check 中引用到的步骤，
  都必须列入 depends_on；不要依赖后续步骤或自身。

### 输出建模
- concept.name 用 PascalCase 英文命名，是下游引用路径的第一段。
- concept 自身无 list 语义，某步输出是不是列表由该步的 is_list 显式声明。
- concept 不支持嵌套或复杂结构，attributes 尽量平铺：把一条信息里的多个维度拆成多个独立字段，
  而不是塞进一个字段（如天气的最低温、最高温拆成 min_temperature、max_temperature）。
- concept.attributes 只需枚举下游步骤、condition、success_check 会引用到的字段——
  这些字段即引用路径的可用目标，用不到的不投影。
{_OUTPUT_CONSTRAINT_RULE}

### 运行状态与引用
- 步骤间通过引用彼此的 outputs 传递数据。计划运行状态 JSON 的结构为
  {{"s1":{{"outputs":{{"ConceptName":{{"attribute_name":...}}}}}},...}}：顶层 key 是 step_id，
  往下依次是 outputs、concept.name、concept.attributes 中的字段名。
- 任何引用里的 ConceptName、attribute_name 都必须来自对应步骤 outputs 中已声明的
  concept.name 与 attribute.name。
- 两套引用写法，用途不同：
  · inputs 用模板占位符 {{{{/step_id/outputs/ConceptName/attribute_name}}}}
    （以 / 分隔、下标用 /0 /1，禁止 [0] [1] 写法），例如 {{{{/s1/outputs/RoastDuckShop/0/address}}}}。
    需要把上游 is_list=True 列表里每个元素的某字段批量取出时，下标段可写通配符 *：
    {{{{/step_id/outputs/ConceptName/*/attribute_name}}}}，例如 {{{{/s1/outputs/LightMusicSong/*/play_id}}}}，
    顺序和数量与上游列表一致。* 的约束：一条路径最多一个 *；* 后必须紧跟且只跟一个叶子属性段，
    不能是最后一段、不能再嵌套下标或第二个 *；只有上游 outputs.is_list 为 true 时才能用 *。
    当占位符是某入参字段的全部内容时，取值保持原始列表类型（用于该字段本身接受列表的场景）；
    当占位符嵌在更长字符串里（如自然语言描述）时，列表会被转成用「, 」连接的文本再拼入。
  · condition 与 success_check 用 jq 路径 .step_id.outputs.ConceptName.attribute_name，
    禁止使用未定义变量如 $s1、$s2，禁止写自然语言条件。
- condition 与 success_check 都是 runner 会用 jq 实际编译并求值的布尔表达式，结果必须为 true 或 false；
  语法错误或结果非 true/false 都会被判定为错误，不是仅供参考的自然语言。
  数组长度判断示例：((.s2.outputs.PoiResult.poi_list // []) | length) > 0；
  复合条件示例：(.s1.outputs.WeatherInfo.min_temperature < 21) and
  (((.s2.outputs.PoiResult.poi_list // []) | length) > 0)。

### 控制流
- 当用户需求包含"如果/否则/满足条件才执行"等控制流时，必须拆成多个带 condition 的互斥分支步骤；
  不要把条件判断合并进某个步骤的 inputs 或自然语言描述（inputs 只是纯参数值，不支持 for/if/eq 等表达式）。
- 分支步骤的 condition 只能引用 depends_on 中前序步骤已声明的 outputs。
- condition 求值为 false 时，本步骤被跳过且不产生任何 outputs；任何 depends_on 直接或间接包含
  该步骤的下游步骤也会被级联跳过，不再单独判断自己的 condition。因此除非是故意设计的互斥分支
  （下游本就该随之跳过），不要让某个步骤依赖一个可能被跳过的步骤的 outputs。

### 达成校验
- 每个 step 都必须写 success_check、不能留空；它在执行后判断本步产出算不算达成
  （与 condition 相反：condition 在执行前决定这步跑不跑）。
- 必须自约束：至少引用一次本步自身 outputs，否则本步失败时 check 仍可能判 true 而漏判。
- 它是『完全达成』的严格判据：通过即认定该步完美达成、不再复核；不通过才进诊断模块复核
  （可能重新规划 / 判部分达成 / 降级接受）。据此从严写——宁可失败后交诊断兜底，也不要写松而放过未达成的情况。
- 要校验的判别字段（如 singer、duration、play_id）必须先在本步 outputs 里投影出来；
  看似模糊的语义判断（如曲风是否属于轻音乐）也要落成 check——交给 concept 投影成判别字段（如 genre）再校验。
- 典型用途：校验搜索结果非空、必填字段非空、判别字段与用户目标一致。
  示例 .s3.outputs.SongInfo.singer == "周杰伦" and (.s3.outputs.SongInfo.song_name | contains("晴天"))。
"""
        return f"{rules}\n## 可以使用的工具\n{_generate_tools_description_v3(tools)}\n"


plan_spec_v3: PlanSpec[StructuredPlanV1] = PlanSpecV3()
