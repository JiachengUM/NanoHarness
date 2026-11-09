"""Judge 模块测试：打分 + trace 渲染 + LLM 评判 + 格式容错。

设计原则（§0.4）：新功能必须附上可运行测试。
本测试用 MockModel 不依赖真实 LLM API，可一键跑通。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    StateCheckRecord,
    TraceRecorder,
)
from projects.experiments.time_travel_auto_test.judge import (
    AssertionResult,
    AssertionType,
    Judge,
    JudgeInput,
    JudgeVerdict,
    ScoreBreakdown,
    compute_score,
    render_timeline_text,
)
from projects.experiments.time_travel_auto_test.judge.prompt import (
    JUDGE_SYSTEM_PROMPT,
)


# ---------------- Mock Model ----------------


class MockModel:
    """模拟 LLM：按预设返回内容。"""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def ainvoke(self, prompt: str):
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("MockModel responses 已耗尽")

        class _Resp:
            pass

        resp = _Resp()
        resp.content = self.responses.pop(0)
        return resp


# ---------------- trace 工厂 ----------------


def _make_recorder_with_simple_dialogue() -> TraceRecorder:
    rec = TraceRecorder()
    t0 = datetime(2025, 1, 3, 18, 0, 0)
    rec.record_utterance(
        role="fake_person:driver",
        content="你好小涂，有点热，把空调打开吧。",
        kind=RecordKind.FAKE_PERSON_SPEAK,
        started_at=t0,
        ended_at=t0,
    )
    rec.record_utterance(
        role="assistant",
        content="好的，已为您打开空调并调至制冷模式。",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=3),
    )
    rec.record_state_check(
        at=t0 + timedelta(seconds=45),
        result=StateCheckRecord(
            expected_fields={"空调开启状态及模式": "制冷中"},
            actual_fields={"空调开启状态及模式": "制冷中"},
            passed=True,
        ),
    )
    return rec


def _make_recorder_with_acceleration_and_proactive() -> TraceRecorder:
    rec = TraceRecorder()
    t0 = datetime(2025, 1, 3, 18, 0, 0)
    rec.record_utterance(
        role="fake_person:driver",
        content="30分钟后提醒我开会。",
        kind=RecordKind.FAKE_PERSON_SPEAK,
        started_at=t0,
        ended_at=t0,
    )
    rec.record_utterance(
        role="assistant",
        content="好的，已设置 30 分钟后的开会提醒。",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
    )
    rec.record_acceleration(t0, t0 + timedelta(minutes=30))
    rec.record_utterance(
        role="assistant",
        content="时间到了，您该开会了。",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0 + timedelta(minutes=30),
        ended_at=t0 + timedelta(minutes=30, seconds=1),
    )
    return rec


def _make_recorder_with_interrupt() -> TraceRecorder:
    rec = TraceRecorder()
    t0 = datetime(2025, 1, 3, 18, 0, 0)
    rec.record_utterance(
        role="fake_person:driver",
        content="你好小涂，帮我查一下明天的天气。",
        kind=RecordKind.FAKE_PERSON_SPEAK,
        started_at=t0,
        ended_at=t0,
    )
    rec.record_utterance(
        role="assistant",
        content="好的，我帮您查一下...",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
        is_partial=True,
        interrupted_by_barge_in=True,
    )
    rec.record_utterance(
        role="fake_person:driver",
        content="等等，还是先帮我导航到公司吧。",
        kind=RecordKind.FAKE_PERSON_SPEAK,
        started_at=t0 + timedelta(seconds=2),
        ended_at=t0 + timedelta(seconds=2),
    )
    return rec


# ---------------- 打分测试 ----------------


def test_score_all_pass_no_bonus() -> None:
    """必过全过 + 无加分 → 满分 100。"""
    b = compute_score(must_pass_passed=2, must_pass_total=2, bonus_passed=0, bonus_total=0)
    assert b.score == 100.0
    assert b.passed is True


def test_score_all_pass_with_all_bonus() -> None:
    """必过全过 + 加分全过 → 满分 100。"""
    b = compute_score(must_pass_passed=2, must_pass_total=2, bonus_passed=3, bonus_total=3)
    assert b.score == 100.0
    assert b.passed is True


def test_score_all_pass_no_bonus_passed() -> None:
    """必过全过 + 加分全没过 → 及格分 60。"""
    b = compute_score(must_pass_passed=2, must_pass_total=2, bonus_passed=0, bonus_total=3)
    assert b.score == 60.0
    assert b.passed is True


def test_score_all_pass_partial_bonus() -> None:
    """必过全过 + 加分部分过 → 60 + 40 * 比例。"""
    b = compute_score(must_pass_passed=1, must_pass_total=1, bonus_passed=2, bonus_total=4)
    assert b.score == 60.0 + 40.0 * 0.5  # 80
    assert b.passed is True


def test_score_must_pass_fail() -> None:
    """必过任一不过 → 0 分。"""
    b = compute_score(must_pass_passed=1, must_pass_total=2, bonus_passed=3, bonus_total=3)
    assert b.score == 0.0
    assert b.passed is False


def test_score_state_check_merged_into_must_pass() -> None:
    """state_check 失败也算必过项失败 → 0 分。"""
    b = compute_score(
        must_pass_passed=2,
        must_pass_total=2,
        bonus_passed=0,
        bonus_total=0,
        state_check_passed=1,
        state_check_total=2,
    )
    assert b.score == 0.0
    assert b.passed is False


def test_score_state_check_all_pass_no_bonus() -> None:
    """state_check 全过 + 必过全过 + 无加分 → 满分。"""
    b = compute_score(
        must_pass_passed=2,
        must_pass_total=2,
        bonus_passed=0,
        bonus_total=0,
        state_check_passed=3,
        state_check_total=3,
    )
    assert b.score == 100.0


def test_score_breakdown_fields() -> None:
    """测试 ScoreBreakdown 字段完整性。"""
    b = compute_score(
        must_pass_passed=2,
        must_pass_total=3,
        bonus_passed=1,
        bonus_total=2,
        state_check_passed=1,
        state_check_total=1,
    )
    assert b.must_pass_total == 3
    assert b.must_pass_passed == 2
    assert b.bonus_total == 2
    assert b.bonus_passed == 1
    assert b.state_check_total == 1
    assert b.state_check_passed == 1
    # 必过没全过 → 0 分
    assert b.score == 0.0


# ---------------- trace 渲染测试 ----------------


def test_render_simple_dialogue() -> None:
    rec = _make_recorder_with_simple_dialogue()
    text = render_timeline_text(rec)
    assert "T0 = 2025-01-03T18:00:00" in text
    assert "假人(driver)" in text
    assert "你好小涂，有点热" in text
    assert "已为您打开空调" in text
    assert "[状态检查]" in text
    assert "✓ 通过" in text


def test_render_acceleration_and_proactive() -> None:
    rec = _make_recorder_with_acceleration_and_proactive()
    text = render_timeline_text(rec)
    assert "[时间快进]" in text
    assert "30m" in text
    assert "时间到了，您该开会了" in text


def test_render_interrupt_and_partial() -> None:
    """插话打断在 trace 上就是一条没说完的半截话（成因标记=被用户插话打断）。"""
    rec = _make_recorder_with_interrupt()
    text = render_timeline_text(rec)
    assert "（半截话，被用户插话打断）" in text
    # 打断不再有独立事件行——半截话本身就是打断的自然呈现
    assert "[打断事件]" not in text


def test_render_partial_timeout_marker() -> None:
    """超时截断的半截话用不同成因标记（与插话打断区分，Judge 评判含义相反）。"""
    rec = TraceRecorder()
    t0 = datetime(2025, 1, 3, 18, 0, 0)
    rec.record_utterance(
        role="assistant",
        content="正在思考中",
        kind=RecordKind.ASSISTANT_REPLY,
        started_at=t0,
        ended_at=t0 + timedelta(seconds=1),
        is_partial=True,  # 未设 interrupted_by_barge_in → 超时截断
    )
    text = render_timeline_text(rec)
    assert "（半截话，超时截断）" in text
    assert "被用户插话打断" not in text


def test_render_empty_trace() -> None:
    rec = TraceRecorder()
    text = render_timeline_text(rec)
    assert "空 trace" in text


# ---------------- Judge 评判测试 ----------------


@pytest.mark.anyio
async def test_judge_pass_with_bonus_pass() -> None:
    """测试 Judge 评判：必过全过 + 加分也过 → 满分。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
```json
{
  "assertion_results": [
    {
      "assertion": "助手应理解用户觉得热并开启空调",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "助手回复已开空调，状态检查通过",
      "evidence": ["[T0 + 3s] 助手: 好的，已为您打开空调"]
    },
    {
      "assertion": "助手应主动询问用户期望的温度",
      "assertion_type": "bonus",
      "passed": true,
      "reasoning": "助手主动询问了温度偏好",
      "evidence": ["[T0 + 3s] 助手: 好的，已为您打开空调并调至制冷模式"]
    }
  ],
  "overall_passed": true,
  "summary": "被测助手表现优秀，不仅开了空调还主动询问温度。"
}
```
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-001",
        case_name="有点热开空调",
        case_description="主驾说有点热",
        timeline_text=timeline,
        must_pass_assertions=["助手应理解用户觉得热并开启空调"],
        bonus_assertions=["助手应主动询问用户期望的温度"],
        state_check_summary={"state_checks_passed": 1, "state_checks_failed": 0},
        fake_person_profiles=[{"role_id": "driver", "profile": "李明，32岁，产品经理"}],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is True
    assert verdict.score == 100.0  # 必过全过 + 加分全过
    assert len(verdict.assertion_results) == 2
    assert verdict.score_breakdown.must_pass_passed == 1
    assert verdict.score_breakdown.bonus_passed == 1


@pytest.mark.anyio
async def test_judge_pass_with_bonus_fail() -> None:
    """测试 Judge 评判：必过全过 + 加分没过 → 及格分 60。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应开空调",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "助手开了空调",
      "evidence": ["[T0 + 3s] 助手: 好的"]
    },
    {
      "assertion": "助手应主动询问温度",
      "assertion_type": "bonus",
      "passed": false,
      "reasoning": "助手没有主动询问温度",
      "evidence": ["trace 中未出现询问温度的内容"]
    }
  ],
  "overall_passed": true,
  "summary": "助手开了空调但没主动询问温度。"
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-001",
        case_name="测试",
        case_description="测试",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
        bonus_assertions=["助手应主动询问温度"],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is True  # 必过过了
    assert verdict.score == 60.0  # 加分没过 → 及格分


@pytest.mark.anyio
async def test_judge_must_pass_fail() -> None:
    """测试 Judge 评判：必过没过 → 0 分。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应开空调",
      "assertion_type": "must_pass",
      "passed": false,
      "reasoning": "助手没开空调",
      "evidence": ["[T0 + 3s] 助手: 抱歉我无法操作"]
    },
    {
      "assertion": "助手应主动询问温度",
      "assertion_type": "bonus",
      "passed": true,
      "reasoning": "助手主动询问了",
      "evidence": ["[T0 + 3s] 助手: 您期望多少度"]
    }
  ],
  "overall_passed": false,
  "summary": "助手没开空调但主动询问了温度。"
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-fail",
        case_name="必过失败",
        case_description="测试必过失败",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
        bonus_assertions=["助手应主动询问温度"],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is False
    assert verdict.score == 0.0  # 必过失败 → 0 分


@pytest.mark.anyio
async def test_judge_no_bonus_assertions() -> None:
    """测试 Judge 评判：只有必过项，无加分项。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应开空调",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "通过",
      "evidence": ["证据"]
    }
  ],
  "overall_passed": true,
  "summary": "通过"
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-no-bonus",
        case_name="无加分",
        case_description="无加分项",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is True
    assert verdict.score == 100.0  # 必过全过 + 无加分 → 满分


@pytest.mark.anyio
async def test_judge_state_check_fail_makes_zero() -> None:
    """测试 state_check 失败导致 0 分。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应开空调",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "通过",
      "evidence": ["证据"]
    }
  ],
  "overall_passed": true,
  "summary": "通过"
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-sc-fail",
        case_name="state_check 失败",
        case_description="state_check 失败导致 0 分",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
        state_check_summary={"state_checks_passed": 0, "state_checks_failed": 1},
    )

    verdict = await judge.ajudge(judge_input)

    # NL 必过过了，但 state_check 失败 → 0 分
    assert verdict.score == 0.0
    assert verdict.overall_passed is False


@pytest.mark.anyio
async def test_judge_proactive_intelligence() -> None:
    """测试 Judge 评判主动智能场景。"""
    rec = _make_recorder_with_acceleration_and_proactive()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应在30分钟后主动提醒用户开会",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "trace 显示 T0+30m 时助手主动开口提醒",
      "evidence": ["[T0 + 30m] 助手: 时间到了，您该开会了。"]
    }
  ],
  "overall_passed": true,
  "summary": "被测助手正确实现了主动提醒能力。"
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-proactive",
        case_name="30分钟提醒",
        case_description="测试主动智能",
        timeline_text=timeline,
        must_pass_assertions=["助手应在30分钟后主动提醒用户开会"],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is True
    assert verdict.score == 100.0


@pytest.mark.anyio
async def test_judge_format_retry() -> None:
    """测试 Judge 格式容错：第一次格式错误，重试后成功。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    bad_response = "抱歉，我无法判断。"
    good_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应开空调",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "通过",
      "evidence": ["证据"]
    }
  ],
  "overall_passed": true,
  "summary": "通过"
}
"""
    model = MockModel([bad_response, good_response])
    judge = Judge(model=model, judge_format_max_retries=3)

    judge_input = JudgeInput(
        case_id="case-retry",
        case_name="格式重试",
        case_description="测试格式容错",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is True
    assert len(model.calls) == 2


@pytest.mark.anyio
async def test_judge_all_retries_failed() -> None:
    """测试 Judge 所有重试都失败的兜底。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    bad_responses = ["不会", "还是不会", "依然不会"]
    model = MockModel(bad_responses)
    judge = Judge(model=model, judge_format_max_retries=2)

    judge_input = JudgeInput(
        case_id="case-all-fail",
        case_name="全失败",
        case_description="测试兜底",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
        bonus_assertions=["加分项1"],
    )

    verdict = await judge.ajudge(judge_input)

    assert verdict.overall_passed is False
    assert verdict.score == 0.0
    assert verdict.raw_response is not None
    # 所有断言都标记为失败
    assert all(not r.passed for r in verdict.assertion_results)
    # 必过和加分都在 assertion_results 里
    assert len(verdict.assertion_results) == 2


@pytest.mark.anyio
async def test_judge_missing_overall_passed() -> None:
    """测试 Judge 缺少 overall_passed 字段时自动用打分结果。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "断言1",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "通过",
      "evidence": ["证据1"]
    },
    {
      "assertion": "加分1",
      "assertion_type": "bonus",
      "passed": false,
      "reasoning": "失败",
      "evidence": ["证据2"]
    }
  ]
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-missing",
        case_name="缺 overall",
        case_description="测试自动计算",
        timeline_text=timeline,
        must_pass_assertions=["断言1"],
        bonus_assertions=["加分1"],
    )

    verdict = await judge.ajudge(judge_input)

    # 必过过了，加分没过 → 60 分，及格
    assert verdict.score == 60.0
    assert verdict.overall_passed is True  # 60 分及格


def test_judge_sync_wrapper() -> None:
    """测试 Judge 同步包装方法。"""
    rec = _make_recorder_with_simple_dialogue()
    timeline = render_timeline_text(rec)

    mock_response = """
{
  "assertion_results": [
    {
      "assertion": "助手应开空调",
      "assertion_type": "must_pass",
      "passed": true,
      "reasoning": "通过",
      "evidence": ["证据"]
    }
  ],
  "overall_passed": true,
  "summary": "通过"
}
"""
    model = MockModel([mock_response])
    judge = Judge(model=model)

    judge_input = JudgeInput(
        case_id="case-sync",
        case_name="同步",
        case_description="测试同步",
        timeline_text=timeline,
        must_pass_assertions=["助手应开空调"],
    )

    verdict = judge.judge(judge_input)
    assert verdict.overall_passed is True


# ---------------- 数据模型测试 ----------------


def test_judge_input_validation() -> None:
    """测试 JudgeInput 数据模型校验。"""
    judge_input = JudgeInput(
        case_id="case-001",
        case_name="测试",
        timeline_text="trace",
        must_pass_assertions=["断言1"],
    )
    assert judge_input.case_description == ""
    assert judge_input.bonus_assertions == []
    assert judge_input.state_check_summary == {}
    assert judge_input.assistant_history == []
    assert judge_input.fake_person_profiles == []


def test_judge_verdict_serialization() -> None:
    """测试 JudgeVerdict 可序列化。"""
    from projects.experiments.time_travel_auto_test.judge.scoring import compute_score

    breakdown = compute_score(
        must_pass_passed=1, must_pass_total=1, bonus_passed=1, bonus_total=1
    )
    verdict = JudgeVerdict(
        case_id="case-001",
        overall_passed=True,
        score=100.0,
        score_breakdown=breakdown,
        assertion_results=[
            AssertionResult(
                assertion="断言1",
                assertion_type=AssertionType.MUST_PASS,
                passed=True,
                reasoning="理由",
                evidence=["证据1"],
            )
        ],
        summary="总结",
    )
    data = verdict.model_dump()
    assert data["overall_passed"] is True
    assert data["score"] == 100.0
    assert data["score_breakdown"]["must_pass_passed"] == 1
    json_str = verdict.model_dump_json()
    assert "断言1" in json_str


# ---------------- prompt 内容测试 ----------------


def test_judge_prompt_contains_timeline_semantics() -> None:
    """测试 Judge prompt 包含时序演进语义说明。"""
    assert "时间快进" in JUDGE_SYSTEM_PROMPT
    assert "半截话" in JUDGE_SYSTEM_PROMPT
    # 打断已无独立事件类型（半截话即打断的自然呈现），prompt 不应再提"打断事件"
    assert "打断事件" not in JUDGE_SYSTEM_PROMPT
    assert "状态检查" in JUDGE_SYSTEM_PROMPT
    assert "主动" in JUDGE_SYSTEM_PROMPT
    # 必过/加分项
    assert "必过项" in JUDGE_SYSTEM_PROMPT
    assert "加分项" in JUDGE_SYSTEM_PROMPT
    # 假人价值观对齐
    assert "假人" in JUDGE_SYSTEM_PROMPT
    assert "视角" in JUDGE_SYSTEM_PROMPT


def test_judge_prompt_neutral_no_hardcoded_verdict_rules() -> None:
    """裁判中立性：prompt 只含读懂 trace 的机制常识，不写死行为对错评判原则。

    行为对错（该合作容忍还是该中止响应、是否扣分等）由各用例断言定义，
    prompt 中不得出现预设评判结论的措辞。
    """
    # 不写死插话类型的对错评判
    assert "不应扣分" not in JUDGE_SYSTEM_PROMPT
    assert "才是问题" not in JUDGE_SYSTEM_PROMPT
    assert "合理合作" not in JUDGE_SYSTEM_PROMPT
    # 不写死半截话/停顿的评分倾向
    assert "通常是扣分信号" not in JUDGE_SYSTEM_PROMPT
    assert "体验不佳" not in JUDGE_SYSTEM_PROMPT
    # 不做褒贬预判（"主动智能的体现"会引导裁判倾向加分）
    assert "主动智能的体现" not in JUDGE_SYSTEM_PROMPT
    # 明确声明评判标准以断言为准（中立平台：判分依据来自用例断言）
    assert "以断言为准" in JUDGE_SYSTEM_PROMPT
    assert "不要预设某种反应模式必然对或必然错" in JUDGE_SYSTEM_PROMPT
