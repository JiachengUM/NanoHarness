"""达成判据（``success_check``）：整个 plact 里**唯一**随"谁来验收"变化的形态。

设计约束
--------
判据的形态是这个系统里唯一被允许存在的自变量：

======================  ==============================  ==================================
形态                     谁来判定                        典型注入
======================  ==============================  ==================================
``jq_expr``            规则层（runner 用 jq 确定性求值）   不注入把控（judge=None）
``nature_assertion``   判定器（LLM / Jev）               ``LlmJudge`` / ``JevJudge``
======================  ==============================  ==================================

除此以外的一切——计划 schema 的其它字段、提示词的其余段落、静态校验的其余条目、事件与
错误的载荷形状、runner 的验证尾段——都必须与形态无关。所以本模块集中承载那"唯一变化"的
三件事，别的模块一律通过这里读写，不再各自判断形态：

1. :data:`SuccessCheck` 两个形态的类型（进 JSON schema，``kind`` 可见且必填）；
2. :func:`rules` 提示词里**唯一**随形态变化的那一段；
3. :func:`render` / :func:`label` 人读呈现（事件、错误、repair 上下文）。

为什么用"字面量标签 + 普通联合"而不是 ``Field(discriminator=...)``
----------------------------------------------------------------
每个变体自带 ``kind: Literal[...]``，pydantic 据此唯一匹配，schema 出 ``anyOf``（每支的
``kind`` 是 ``const``）——CriterionKind 在 schema 里**直接可见且必填**，同时避开
``oneOf + discriminator``：项目里已有实测结论，火山/OpenAI 的 strict json_schema 认
``anyOf``、不认 ``oneOf/discriminator``（见 ``diagnosis.RemediationDiagnosis`` 的注释）。

判据的**静态校验**在 :mod:`.dag_checker` 里（那里已经 import errors，避免本模块反向依赖）。
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, Field

__all__ = [
    "CriterionKind",
    "KIND_JQ",
    "KIND_ASSERTION",
    "ALL_KINDS",
    "MAX_ASSERTIONS",
    "JqExprCriterion",
    "NatureAssertionCriterion",
    "jq_expr",
    "nature_assertion",
    "SuccessCheck",
    "rules",
    "render",
    "label",
    "describe",
    "kind_of",
    "kind_mismatch_message",
    "mismatched_step_ids",
    "as_dict",
    "CriterionAware",
    "bind_criterion",
]

# 两个枚举值就是产品语义：jq_expr 由规则层求值，nature_assertion 由判定器判定。
type CriterionKind = Literal["jq_expr", "nature_assertion"]

# 声明成各自的字面量类型（而不是宽的 CriterionKind）：构造时才能被 pyright 认出
# "kind 只能是这一个值"——否则每个构造函数都要写一遍字面量。
KIND_JQ: Literal["jq_expr"] = "jq_expr"
KIND_ASSERTION: Literal["nature_assertion"] = "nature_assertion"
ALL_KINDS: tuple[CriterionKind, ...] = (KIND_JQ, KIND_ASSERTION)

# 断言条数上限（与提示词里写的 "1~3 条" 一致；静态校验按此拦超量）。
MAX_ASSERTIONS = 3


class JqExprCriterion(BaseModel):
    """jq 形态：一个布尔表达式，由规则层（runner）确定性求值。

    引用路径从 ``.step_id.outputs.ConceptName.attribute_name`` 开始，与 ``condition`` 同一套
    受限 jq 语法；求值结果必须严格是 ``true``/``false``。
    """

    kind: Literal["jq_expr"] = Field(
        description="判据形态：jq_expr = jq 布尔表达式，由规则层确定性求值。",
    )
    expression: str = Field(
        description=(
            "jq 布尔表达式，判定本步产出是否达成。必须至少引用一次本步自身 outputs"
            "（如 .s1.outputs.WeatherInfo.temperature > 30），否则本步失败时它仍可能判 true。"
        ),
    )


class NatureAssertionCriterion(BaseModel):
    """自然语言形态：1~3 条可判真假的断言，由判定器逐条判定（全部成立才算达成）。

    断言是"本步产出应当满足什么"的一句话，不写 jq、不写引用路径——判定器读的是语义。
    """

    kind: Literal["nature_assertion"] = Field(
        description="判据形态：nature_assertion = 自然语言断言，由判定器逐条判定。",
    )
    assertions: list[str] = Field(
        description=(
            "1~3 条可判真假的断言，全部成立才算达成。例：[\"至少返回 3 家烤鸭店\", "
            "\"评分最高的那家评分不低于 4.0\"]。不要写 jq 表达式、引用路径或操作符。"
        ),
    )


# 普通联合（非判别联合）：见模块 docstring 的 strict json_schema 说明。
type SuccessCheck = JqExprCriterion | NatureAssertionCriterion


def jq_expr(expression: str) -> JqExprCriterion:
    """构造 jq 形态判据（``kind`` 在 schema 里是必填的，代码里用本函数省掉重复）。"""
    return JqExprCriterion(kind=KIND_JQ, expression=expression)


def nature_assertion(assertions: list[str]) -> NatureAssertionCriterion:
    """构造自然语言断言形态判据（同上）。"""
    return NatureAssertionCriterion(kind=KIND_ASSERTION, assertions=assertions)


def kind_of(check: SuccessCheck) -> CriterionKind:
    """取判据形态。"""
    return check.kind


def describe(kind: CriterionKind) -> str:
    """形态的中文名（用于错误信息与 trace）。"""
    return "jq 表达式" if kind == KIND_JQ else "自然语言断言"


def label(check: SuccessCheck | None) -> str:
    """判据的短标签（``success_check`` / ``断言``），用于错误与事件的人读文案。"""
    if isinstance(check, NatureAssertionCriterion):
        return "断言"
    return "success_check"


def render(check: SuccessCheck | None) -> str:
    """判据 → 单行人读文本（repair 上下文、事件摘要、诊断提示）。

    jq 形态给出表达式原文；自然语言形态把多条断言用「；」连成一句。
    """
    if check is None:
        return "（未给出达成判据）"
    if isinstance(check, JqExprCriterion):
        return check.expression
    return "；".join(check.assertions) if check.assertions else "（断言为空）"


def kind_mismatch_message(kind: CriterionKind, step_ids: list[str]) -> str:
    """形态不匹配时的错误文案（进 repair 上下文，要写清"该怎么改"）。"""
    example = (
        '{"kind": "jq_expr", "expression": ".s1.outputs.Out.field != null"}'
        if kind == KIND_JQ
        else '{"kind": "nature_assertion", "assertions": ["至少返回 3 家烤鸭店"]}'
    )
    return (
        f"以下 step 的 success_check 形态不对：{'、'.join(step_ids)}。"
        f"本计划要求 success_check 必须是{describe(kind)}形态，形如 {example}；"
        f"kind 必须是 {kind!r}，且只填该形态对应的字段。"
    )


# ══════════════════════════════════════════════════════════════════════════
# 提示词：唯一随形态变化的那一段
# ══════════════════════════════════════════════════════════════════════════
# 组装顺序见 plan_schema_v1.build_sys_prompt：
#   HEAD（中性） + CONDITION_RULES（共用） + FLOW（共用） + CRITERION_RULES[kind] + TAIL（共用）
# 这里的判据段是**唯一**允许随形态变化的部分；共用段一律写"达成判据"，不写形态名，
# 否则模型会照着共用段的字样去填另一种形态。

_JQ_CRITERION_RULES = """### 达成校验
- 每个 step 都必须写 success_check、不能留空；它在执行后判断本步产出算不算达成
  （与 condition 相反：condition 在执行前决定这步跑不跑）。
- success_check 的形态是 {"kind": "jq_expr", "expression": "<jq 布尔表达式>"}，
  本计划只接受这一种形态，kind 必须原样填 "jq_expr"。
- 必须自约束：至少引用一次本步自身 outputs，否则本步失败时 check 仍可能判 true 而漏判。
- 它是『完全达成』的严格判据：通过即认定该步完美达成、不再复核；不通过才进诊断模块复核
  （可能重新规划 / 判部分达成 / 降级接受）。据此从严写——宁可失败后交诊断兜底，也不要写松而放过未达成的情况。
- 要校验的判别字段（如 singer、duration、play_id）必须先在本步 outputs 里投影出来；
  看似模糊的语义判断（如曲风是否属于轻音乐）也要落成 check——交给 concept 投影成判别字段（如 genre）再校验。
- 典型用途：校验搜索结果非空、必填字段非空、判别字段与用户目标一致。示例：
  {"kind": "jq_expr", "expression": ".s3.outputs.SongInfo.singer == \\"周杰伦\\" and (.s3.outputs.SongInfo.song_name | contains(\\"晴天\\"))"}。
"""

_NATURE_CRITERION_RULES = """### 达成校验
- 每个 step 都必须写 success_check、不能留空；它在执行后判断本步产出算不算达成
  （与 condition 相反：condition 在执行前决定这步跑不跑）。
- success_check 的形态是 {"kind": "nature_assertion", "assertions": ["第一条断言", "第二条断言"]}
  （1~3 条），本计划只接受这一种形态，kind 必须原样填 "nature_assertion"：
  不要写 jq 表达式、引用路径、操作符或工具名——判定器读的是断言的语义。
- 每条断言是一句可判真假的话，只描述"本步产出应当满足什么"，形如：
  "至少返回 3 家烤鸭店"、"结果里评分最高的那家评分不低于 4.0"、"目标地址等于上一步评分最高那家店的地址"。
- 断言里引用的判别字段必须能判定：本步 outputs.concept.attributes 里没声明的字段判不了，
  要把"曲风是否属于轻音乐"这类语义要求落成断言，就得先把判别字段（如 genre）投影出来。
- 可以引用上游步骤的产出做对比，但被引用到的步骤必须列入 depends_on。
- 宁少勿滥：只断言你真正要校验的（产出非空、内容与用户要求相符、关键字段一致），不要凑数。
"""

CRITERION_RULES: dict[CriterionKind, str] = {
    KIND_JQ: _JQ_CRITERION_RULES,
    KIND_ASSERTION: _NATURE_CRITERION_RULES,
}


@runtime_checkable
class CriterionAware(Protocol):
    """可选能力：该 spec 的提示词随判据形态切换（见 :func:`bind_criterion`）。"""

    def with_criterion(self, criterion: CriterionKind) -> Any:
        """返回一份"绑定了该判据形态"的 spec（原实例不变）。"""
        ...


def bind_criterion[SpecT](spec: SpecT, criterion: CriterionKind) -> SpecT:
    """把判据形态绑到 spec 上（注入点）；不实现该能力的 spec 原样返回。

    为什么用可选能力而不是给 `PlanSpec.build_sys_prompt` 加参数：
    ``experiment/plan_schema_v0/v2/v3`` 也是 PlanSpec 的实现，但它们的提示词各自冻结、
    不参与判据形态注入；给协议加必需参数会让这些**不该改动**的历史文件集体不满足协议。
    所以约定是：想跟随形态的 spec 实现本协议，core 在唯一的入口处用本函数取"绑好的那份对象"。
    """
    if isinstance(spec, CriterionAware):
        return cast(SpecT, spec.with_criterion(criterion))
    return spec


def rules(kind: CriterionKind) -> str:
    """提示词里唯一随形态变化的段。"""
    try:
        return CRITERION_RULES[kind]
    except KeyError:  # pragma: no cover - 类型上不可能，防 isinstance 之外的手滑
        raise ValueError(
            f"未知的判据形态 {kind!r}；只支持 {list(ALL_KINDS)}"
        ) from None


def as_dict(check: SuccessCheck | None) -> dict[str, Any] | None:
    """判据 → 可 JSON 序列化的 dict（判定器 state 里用，kind 显式可见）。"""
    return None if check is None else check.model_dump(mode="json")


def mismatched_step_ids(plan: Any, kind: CriterionKind) -> list[str]:
    """找出 success_check 形态与注入要求不符的 step（create_plan 解析后立即校验）。

    只看带 ``kind`` 标签的判据：v0/v2 等历史 schema 的 step 还是裸 ``str``，那些实验不参与
    形态注入，不能被这里的校验误伤。
    """
    wrong: list[str] = []
    for step in getattr(plan, "steps", None) or []:
        check = getattr(step, "success_check", None)
        if check is None or getattr(check, "kind", kind) == kind:
            continue
        wrong.append(str(getattr(step, "step_id", "?")))
    return wrong
