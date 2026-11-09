from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IntentType = Literal["simple", "complex"]
DecisionSource = Literal[
    "exact_simple",
    "exact_complex",
    "parser_simple",
    "parser_veto",
    "llm_simple",
    "llm_complex",
    "default_complex",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParseCandidate(StrictModel):
    capability_id: str
    covered_text: str = ""
    unconsumed_text: str = ""
    missing_slots: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def is_complete(self) -> bool:
        return not self.missing_slots and not self.unconsumed_text.strip() and not self.risk_flags


class RouterTrace(StrictModel):
    project: str
    query: str
    normalized_query: str
    decision_path: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    matched_candidates: list[ParseCandidate] = Field(default_factory=list)
    rule_version: str


class RouterDecision(StrictModel):
    label: IntentType
    source: DecisionSource
    trace: RouterTrace


class LLMPromptAsset(StrictModel):
    id: str
    system_prompt: str


class ValueSpec(StrictModel):
    literals: list[str] = Field(
        default_factory=list,
        description="可枚举的值白名单，例如蓝色、三档、24小时制。",
    )
    patterns: list[str] = Field(
        default_factory=list,
        description="值的正则签名，例如28度、百分之三十、天蓝色。",
    )


class CapabilityCard(StrictModel):
    id: str = Field(description="能力项唯一ID，稳定用于 trace、审计和回归定位。")
    name: str = Field(description="中文能力名，说明这条白名单覆盖的用户可感知场景。")
    executor: str = Field(description="具体执行工具或大场景，例如端侧车控、系统、音乐、导航、天气。")
    required_slots: list[str] = Field(
        default_factory=list,
        description="判定为 simple 必须命中的槽位，例如 action、target。",
    )
    targets: list[str] = Field(
        default_factory=list,
        description="目标白名单，表示用户要控制或查询的对象。",
    )
    actions: list[str] = Field(
        default_factory=list,
        description="动作白名单，表示允许的控制、查询或播放动作。",
    )
    values: ValueSpec = Field(
        default_factory=ValueSpec,
        description="值白名单和值正则，用于温度、颜色、档位、百分比等泛化。",
    )
    target_policy: Literal["closed", "open_after_action"] = Field(
        default="closed",
        description="目标槽匹配策略：封闭白名单，或允许动作后的自由文本作为目标。",
    )
    residue_policy: Literal["strict", "safe_modifier"] = Field(
        default="strict",
        description="残留文本处理策略：严格无残留，或允许安全修饰语残留。",
    )
    route_policy: Literal["parser_simple", "llm_fallback"] = Field(
        default="parser_simple",
        description="路由策略：完整命中后直接证明 simple，或继续交给 LLM fallback 判断。",
    )
    intent_markers: list[str] = Field(
        default_factory=list,
        description="开放目标 fallback 的轻量意图标记；只在 route_policy=llm_fallback 的能力卡上生效。",
    )
    intent_marker_policy: Literal["when_unresolved", "override_cross_executor"] = Field(
        default="when_unresolved",
        description="intent_markers 生效范围：仅无完整解析时生效，或覆盖跨执行器的完整解析。",
    )


class LexiconEntry(StrictModel):
    slot: str
    canonical: str
    aliases: list[str]


class RiskRule(StrictModel):
    risk_id: str
    patterns: list[str]
    # strong：命中即进入 global veto，并被视作 residue 不安全的强分裂信号。
    # weak：不参与 global veto，仅作为 parser 内的弱分裂信号（需配合 extra capability 才升级）。
    severity: Literal["strong", "weak"] = "strong"


class ParserRules(StrictModel):
    harmless_fillers: list[str] = Field(
        default_factory=list,
        description="解析残留文本时可忽略的礼貌词、语气词和轻量修饰词。",
    )
    generic_value_patterns: list[str] = Field(
        default_factory=list,
        description="跨能力复用的取值正则信号，只用于多取值/多意图探测，不替代 card.values.patterns。",
    )
    broad_target_canonicals: list[str] = Field(
        default_factory=list,
        description="只作为维护分组的 target canonical，去重时不能吞掉真实 surface。",
    )
    query_like_capabilities: list[str] = Field(
        default_factory=list,
        description="状态/查询类能力，疑问句不一定意味着复杂。",
    )
    question_or_condition_markers: list[str] = Field(
        default_factory=list,
        description="未消费文本中出现后需要审慎处理的疑问/状态询问信号。",
    )
    conditional_markers: list[str] = Field(
        default_factory=list,
        description="未消费文本中出现后直接进入 question_or_condition 风险的条件触发信号。",
    )
    scenario_capability_aux: dict[str, list[str]] = Field(
        default_factory=dict,
        description="按 capability 声明的场景辅助词，只能在该能力完整命中后解释残留。",
    )
    scenario_friendly_risks: list[str] = Field(
        default_factory=list,
        description="命中场景辅助词后允许剥离的风险类型。",
    )
