"""Judge 类：终局评判主逻辑。

设计（见 CONTEXT §2.7）：
- 独立模块，Runner 不调——Runner 只负责跑出 trace，评判是独立步骤
- 输入 JudgeInput（含 timeline_text + must_pass/bonus 断言 + 假人人设）
- 输出 JudgeVerdict（含打分明细 ScoreBreakdown + 每条断言结果）
- prompt 让 LLM 理解时序演进语义 + 对齐假人价值观
- 打分公式见 scoring.py
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from projects.experiments.time_travel_auto_test.judge.models import (
    AssertionResult,
    AssertionType,
    JudgeInput,
    JudgeVerdict,
)
from projects.experiments.time_travel_auto_test.judge.prompt import (
    JUDGE_SYSTEM_PROMPT,
)
from projects.experiments.time_travel_auto_test.judge.scoring import compute_score

# ---------------- 默认配置 ----------------

DEFAULT_EXTERNAL_API_MAX_RETRIES = 2
DEFAULT_JUDGE_FORMAT_MAX_RETRIES = 3


class Judge:
    """终局裁判：拿 trace + 必过/加分断言评判被测助手表现。

    用法：
        judge = Judge()
        verdict = await judge.ajudge(judge_input)
        # verdict.score / verdict.overall_passed / verdict.assertion_results
    """

    def __init__(
        self,
        model=None,
        *,
        external_api_max_retries: int = DEFAULT_EXTERNAL_API_MAX_RETRIES,
        judge_format_max_retries: int = DEFAULT_JUDGE_FORMAT_MAX_RETRIES,
    ) -> None:
        if model is None:
            model = _load_default_model()
        self.model = model
        self.external_api_max_retries = external_api_max_retries
        self.judge_format_max_retries = judge_format_max_retries

    # ---------------- 对外 API ----------------

    async def ajudge(self, judge_input: JudgeInput) -> JudgeVerdict:
        """异步评判。"""
        prompt = self._build_prompt(judge_input)

        last_content: Optional[str] = None
        last_error_msg: str = ""
        for attempt in range(self.judge_format_max_retries + 1):
            cur_prompt = prompt
            if attempt > 0:
                cur_prompt = (
                    prompt
                    + f"\n\n注意：你上一次的回复格式不正确（{last_error_msg}）。"
                    + "请严格只输出 JSON，不要有任何其他内容。"
                )

            try:
                response = await self._call_model(cur_prompt)
                last_content = response
            except Exception:
                if attempt >= self.external_api_max_retries:
                    raise
                await asyncio.sleep(min(2.0**attempt, 30.0))
                continue

            try:
                return self._parse_verdict(last_content, judge_input)
            except _JudgeFormatError as e:
                last_error_msg = str(e)
                continue

        # 所有重试均失败 → 返回失败 verdict
        return self._build_failure_verdict(judge_input, last_content)

    def judge(self, judge_input: JudgeInput) -> JudgeVerdict:
        """同步包装（asyncio.run）。"""
        return asyncio.run(self.ajudge(judge_input))

    # ---------------- 内部 ----------------

    def _build_prompt(self, judge_input: JudgeInput) -> str:
        """构造发给 LLM 的完整 prompt。"""
        must_pass_text = "\n".join(
            f"{i+1}. {a}" for i, a in enumerate(judge_input.must_pass_assertions)
        )
        bonus_text = (
            "\n".join(f"{i+1}. {a}" for i, a in enumerate(judge_input.bonus_assertions))
            if judge_input.bonus_assertions
            else "（无加分项）"
        )

        state_check_text = ""
        if judge_input.state_check_summary:
            state_check_text = (
                "\n\n## 结构化断言结果（已自动判定，全部算必过项，不要重复评判）\n"
                f"通过: {judge_input.state_check_summary.get('state_checks_passed', 0)}, "
                f"失败: {judge_input.state_check_summary.get('state_checks_failed', 0)}"
            )

        history_text = ""
        if judge_input.assistant_history:
            history_lines = []
            for msg in judge_input.assistant_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                history_lines.append(f"[{role}] {content}")
            history_text = "\n\n## 助手视角的对话历史\n" + "\n".join(history_lines)

        fake_person_text = ""
        if judge_input.fake_person_profiles:
            person_lines = []
            for p in judge_input.fake_person_profiles:
                role_id = p.get("role_id", "")
                profile = p.get("profile", "")
                person_lines.append(f"- {role_id}: {profile}")
            fake_person_text = "\n\n## 假人人设（评判时请代入该用户视角）\n" + "\n".join(
                person_lines
            )

        return (
            f"{JUDGE_SYSTEM_PROMPT}\n\n"
            f"## 测试用例\n"
            f"- 用例ID: {judge_input.case_id}\n"
            f"- 用例名: {judge_input.case_name}\n"
            f"- 用例描述: {judge_input.case_description or '无'}\n"
            f"{fake_person_text}"
            f"\n\n## 测试轨迹（trace）\n{judge_input.timeline_text}"
            f"{state_check_text}"
            f"{history_text}"
            f"\n\n## 必过项断言\n{must_pass_text}"
            f"\n\n## 加分项断言\n{bonus_text}\n\n"
            f"请输出 JSON："
        )

    async def _call_model(self, prompt: str) -> str:
        """调用 LLM，返回字符串内容。"""
        if hasattr(self.model, "ainvoke"):
            response = await self.model.ainvoke(prompt)
            if hasattr(response, "content"):
                return response.content
            return str(response)
        if callable(self.model):
            result = self.model(prompt)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result)
        raise TypeError(f"不支持的 model 类型: {type(self.model)}")

    def _parse_verdict(
        self, content: str, judge_input: JudgeInput
    ) -> JudgeVerdict:
        """解析 LLM 回复为 JudgeVerdict（含打分）。"""
        json_str = _extract_json(content)
        if json_str is None:
            raise _JudgeFormatError(f"未找到 JSON 块，原始回复前200字符: {content[:200]}")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise _JudgeFormatError(f"JSON 解析失败: {e}")

        if "assertion_results" not in data:
            raise _JudgeFormatError("缺少 assertion_results 字段")
        if not isinstance(data["assertion_results"], list):
            raise _JudgeFormatError("assertion_results 不是列表")

        # 解析每条断言结果
        assertion_results: list[AssertionResult] = []
        must_pass_passed = 0
        bonus_passed = 0

        for i, item in enumerate(data["assertion_results"]):
            if not isinstance(item, dict):
                raise _JudgeFormatError(f"assertion_results[{i}] 不是对象")

            assertion = item.get("assertion", "")
            assertion_type_str = item.get("assertion_type", "must_pass")
            try:
                assertion_type = AssertionType(assertion_type_str)
            except ValueError:
                raise _JudgeFormatError(
                    f"assertion_results[{i}].assertion_type 不是合法值: {assertion_type_str}"
                )

            passed = item.get("passed")
            if not isinstance(passed, bool):
                raise _JudgeFormatError(f"assertion_results[{i}].passed 不是布尔值")

            reasoning = item.get("reasoning", "")
            evidence = item.get("evidence", [])
            if not isinstance(evidence, list):
                evidence = [str(evidence)]

            assertion_results.append(
                AssertionResult(
                    assertion=assertion,
                    assertion_type=assertion_type,
                    passed=passed,
                    reasoning=reasoning,
                    evidence=[str(e) for e in evidence],
                )
            )

            if passed:
                if assertion_type == AssertionType.MUST_PASS:
                    must_pass_passed += 1
                else:
                    bonus_passed += 1

        # 计算打分
        state_check_passed = judge_input.state_check_summary.get(
            "state_checks_passed", 0
        )
        state_check_total = state_check_passed + judge_input.state_check_summary.get(
            "state_checks_failed", 0
        )

        breakdown = compute_score(
            must_pass_passed=must_pass_passed,
            must_pass_total=len(judge_input.must_pass_assertions),
            bonus_passed=bonus_passed,
            bonus_total=len(judge_input.bonus_assertions),
            state_check_passed=state_check_passed,
            state_check_total=state_check_total,
        )

        # overall_passed：以打分结果为准（打分综合了必过/加分/state_check）
        # LLM 给的 overall_passed 仅参考，不覆盖打分结果
        overall = breakdown.passed

        summary = data.get("summary", "")

        return JudgeVerdict(
            case_id=judge_input.case_id,
            overall_passed=overall,
            score=breakdown.score,
            score_breakdown=breakdown,
            assertion_results=assertion_results,
            summary=summary,
        )

    def _build_failure_verdict(
        self, judge_input: JudgeInput, raw_response: Optional[str]
    ) -> JudgeVerdict:
        """解析全失败时的兜底 verdict。"""
        all_assertions = [
            AssertionResult(
                assertion=a,
                assertion_type=AssertionType.MUST_PASS,
                passed=False,
                reasoning=f"Judge 解析失败 {self.judge_format_max_retries} 次仍不合规",
                evidence=[],
            )
            for a in judge_input.must_pass_assertions
        ] + [
            AssertionResult(
                assertion=a,
                assertion_type=AssertionType.BONUS,
                passed=False,
                reasoning="Judge 解析失败，未评判",
                evidence=[],
            )
            for a in judge_input.bonus_assertions
        ]

        state_check_total = judge_input.state_check_summary.get(
            "state_checks_passed", 0
        ) + judge_input.state_check_summary.get("state_checks_failed", 0)

        breakdown = compute_score(
            must_pass_passed=0,
            must_pass_total=len(judge_input.must_pass_assertions),
            bonus_passed=0,
            bonus_total=len(judge_input.bonus_assertions),
            state_check_passed=judge_input.state_check_summary.get(
                "state_checks_passed", 0
            ),
            state_check_total=state_check_total,
        )

        return JudgeVerdict(
            case_id=judge_input.case_id,
            overall_passed=False,
            score=breakdown.score,
            score_breakdown=breakdown,
            assertion_results=all_assertions,
            summary=f"Judge 解析失败，原始回复：{raw_response}",
            raw_response=raw_response,
        )


# ---------------- 辅助函数 ----------------


class _JudgeFormatError(Exception):
    """Judge 输出格式错误（用于内部重试控制）。"""


def _extract_json(text: str) -> Optional[str]:
    """从 LLM 回复中提取 JSON 块。"""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first : last + 1]
    return None


def _load_default_model():
    """加载默认 LLM 模型（懒加载）。"""
    try:
        from projects.mind.mem.auto_test_script.langchain_models import doubao_model
        return doubao_model
    except ImportError:
        raise ImportError(
            "未提供 model，且无法导入默认 doubao_model。"
            "请显式传入 model 参数，或安装 projects.mind.mem.auto_test_script.langchain_models。"
        )


# ---------------- 便捷工具 ----------------


def build_judge_input_from_run_result(
    case,
    recorder: TraceRecorder,
    run_result,
    assistant_history: Optional[list[dict[str, str]]] = None,
) -> JudgeInput:
    """从 RunResult + TraceRecorder 构造 JudgeInput 的便捷工具。

    Args:
        case: TestCase（含 must_pass_assertions / bonus_assertions / fake_persons）
        recorder: 本次 run 的 TraceRecorder
        run_result: 本次 run 的 RunResult
        assistant_history: 助手 adump_history() 的返回值（可选）
    """
    from projects.experiments.time_travel_auto_test.judge.prompt import render_timeline_text

    timeline_text = render_timeline_text(recorder)
    state_check_summary = {
        "state_checks_passed": run_result.trace_summary.get("state_checks_passed", 0),
        "state_checks_failed": run_result.trace_summary.get("state_checks_failed", 0),
    }
    fake_person_profiles = [
        {"role_id": p.role_id, "profile": p.profile} for p in case.fake_persons
    ]

    return JudgeInput(
        case_id=case.id,
        case_name=case.case_name,
        case_description=case.case_description,
        timeline_text=timeline_text,
        must_pass_assertions=list(run_result.must_pass_assertions),
        bonus_assertions=list(run_result.bonus_assertions),
        state_check_summary=state_check_summary,
        assistant_history=assistant_history or [],
        fake_person_profiles=fake_person_profiles,
    )


# 为了避免循环导入，延迟导入 TraceRecorder 类型
from projects.experiments.time_travel_auto_test.case_runner.trace import TraceRecorder  # noqa: E402
