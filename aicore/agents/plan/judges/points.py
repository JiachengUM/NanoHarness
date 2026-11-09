"""判定点的定义表：原子问题集 + 组合方程（Jev 侧）+ 结构化输出与提示（LLM 侧）。

核心设计：**一个判定点 = 一份数据**
--------------------------------
每个 :class:`DecisionPoint` 打包了同一判定点的两种后端所需的一切：

- ``questions``：交给 Jev 的原子问题集。每个问题只问一件事（gut-check 粒度），
  需要综合判断时由 ``compose`` 在代码里组合——这是 System One 官方推荐的用法，
  也是本目录所有判定点的统一风格。一个问题只允许一个语义维度，
  否则分布会被混合维度污染，概率也不再可解释。
- ``schema`` / ``system_prompt``：交给 LLM 的结构化输出类型与系统提示。
- ``compose``：原子答案 → 裁决的**代码组合方程**（纯函数，可单测）。

于是 ``JevJudge`` / ``LlmJudge`` 各自只需要一个通用 ``decide`` 实现，新增判定点只是加数据。

为什么把判定方程写成代码而不是交给模型
------------------------------------
1. 概率是校准过的工程量（RLCD），可以用阈值；阈值写在代码里，改动可评审、可回归。
2. 同样的输入必得同样的裁决（除了判定器本身的采样），便于 A/B 与快照测试。
3. 判定依据以**数值**落进事件，可离线统计"哪条分支最常触发"，
   而自由文本的裁决理由统计不了。

灰区策略
--------
阈值附近（各维度概率都不尖锐）时，Jev 后端**不回退 LLM**（项目约定：失败就报错，
不静默降级），而是取保守分支并把低置信度如实记进裁决。真正的"止损"由轮次闸门负责——
判定点各自保持局部、单一职责，互相兜底而不互相耦合。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, Question, Score

from aicore.agents.plan.diagnosis import AcceptDegraded, Replan, SkipUnsolvable

from aicore.agents.plan.judge import Point
from aicore.agents.plan.judges.jev_client import JevAnswer
from aicore.agents.plan.decisions import (
    DiagnosisAtoms,
    DiagnosisDecision,
    DiagnosisOutcome,
    FinishDecision,
    PlanAuditDecision,
    PreflightDecision,
    RoundGateDecision,
    StepAssertDecision,
    combine_finish_confidence,
)

__all__ = [
    "DiagnosisFacts",
    "DecisionPoint",
    "PREFLIGHT",
    "PLAN_AUDIT",
    "STEP_ASSERT",
    "DIAGNOSIS",
    "ROUND_GATE",
    "FINISH",
    "ALL_POINTS",
    "clause_question_id",
    "CLAUSE_HOLDS",
    "CLAUSE_FALSIFIED",
    "CLAUSE_UNSUPPORTED",
    "FINISH_COVERAGE_LEVELS",
    "RISK_LEVELS",
]


@dataclass(frozen=True)
class DecisionPoint[DecisionT: BaseModel]:
    """一个判定点的完整定义（问题集 + LLM 契约 + 组合方程 + 共享路由）。

    ``name`` 是 core 的判定点词汇（:class:`~aicore.agents.plan.judge.Point`）：core 只认它，
    不问实现怎么问。

    ``route`` 是**两条后端共用**的规则钩子：那些“必须两端一致、不该由判定器自由发挥”的
    裁决规则（如“判据不可用 → 不按断言的结论定成败”）写成纯函数，由 LLM 后端在解析后
    立即应用（见 :class:`~...judges.LlmJudge`）。JEV 后端的 ``compose`` 必须与它一致
    （幂等：``route(compose(a)) == compose(a)``，有测试钉住）。

    这不动 A/B 的实验变量：“一个模型直接给裁决”依然是 LLM 对照组的特征，被收到代码里的
    只是那几条**规则性出口**（判据自设/判不了）；补救裁决三选一仍由判定器给出。
    """

    name: Point
    questions: Callable[[Mapping[str, Any]], dict[str, Question]]
    schema: type[DecisionT]
    system_prompt: str
    compose: Callable[[dict[str, JevAnswer]], DecisionT]
    route: Callable[[DecisionT], DecisionT] | None = None


# 未命中任何分支时（灰区）的保守裁决理由，会进事件的 rationale 供统计。
GRAY_ZONE = "各维度概率都不尖锐（灰区），取保守分支"


def _require(answers: Mapping[str, JevAnswer], qid: str, kind: str) -> JevAnswer:
    """取答案并校验类型——判定器答非所问时立刻报错，而不是静默取 None。"""
    answer = answers.get(qid)
    if answer is None:
        raise KeyError(f"Jev 未返回问题 {qid!r} 的答案（已返回：{sorted(answers)}）")
    if answer.kind != kind:
        raise TypeError(f"问题 {qid!r} 期望 {kind}，实际 {answer.kind}")
    return answer


def _noul(answers: Mapping[str, JevAnswer], qid: str) -> float:
    value = _require(answers, qid, "noul").noul
    return 0.0 if value is None else float(value)


def _choice(answers: Mapping[str, JevAnswer], qid: str) -> str:
    value = _require(answers, qid, "choice").choice
    return "" if value is None else value


def _confidence(answers: Mapping[str, JevAnswer], qid: str) -> float | None:
    return _require(answers, qid, "choice").confidence


def _score(answers: Mapping[str, JevAnswer], qid: str) -> float:
    value = _require(answers, qid, "score").score
    return 0.0 if value is None else float(value)


def _sharpness(noul: float) -> float:
    """Noul 没有 confidence 字段，用 |p-0.5|*2 作为分布尖锐度的代理（0=两可，1=确定）。"""
    return round(abs(noul - 0.5) * 2, 4)


# ══════════════════════════════════════════════════════════════════════════
# 判定点 1：入口分流 preflight
# ══════════════════════════════════════════════════════════════════════════
# 现状：plact 入口无状态，永远进 plan。判定点补上"该不该规划 / 要不要先澄清"。

Q_PATH = "execution_path"
Q_NEEDS_PLAN = "needs_tool_execution"
Q_AMBIGUITY = "blocking_ambiguity"
Q_GOAL_COUNT = "independent_goal_count"
Q_PRE_RISK = "action_risk"
Q_PRE_CONFIRM = "needs_user_confirmation"

# 护栏阈值：护栏**只单向升级谨慎度**（见 compose_preflight）。
AMBIGUITY_BLOCK = 0.8
# needs_plan 低到该值时路由仍选 plan，视作路由与原子判断不一致（目前只记录、不改路径）。
NEEDS_PLAN_GATE = 0.4
RISK_MEDIUM = 0.75
RISK_HIGH = 1.5

RISK_LEVELS: tuple[str, ...] = ("低风险且容易撤销", "中等后果", "高风险或难以撤销")


def _questions_preflight(state: Mapping[str, Any]) -> dict[str, Question]:
    return {
        # 路由：这是 Choice 的原生用途（jet 官方 router 示例即此形态）。
        Q_PATH: Choice(
            instructions=(
                "How should this user request be handled? "
                "plan = 需要调用一个或多个工具、且工具之间存在数据依赖；"
                "direct = 不需要工具，直接回答即可；"
                "clarify = 缺少关键信息，任何计划都只能是猜测，应先向用户确认。"
            ),
            criteria={
                "plan": "需要多步工具调用（查询、筛选、导航、车控等）才能回答",
                "direct": "不需要任何工具调用，直接回答用户即可",
                "clarify": "缺少关键信息（时间/地点/对象/偏好等），必须先问用户",
            },
        ),
        Q_NEEDS_PLAN: Noul(
            instructions="Does answering require calling at least one tool (with data dependency between calls)?"
        ),
        Q_AMBIGUITY: Noul(
            instructions=(
                "Is key information missing such that any plan would be based on a guess "
                "rather than on what the user actually asked for?"
            )
        ),
        Q_GOAL_COUNT: Choice(
            instructions="How many independent sub-goals does this request contain?",
            criteria={
                "one": "一个子目标",
                "two": "两个互相独立的子目标",
                "three_plus": "三个及以上互相独立的子目标",
            },
        ),
        Q_PRE_RISK: Score(
            instructions="How consequential would an incorrect automated action be?",
            criteria=list(RISK_LEVELS),
        ),
        Q_PRE_CONFIRM: Noul(
            instructions="Should the system request user confirmation before executing the plan?"
        ),
    }


def _risk_level(score: float) -> str:
    if score >= RISK_HIGH:
        return "high"
    if score >= RISK_MEDIUM:
        return "medium"
    return "low"


def compose_preflight(answers: dict[str, JevAnswer]) -> PreflightDecision:
    """入口分流方程：Choice 给主判，原子判断做**单向保守覆盖**。

    覆盖只有两个方向，且都只会把路径改得更谨慎：
    - ``ambiguity`` 高 → 无论路由说什么都升为 clarify；
    - ``risk`` 高 / ``needs_confirmation`` 高 → 打标，由执行前的确认闸门使用。

    **刻意不做 plan → direct 的降级**（早期版本做过，真机验证后撤掉）：实测
    "打开车窗"这类指令的 ``needs_plan`` 会低到 0.22（判断失误），而路由 Choice 看得到工具
    目录、正确选了 ``plan``；降级护栏会把正确的路由改错。而反向的升级护栏只会多问一句，
    代价小得多——护栏的价值不对称，就不应该做成对称的。
    """
    path = _choice(answers, Q_PATH)
    needs_plan = _noul(answers, Q_NEEDS_PLAN)
    ambiguity = _noul(answers, Q_AMBIGUITY)
    risk = _score(answers, Q_PRE_RISK)
    confirm = _noul(answers, Q_PRE_CONFIRM)
    confidence = _confidence(answers, Q_PATH)

    rails: list[str] = []
    if ambiguity > AMBIGUITY_BLOCK and path != "clarify":
        rails.append(f"歧义概率 {ambiguity:.2f} 高于阈值，路径保守升为 clarify")
        path = "clarify"

    rationale = "；".join(rails) if rails else "原子判断与路由一致"
    return PreflightDecision(
        path=path,  # type: ignore[arg-type]
        needs_plan=needs_plan,
        blocking_ambiguity=ambiguity,
        goal_count=_choice(answers, Q_GOAL_COUNT) or "one",  # type: ignore[arg-type]
        risk_score=risk,
        risk_level=_risk_level(risk),  # type: ignore[arg-type]
        needs_confirmation=confirm,
        confidence=confidence,
        rationale=rationale,
    )


PREFLIGHT = DecisionPoint[PreflightDecision](
    name=Point.PREFLIGHT,
    questions=_questions_preflight,
    schema=PreflightDecision,
    system_prompt="""你是 plan-and-act 执行器的入口分流器。判断这条用户请求该走哪条执行路径。

- plan：需要调用工具、且工具间存在数据依赖（查询→筛选→导航这类链路）。
- direct：不需要工具，直接回答即可。
- clarify：缺关键信息（城市/时间/对象/偏好等），任何计划都只能是猜测。

再补齐几个独立维度：是否必须调用工具、信息缺失是否阻塞、独立子目标数量、错误执行的后果、
是否需要用户确认。每个维度只判一件事，不要把它们揉成一个综合印象。""",
    compose=compose_preflight,
)


# ══════════════════════════════════════════════════════════════════════════
# 判定点 2：计划语义审计 plan_audit
# ══════════════════════════════════════════════════════════════════════════
# 现状：plan 生成后唯一的门是 dag_checker（13 条纯静态规则，无任何语义判断）。
# 语义缺陷只能等执行完、success_check 判 false 才暴露——而 success_check 本身也是有缺陷的
# LLM 产物。审计把这个发现点前移到执行之前。

Q_AUDIT_COVERAGE = "perfect_execution_satisfies_request"
Q_AUDIT_STRICTNESS = "checks_strict_enough"
Q_AUDIT_GAP = "main_gap"
Q_AUDIT_RISK = "action_risk"
Q_AUDIT_CONFIRM = "needs_user_confirmation"

COVERAGE_MIN = 0.6
STRICTNESS_MIN = 0.5

GAP_KINDS: tuple[str, ...] = (
    "none",
    "missing_explicit_goal",
    "missing_implicit_need",
    "constraint_mismatch",
    "check_too_loose",
    "dependency_invalid",
)

GAP_TEXT: dict[str, str] = {
    "missing_explicit_goal": "漏了用户明确提到的诉求",
    "missing_implicit_need": "漏了完成用户诉求所必需的前置查询",
    "constraint_mismatch": "步骤参数与用户给出的硬约束不符",
    "check_too_loose": "success_check 写得太松，会放过实际未达成的结果",
    "dependency_invalid": "步骤依赖或条件写错，执行顺序不成立",
}


def _questions_plan_audit(state: Mapping[str, Any]) -> dict[str, Question]:
    return {
        Q_AUDIT_COVERAGE: Noul(
            instructions=(
                "If this plan were executed exactly as written and every step "
                "succeeded, would the user's request be fully satisfied?"
            )
        ),
        Q_AUDIT_STRICTNESS: Noul(
            instructions=(
                "Are the success_check expressions strict enough that they would catch "
                "results which look non-empty but do not actually satisfy the step goal?"
            )
        ),
        Q_AUDIT_GAP: Choice(
            instructions="What is the single most important gap in this plan, if any?",
            criteria={
                "none": "没有明显缺口，计划可以执行",
                "missing_explicit_goal": "漏了用户明确提到的某个诉求/维度",
                "missing_implicit_need": "漏了完成诉求所必需的前置查询步骤",
                "constraint_mismatch": "步骤输入参数与用户给出的硬约束（预算/距离/时间等）不符",
                # "check_too_loose": "success_check 太松，空结果或错结果也能通过",
                "dependency_invalid": "步骤依赖/条件/引用不成立，执行顺序有问题",
            },
        ),
        Q_AUDIT_RISK: Score(
            instructions="How consequential would it be if this plan were executed incorrectly?",
            criteria=list(RISK_LEVELS),
        ),
        Q_AUDIT_CONFIRM: Noul(
            instructions="Should the system ask the user to confirm before executing this plan?"
        ),
    }


def compose_plan_audit(answers: dict[str, JevAnswer]) -> PlanAuditDecision:
    """审计方程：覆盖度与判据严格度**双双达标**才放行（两个独立的失败模式，取与）。"""
    coverage = _noul(answers, Q_AUDIT_COVERAGE)
    strictness = _noul(answers, Q_AUDIT_STRICTNESS)
    gap = _choice(answers, Q_AUDIT_GAP) or "none"
    risk = _score(answers, Q_AUDIT_RISK)
    confirm = _noul(answers, Q_AUDIT_CONFIRM)

    reasons: list[str] = []
    if coverage < COVERAGE_MIN:
        reasons.append(f"覆盖度 {coverage:.2f} < {COVERAGE_MIN}")
    if strictness < STRICTNESS_MIN:
        reasons.append(f"判据严格度 {strictness:.2f} < {STRICTNESS_MIN}")
    passed = not reasons
    rationale = GAP_TEXT.get(gap, "") if not passed else "审计通过"
    if reasons and not rationale:
        rationale = "；".join(reasons)
    return PlanAuditDecision(
        passed=passed,
        coverage=coverage,
        check_strictness=strictness,
        gap_kind=gap,  # type: ignore[arg-type]
        risk_level=_risk_level(risk),  # type: ignore[arg-type]
        needs_confirmation=confirm,
        confidence=_confidence(answers, Q_AUDIT_GAP),
        rationale=rationale,
    )


PLAN_AUDIT = DecisionPoint[PlanAuditDecision](
    name=Point.PLAN_AUDIT,
    schema=PlanAuditDecision,
    questions=_questions_plan_audit,
    system_prompt="""你是 plan-and-act 的计划审计器。计划尚未执行，你的任务是回答一个假设问题：

  这个计划如果**被完美执行**（每步都成功、参数都生效），能否满足用户的原始请求？

同时独立判断：
- success_check 的严格度：这些验收表达式会不会放过"非空但没答对"的结果？
  （例如用户要"周杰伦的晴天"，而 check 只判了结果非空 → 太松。）
- 最主要的一处缺口是什么（漏了明确诉求 / 漏了必要的前置查询 / 参数与用户硬约束不符 /
  判据太松 / 依赖不成立）。
- 若执行错误，后果有多严重；是否需要先让用户确认。

只判"计划本身"，不要讨论如何修——修由重规划负责。每个维度独立判断，不要揉成综合印象。""",
    compose=compose_plan_audit,
)


# ══════════════════════════════════════════════════════════════════════════
# 判定点 3：step 断言验收 + 补救裁决 step_assert
# ══════════════════════════════════════════════════════════════════════════
# 现状：step 的唯一达成门是 success_check（jq 布尔式，LLM 写的），语义只能靠"先投影成字段
# 再比"近似；一旦判据写到投影不出的字段上（如 POI 数据里没有"是否营业"），产出完全正常也
# 必然判失败，并被重规划带走。
#
# 本判定点把"达成了吗"与"没达成怎么办"合成**一次**判定：
# - 逐条断言验收，每条三态：成立 / 被证伪 / **无证据**——"无证据"是从"产出不合格"里切出来
#   的独立裁决（原来这两者都表现为 success_check=false，只能一概重规划）；
# - 断言被证伪时直接复用下面 diagnosis 段的原子问题与组合方程产出补救裁决，于是失因与补救
#   出自同一次推理，不会出现"产出可用却判 replan"那类自相矛盾的裁决。
#
# 注：本段前向引用了下面的 ``_questions_diagnosis`` / ``compose_diagnosis``（同模块、调用时
# 才解析），因为补救那一半的问题集与方程与 diagnosis 判定点必须**逐字同一份**。

Q_ASSERT_GOAL = "step_goal_truly_achieved"
Q_CLAUSE_PREFIX = "clause_"

# 每条断言的三态。刻意保留第三种状态"无证据"：断言提到的字段在产出里缺失/为 null
# （工具返回空、投影没拿到）时，既不能算成立，也不该当成"产出错了"去重规划——
# 那正是 jq 判据最常误伤的形态。
CLAUSE_HOLDS = "成立"
CLAUSE_FALSIFIED = "被证伪"
CLAUSE_UNSUPPORTED = "无证据"

CLAUSE_CRITERIA: dict[str, str] = {
    CLAUSE_HOLDS: "产出里有明确内容支持这条断言",
    CLAUSE_FALSIFIED: (
        "产出里有明确内容**与这条断言矛盾**（如断言「至少 3 家」但只返回 1 家；"
        "断言「地址与上一步那家一致」但地址不同）"
    ),
    CLAUSE_UNSUPPORTED: (
        "产出既没有支持也没有反驳它的内容（断言提到的字段缺失、为 null，或工具返回为空），"
        "无法判断真假"
    ),
}

# 模型漏写断言（schema 要求非空，但仍是外部输入）时的兜底阈值。
ASSERT_GOAL_PASS = 0.6

# ── A 轴：判据可靠性（与三态正交）─────────────────────────────────────────
# 三态回答“产出对这条断言是什么结论”（事实）；A 轴回答“这条断言本身值不值得当判据”
# （合法性）。分开问的理由：实测用户只说“找一家”，计划却断言“至少返回 5 家”，被证伪时
# 三态只会说“产出不符”，而“这是计划自己设的”只能靠补救诊断里那个 A-or-B 的 Noul 去猜
# （实测 0.68 → 灰区 → 白花一轮重规划）。提成每条断言的显式 Choice 后，路由才能一眼
# 分开“产出不行”与“判据不行”（见 runner 的 assert 质量门）。
QUALITY_GROUNDED = "grounded"
QUALITY_INVENTED = "invented"
QUALITY_UNVERIFIABLE = "unverifiable"
QUALITY_UNKNOWN = "unknown"

CLAUSE_QUALITY_CRITERIA: dict[str, str] = {
    QUALITY_GROUNDED: (
        "用户请求里有依据（能引用原文，如「找一家」），或用本步产出/上游产出能判真假"
    ),
    QUALITY_INVENTED: (
        "用户请求里没有这个数量/阈值/口径，是计划把模糊需求操作化时自己设的"
        "（如用户只说「找一家」却断言「至少返回 5 家」）"
    ),
    QUALITY_UNVERIFIABLE: (
        "判据落在本步产出给不出的东西上（字段未声明/为空，或需要本步拿不到的证据），"
        "产出再正常也判不了真假"
    ),
}

QUALITY_PREFIX = "clause_quality_"

# Choice 尖锐度阈值：低于此值视为“判不准”（真·两可），与“是否被证伪”无关。
# 实测参考：历史 trace 的断言三态 confidence 均在 0.79~1.0，所以这条门槛是**安全网**而非常规
# 通道——真正在干活的是 A 轴（判据是否成立），因为“判得很确信但判据本身是计划自编的”
# （实测 0.94）恰好是本类 badcase 的形态。
CLAUSE_CONF_MIN = 0.6

# goal 完成度的两档门：>=PASS 才算“目标达成”，<FLOOR 视为“连达成度都不足信”（判定器自己
# 也只敢给低分），中间那档是灰区（不静默放行，也不因此重规划）。
ASSERT_GOAL_FLOOR = 0.4

# 判据不可靠的**两条来源**，路由按它们分流（而不是笼统地“不看断言”）：
#   - UNRELIABLE_INVENTED：判据本身不是用户的要求（计划把模糊需求操作化时自设的阈值，
#     如用户说“找一家”而计划写“至少返回 5 家”）→ 这条断言不该当失败依据，改看“该步目标
#     达成没有”（与“没有断言可判”是同一套兜底）；
#   - UNRELIABLE_EVIDENCE：判据可信但产出给不出证据，或判定器对结论本身没把握（真·两可）
#     → 既不该据此判失败，**也不能拿 goal 当依据**：goal 这时同样被这条判不了的断言带偏
#     （实测 nav 那条：无证据 conf=0.79，goal 只敢给 0.40）→ 保产出 + 降级 + 如实披露。
UNRELIABLE_INVENTED = "invented"
UNRELIABLE_EVIDENCE = "evidence"


def _clause_certainties(answers: Mapping[str, JevAnswer], count: int) -> list[float]:
    """取出逐条断言结论的把握（= Choice 答案的尖锐度）；缺失补 1.0（**按确信处理**）。

    兜底方向与 :func:`_clause_qualities` 一致，都是为了“不把真失败降级”：
    后端没给把握 ≠ 判不准，只是无从得知；只有**显式**低于 :data:`CLAUSE_CONF_MIN` 的把握
    才进“判不准”那支（否则一个字段漏填就能把真失败变成降级接受）。
    """
    found = {
        index: (confidence if confidence is not None else 1.0)
        for index, _, confidence in _clause_verdicts(answers)
    }
    return [found.get(index, 1.0) for index in range(count)]


def _unreliable_kind(
    falsified: list[int],
    qualities: Mapping[int, str],
    confidences: Mapping[int, float | None],
) -> str | None:
    """被证伪的断言“整体不可靠”时返回类型，否则 ``None``（有可信断言被证伪 = 真失败）。

    三条约定，都是刻意的：

    - **全有或全无**：只要有一条断言既 grounded 又判得确信，本次就是真失败。否则
      “某条判据不靠谱”会变成洗白真失败的通道；
    - **unknown 视为可信**（保守）：LLM 后端漏填 quality、或后端不给 confidence 时
      **不许**触发忽略，否则一次字段缺失就能把整套断言关掉；
    - **判据不适用 > 判不准**：invented 的断言不管判定器多有把握（实测 0.94）都不该当依据；
      而 unverifiable / 低置信是“判不了”，与判据合法与否无关，走另一支。
    """
    kind: str | None = None
    for index in falsified:
        quality = qualities.get(index, QUALITY_UNKNOWN)
        confidence = confidences.get(index)
        if quality == QUALITY_INVENTED:
            kind = kind or UNRELIABLE_INVENTED
            continue
        if quality == QUALITY_UNVERIFIABLE or (
            confidence is not None and confidence < CLAUSE_CONF_MIN
        ):
            # 混合时取更保守的一支：只要有一条属于“证据/把握不足”，就不拿 goal 当依据。
            return UNRELIABLE_EVIDENCE
        return None  # grounded（或 unknown）且判得确信：真失败
    return kind


def clause_quality_question_id(index: int) -> str:
    """第 index 条断言的“判据可靠性”问题 id（与三态问题并列，分属两条轴）。"""
    return f"{QUALITY_PREFIX}{index}_quality"


def _clause_qualities(answers: Mapping[str, JevAnswer], count: int) -> list[str]:
    """取出逐条断言的判据可靠性；缺失（脚本化判定器 / LLM 漏填）补 ``unknown``。

    与三态的取值器不同，这里**不报错**：老脚本化答案、外部后端漏填字段都不该把流程打断，
    “未给出”本身就是要记录的事实（未知一律不参与质量门）。
    """
    found: dict[int, str] = {}
    for qid, answer in answers.items():
        if not qid.startswith(QUALITY_PREFIX):
            continue
        index_text = qid[len(QUALITY_PREFIX) :].split("_", 1)[0]
        if not index_text.isdigit():
            continue
        if answer.kind != "choice":
            raise TypeError(f"判据可靠性问题 {qid!r} 期望 choice，实际 {answer.kind}")
        found[int(index_text)] = answer.choice or QUALITY_UNKNOWN
    return [found.get(index, QUALITY_UNKNOWN) for index in range(count)]


def clause_question_id(index: int) -> str:
    """第 index 条断言的原子问题 id（compose 按此解析，测试也用它脚本化答案）。"""
    return f"{Q_CLAUSE_PREFIX}{index}_verdict"


def _clause_verdicts(answers: Mapping[str, JevAnswer]) -> list[tuple[int, str, float | None]]:
    """取出断言三态答案，按断言下标升序返回 ``(下标, 裁决, 尖锐度)``。

    尖锐度（``confidence``）**一并带出来**：它回答的是另一个问题——“判定器对这条结论
    有多确信”。被证伪但只有 0.4 确信时，这条结论本身就不该当失败依据（见
    :func:`_unreliable_kind`），而只看标签看不到这一点。
    """
    out: list[tuple[int, str, float | None]] = []
    for qid, answer in answers.items():
        if not qid.startswith(Q_CLAUSE_PREFIX):
            continue
        index_text = qid[len(Q_CLAUSE_PREFIX) :].split("_", 1)[0]
        if not index_text.isdigit():
            continue
        if answer.kind != "choice":
            raise TypeError(f"断言问题 {qid!r} 期望 choice，实际 {answer.kind}")
        out.append((int(index_text), answer.choice or "", answer.confidence))
    return sorted(out)


def _questions_step_assert(state: Mapping[str, Any]) -> dict[str, Question]:
    """断言验收 + 补救：逐条断言问三态，补救那一半复用 diagnosis 的问题集。"""
    step = state.get("step") or {}
    goal = step.get("step_goal") or "（未提供步骤目标）"
    # 达成判据只有一个键（success_check），形态用 kind 分辨：本判定点只在
    # nature_assertion 形态下被调用（jq 形态由规则层求值，见 runner 的分派）。
    criterion = step.get("success_check") or {}
    assertions = [
        a for a in (criterion.get("assertions") or []) if isinstance(a, str)
    ]
    questions: dict[str, Question] = {
        Q_ASSERT_GOAL: Noul(
            instructions=(
                f"该步骤声明的小目标是：{goal}。"
                "判断只看两样东西：**用户原始请求**（query，含它的隐含要求）里与本步相关的"
                "那一句，以及**本步的实际产出**。"
                "**不要参考本步自己声明的 assertion 清单**——那些是计划写的判据，可能包含用户并"
                "没有要求的数量/阈值（如用户只说「找一家」却写了「至少 5 家」）；拿它们当尺子会"
                "把这个判断本身污染成低分。若本步只是中间步骤、请求里没有直接对应的话，就问："
                "产出是否足以支撑请求里那件事，而不是产出是否满足计划自设的口径。"
                "注意区分「工具报告成功」与「结果真的符合目标」：返回了非空结果但内容与目标"
                "不符，属于未达成。"
            )
        )
    }
    for index, clause in enumerate(assertions):
        questions[clause_question_id(index)] = Choice(
            instructions=(
                f"该步骤声明的第 {index + 1} 条断言是：「{clause}」。"
                "实际产出对这条断言是什么结论？"
            ),
            criteria=CLAUSE_CRITERIA,
        )
        # A 轴（与上面那条正交）：这条断言本身值不值得当判据。别把它和“成立/被证伪/
        # 无证据”混在一起——那条说的是产出，这条说的是判据。
        questions[clause_quality_question_id(index)] = Choice(
            instructions=(
                f"第 {index + 1} 条断言「{clause}」这条判据本身可靠吗？"
                "即：它的数量/阈值/口径是用户请求里有的，还是计划自己设的？"
                "若判 grounded，必须能在用户请求或本步（含上游）产出里指出依据。"
            ),
            criteria=CLAUSE_QUALITY_CRITERIA,
        )
    questions.update(_questions_diagnosis(state))
    return questions


def _remediation_from_atoms(decision: "StepAssertDecision") -> DiagnosisOutcome | None:
    """从裁决里的原子字段算补救 outcome；原子字段缺失时返回 None（保留原有裁决）。

    这是“三选一由代码算”的入口：LLM 后端自己填的 outcome 在需要时会被这里覆盖，
    Jev 后端已经算过一遍，这里重算得到同一个值（幂等）。
    """
    facts = _facts_from_decision(decision.diagnosis_atoms)
    if facts is None:
        return None
    return _outcome_from_facts(facts).decision


def route_step_assert(decision: StepAssertDecision) -> StepAssertDecision:
    """断言裁决的**共享路由规则**（两条后端同一份代码）。

    这里只做一件事：把“判据不可用”与“产出没做到”分开。这两种情形在旧实现里都表现为
    ``passed=False``，只能靠补救方程去猜（实测 hard=0.68 → 灰区 → 白花一轮），而它本质上是
    **规则性出口**，不该交给判定器自由发挥：

    - 被证伪的断言全部 invented（判据不是用户要求的）→ 忽略断言结论，改看 goal
      （≥PASS 干净放行；灰区降级披露；<FLOOR 保留原有补救裁决——目标真没达成）；
    - 含有 unverifiable / 把握低于阈值的断言 → 不判失败，也**不咨询 goal**
      （goal 同样被这条判不了的断言带偏）→ 保产出 + 降级披露；
    - 只有无证据（无证伪）→ 降级披露（同一条理由）；
    - 其余（有 grounded 且确信的断言被证伪，或根本没被证伪）→ 原样返回。

    **幂等**：面对 :func:`compose_step_assert` 已按同一规则算出的裁决，它返回等价值；
    因此 Jev 后端（compose 后已符合）与 LLM 后端（解析后补上这一层）得到同一套语义。
    """
    if decision.passed:
        return decision

    clauses = [index + 1 for index in decision.falsified_clauses]
    updated: dict[str, Any] = {}

    if not decision.falsified_clauses and not decision.unsupported_clauses:
        # 判失败却没有任何逐条证据（LLM 后端可能漏填），或计划本来就没写断言：
        # 按“无断言可判”的同一套兜底——只看 goal。不补这一步，模型只要不报“哪条断言
        # 失败”就能绕开上面的全部规则（真失败会被它自己一句 passed=false 定死）。
        if decision.goal_achieved >= ASSERT_GOAL_PASS:
            return decision.model_copy(
                update={
                    "passed": True,
                    "diagnosis": None,
                    "assert_verdict_ignored": True,
                    "rationale": (
                        "无可判的断言结论，按整体达成度 "
                        f"{decision.goal_achieved:.2f} 判达成"
                    ),
                }
            )
        return decision.model_copy(
            update={
                "assert_verdict_ignored": True,
                "diagnosis": _remediation_from_atoms(decision) or decision.diagnosis,
                "rationale": (
                    "无可判的断言结论，且整体达成度 "
                    f"{decision.goal_achieved:.2f} 未达标"
                ),
            }
        )

    if decision.falsified_clauses:
        kind = _unreliable_kind(
            decision.falsified_clauses,
            dict(enumerate(decision.clause_quality)),
            dict(enumerate(decision.clause_certainty)),
        )
        if kind is None:
            # 有可信断言被证伪：真失败。补救裁决由方程从原子字段算（LLM 后端自己填的那份
            # 不再作数——这正是“三选一由代码算”的对齐）。
            derived = _remediation_from_atoms(decision)
            return decision.model_copy(update={"diagnosis": derived}) if derived else decision
        updated["assert_verdict_ignored"] = True
        if kind == UNRELIABLE_INVENTED:
            if decision.goal_achieved >= ASSERT_GOAL_PASS:
                updated.update(
                    passed=True,
                    diagnosis=None,
                    rationale=(
                        f"第 {clauses} 条断言的判据是计划自设的（用户没要求该数量/阈值），"
                        f"忽略其结论，按该步目标达成度 {decision.goal_achieved:.2f} 判达成"
                    ),
                )
            elif decision.goal_achieved >= ASSERT_GOAL_FLOOR:
                updated.update(
                    rationale=(
                        f"判据自设（第 {clauses} 条），但目标达成度 "
                        f"{decision.goal_achieved:.2f} 落在灰区"
                        f"（{ASSERT_GOAL_FLOOR}~{ASSERT_GOAL_PASS}），按部分达成接受"
                    ),
                    diagnosis=AcceptDegraded(
                        limitation=(
                            f"第 {clauses} 条断言是计划自设的判据、其结论不作数；"
                            f"该步目标达成度 {decision.goal_achieved:.2f}，结果按部分达成接受。"
                        )
                    ),
                )
            else:
                # 目标确实没达成：补救裁决同样由方程从原子字段算（没原子字段就保留原值）。
                updated["diagnosis"] = _remediation_from_atoms(decision) or decision.diagnosis
                updated["rationale"] = (
                    f"判据自设（第 {clauses} 条），且该步目标达成度仅 "
                    f"{decision.goal_achieved:.2f}（低于下限），仍需补救"
                )
        else:  # UNRELIABLE_EVIDENCE
            updated.update(
                rationale=f"第 {clauses} 条断言的结论不可用（判据不可判或判定器不确定），产出保留",
                diagnosis=AcceptDegraded(
                    limitation=(
                        f"第 {clauses} 条断言无法用产出判定（判据不可用或结论两可），"
                        "产出保留但结果不完整。"
                    )
                ),
            )

    elif decision.unsupported_clauses:
        # 无证伪、只有无证据：判不了不等于产出错了 → 降级接受（两条后端同一条规则）。
        unsupported = [index + 1 for index in decision.unsupported_clauses]
        updated.update(
            rationale=(
                f"第 {unsupported} 条断言无产出可判（相关字段缺失或结果为空），"
                "产出保留但结果不完整"
            ),
            diagnosis=AcceptDegraded(
                limitation=(
                    f"第 {unsupported} 条断言无法用产出判定（相关字段缺失或为空），结果不完整。"
                )
            ),
        )

    return decision.model_copy(update=updated) if updated else decision


def compose_step_assert(answers: dict[str, JevAnswer]) -> StepAssertDecision:
    """断言验收方程：逐条三态 → 事实 → 共享路由（:func:`route_step_assert`）。

    两条**正交**的轴决定出口：

    - 三态（C 轴）回答“产出对这条断言是什么结论”（成立 / 被证伪 / 无证据）；
    - 判据可靠性（A 轴）回答“这条断言值不值得当判据”（grounded / invented /
      unverifiable）+ 判定器对结论的把握（certainty）。

    本方程只负责把原子答案翻成**事实**（三态、质量、把握、goal、产出可用度）与“默认裁决”
    （真失败 → :func:`compose_diagnosis`；无证据 → 降级），再由 :func:`route_step_assert`
    按同一套规则决定性克裁——这样 Jev 组合方程与 LLM 直填 schema 两条后端在“判据不可用”
    这类规则性出口上语义完全一致（对称性靠“共享路由”而不是“让 LLM 也去算概率”保证）。
    """
    achieved = _noul(answers, Q_ASSERT_GOAL)
    verdicts = _clause_verdicts(answers)
    qualities = _clause_qualities(answers, len(verdicts))
    certainties = _clause_certainties(answers, len(verdicts))
    confidence = _sharpness(achieved)
    usable = _noul(answers, Q_DIAG_USABLE)

    if not verdicts:
        if achieved >= ASSERT_GOAL_PASS:
            return StepAssertDecision(
                passed=True,
                goal_achieved=achieved,
                output_usable=usable,
                confidence=confidence,
                rationale="无断言可判，整体达成概率达标",
            )
        diagnosis = compose_diagnosis(answers)
        return StepAssertDecision(
            passed=False,
            goal_achieved=achieved,
            output_usable=usable,
            confidence=diagnosis.confidence or confidence,
            rationale=f"无断言可判，整体达成概率 {achieved:.2f} 未达标",
            diagnosis=diagnosis.decision,
        )

    falsified = [index for index, verdict, _ in verdicts if verdict == CLAUSE_FALSIFIED]
    unsupported = [index for index, verdict, _ in verdicts if verdict == CLAUSE_UNSUPPORTED]

    if falsified:
        # 默认按“真的没做到”处理（交补救方程），再由共享路由接管“判据不可用”那几支。
        facts = _facts_from_answers(answers)
        diagnosis = _outcome_from_facts(facts)
        return route_step_assert(
            StepAssertDecision(
                passed=False,
                goal_achieved=achieved,
                falsified_clauses=falsified,
                unsupported_clauses=unsupported,
                clause_quality=qualities,
                clause_certainty=certainties,
                output_usable=usable,
                confidence=diagnosis.confidence or confidence,
                diagnosis_atoms=_atoms_from_facts(facts),
                rationale=f"第 {[i + 1 for i in falsified]} 条断言被产出证伪",
                diagnosis=diagnosis.decision,
            )
        )

    if unsupported:
        # 无证伪、只有无证据 → 降级接受（两条后端同一条规则）；原子事实一并落进 trace，
        # 保证两条后端的裁决形状一致（对齐之后才能逐字段比）。
        facts = _facts_from_answers(answers)
        return route_step_assert(
            StepAssertDecision(
                passed=False,
                goal_achieved=achieved,
                unsupported_clauses=unsupported,
                clause_quality=qualities,
                clause_certainty=certainties,
                output_usable=usable,
                confidence=confidence,
                diagnosis_atoms=_atoms_from_facts(facts),
            )
        )

    return StepAssertDecision(
        passed=True,
        goal_achieved=achieved,
        clause_quality=qualities,
        clause_certainty=certainties,
        output_usable=usable,
        confidence=confidence,
        rationale=f"{len(verdicts)} 条断言全部成立",
    )


STEP_ASSERT = DecisionPoint[StepAssertDecision](
    name=Point.STEP_ASSERT,
    questions=_questions_step_assert,
    schema=StepAssertDecision,
    system_prompt="""你是 plan-and-act 的步骤验收器。某个步骤已经执行完，你要做两件事：验收它的产出，
并在它没做到时给出补救裁决。

**第一件：逐条验收该步骤自己声明的断言**（步骤声明里有 assertion 列表）。每条断言给三态之一，
不要混成综合印象：
- 成立：产出里有明确内容支持它；
- 被证伪：产出里有明确内容与它矛盾；
- 无证据：产出里既没支持也没反驳它的内容（字段缺失、为 null、结果为空）——判不了就说判不了，
  不要替产出补全，也不要因为无法确认就当成失败。

**同时给每条断言的判据可靠性 clause_quality**（与三态正交，下标与 assertion 对齐）：三态说的是
“产出对这条断言是什么结论”，clause_quality 说的是“这条断言本身值不值得当判据”：
- grounded：用户请求里有依据（能引用原文，如「找一家」），或用产出能判真假；
- invented：用户请求里没有这个数量/阈值/口径，是计划自己设的（如用户只说「找一家」却断言
  「至少返回 5 家」；「附近」被写成「300m 以内」）；
- unverifiable：判据落在本步产出给不出的东西上，产出再正常也判不了真假。
别图省事一律给 grounded：数量、半径、条数这类操作化阈值默认属于 plan 的发明，除非请求里写着。
另外给每条断言的 clause_certainty（0~1）：是你**对上面那条三态结论本身**的把握，不是对产出的
评价。证据缺失、两可、需要猜时给低分（<0.6 会被当作“判不准”）；确实无可争议时才给高分。

**下面这些是代码里的固定规则，你只需如实填字段，不要自己把它们揉进 passed/diagnosis**
（两条后端共用同一份规则，你替它提前裁决只会让 A/B 不可比）：
- 被证伪的断言全部是 invented → 断言结果**不作数**，改看 goal（高→放行，低→补救）；
- 被证伪的断言含有 unverifiable 或低把握 → 不判失败、也不看 goal，取降级接受；
- 无证伪、只有无证据 → 降级接受；
- 只要有一条 grounded 且你判得确信的断言被证伪，就是真失败——不要拿“判据可能太严”当借口跳过。

**第二件：若没做到，填补救所需的原子事实**（``diagnosis_atoms``）。三选一裁决
（replan / skip_unsolvable / accept_degraded）由代码根据这些事实算，**不要自己挑 outcome**——
两条后端跑的是同一份方程，替它抢答只会让 A/B 不可比。

- constraint_is_user_requirement：未满足的那条断言，是用户请求里**明说**的（高），还是 plan
  把模糊需求操作化时**自己猜**的（低，如用户只说“找一家”而计划写“至少 5 家”）？
- alternative_can_satisfy：换一条仍忠于用户意图的做法（更宽参数 / 另一个工具 / 另一条路径）
  能不能满足它？确实没戏→低。
- output_still_usable：这个产出对用户或下游还够不够用？完全用不了→低。
- downstream_blocking：下游是不是真的依赖“未满足的那个方面”（不是“是否用到这个产出”）？
- failure_cause：从五个枚举里选一个根因。
0.5 = 说不清；不要一律给高分或低分（代码在灰区取保守分支，假确信会绕过这条护栏）。

判根因以「工具原始返回」为准：它承载 status/message/error_msg 等线索，而「实际产出」经概念
抽取后可能已丢弃这些线索。断言全部成立时，补救部分留空即可。""",
    compose=compose_step_assert,
    route=route_step_assert,
)


# ══════════════════════════════════════════════════════════════════════════
# 判定点 4：失败补救诊断 diagnosis
# ══════════════════════════════════════════════════════════════════════════
# 现状：一次带全量 tool_output 的生成式 LLM 调用，产出三选一 + 2 段自由文本；
# 解析失败就兜底 replan（继续烧轮次）。判定点把它拆成 5 个原子问题再组合。

Q_DIAG_HARD = "unsatisfied_constraint_is_user_requirement"
Q_DIAG_RETRY = "different_approach_can_satisfy"
Q_DIAG_USABLE = "output_still_usable"
Q_DIAG_BLOCKING = "downstream_depends_on_it"
Q_DIAG_CAUSE = "failure_cause"

DIAG_RETRY_CAN_FIX = 0.7
DIAG_HARD_CONSTRAINT = 0.6
DIAG_HARD_CONSTRAINT_STRICT = 0.8
DIAG_USABLE = 0.6
DIAG_NOT_BLOCKING = 0.4
DIAG_HOPELESS = 0.3

CAUSE_PLAN_MISTAKE = "plan_assumption_wrong"
CAUSE_TOOL_UNSUPPORTED = "tool_cannot_do_it"
CAUSE_DATA_ABSENT = "data_does_not_exist"
CAUSE_PARAM_ERROR = "params_or_ref_wrong"
CAUSE_EXEC_FAILED = "tool_execution_failed"

# cause → 面向用户的一句原因（确定性模板，替代原实现的 LLM 自由文本字段）。
CAUSE_TEXT: dict[str, str] = {
    CAUSE_PLAN_MISTAKE: "当前执行路径的假设不成立",
    CAUSE_TOOL_UNSUPPORTED: "现有工具不具备所需能力",
    CAUSE_DATA_ABSENT: "确实查不到所需信息",
    CAUSE_PARAM_ERROR: "步骤参数或引用写错",
    CAUSE_EXEC_FAILED: "工具执行失败",
}

# 这两个 cause 说明是 plan/写法的问题而非客观不可得 → 应交由重规划修正。
CAUSE_IS_FIXABLE = frozenset({CAUSE_PLAN_MISTAKE, CAUSE_PARAM_ERROR})
# 这两个 cause 是客观限制 → 在硬约束下应老实承认无解。
CAUSE_IS_OBJECTIVE = frozenset({CAUSE_DATA_ABSENT, CAUSE_TOOL_UNSUPPORTED})


def _questions_diagnosis(state: Mapping[str, Any]) -> dict[str, Question]:
    return {
        Q_DIAG_HARD: Noul(
            instructions=(
                "The constraint that failed to be satisfied: is it a hard requirement "
                "stated in the user's original request, or was it an assumption the plan "
                "itself invented when turning a vague need into concrete parameters?"
            )
        ),
        Q_DIAG_RETRY: Noul(
            instructions=(
                "Could a different approach (wider parameters, another tool, another path) "
                "satisfy this constraint while still staying faithful to the user's intent?"
            )
        ),
        Q_DIAG_USABLE: Noul(
            instructions=(
                "Even though the step did not meet its declared check, is what it produced "
                "still usable for the user or for downstream steps?"
            )
        ),
        Q_DIAG_BLOCKING: Noul(
            instructions="Do downstream steps truly depend on this step's output being correct?"
        ),
        Q_DIAG_CAUSE: Choice(
            instructions="What is the underlying cause of this failure?",
            criteria={
                CAUSE_PLAN_MISTAKE: "plan 把模糊需求操作化时猜错了约束（如把「附近」猜成 500m）",
                CAUSE_TOOL_UNSUPPORTED: "现有工具不具备完成该请求的能力",
                CAUSE_DATA_ABSENT: "工具能力足够，但所需数据/条目确实不存在或搜不到",
                CAUSE_PARAM_ERROR: "入参、jq 引用或条件表达式写错，导致工具没被正确调用",
                CAUSE_EXEC_FAILED: "工具被正确调用但执行报错/超时",
            },
        ),
    }


@dataclass(frozen=True)
class DiagnosisFacts:
    """补救裁决的输入事实（唯一入口）：两条后端都以它为输入，组合方程只读它。

    Jev 后端从 Noul/Choice 答案里取（校准概率），LLM 后端从它自己填的原子字段里取
    （自报值）——**输入来源不同是 A/B 的实验变量，控制流相同是这里保证的**。
    之前的不对称在于：LLM 后端是自己选三选一（根本没有方程），于是同一份实验里两条后端
    跑的规则不一样，结果无法归因。
    """

    constraint_is_user_requirement: float
    alternative_can_satisfy: float
    output_still_usable: float
    downstream_blocking: float
    failure_cause: str
    confidence: float | None = None


def _atoms_from_facts(facts: DiagnosisFacts) -> DiagnosisAtoms:
    """事实 → 进裁决的原子字段（两条后端共用一份，trace 里两侧形状一致）。"""
    return DiagnosisAtoms(
        constraint_is_user_requirement=facts.constraint_is_user_requirement,
        alternative_can_satisfy=facts.alternative_can_satisfy,
        output_still_usable=facts.output_still_usable,
        downstream_blocking=facts.downstream_blocking,
        failure_cause=facts.failure_cause,  # type: ignore[arg-type]
    )


def _outcome_from_facts(facts: DiagnosisFacts) -> DiagnosisDecision:
    """补救裁决的组合方程（两条后端共用）：原子事实 → 三选一 + 置信度 + 理由。

    与原实现的关键差异：原实现的 ``Replan`` 需要 LLM 现编两段提示文本
    （failed_assumption / retry_direction）；这里改成由 ``cause`` 枚举驱动**确定性模板**，
    自由文本从"控制流的一部分"降级为"可选的证据"。
    """
    hard = facts.constraint_is_user_requirement
    retry = facts.alternative_can_satisfy
    usable = facts.output_still_usable
    blocking = facts.downstream_blocking
    cause = facts.failure_cause or CAUSE_PLAN_MISTAKE
    cause_text = CAUSE_TEXT.get(cause, "失败原因不明")
    atoms = _atoms_from_facts(facts)

    # 置信度：Jev 取四个原子判断里最尖锐的那个（最确定的维度决定裁决可信度）；
    # LLM 后端没有分布，用自报的 confidence。两者都缺时 None（由 core 兜底）。
    sharp = facts.confidence
    if sharp is None:
        sharp = max(
            _sharpness(hard), _sharpness(retry), _sharpness(usable), _sharpness(blocking)
        )

    # ① 换 approach 能解，且不是"用户硬性要求"（或根因本就是可修的写法问题）→ 重规划
    if retry > DIAG_RETRY_CAN_FIX and (
        hard < DIAG_HARD_CONSTRAINT or cause in CAUSE_IS_FIXABLE
    ):
        return DiagnosisDecision(
            **atoms.model_dump(),
            decision=Replan(
                failed_assumption=(
                    f"被证伪的假设：{cause_text}"
                    if cause in CAUSE_IS_FIXABLE
                    else "把用户的模糊需求操作化时猜的约束不成立"
                ),
                retry_direction=f"换一条仍忠于用户意图的做法重试（{cause_text}）",
            ),
            confidence=sharp,
            rationale=f"retry_can_fix={retry:.2f} hard={hard:.2f} cause={cause}",
        )

    # ② 客观不可得 + 用户硬性要求 + 产出不可用 + **换 approach 也没戏** → 判无解
    #    真机验证的经验："指定歌手的《晴天》搜不到"会给 hard≈0.68 / retry≈0.9（Jev 认为换工具
    #    可能找到）。两个答案同时成立时应该重试（换 web_search 真的可能找到），否则就是把
    #    可解的问题错报成无解。只要留着 retry 这道门，重复失败就由轮次闸门配合跨轮证据收敛。
    if (
        cause in CAUSE_IS_OBJECTIVE
        and hard >= DIAG_HARD_CONSTRAINT
        and usable < DIAG_USABLE
        and retry < DIAG_RETRY_CAN_FIX
    ):
        return DiagnosisDecision(
            **atoms.model_dump(),
            decision=SkipUnsolvable(unsolvable_reason=f"无法完成该子目标：{cause_text}。"),
            confidence=sharp,
            rationale=f"cause={cause} hard={hard:.2f} usable={usable:.2f} retry={retry:.2f}",
        )

    # ③ 产出够用且不阻塞下游 → 降级接受（保留产出、下游照常、如实说明局限）
    if usable > DIAG_USABLE and blocking < DIAG_NOT_BLOCKING:
        return DiagnosisDecision(
            **atoms.model_dump(),
            decision=AcceptDegraded(limitation=f"结果不完整（{cause_text}），仅部分达成。"),
            confidence=sharp,
            rationale=f"usable={usable:.2f} blocking={blocking:.2f}",
        )

    # ④ 用户硬性要求 + 换 approach 也没戏 → 判无解
    if hard >= DIAG_HARD_CONSTRAINT_STRICT and retry < DIAG_HOPELESS:
        return DiagnosisDecision(
            **atoms.model_dump(),
            decision=SkipUnsolvable(unsolvable_reason=f"无法完成该子目标：{cause_text}。"),
            confidence=sharp,
            rationale=f"hard={hard:.2f} retry={retry:.2f}",
        )

    # ⑤ 灰区：不回退 LLM，取保守分支（重试而非宣称无解），并如实记下低置信度
    return DiagnosisDecision(
        **atoms.model_dump(),
        decision=Replan(
            failed_assumption=f"疑似假设不成立（{cause_text}），但证据不充分",
            retry_direction="保守重试：换更宽/更合适的参数或工具",
        ),
        confidence=sharp,
        rationale=f"{GRAY_ZONE}（hard={hard:.2f} retry={retry:.2f} usable={usable:.2f} "
        f"blocking={blocking:.2f} cause={cause}）",
    )


def _facts_from_answers(answers: Mapping[str, JevAnswer]) -> DiagnosisFacts:
    """Jev 后端的事实来源：四个 Noul + 一个 Choice。"""
    return DiagnosisFacts(
        constraint_is_user_requirement=_noul(answers, Q_DIAG_HARD),
        alternative_can_satisfy=_noul(answers, Q_DIAG_RETRY),
        output_still_usable=_noul(answers, Q_DIAG_USABLE),
        downstream_blocking=_noul(answers, Q_DIAG_BLOCKING),
        failure_cause=_choice(answers, Q_DIAG_CAUSE) or CAUSE_PLAN_MISTAKE,
    )


def _facts_from_decision(decision: Any) -> DiagnosisFacts | None:
    """LLM 后端的事实来源：它自己填的原子字段。原子字段缺失时返回 None（不接管）。"""
    if not isinstance(decision, DiagnosisAtoms):
        return None
    return DiagnosisFacts(
        constraint_is_user_requirement=decision.constraint_is_user_requirement,
        alternative_can_satisfy=decision.alternative_can_satisfy,
        output_still_usable=decision.output_still_usable,
        downstream_blocking=decision.downstream_blocking,
        failure_cause=decision.failure_cause,
        # confidence 只在 DiagnosisDecision 上（原子子模型没有它），取不到就 None。
        confidence=getattr(decision, "confidence", None),
    )


def compose_diagnosis(answers: dict[str, JevAnswer]) -> DiagnosisDecision:
    """补救诊断方程（Jev 后端的入口）：原子答案 → 事实 → 共享方程。"""
    return _outcome_from_facts(_facts_from_answers(answers))


def route_diagnosis(decision: DiagnosisDecision) -> DiagnosisDecision:
    """诊断判定点的**共享路由**：不管判定器自己填了什么 outcome，一律由方程从原子算。

    这条对齐把一个纯粹的不对称去掉了：对齐之前，Jev 臂的三选一是方程算的，LLM 臂的是
    模型直接挑的——同一份实验里两条后端的控制流不同，A/B 结果无法归因。现在两条后端都
    只提供事实，outcome / 置信度 / 理由全部由 :func:`_outcome_from_facts` 给出。
    """
    facts = _facts_from_decision(decision)
    if facts is None:
        return decision
    return _outcome_from_facts(facts)


DIAGNOSIS = DecisionPoint[DiagnosisDecision](
    name=Point.DIAGNOSIS,
    schema=DiagnosisDecision,
    questions=_questions_diagnosis,
    system_prompt="""你是 plan-and-act 的补救诊断器。某个步骤的 success_check 未通过，你要提供**原子事实**——
三选一裁决（replan / skip_unsolvable / accept_degraded）由代码根据这些事实算出来，不要自己抢答。

按下面的刻度给四个 0~1 的数（0.5 = 说不清，不要一律给高分或低分）：
- constraint_is_user_requirement：未满足的那条约束，用户请求里**明说**了（高）还是 plan 把
  模糊需求操作化时**自己猜**的（低）？例如用户只说“找一家”而计划写“至少 5 家”→ 低。
- alternative_can_satisfy：换一条仍然忠于用户意图的做法（更宽参数/另一个工具/另一条路径）
  能不能满足它？确实没戏→低。
- output_still_usable：这个产出对用户或下游步骤还够不够用？完全用不了→低。
- downstream_blocking：下游是不是真的依赖“未满足的那个方面”（不是“是否用到这个产出”）？
- failure_cause：从五个枚举里选一个根因。

以「工具原始返回」为准判断根因：它承载 status/message/error_msg 等线索，
而「实际产出（结构化）」经概念抽取后可能已丢失这些线索。

判不准就给中间值与低置信度：代码在灰区会取保守分支（重试而非宣称无解），
但你编一个假的确信度会把这条护栏绕过去。结果判断只输出事实与依据，不要讨论别的。""",
    compose=compose_diagnosis,
    route=route_diagnosis,
)


# ══════════════════════════════════════════════════════════════════════════
# 判定点 5：轮次闸门 round_gate
# ══════════════════════════════════════════════════════════════════════════
# 现状：`errors 非空 → 再修一轮`，只受 max_turns 这个固定预算限制。
# 既不知道"再修有没有希望"，也不知道"这个错是不是已经修过好几轮的同一个"。
# failure_history 由编排层跨轮累积（runner 每轮新建，自己没有记忆）。

Q_GATE_WORTH = "worth_another_repair_round"
Q_GATE_SAME = "same_root_cause_as_history"

SAME_CAUSE_STRONG = 0.8
WORTH_HOPELESS = 0.35
WORTH_STOP = 0.3


def _questions_round_gate(state: Mapping[str, Any]) -> dict[str, Question]:
    return {
        Q_GATE_WORTH: Noul(
            instructions=(
                "Given the errors of this round, how likely is it that regenerating the plan "
                "once more would actually resolve them?"
            )
        ),
        Q_GATE_SAME: Noul(
            instructions=(
                "Comparing this round's failures with the failure history from earlier rounds: "
                "are they the same underlying root cause (the same sub-goal failing for "
                "essentially the same reason), rather than a new/different problem?"
            )
        ),
    }


def compose_round_gate(answers: dict[str, JevAnswer]) -> RoundGateDecision:
    """闸门方程：同根因 + 无希望 → 判无解；单看无希望 → 止损；否则再修一轮。"""
    worth = _noul(answers, Q_GATE_WORTH)
    same = _noul(answers, Q_GATE_SAME)
    sharp = max(_sharpness(worth), _sharpness(same))

    if same >= SAME_CAUSE_STRONG and worth < WORTH_HOPELESS:
        return RoundGateDecision(
            action="mark_unsolvable",
            worth_another_round=worth,
            same_root_cause=same,
            confidence=sharp,
            rationale=f"同根因 {same:.2f} 且无希望 {worth:.2f}：证据门槛达成，判无解",
        )
    if worth < WORTH_STOP:
        return RoundGateDecision(
            action="stop",
            worth_another_round=worth,
            same_root_cause=same,
            confidence=sharp,
            rationale=f"再修希望 {worth:.2f} < {WORTH_STOP}：提前止损",
        )
    return RoundGateDecision(
        action="continue",
        worth_another_round=worth,
        same_root_cause=same,
        confidence=sharp,
        rationale=f"再修希望 {worth:.2f} >= {WORTH_STOP}：继续修复",
    )


ROUND_GATE = DecisionPoint[RoundGateDecision](
    name=Point.ROUND_GATE,
    schema=RoundGateDecision,
    questions=_questions_round_gate,
    system_prompt="""你是 plan-and-act 的轮次闸门。本轮执行产生了错误，要决定是否再花一轮重新规划。

判断两件事（互相独立）：
1. 就本轮的这些错误而言，再重规划一轮真的有可能解决吗？（而不是重复同样的失败）
2. 本轮的失败与「历史失败」相比，是不是同一个根因？
   —— 同一个子目标因同样的原因反复失败，说明它不是"换个写法就能过"的问题。

出口：continue（再修一轮）/ stop（止损，带当前结果出答案并如实说明）/ mark_unsolvable
（多轮同根因无解，明确告知用户无法完成）。""",
    compose=compose_round_gate,
)


# ══════════════════════════════════════════════════════════════════════════
# 判定点 6：收尾评估 finish
# ══════════════════════════════════════════════════════════════════════════
# 现状：`forced = bool(errors) or bool(unmet)` 是个二值标记，没有置信度，
# `reason` 取 errors[0] 这样的任意一条。core 的 docstring 与 events 的 TODO 都点了这两处。

Q_FIN_COVERAGE = "goal_coverage"
Q_FIN_FABRICATED = "claims_unfinished_work_done"
Q_FIN_DISCLOSED = "discloses_limitations"
Q_FIN_OUTCOME = "execution_outcome"
Q_FIN_ASK = "should_ask_user"

FINISH_COVERAGE_LEVELS: tuple[str, ...] = (
    "完全没有满足用户的诉求",
    "只满足了次要部分，主要诉求未达成",
    "主要诉求已达成，但有明显缺口",
    "完全满足用户的诉求",
)


def _questions_finish(state: Mapping[str, Any]) -> dict[str, Question]:
    return {
        Q_FIN_COVERAGE: Score(
            instructions=(
                "Looking at what the executed steps actually produced and what the final "
                "answer claims: how much of the user's original request was really satisfied?"
            ),
            criteria=list(FINISH_COVERAGE_LEVELS),
        ),
        Q_FIN_FABRICATED: Noul(
            instructions=(
                "Does the final answer claim that something was done or found, "
                "when the step results show it was in fact not done or not found?"
            )
        ),
        Q_FIN_DISCLOSED: Noul(
            instructions=(
                "If some sub-goals were not achieved, does the final answer honestly "
                "say so instead of hiding it?"
            )
        ),
        Q_FIN_OUTCOME: Choice(
            instructions="How should this execution be classified overall?",
            criteria={
                "success": "诉求已达成，回答可信",
                "partial": "计划执行了但只有部分达成",
                "not_executed": "计划未能执行或几乎没有有效产出",
                "clarify": "因缺少关键信息而未能真正回答用户",
            },
        ),
        Q_FIN_ASK: Noul(
            instructions=(
                "Should the system ask the user something (clarification or alternative "
                "options) instead of just returning this answer?"
            )
        ),
    }


def compose_finish(answers: dict[str, JevAnswer]) -> FinishDecision:
    """收尾方程：置信度按「覆盖度 ×（1-虚构）× 如实说明折减」组合（见 combine_finish_confidence）。"""
    coverage_raw = _score(answers, Q_FIN_COVERAGE)
    coverage = min(1.0, coverage_raw / max(1, len(FINISH_COVERAGE_LEVELS) - 1))
    fabricated = _noul(answers, Q_FIN_FABRICATED)
    disclosed = _noul(answers, Q_FIN_DISCLOSED)
    ask = _noul(answers, Q_FIN_ASK)
    outcome = _choice(answers, Q_FIN_OUTCOME) or "partial"
    confidence = combine_finish_confidence(
        goal_coverage=coverage, fabricated=fabricated, disclosed=disclosed
    )
    notes: list[str] = []
    if fabricated > 0.5:
        notes.append(f"疑有虚构（{fabricated:.2f}）")
    if coverage < 0.5:
        notes.append(f"覆盖度低（{coverage:.2f}）")
    return FinishDecision(
        goal_coverage=coverage,
        fabricated=fabricated,
        disclosed=disclosed,
        outcome=outcome,  # type: ignore[arg-type]
        ask_user_worth=ask,
        confidence=confidence,
        # Jev 侧的"自报置信度"用量表分布尖锐度表示，供与 LLM 自报值对比校准差异。
        confidence_reported=_confidence(answers, Q_FIN_OUTCOME),
        rationale="；".join(notes) if notes else "无明显虚构/低覆盖",
    )


FINISH = DecisionPoint[FinishDecision](
    name=Point.FINISH,
    schema=FinishDecision,
    questions=_questions_finish,
    system_prompt="""你是 plan-and-act 的收尾评估器。执行已经结束，判断这次到底做得怎么样。

依据是「每步实际产出 + 未达成清单 + 最终回答」。重点回答四件事（互相独立）：
1. 用户原始诉求被满足了多少（0-1）。
2. 最终回答有没有**虚构**：声称做了/找到了，而步骤结果里显示其实没做到。
   （这是最严重的问题，务必对照步骤结果逐条核。）
3. 若有未达成，回答是否如实说明了。
4. 整体归为哪种结局：success / partial / not_executed / clarify。

只判质量，不要重写回答。""",
    compose=compose_finish,
)


ALL_POINTS: dict[Point, DecisionPoint[Any]] = {
    PREFLIGHT.name: PREFLIGHT,
    PLAN_AUDIT.name: PLAN_AUDIT,
    STEP_ASSERT.name: STEP_ASSERT,
    DIAGNOSIS.name: DIAGNOSIS,
    ROUND_GATE.name: ROUND_GATE,
    FINISH.name: FINISH,
}
