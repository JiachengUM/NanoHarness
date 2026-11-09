"""Jev 客户端的测试替身：脚本化答案 + 答案构造便捷函数。

**放在 tests 下**：``FakeJevClient`` 与三个 ``*_answer`` 构造器只服务测试（真实代码里没有任何
调用方），留在运行时模块里会让"生产代码"看起来依赖测试件。

两种用法：
- 传 ``responses``（FIFO 列表）：第 N 次调用返回第 N 份答案，适合"判定点固定顺序"的用例；
- 传 ``responder``（回调）：``responder(state, questions) -> {qid: JevAnswer}``，
  适合按 ``state["judge_point"]`` 分派的用例。

调用记录在 :attr:`calls` 里（含 state 与 questions 的 id 集合），便于断言"裁剪确实生效"、
"该判定点确实被问到了"。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from aicore.agents.plan.judges.jev_client import JevAnswer, JevResponse

__all__ = [
    "FakeJevClient",
    "noul_answer",
    "choice_answer",
    "score_answer",
]


class FakeJevClient:
    """离线/测试用的 Jev 客户端：按脚本或回调产出答案，并记录每次调用。"""

    def __init__(
        self,
        responses: list[Mapping[str, JevAnswer]] | None = None,
        *,
        responder: Callable[[Any, Mapping[str, Any]], Mapping[str, JevAnswer]] | None = None,
        latency_ms: float = 1.0,
    ) -> None:
        if responses is None and responder is None:
            raise ValueError("FakeJevClient 需要 responses 或 responder 之一")
        self._responses = list(responses or [])
        self._responder = responder
        self._latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    async def system_one(
        self,
        *,
        state: Any,
        questions: Mapping[str, Any],
        timeout: float | None = None,
    ) -> JevResponse:
        self.calls.append(
            {
                "state": state,
                "question_ids": sorted(questions),
                "timeout": timeout,
            }
        )
        if self._responder is not None:
            raw = dict(self._responder(state, questions))
        else:
            if not self._responses:
                raise AssertionError(
                    f"FakeJevClient 脚本已耗尽，但仍被调用（questions={sorted(questions)}）"
                )
            raw = dict(self._responses.pop(0))
        missing = set(questions) - set(raw)
        extra = set(raw) - set(questions)
        if missing or extra:
            raise AssertionError(
                f"FakeJevClient 答案与问题不匹配：缺失={sorted(missing)} 多余={sorted(extra)}"
            )
        return JevResponse(answers=raw, model="fake", latency_ms=self._latency_ms)


def noul_answer(qid: str, value: float) -> JevAnswer:
    return JevAnswer(id=qid, kind="noul", noul=value)


def choice_answer(
    qid: str,
    choice: str,
    *,
    confidence: float = 0.9,
    probabilities: dict[str, float] | None = None,
) -> JevAnswer:
    return JevAnswer(
        id=qid,
        kind="choice",
        choice=choice,
        probabilities=probabilities or {choice: confidence},
        confidence=confidence,
    )


def score_answer(
    qid: str,
    score: float,
    *,
    level: str | None = None,
    probabilities: dict[str, float] | None = None,
    confidence: float = 0.9,
) -> JevAnswer:
    return JevAnswer(
        id=qid,
        kind="score",
        score=score,
        level=level,
        probabilities=probabilities or {},
        confidence=confidence,
    )
