import json
from typing import Literal, Annotated, Any
from enum import StrEnum

from pydantic import BaseModel, Field

from aicore.tools.concept_outputs import ConceptItemError
from aicore.utils.nl_repr import nl_repr as _nl_repr

from aicore.agents.plan.criterion import SuccessCheck, label, render


# ── plan.logic 子类型 ──────────────────────────────────────────────────────────


class LogicDupStepIdError(BaseModel):
    """同一 step_id 出现多次。"""

    kind: Literal["logic.dup_step_id"] = "logic.dup_step_id"
    step_id: str
    count: int

    def __nl_repr__(self, **_: Any) -> str:
        return f"duplicate step_id {self.step_id!r} (appears {self.count} times)"


class LogicSelfDepError(BaseModel):
    """step 的 depends_on 中包含自身。"""

    kind: Literal["logic.self_dep"] = "logic.self_dep"
    step_id: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step {self.step_id!r} depends on itself"


class LogicUnknownDepError(BaseModel):
    """step 的 depends_on 引用了不存在的 step。"""

    kind: Literal["logic.unknown_dep"] = "logic.unknown_dep"
    step_id: str  # 含有坏依赖的 step
    dep_id: str  # 被引用但不存在的 step_id

    def __nl_repr__(self, **_: Any) -> str:
        return f"step {self.step_id!r} depends on unknown step {self.dep_id!r}"


class LogicUnknownOpError(BaseModel):
    """step 引用了未注册的 tool。"""

    kind: Literal["logic.unknown_op"] = "logic.unknown_op"
    step_id: str
    op: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step {self.step_id!r}: tool {self.op!r} not found"


class LogicCycleError(BaseModel):
    """plan 中存在循环依赖，members 为环中所有节点。"""

    kind: Literal["logic.cycle"] = "logic.cycle"
    members: list[str]

    def __nl_repr__(self, **_: Any) -> str:
        return f"cyclic dependency among steps: {', '.join(self.members)}"


class LogicUndeclaredRefError(BaseModel):
    """step inputs 或 condition 中通过引用了某步骤的输出，但该步骤未出现在 depends_on 中。

    意味着执行顺序未被显式约束，可能导致引用到未完成步骤的输出。
    修复方式：在 step_id 的 depends_on 中补充 ref_step_id。
    """

    kind: Literal["logic.undeclared_ref"] = "logic.undeclared_ref"
    step_id: str  # inputs/condition 中含有引用的 step
    ref_step_id: str  # 被引用但未声明依赖的 step

    def __nl_repr__(self, **_: Any) -> str:
        return (
            f"step {self.step_id!r} references step {self.ref_step_id!r} "
            f"but {self.ref_step_id!r} is not in depends_on"
        )


class LogicInvalidConditionError(BaseModel):
    """step.condition 不是合法的 jq 表达式（编译失败）。"""

    kind: Literal["logic.invalid_condition"] = "logic.invalid_condition"
    step_id: str
    condition: str
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step {self.step_id!r} condition {self.condition!r} is not valid jq: {self.message}"


class LogicInvalidSuccessCheckError(BaseModel):
    """step 的达成判据（success_check）非法。

    三种情形共用本类型（都是「判据本身写坏了」，修复动作也一样）：jq 形态编译失败、
    判据为空（jq 空串 / 断言空列表）、断言条数超过上限。判据形态本身不匹配注入要求
    时走 ``plan.schema``（见 core.create_plan），不在静态检查这里。
    """

    kind: Literal["logic.invalid_success_check"] = "logic.invalid_success_check"
    step_id: str
    success_check: str
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step {self.step_id!r} 达成判据 {self.success_check!r} 非法：{self.message}"


class LogicSuccessCheckNotSelfConstrainedError(BaseModel):
    """step.success_check 未引用自身 outputs（缺少 `.<step_id>.outputs` 引用）。

    success_check 是本 step 的**唯一**达成门：若它只引用别的 step、不约束自身产出，本 step 执行
    失败（outputs 为空）时 check 仍可能判 true，导致失败被漏判。故要求至少自引用一次。
    """

    kind: Literal["logic.success_check_not_self_constrained"] = (
        "logic.success_check_not_self_constrained"
    )
    step_id: str
    success_check: str

    def __nl_repr__(self, **_: Any) -> str:
        return (
            f"step {self.step_id!r} success_check {self.success_check!r} does not reference its own "
            f"outputs (.{self.step_id}.outputs...); it must constrain this step's own result"
        )


class LogicRefMalformedError(BaseModel):
    """step.inputs 中的引用路径不是受限 jq path 形状。

    覆盖两种情况：不是 path-only jq，或路径长度不够 / 第二段不是字面量 outputs。
    """

    kind: Literal["logic.ref_malformed"] = "logic.ref_malformed"
    step_id: str  # 含有该 ref 的 step
    ref: str
    found_segment: str | None  # 第二段实际内容；None 表示路径连这一段都没有

    def __nl_repr__(self, **_: Any) -> str:
        got = self.found_segment if self.found_segment is not None else "<missing>"
        return (
            f"step {self.step_id!r} ref {self.ref!r} malformed: "
            f"expected '.step_id.outputs.ConceptName...', got second segment {got!r}"
        )


class LogicRefConceptMismatchError(BaseModel):
    """ref 中的 ConceptName 与被引用 step 实际声明的 outputs.concept.name 不一致。"""

    kind: Literal["logic.ref_concept_mismatch"] = "logic.ref_concept_mismatch"
    step_id: str
    ref: str
    ref_step_id: str  # 被引用的 step（ref 第一段）
    expected_concept: str  # ref_step_id 实际声明的 concept name
    actual_concept: str  # ref 里写的 concept name

    def __nl_repr__(self, **_: Any) -> str:
        return (
            f"step {self.step_id!r} ref {self.ref!r}: step {self.ref_step_id!r} declares "
            f"output concept {self.expected_concept!r}, but ref references {self.actual_concept!r}"
        )


class LogicRefShapeMismatchError(BaseModel):
    """ref 的下标/数组迭代段与被引用 step 的 outputs.is_list 不匹配。

    两种子情况用 reason 区分：
    - segment_count_mismatch：concept name 之后的段数不对（is_list=True 应为 2 段
      [index-or-[], attribute]，is_list=False 应为 1 段 [attribute]），涵盖缺段、多段。
    - invalid_index_segment：段数对，但 is_list=True 时的下标段既不是十进制数字也不是 []。
    """

    kind: Literal["logic.ref_shape_mismatch"] = "logic.ref_shape_mismatch"
    step_id: str
    ref: str
    ref_step_id: str
    is_list: bool
    reason: Literal["segment_count_mismatch", "invalid_index_segment"]
    expected_segment_count: int
    actual_segment_count: int
    found_index_segment: str | None = None  # 仅 invalid_index_segment 时有意义

    def __nl_repr__(self, **_: Any) -> str:
        prefix = f"step {self.step_id!r} ref {self.ref!r}"
        if self.reason == "segment_count_mismatch":
            shape = (
                "[<index-or-empty>].attribute_name"
                if self.is_list
                else ".attribute_name"
            )
            return (
                f"{prefix}: step {self.ref_step_id!r} output is_list={self.is_list}, "
                f"ref after concept name must be shaped {shape} "
                f"(expected {self.expected_segment_count} segment(s), got {self.actual_segment_count})"
            )
        return (
            f"{prefix}: expected a numeric index or [] at this position, "
            f"got {self.found_index_segment!r}"
        )


class LogicRefUnknownAttributeError(BaseModel):
    """ref 引用的属性名不在被引用 step 声明的 concept.attributes 中。"""

    kind: Literal["logic.ref_unknown_attribute"] = "logic.ref_unknown_attribute"
    step_id: str
    ref: str
    ref_step_id: str
    concept_name: str
    attribute: str
    known_attributes: list[str]

    def __nl_repr__(self, **_: Any) -> str:
        return (
            f"step {self.step_id!r} ref {self.ref!r}: concept {self.concept_name!r} "
            f"(from step {self.ref_step_id!r}) has no attribute {self.attribute!r}; "
            f"declared attributes: {self.known_attributes!r}"
        )


# ── 其他 detail 类型 ───────────────────────────────────────────────────────────


class SchemaErrorDetail(BaseModel):
    """LLM 输出无法解析为合法 schema（Pydantic ValidationError 或 API 异常）。"""

    kind: Literal["schema"] = "schema"
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return self.message


class ParamsErrorDetail(BaseModel):
    """step inputs 校验失败（validate_tool_arguments 抛出异常）。"""

    kind: Literal["params"] = "params"
    step_id: str
    tool_name: str
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step={self.step_id} {self.tool_name}: {self.message}"


class InputRefErrorDetail(BaseModel):
    """step.inputs 中的 jq 模板引用在运行时解析失败或解析结果为空。"""

    kind: Literal["input_ref"] = "input_ref"
    step_id: str
    ref: str
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step={self.step_id} input ref {self.ref!r} failed: {self.message}"


class ExecutionErrorDetail(BaseModel):
    """tool call 失败（TaskToolRunner 已耗尽重试）。

    TODO: message 应替换为来自 tool 层的结构化 ToolError，待 tool 包定义后启用。
    """

    kind: Literal["execution"] = "execution"
    step_id: str
    tool_name: str
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return f"step={self.step_id} {self.tool_name}: {self.message}"


class ConditionErrorDetail(BaseModel):
    """step.condition 在运行时求值失败：jq 求值抛异常，或结果不是布尔值。

    与 LogicInvalidConditionError（jq 语法错误，静态可查）不同，这里是
    表达式本身合法但引用的字段在实际运行状态中不可用/类型不符等动态问题。
    """

    kind: Literal["condition"] = "condition"
    step_id: str
    condition: str
    message: str

    def __nl_repr__(self, **_: Any) -> str:
        return (
            f"step={self.step_id} condition {self.condition!r} failed: {self.message}"
        )


class ProjectionErrorDetail(BaseModel):
    """concept_tool_outputs 投影失败或返回空结果。

    item_errors 在 is_list=True 且整体失败时携带各元素的错误明细。
    部分成功（item_errors 非空但 data 非空）由 policy 层决定是否视为错误，不在此体现。
    """

    kind: Literal["projection"] = "projection"
    step_id: str
    concept_name: str
    message: str = "projection returned empty"
    item_errors: list[ConceptItemError] = []

    def __nl_repr__(self, **_: Any) -> str:
        base = f"step={self.step_id} concept '{self.concept_name}' {self.message}"
        if self.item_errors:
            failed = ", ".join(str(e.index) for e in self.item_errors)
            return f"{base} (failed indices: {failed})"
        return base


class SemanticGapError(BaseModel):
    """计划语义审计未通过：静态结构完全合法，但"按字面完美执行"无法满足用户请求。

    与 dag_checker 的 13 条 LogicXxxError 正交——那些只查语法与引用形状，本类型承载的是
    **语义**缺陷（漏了诉求、参数与硬约束不符、success_check 过松、依赖不成立）。
    之所以要有独立类型而非塞进 SchemaErrorDetail：gap_kind 是枚举，进 repair 上下文后
    下一轮 planner 能直接照抄修什么，也便于离线统计"审计最常拦下哪类缺陷"。

    由 ``aicore.agents.plan.jev`` 的 plan_audit 判定点产出（判定器可以是 Jev 或 LLM）。
    """

    kind: Literal["plan.semantics"] = "plan.semantics"
    gap_kind: str
    coverage: float = 0.0
    check_strictness: float = 0.0
    rationale: str = ""

    def __nl_repr__(self, **_: Any) -> str:
        detail = f"：{self.rationale}" if self.rationale else ""
        return (
            f"计划语义审计未通过（缺口类型 {self.gap_kind}，覆盖度 {self.coverage:.2f}，"
            f"success_check 严格度 {self.check_strictness:.2f}）{detail}"
        )


class RemediationErrorDetail(BaseModel):
    """step 未达成（达成判据未通过），且补救诊断判定为 **replan**。

    进入本错误通道的**只有 replan 裁决**——判据未通过本身不作为独立 error/事件上报；
    诊断判定无解 / 降级接受时走 PlanStepDoneEvent.unmet（StepUnmet），不在此。因此本 detail
    的语义是「诊断要求重规划」，而非「判据未通过」：
    - diagnosis_reason 是诊断给出的重规划依据（如“500m 是 plan 猜测，应扩大搜索半径”），
      经 nl_repr 进入 repair_context，提示下一轮 LLM 到底该怎么改，避免原样重来；
    - 判据（``success_check``，jq 表达式或自然语言断言，形态见 criterion）/ message /
      outputs_snapshot / tool_output 是支撑该判断的客观证据（当时校验了什么、为何不过、
      投影后拿到什么、工具原始返回了什么）。tool_output 是未经 concept 投影的工具原始返回，
      承载 status/message/error_msg 等失败线索——这些字段常被投影丢弃，却是下一轮该怎么改
      的关键依据。
    """

    kind: Literal["remediation"] = "remediation"
    step_id: str
    diagnosis_reason: str
    success_check: SuccessCheck | None = None
    message: str
    outputs_snapshot: dict[str, Any] = {}
    tool_output: dict[str, Any] | list[Any] = {}

    def __nl_repr__(self, **_: Any) -> str:
        criterion = (
            f"{label(self.success_check)} {render(self.success_check)!r}"
            if self.success_check is not None
            else "达成判据"
        )
        base = (
            f"step={self.step_id} 目标未达成，诊断结论：换 approach 可解——{self.diagnosis_reason}"
            f"（{criterion} 未通过：{self.message}"
        )
        if self.tool_output:
            raw = json.dumps(self.tool_output, ensure_ascii=False, default=str)
            base += f"；工具原始返回={raw}"
        if self.outputs_snapshot:
            snap = json.dumps(self.outputs_snapshot, ensure_ascii=False, default=str)
            base += f"；投影后 outputs={snap}"
        return base + "）"


PlanErrorDetail = Annotated[
    LogicDupStepIdError
    | LogicSelfDepError
    | LogicUnknownDepError
    | LogicUnknownOpError
    | LogicCycleError
    | LogicUndeclaredRefError
    | LogicInvalidConditionError
    | LogicInvalidSuccessCheckError
    | LogicSuccessCheckNotSelfConstrainedError
    | LogicRefMalformedError
    | LogicRefConceptMismatchError
    | LogicRefShapeMismatchError
    | LogicRefUnknownAttributeError
    | SchemaErrorDetail
    | ParamsErrorDetail
    | InputRefErrorDetail
    | ExecutionErrorDetail
    | ConditionErrorDetail
    | ProjectionErrorDetail
    | SemanticGapError
    | RemediationErrorDetail,
    Field(discriminator="kind"),
]


# ── RepairPolicy / PlanError / PlanRepairContext ───────────────────────────────


class RepairPolicy(StrEnum):
    """loop 在检测到错误后的处置策略。

    REGENERATE_PLAN: 重新生成完整 plan（当前唯一可用的 LLM 介入方式）。
    REGENERATE_STEP: 只更新出错 step（需要 runner 支持动态 step 更新，当前未实现）。
    ACCEPT_DEGRADED: 不再修复，带着已有（部分）结果继续出答案。
    """

    REGENERATE_PLAN = "regenerate_plan"
    REGENERATE_STEP = "regenerate_step"  # 占坑：runner 支持动态 step 更新后启用
    ACCEPT_DEGRADED = "accept_degraded"


class PlanError(BaseModel):
    source: Literal[
        "plan.schema",  # LLM 输出无法解析为合法 schema
        "plan.logic",  # 结构问题：cycle、unknown op、dup step_id、非法 condition 语法等
        "step.input_ref",  # step inputs 中的 jq 模板引用运行时解析失败或为空
        "step.params",  # step inputs 校验失败
        "step.condition",  # step condition 运行时求值失败
        "step.execution",  # tool call 失败（runner 已耗尽重试）
        "step.projection",  # concept 投影失败
        "step.remediation",  # 补救诊断判定 replan（success_check 未达成，且诊断为换 approach 可解）
        "plan.semantics",  # 计划语义审计未通过（结构合法但无法满足用户请求）
    ]  # 注：诊断判定无解/降级接受不进 error 通道，走 PlanStepDoneEvent.unmet
    detail: PlanErrorDetail

    def nl_repr(self) -> str:
        return f"[{self.source}] {_nl_repr(self.detail)}"


class PlanRepairContext(BaseModel):
    """传给下一轮 create_plan 的 repair 上下文。

    设计约束：只携带本轮的错误，不累积历史轮次。
    历史对话由 model_api 的 state（即对话消息历史）隐式携带。

    policy 指导 _format_repair_message 如何向 LLM 描述修复任务：
    - REGENERATE_PLAN：要求重新输出完整 plan
    - REGENERATE_STEP：要求只更新出错 step（runner 侧尚未实现，当前不可达）
    """

    errors: list[PlanError]
    failed_plan: BaseModel | None = None  # None 当且仅当 create_plan 本身抛出
    policy: RepairPolicy
    round: int
