"""Jev 客户端归一化层的单测（离线）。

归一化是 SDK 与判定方程之间唯一的转换层，判错就是全线判错，所以逐字段冻结。
**score 的坑是真机踩出来的**：``ScoreAnswer.probabilities`` 以档位下标（int）为 key，
标签单独放在 ``legend`` 里（``{0: 0.97, 1: 0.03, 2: 0.0}`` + ``{0: '低风险', ...}``）；
若照抄进 ``dict[str, float]`` 会在 pydantic 校验处直接炸，而且分布也读不出语义。
"""

from __future__ import annotations

from typing import Any

import pytest

from aicore.agents.plan.judges.jev_client import (
    AsyncJevClient,
    JevError,
    JevTimeoutError,
    _argmax_key,
    _normalize_answer,
)
from tests.agents._fake_jev import (
    FakeJevClient,
    choice_answer,
    noul_answer,
)
from typesafe_sdk import Choice, Noul

# ────────────────────────── 假 SDK 答案对象（形状对齐真机）──────────────────────────


class _Choice:
    type = "choice"

    def __init__(self, choice: str, probs: dict[str, float], conf: float) -> None:
        self.choice = choice
        self.probabilities = probs
        self.confidence = conf


class _Score:
    type = "score"

    def __init__(self, score: float, probs: dict[int, float], legend: dict[int, str], conf: float) -> None:
        self.score = score
        self.probabilities = probs
        self.legend = legend
        self.confidence = conf


class _Noul:
    type = "noul"

    def __init__(self, noul: float) -> None:
        self.noul = noul


class _Unknown:
    type = "whatever"


def test_normalize_choice_keeps_distribution_and_confidence():
    a = _normalize_answer("route", _Choice("car_control", {"car_control": 1.0, "media": 0.0}, 1.0))
    assert a.kind == "choice" and a.choice == "car_control"
    assert a.confidence == 1.0
    assert a.probabilities == {"car_control": 1.0, "media": 0.0}


def test_normalize_score_maps_int_levels_to_legend_labels():
    a = _normalize_answer(
        "risk",
        _Score(
            0.03,
            {0: 0.97, 1: 0.03, 2: 0.0},
            {0: "低风险且容易撤销", 1: "中等后果", 2: "高风险或难以撤销"},
            0.95,
        ),
    )
    assert a.kind == "score" and a.score == 0.03
    assert a.level == "低风险且容易撤销"
    assert a.probabilities == {
        "低风险且容易撤销": 0.97,
        "中等后果": 0.03,
        "高风险或难以撤销": 0.0,
    }
    assert a.legend == ["低风险且容易撤销", "中等后果", "高风险或难以撤销"]
    assert a.confidence == 0.95


def test_normalize_score_argmax_not_rounding():
    """偏斜分布下四舍五入会指错档位：score=1.4 但概率质量在档位 2 上。"""
    a = _normalize_answer(
        "x", _Score(1.4, {0: 0.0, 1: 0.4, 2: 0.6}, {0: "a", 1: "b", 2: "c"}, 0.4)
    )
    assert a.level == "c"


def test_normalize_noul_is_plain_probability():
    a = _normalize_answer("q", _Noul(0.17))
    assert a.kind == "noul" and a.noul == 0.17 and a.confidence is None


def test_normalize_rejects_unknown_answer_type():
    with pytest.raises(JevError, match="未知答案类型"):
        _normalize_answer("q", _Unknown())


def test_argmax_is_deterministic_on_ties():
    assert _argmax_key({"b": 0.5, "a": 0.5}) == "a"
    assert _argmax_key({}) is None


# ────────────────────────── FakeJevClient 的契约 ──────────────────────────


@pytest.mark.anyio
async def test_fake_client_rejects_answer_question_mismatch():
    client = FakeJevClient([{"q1": noul_answer("q1", 0.5)}])
    with pytest.raises(AssertionError, match="不匹配"):
        await client.system_one(
            state={}, questions={"q1": Noul(instructions="x"), "q2": Choice(instructions="y", criteria={"a": "a"})}
        )


@pytest.mark.anyio
async def test_fake_client_raises_when_script_exhausted():
    client = FakeJevClient([])
    with pytest.raises(AssertionError, match="脚本已耗尽"):
        await client.system_one(state={}, questions={"q1": Noul(instructions="x")})


@pytest.mark.anyio
async def test_fake_client_records_calls_for_assertions():
    client = FakeJevClient(responder=lambda state, questions: {"q1": noul_answer("q1", 0.9)})
    await client.system_one(state={"judge_point": "diagnosis"}, questions={"q1": Noul(instructions="x")})
    assert client.calls[0]["state"] == {"judge_point": "diagnosis"}
    assert client.calls[0]["question_ids"] == ["q1"]


def test_jevas_answer_json_drops_none_fields():
    payload: dict[str, Any] = choice_answer("route", "plan").as_json()
    assert payload["choice"] == "plan" and "noul" not in payload


# ────────────────────────── AsyncJevClient：超时与错误归一化 ──────────────────────────


class _FakeSdkClient:
    """假的 SDK 异步客户端：只实现 system_one / aclose，并可脚本化抛错。"""

    def __init__(self, *, response: Any = None, error: BaseException | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.closed = 0

    async def system_one(self, state: Any, questions: Any, *, timeout: Any = None) -> Any:
        self.calls.append({"state": state, "questions": questions, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response

    async def aclose(self) -> None:
        self.closed += 1


def _client_with(sdk: _FakeSdkClient) -> AsyncJevClient:
    """构造一个已注入假 SDK 客户端的 AsyncJevClient（绕过懒建与鉴权）。"""
    client = AsyncJevClient(api_key="REDACTED", timeout=6.0)
    client._client = sdk  # type: ignore[assignment]
    return client


@pytest.mark.anyio
async def test_async_client_passes_per_call_timeout_to_sdk():
    sdk = _FakeSdkClient(response=type("R", (), {"answers": {}, "model": "m"})())
    client = _client_with(sdk)

    response = await client.system_one(state={"a": 1}, questions={"q": Noul(instructions="x")})

    assert sdk.calls[0]["timeout"] == 6.0  # 默认取客户端 timeout
    assert response.model == "m"
    assert response.latency_ms >= 0


@pytest.mark.anyio
async def test_async_client_maps_sdk_timeout_to_jev_timeout():
    from typesafe_sdk import TypeSafeAPITimeoutError

    client = _client_with(_FakeSdkClient(error=TypeSafeAPITimeoutError(6.0)))

    with pytest.raises(JevTimeoutError, match="超时"):
        await client.system_one(state={}, questions={"q": Noul(instructions="x")})


@pytest.mark.anyio
async def test_async_client_maps_other_sdk_errors_to_jev_error():
    from typesafe_sdk import TypeSafeError

    client = _client_with(_FakeSdkClient(error=TypeSafeError("boom")))

    with pytest.raises(JevError, match="调用失败"):
        await client.system_one(state={}, questions={"q": Noul(instructions="x")})


@pytest.mark.anyio
async def test_async_client_aclose_releases_and_is_idempotent():
    sdk = _FakeSdkClient(response=type("R", (), {"answers": {}, "model": None})())
    client = _client_with(sdk)

    await client.aclose()
    await client.aclose()

    assert sdk.closed == 1
    assert client._client is None
