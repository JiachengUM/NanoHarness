"""success_check 失败后的补救诊断（独立 model call）。

success_check 是**客观、意图盲**的验收判据：它只判断“达没达到 plan 声明的标准”，
并不知道某条约束是用户硬性要求、还是 plan 把模糊需求操作化时自己猜的。因此
“失败之后该 replan 还是判定无解”无法从 error source 静态推出，需要结合原始 query
判断失败约束的来源与可放松性——这正是本模块做的事。

判断分两步：
1. 失败约束是 plan 的操作化猜测、换个仍忠于用户意图的做法能满足吗？
   能（如把“附近”猜成 500m、把筛选设得过窄）→ replan。
2. 不能满足时，看这步的产出对用户 / 下游是否仍够用：
   - 完全用不了且阻塞下游（约束内在于用户意图且确实没有，如显式“500m 内”没有、
     指定歌曲/歌手就是搜不到）→ skip_unsolvable：runner 级联跳过下游，最终回答如实说明无法完成。
   - 不完美但够用、不阻塞（如导航返回成功但缺路线详情，用户核心需求已达成）→
     accept_degraded：产出保留、下游照常执行，仅标记以便最终回答如实说明局限。

TODO(ask_user): 设计上还有第四个出口——当硬约束存在用户可能接受的放松 / near-miss 时，
    应澄清（human-in-the-loop）而非静默降级。当前未实现交互通道，暂并入 skip_unsolvable。
TODO(evidence-gating): 理想情况下 skip_unsolvable 应有证据门槛（同一 goal 换 approach
    后仍失败才判无解），需要跨轮失败记忆；当前为单次 model call 直接定夺。
TODO(step-level replan): 诊断目前只输出 replan（整个 plan 重生成）。换参数即可解的场景
    本应有更省的「重试本 step」出口，但依赖 runner 的动态单步重执行，尚未实现（见
    errors.RepairPolicy.REGENERATE_STEP 占位桩），暂由整体 replan 承接。
TODO(music-hardcode): 当前在系统提示里硬性规定「音乐/歌曲搜不到或信息不全 → 一律
    skip_unsolvable」。这是权宜之计——本该由诊断结合 query 判断歌曲是否用户硬性指定
    （指定歌手/歌名搜不到才无解，模糊描述搜不到其实可 replan 放宽）。等诊断判断足够可靠、
    或音乐搜索支持渐进放宽后应移除此规则，回归通用判据。
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from aicore.models.model_api import UserMessage, ModelAPI, ModelCallParams


# 当前实现的三个出口，各建模为一个变体（ask_user 见模块 docstring 的 TODO，暂不加入）。
# 三选一用「outcome 判别的 Union」表达，而非单 model + Literal 字段：每个出口只携带自己
# 真正需要的字段（replan 面向重规划模型、故拆成假设+方向；skip/degraded 面向用户、各一句话），
# 类型层面就排除了「outcome 与所填字段错配」。


class Replan(BaseModel):
    """失败约束是 plan 的操作化猜测，换更宽/更合适的参数或工具仍能忠于用户意图 → 重新规划。
    payload 面向重规划模型，故拆成「被证伪的假设」+「重做方向」两段以更好地引导。"""

    outcome: Literal["replan"] = "replan"
    failed_assumption: str = Field(
        description="plan 把用户模糊需求操作化时猜的、现已被结果证伪的那条约束（如把“附近”当作“500m 内”）。"
    )
    retry_direction: str = Field(
        description="忠于用户意图的重做方向，将随 repair 上下文提示重规划模型（如“扩大半径或改用周边搜索”）。"
    )


class SkipUnsolvable(BaseModel):
    """失败约束内在于用户意图且确实无法满足，产出完全用不了 → 判无解，
    跳过依赖它的后续步骤并如实告知用户无法完成。"""

    outcome: Literal["skip_unsolvable"] = "skip_unsolvable"
    unsolvable_reason: str = Field(
        description="一句话说明为何无法完成，会如实呈现给用户，请写得对用户可读。"
    )


class AcceptDegraded(BaseModel):
    """产出不完美但够用、不阻塞下游（用户核心需求已达成）→ 接受降级，
    下游照常执行，仅在回答中说明局限。"""

    outcome: Literal["accept_degraded"] = "accept_degraded"
    limitation: str = Field(
        description="一句话说明产出的局限，会如实呈现给用户，请写得对用户可读。"
    )


# 三选一的补救裁决。用普通 Union（非判别联合）：每个变体的 outcome Literal 已保证互斥，
# pydantic 解析时据此唯一匹配；schema 出 anyOf 而非 oneOf + discriminator，对 strict
# json_schema 更友好（火山/OpenAI strict 认 anyOf、不认 oneOf/discriminator）。
RemediationDiagnosis = Replan | SkipUnsolvable | AcceptDegraded
# "jev" 是 TypeSafe System One 判定器的来源标记（见 aicore/agents/plan/jev/），
# 与 "rule"/"llm"/"fallback" 并列；加它是纯类型放宽，不影响任何既有分支。
type DiagnosisSource = Literal["rule", "llm", "fallback", "jev"]


class DiagnosisResult(BaseModel):
    source: DiagnosisSource
    decision: RemediationDiagnosis


class _DiagnosisEnvelope(BaseModel):
    """结构化输出信封：把联合包一层 object 作 root，避免 root 直接是 anyOf 被 strict 拒绝。
    仅作 structured_output 的 output_type 用，诊断函数对外返回 .decision。"""

    decision: RemediationDiagnosis


_SYS_PROMPT = """你是计划执行的补救诊断器。某个计划步骤已执行完成，但它的 success_check（一个客观的验收判据）未通过，意味着该步骤没有真正达成它的小目标。你的任务是判断接下来该怎么办。

注意「工具原始返回」是工具真实报出的内容（含 status/message/error_msg 等），往往直接说明失败原因（如"不支持该 query""搜不到""返回为空"）；而「该步骤实际产出（结构化）」是经概念抽取后的结果，可能已丢弃这些线索。判断时以原始返回为准。

先问：success_check 里**没被满足的那条约束**，是用户在原始请求里**硬性要求**的，还是 plan 为了执行把**模糊需求操作化**时自己猜的？换一条仍然忠于用户意图的做法，能不能满足它？

- 能满足（约束来自 plan 的猜测）→ outcome=replan。
  例：用户说“附近的停车场”，plan 自己猜成“500m 内”，结果为空——“附近”并没限定 500m，扩大半径仍忠于意图，应 replan。
  例：搜索筛选条件设得过窄导致结果为空或不匹配，放宽条件仍能满足用户，应 replan。
  例：用户想查看餐厅评价，plan 猜测使用poi_search，但工具为找到结果——用户意图是“查看评价”，并不硬性限定用哪个工具，换用 web_search 如果能找到相关信息，应 replan。
- 不能满足时，再看这步的产出对用户/下游是否还够用：
  - 完全用不了、且后续步骤依赖它（约束内在于用户意图且确实没有）→ outcome=skip_unsolvable。
    例：用户明确要求“500m 内”的停车场但确实没有——放松就违背硬性限定，判无解。
    例：用户指定某歌手的某首歌，工具里确实搜不到——换别的歌就不是用户要的了，判无解。
  - 不完美但够用、不阻塞下游，用户核心需求其实已达成 → outcome=accept_degraded。
    例：导航工具返回“规划成功”但没给出路线里程/时长等细节——核心的导航操作已完成，缺的只是锦上添花的细节，接受降级并在回答里说明。
    例：结果基本满足只是某个次要字段缺失，不影响用户主要目的，接受降级。

根据判断只输出三种裁决之一，并填对应字段：
- replan：给出 failed_assumption（plan 操作化时猜错、现被证伪的那条约束）与 retry_direction（忠于用户意图的重做方向）。这两段会提示重规划模型，请写得具体可执行。
- skip_unsolvable：给出 unsolvable_reason，一句话说明无法完成的原因，会原样告知用户，请写得对用户可读。
- accept_degraded：给出 limitation，一句话说明结果的局限，会原样告知用户，请写得对用户可读。"""


# runner 里 is_list 空结果的 projection 消息（EMPTY_LIST_OUTPUT_MESSAGE）。这里复制一份而非
# import，避免 diagnosis <-> plan_dag_runner 循环依赖；改动时两处保持一致。
_EMPTY_LIST_OUTPUT_MESSAGE = "is_list output is empty"


def _rule_based_diagnosis(
    *,
    op: str,
    process_error_kind: str | None,
    failure_message: str,
) -> RemediationDiagnosis | None:
    """规则前置层：命中最直接的场景即确定性定夺，返回 None 表示交由 LLM 兜底。

    顺序即优先级：先用"过程错误"判 replan（plan/工具层问题，换 approach 可解），未命中再看
    是否音乐搜索类未达成（无解）。projection 类型不匹配（非空 list）不在 replan 规则内，会落到
    音乐/联网规则或 LLM——这是有意的：s1 那类"指定歌手/歌名搜不到"应判无解而非反复重规划。
    """
    if (
        process_error_kind == "projection"
        and _EMPTY_LIST_OUTPUT_MESSAGE in failure_message
    ):
        return Replan(
            failed_assumption="当前执行路径未取得可用候选（列表输出为空）",
            retry_direction="换更宽/更合适的参数或工具重规划",
        )
    if process_error_kind in ("input_ref", "params", "condition", "execution"):
        return Replan(
            failed_assumption="步骤引用/入参/条件写错或工具执行失败",
            retry_direction="重规划修正后重试",
        )
    return None


def _build_user_message(
    *,
    query: str,
    step_goal: str,
    op: str,
    inputs: dict[str, Any],
    success_check: str,
    outputs_snapshot: dict[str, Any],
    tool_output: dict[str, Any] | list[Any],
    failure_message: str,
) -> str:
    return (
        f"原始用户请求：\n{query}\n\n"
        f"未达成的步骤：\n"
        f"- 步骤目标：{step_goal}\n"
        f"- 使用工具：{op}\n"
        f"- 工具入参：{json.dumps(inputs, ensure_ascii=False, default=str)}\n"
        f"- success_check 表达式：{success_check}\n"
        f"- 未通过原因：{failure_message}\n"
        f"- 工具原始返回：{json.dumps(tool_output, ensure_ascii=False, default=str)}\n"
        f"- 该步骤实际产出（结构化）：{json.dumps(outputs_snapshot, ensure_ascii=False, default=str)}\n\n"
        f"请判断补救策略（replan / skip_unsolvable / accept_degraded 之一）。"
    )


async def diagnose_success_check_failure(
    *,
    query: str,
    step_goal: str,
    op: str,
    inputs: dict[str, Any],
    success_check: str,
    outputs_snapshot: dict[str, Any],
    tool_output: dict[str, Any] | list[Any],
    failure_message: str,
    model_api: ModelAPI[Any],
    process_error_kind: str | None = None,
    params: ModelCallParams | None = None,
) -> DiagnosisResult:
    """对一次 success_check 失败做补救诊断。结构化输出解析失败时抛出，由调用方兜底。

    先过规则前置层（_rule_based_diagnosis）：命中最直接的场景即确定性定夺、不打 LLM；未命中
    再走 LLM 兜底。process_error_kind 是导致失败的过程错误类型（input_ref/params/condition/
    execution/projection，或 None 表示纯 success_check 判 false），供规则层区分
    "plan/工具问题（replan）"与"数据确实不可得（unsolvable）"。

    tool_output 是工具的原始返回（未经 concept 投影），承载 status/message/error_msg
    等失败线索——这些字段常被 concept 抽取丢弃，却是判 replan / unsolvable 的关键证据。
    """
    rule = _rule_based_diagnosis(
        op=op,
        process_error_kind=process_error_kind,
        failure_message=failure_message,
    )
    if rule is not None:
        return DiagnosisResult(source="rule", decision=rule)

    state = model_api.initial_state(system_prompt=_SYS_PROMPT)
    msg = UserMessage(
        text=_build_user_message(
            query=query,
            step_goal=step_goal,
            op=op,
            inputs=inputs,
            success_check=success_check,
            outputs_snapshot=outputs_snapshot,
            tool_output=tool_output,
            failure_message=failure_message,
        )
    )
    result = await model_api.structured_output(
        msg,
        output_type=_DiagnosisEnvelope,
        state=state,
        params=params,
    )
    if result.parsed is None:
        raise ValueError("remediation diagnosis structured output failed to parse")
    return DiagnosisResult(source="llm", decision=result.parsed.decision)
