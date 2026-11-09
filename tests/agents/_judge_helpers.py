"""Jev 判定器测试共用件：可脚本化的假判定器 + 假模型 + 工具 stub。

放在 tests/ 下但文件名不以 test_ 开头，不参与 pytest 收集。

三类件：
- :class:`ScriptedJudge`：按 ``state["judge_point"]`` 给出默认答案，测试只需覆盖关心的维度。
  默认答案是"一切正常"（覆盖度高、不虚构、无歧义），这样每个用例只表达它真正要测的那件事。
- :class:`FakeModelAPI`：只实现被测路径用到的 ``initial_state`` / ``invoke`` / ``structured_output``。
- :func:`make_tool`：构造 passthrough 能命中的工具（返回 dict 的 key 与 concept attribute 同名），
  于是投影不走 LLM，测试可完全离线。
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field

from aicore.agents.plan.criterion import KIND_ASSERTION
from aicore.agents.plan.judges.jev import JevJudge
from aicore.agents.plan.judges.jev_client import JevAnswer
from aicore.agents.plan.judges.points import (
    CAUSE_PLAN_MISTAKE,
    FINISH_COVERAGE_LEVELS,
    Q_AMBIGUITY,
    Q_AUDIT_CONFIRM,
    Q_AUDIT_COVERAGE,
    Q_AUDIT_GAP,
    Q_AUDIT_RISK,
    Q_AUDIT_STRICTNESS,
    Q_DIAG_BLOCKING,
    Q_DIAG_CAUSE,
    Q_DIAG_HARD,
    Q_DIAG_RETRY,
    Q_DIAG_USABLE,
    Q_FIN_ASK,
    Q_FIN_COVERAGE,
    Q_FIN_DISCLOSED,
    Q_FIN_FABRICATED,
    Q_FIN_OUTCOME,
    Q_GATE_SAME,
    Q_GATE_WORTH,
    Q_GOAL_COUNT,
    Q_NEEDS_PLAN,
    Q_PATH,
    Q_PRE_CONFIRM,
    Q_PRE_RISK,
    Q_ASSERT_GOAL,
    CLAUSE_HOLDS,
    QUALITY_GROUNDED,
    clause_quality_question_id,
    clause_question_id,
)
from aicore.models.model_api import (
    ModelResponse,
    ModelState,
    StructuredModelResponse,
    UserMessage,
)
from aicore.tools import TaskTool
from tests.agents._fake_jev import (
    FakeJevClient,
    choice_answer,
    noul_answer,
    score_answer,
)


class FakeState(ModelState):
    """最小可用的模型状态（测试里不需要真的续接对话）。"""

    marker: str = "test"


def _all_pass_answers(point: str, state: Mapping[str, Any]) -> dict[str, JevAnswer]:
    """每个判定点的"一切正常"默认答案。"""
    if point == "preflight":
        return {
            Q_PATH: choice_answer(Q_PATH, "plan", confidence=0.95),
            Q_NEEDS_PLAN: noul_answer(Q_NEEDS_PLAN, 0.95),
            Q_AMBIGUITY: noul_answer(Q_AMBIGUITY, 0.02),
            Q_GOAL_COUNT: choice_answer(Q_GOAL_COUNT, "one"),
            Q_PRE_RISK: score_answer(Q_PRE_RISK, 0.1, probabilities={"0": 0.9}),
            Q_PRE_CONFIRM: noul_answer(Q_PRE_CONFIRM, 0.05),
        }
    if point == "plan_audit":
        return {
            Q_AUDIT_COVERAGE: noul_answer(Q_AUDIT_COVERAGE, 0.95),
            Q_AUDIT_STRICTNESS: noul_answer(Q_AUDIT_STRICTNESS, 0.9),
            Q_AUDIT_GAP: choice_answer(Q_AUDIT_GAP, "none"),
            Q_AUDIT_RISK: score_answer(Q_AUDIT_RISK, 0.1),
            Q_AUDIT_CONFIRM: noul_answer(Q_AUDIT_CONFIRM, 0.05),
        }
    if point == "step_assert":
        # 断言逐条给三态答案：条数由 state 里该步声明的判据决定（看到几条问几条）。
        # 判据只有一个键 success_check，形态靠 kind 分辨（见 aicore.agents.plan.criterion）。
        criterion = (state.get("step") or {}).get("success_check") or {}
        assertions = criterion.get("assertions") or []
        return {
            Q_ASSERT_GOAL: noul_answer(Q_ASSERT_GOAL, 0.95),
            **{
                clause_question_id(i): choice_answer(clause_question_id(i), CLAUSE_HOLDS)
                for i in range(len(assertions))
            },
            # A 轴默认“判据靠谱”（一切正常），与三态并列但正交：测试要测质量门时再覆盖。
            **{
                clause_quality_question_id(i): choice_answer(
                    clause_quality_question_id(i), QUALITY_GROUNDED
                )
                for i in range(len(assertions))
            },
            # 补救那一半：断言全部成立时不会被读，但问题一律照问（同一次判定的成本不变）。
            # 默认取“产出可用、换做法也有戏”，让未达成时优先走降级而不是重规划。
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.2),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.9),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.9),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.9),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
        }
    if point == "diagnosis":
        return {
            Q_DIAG_HARD: noul_answer(Q_DIAG_HARD, 0.2),
            Q_DIAG_RETRY: noul_answer(Q_DIAG_RETRY, 0.9),
            Q_DIAG_USABLE: noul_answer(Q_DIAG_USABLE, 0.1),
            Q_DIAG_BLOCKING: noul_answer(Q_DIAG_BLOCKING, 0.9),
            Q_DIAG_CAUSE: choice_answer(Q_DIAG_CAUSE, CAUSE_PLAN_MISTAKE),
        }
    if point == "round_gate":
        return {
            Q_GATE_WORTH: noul_answer(Q_GATE_WORTH, 0.85),
            Q_GATE_SAME: noul_answer(Q_GATE_SAME, 0.1),
        }
    if point == "finish":
        return {
            Q_FIN_COVERAGE: score_answer(
                Q_FIN_COVERAGE, float(len(FINISH_COVERAGE_LEVELS) - 1)
            ),
            Q_FIN_FABRICATED: noul_answer(Q_FIN_FABRICATED, 0.02),
            Q_FIN_DISCLOSED: noul_answer(Q_FIN_DISCLOSED, 0.9),
            Q_FIN_OUTCOME: choice_answer(Q_FIN_OUTCOME, "success", confidence=0.9),
            Q_FIN_ASK: noul_answer(Q_FIN_ASK, 0.05),
        }
    raise KeyError(f"未知判定点：{point!r}")


class ScriptedJudge:
    """按判定点给默认答案的脚本化判定器，可对任意维度做覆盖。"""

    def __init__(self, **overrides: dict[str, JevAnswer]) -> None:
        self.overrides = overrides
        self.client = FakeJevClient(responder=self._respond)
        self.judge = JevJudge(self.client)

    def _respond(
        self, state: Mapping[str, Any], questions: Mapping[str, Any]
    ) -> dict[str, JevAnswer]:
        point = str(state.get("judge_point"))  # Point 是 StrEnum，字符串比较即可
        answers = _all_pass_answers(point, state)
        answers.update(self.overrides.get(point, {}))
        return {qid: answers[qid] for qid in questions}

    # 便捷断言：某个判定点被打过几次
    def calls_for(self, point: str) -> list[dict[str, Any]]:
        return [c for c in self.client.calls if c["state"].get("judge_point") == point]


class RejectingJudge:
    """调用即抛错（模拟把控不可用），用于验证"失败不回退"。"""

    name = "jev"
    criterion = KIND_ASSERTION

    def __init__(self, exc: Exception | None = None, *, points: Any = None) -> None:
        self.exc = exc or RuntimeError("jev down")
        self.calls = 0
        self._points = points

    def supports(self, point: Any) -> bool:
        return self._points is None or point in self._points

    async def decide(self, point: Any, state: Mapping[str, Any]) -> Any:
        self.calls += 1
        raise self.exc


class FakeModelAPI:
    """最小 ModelAPI：只实现被测路径用到的方法。"""

    def __init__(self, answer: str = "这是最终回答") -> None:
        self.answer = answer
        self.invoke_calls: list[str] = []
        self.structured_calls: list[str] = []

    def initial_state(self, *, system_prompt: str | None = None) -> FakeState:
        return FakeState()

    async def invoke(self, input: Any, *, state: Any = None, tools: Any = None, params: Any = None) -> ModelResponse[Any]:
        text = input.text if isinstance(input, UserMessage) else str(input)
        self.invoke_calls.append(text)
        return ModelResponse(text=self.answer, state=state or FakeState())

    async def structured_output(
        self, input: Any, *, output_type: type[Any], state: Any = None, params: Any = None
    ) -> StructuredModelResponse[Any, Any]:
        text = input.text if isinstance(input, UserMessage) else str(input)
        self.structured_calls.append(text)
        raise NotImplementedError("本测试的 Jev 路径不应触发结构化生成；如需请显式覆盖")


class _ToolArgs(BaseModel):
    q: str = Field(default="x")


def make_tool(
    name: str, *, value: Any, raises: bool = False, timeout: float = 5.0
) -> TaskTool[Any, Any, Any, Any]:
    """构造工具：``value`` 的 key 与 concept attribute 同名即可命中 passthrough 投影（不打模型）。"""

    async def worker(q: str = "x") -> Any:
        if raises:
            raise RuntimeError("tool boom")
        return value

    return TaskTool[Any, Any, Any, Any](
        name=name,
        description="test tool",
        args_schema=_ToolArgs,
        worker=worker,
        timeout=timeout,
    )


__all__ = [
    "FakeState",
    "ScriptedJudge",
    "RejectingJudge",
    "FakeModelAPI",
    "make_tool",
    "FakeJevClient",
    "choice_answer",
    "noul_answer",
    "score_answer",
]
