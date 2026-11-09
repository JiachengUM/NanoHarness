"""Case 编排（单条用例：prepare → dialogues → judge → outcome）。

从 voice_test_api.py 拆分。包含：
- VoiceCaseOutcome / VoiceRunParams 数据类
- _prepare_auto_test / _run_voice_dialogues / _run_text_dialogues
- _finalize_case_outcome / _build_outcome
- _run_test_session（单 case 入口）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    DEFAULT_EXTERNAL_API_MAX_RETRIES,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.voice_test.adapter._logger import (
    get_vt_logger,
    new_run_id,
)
from projects.voice_test.adapter.browser_agent_catalog import (
    TestMode,
    VoiceTestTarget,
    bot_for_voice_test,
    is_voice_target,
    resolve_test_mode,
)
from projects.voice_test.schemas.browser_schemas import (
    DialogueHistoryEvent,
    ErrorEvent,
    JudgeResultEvent,
    JudgeSkippedEvent,
    JudgeStatus,
    JudgingEvent,
    LogEvent,
)
from projects.voice_test.adapter.browser_text_adapter import BrowserTextAdapter
from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.config.adapter_config import (
    VoiceAdapterConfig,
    adapter_config,
)
from projects.voice_test.adapter.voice_case_dialogues import (
    run_voice_case_dialogues,
)

# 文本链路清记忆后的短暂等待（框架无完成回调可 await）。
_TEXT_MEMORY_CLEAN_WAIT_SEC = 2

_log = get_vt_logger("case_runner")


@dataclass(frozen=True)
class VoiceCaseOutcome:
    """单个 case 的统一结果，供单测和批量编排共同使用。"""

    execution_success: bool
    execution_error: str | None
    judge_status: JudgeStatus
    history_for_judge: str = ""
    case_traces: list[dict] | None = None
    is_passed: bool | None = None
    reason: str | None = None
    # 首轮响应耗时（ms）：仅首个 dialogue 采集，None=超时/无 ASR/文本链路
    first_response_ms: float | None = None

    def counts_as_success(self, *, enable_judge: bool) -> bool:
        """task_run.progress.success 与批跑汇总用的同一套「成功」语义。"""
        if enable_judge:
            return self.judge_status == JudgeStatus.COMPLETED and self.is_passed is True
        return self.execution_success


@dataclass(frozen=True)
class VoiceRunParams:
    """单条 / 批跑共用的已解析运行参数（adapter_config 已 resolve）。"""

    session_config: VoiceAdapterConfig
    enable_judge: bool
    target: VoiceTestTarget = VoiceTestTarget.VOICE

    @property
    def test_mode(self) -> TestMode:
        return resolve_test_mode(self.target)


def _prepare_auto_test(
    adapter: BrowserVoiceAdapter | BrowserTextAdapter,
    case: TestCase,
    *,
    target: VoiceTestTarget,
) -> AutoTestAndRLDataGenerator:
    bot_cls = bot_for_voice_test(adapter, target=target)
    # 语音链路与 adapter_config 对齐；文本走框架默认
    max_retries = (
        adapter.config.external_api_max_retries
        if isinstance(adapter, BrowserVoiceAdapter)
        else DEFAULT_EXTERNAL_API_MAX_RETRIES
    )
    # 框架 test_mode 映射：voice-test 的 "voice"→"voice"（假人主动开口+裁判语音提示），
    # "text"→"api"（被测助手直接收 car_info 注入，冷启动台词直发被测助手）
    framework_test_mode = "voice" if is_voice_target(target) else "api"
    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=bot_cls,  # type: ignore[arg-type]
        memory_test_cases=[case],
        give_score=False,
        verbose=False,
        log_dialogue=False,
        show_progress=False,
        external_api_max_retries=max_retries,
        test_mode=framework_test_mode,
    )
    adapter.reset_session_events()
    auto_test.pause_mode = False
    auto_test.memory_reset_mode = False
    auto_test.upload_history_to_volc_memory = False
    return auto_test


async def _run_voice_dialogues(
    auto_test: AutoTestAndRLDataGenerator,
    case: TestCase,
    adapter: BrowserVoiceAdapter,
    cfg: VoiceAdapterConfig,
) -> tuple[str, list[dict], bool, str | None]:
    """语音：冷启动间等待 / case 音旁路在 run_voice_case_dialogues；结束后释放 S2S。"""
    try:
        return await run_voice_case_dialogues(auto_test, case, adapter, cfg)
    finally:
        await adapter.release_s2s_after_case()


async def _run_text_dialogues(
    auto_test: AutoTestAndRLDataGenerator,
    case: TestCase,
    adapter: BrowserTextAdapter,
) -> tuple[str, list[dict], bool, str | None]:
    """文本：跑前清火山记忆，再走框架对话。"""
    await adapter.push_event(LogEvent(message="正在清除记忆…"))
    await auto_test.clean_case_memory()
    import asyncio

    await asyncio.sleep(_TEXT_MEMORY_CLEAN_WAIT_SEC)
    return await auto_test._a_run_case_dialogues(case)


def _build_outcome(
    *,
    history_for_judge: str,
    case_traces: list[dict],
    first_response_ms: float | None,
    execution_success: bool,
    execution_error: str | None,
    judge_status: JudgeStatus,
    is_passed: bool | None = None,
    reason: str | None = None,
) -> VoiceCaseOutcome:
    """构造 VoiceCaseOutcome：统一 4 处构造的公共字段，避免重复。"""
    return VoiceCaseOutcome(
        execution_success=execution_success,
        execution_error=execution_error,
        judge_status=judge_status,
        history_for_judge=history_for_judge,
        case_traces=case_traces,
        is_passed=is_passed,
        reason=reason,
        first_response_ms=first_response_ms,
    )


async def _finalize_case_outcome(
    adapter: BrowserVoiceAdapter | BrowserTextAdapter,
    case: TestCase,
    auto_test: AutoTestAndRLDataGenerator,
    *,
    history_for_judge: str,
    case_traces: list[dict],
    execution_success: bool,
    execution_error: str | None,
    enable_judge: bool,
    first_response_ms: float | None = None,
) -> VoiceCaseOutcome:
    """对话跑完后的共用收尾：推历史 → 可选 Judge → Outcome。"""
    history_text = history_for_judge.strip() if history_for_judge else ""

    if not execution_success:
        if history_text:
            await adapter.push_event(DialogueHistoryEvent(text=history_text))
        await adapter.push_event(ErrorEvent(message=execution_error or "用例执行失败"))
        return _build_outcome(
            history_for_judge=history_for_judge,
            case_traces=case_traces,
            first_response_ms=first_response_ms,
            execution_success=False,
            execution_error=execution_error or "用例执行失败",
            judge_status=JudgeStatus.NOT_RUN,
        )

    if history_text:
        await adapter.push_event(DialogueHistoryEvent(text=history_text))

    # give_score=False 只是不解析 FakePerson 的用户评分，并不会关闭导演 Judge；
    # 是否调用 Judge 由 WebSocket 请求中的 enable_judge 单独控制。
    if not enable_judge:
        await adapter.push_event(JudgeSkippedEvent())
        return _build_outcome(
            history_for_judge=history_for_judge,
            case_traces=case_traces,
            first_response_ms=first_response_ms,
            execution_success=True,
            execution_error=None,
            judge_status=JudgeStatus.SKIPPED,
        )

    await adapter.push_event(JudgingEvent(message="对话结束，正在出具导演评估意见…"))

    try:
        result = await auto_test._a_judge_a_case(case, history_for_judge, case_traces)
    except Exception as exc:
        # Judge 失败不应让批量任务丢失后续 case；对话执行和评测执行分别计数。
        reason = str(exc)
        await adapter.push_event(ErrorEvent(message=f"自动评测失败: {reason}"))
        return _build_outcome(
            history_for_judge=history_for_judge,
            case_traces=case_traces,
            first_response_ms=first_response_ms,
            execution_success=True,
            execution_error=None,
            judge_status=JudgeStatus.FAILED,
            reason=reason,
        )

    await adapter.push_event(
        JudgeResultEvent(is_passed=result.is_passed, reason=result.reason)
    )
    return _build_outcome(
        history_for_judge=result.history_for_judge,
        case_traces=result.case_traces,
        first_response_ms=first_response_ms,
        execution_success=True,
        execution_error=None,
        judge_status=JudgeStatus.COMPLETED,
        is_passed=result.is_passed,
        reason=result.reason,
    )


async def run_test_session(
    adapter: BrowserVoiceAdapter | BrowserTextAdapter,
    case: TestCase,
    *,
    target: VoiceTestTarget,
    enable_judge: bool = True,
    session_config: VoiceAdapterConfig | None = None,
) -> VoiceCaseOutcome:
    """单条用例入口：按 channel 分到语音/文本 runner，再共用 Judge 收尾。"""
    cfg = session_config or adapter_config
    auto_test = _prepare_auto_test(adapter, case, target=target)
    # 给本次 case 执行打一个 run_id，全链路日志带 [run=xxx]，便于定位具体哪一轮
    run_id = new_run_id()
    if isinstance(adapter, BrowserVoiceAdapter):
        adapter.set_case_run_id(run_id)
    # 用 adapter 的 logger 打 ws 层日志，自动带 [sid=xxx][run=xxx] 前缀
    rlog = getattr(adapter, "_log", _log)
    rlog.info("case run start case_id=%s", case.case_id)
    await adapter.push_event(
        LogEvent(message=f"[run={run_id}] case={case.case_id} 开始执行")
    )

    try:
        if is_voice_target(target):
            if not isinstance(adapter, BrowserVoiceAdapter):
                raise TypeError("语音链路需要 BrowserVoiceAdapter")
            history_for_judge, case_traces, execution_success, execution_error = (
                await _run_voice_dialogues(auto_test, case, adapter, cfg)
            )
            # 取走 case 级首轮响应时间（voice_case_dialogues 写入）
            first_response_ms = adapter.case_first_response_ms
            adapter.case_first_response_ms = None
        else:
            if not isinstance(adapter, BrowserTextAdapter):
                raise TypeError("文本链路需要 BrowserTextAdapter")
            history_for_judge, case_traces, execution_success, execution_error = (
                await _run_text_dialogues(auto_test, case, adapter)
            )
            first_response_ms = None

        return await _finalize_case_outcome(
            adapter,
            case,
            auto_test,
            history_for_judge=history_for_judge,
            case_traces=case_traces,
            execution_success=execution_success,
            execution_error=execution_error,
            enable_judge=enable_judge,
            first_response_ms=first_response_ms,
        )
    finally:
        if isinstance(adapter, BrowserVoiceAdapter):
            adapter.set_case_run_id("")
        rlog.info("case run end case_id=%s", case.case_id)
