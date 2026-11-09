"""批跑编排（数据集串行 + 手动步进 + 单 case 重复）。

从 voice_test_api.py 拆分。包含：
- _BatchStats 统计容器
- BatchStepController 步进/暂停控制
- _run_voice_repeat（单 case N 遍）
- _run_voice_batch（数据集批跑）+ 子函数
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from beanie import PydanticObjectId

from projects.mind.test_backend.mdb_models.task import TaskDoc, TaskRunDoc
from projects.mind.test_backend.repositories import mdb_service
from projects.voice_test.schemas.browser_schemas import (
    BatchCaseResultEvent,
    BatchCaseStartedEvent,
    BatchCaseWaitingEvent,
    BatchDoneEvent,
    BatchPausedEvent,
    BatchPace,
    BatchResumedEvent,
    BatchStartedEvent,
    JudgeStatus,
    TaskRunCreatedEvent,
)
from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.config.adapter_config import (
    VoiceAdapterConfig,
    adapter_config,
)
from projects.voice_test.adapter.voice_case_dialogues import await_countdown_wait

from projects.mind.test_backend.api.voice_test.case_runner import (
    VoiceCaseOutcome,
    run_test_session,
)
from projects.mind.test_backend.api.voice_test.persistence import (
    create_voice_task_run,
    get_or_create_voice_task,
    load_dataset_cases,
    mark_voice_task_run_complete,
    mark_voice_task_run_failed,
    mark_voice_task_run_paused,
    save_voice_case_result,
    update_voice_task_run_progress,
)

if TYPE_CHECKING:
    from projects.mind.test_backend.api.voice_test.ws_session import VoiceWsSession


# =============================================================================
# 暂停原因 + 步进控制器
# （CancelReason 也定义在此处，避免与 ws_session 循环依赖）
# =============================================================================

from enum import StrEnum

_log = get_vt_logger("batch")


class CancelReason(StrEnum):
    """批跑取消原因：决定 CancelledError 分支标记 PAUSED 还是 FAILED。"""

    USER_STOP = "user_stop"        # 用户点停止 → FAILED（不可恢复）
    PAUSE = "pause"                # 用户点暂停 → PAUSED（可续跑）
    WS_DISCONNECT = "ws_disconnect"  # WS 断连 → PAUSED（可续跑）


class BatchStepController:
    """手动批跑时在 case 之间挂起，等待前端 next_case / skip_case；并支持 AUTO/MANUAL 模式下的暂停/继续。"""

    def __init__(self) -> None:
        self._resume = asyncio.Event()
        self._skip = False
        self.waiting = False
        # 暂停/继续
        self._resume_from_pause = asyncio.Event()
        self._resume_from_pause.set()  # 初始非暂停状态
        self.pause_requested = False
        self.paused = False

    def approve(self, *, skip: bool = False) -> None:
        if not self.waiting:
            return
        self._skip = skip
        self._resume.set()

    async def wait_before_case(self) -> bool:
        """返回 True 表示用户跳过本 case。"""
        self.waiting = True
        self._skip = False
        self._resume.clear()
        await self._resume.wait()
        self.waiting = False
        return self._skip

    def request_pause(self) -> None:
        """请求暂停：下一个 case 开始前挂起。当前 case 不打断。"""
        self.pause_requested = True
        self._resume_from_pause.clear()

    def request_resume(self) -> None:
        """解除暂停：若已挂起则立即恢复；否则只清标志。"""
        self.pause_requested = False
        self._resume_from_pause.set()

    async def wait_if_paused(
        self,
        adapter: BrowserVoiceAdapter | None = None,
        event_factory=None,
    ) -> bool:
        """在 case 开始前调用；若已请求暂停则挂起，返回 True 表示曾被暂停。"""
        if not self.pause_requested:
            return False
        self.paused = True
        if adapter is not None and event_factory is not None:
            await adapter.push_event(event_factory())
        await self._resume_from_pause.wait()
        self.paused = False
        return True

    def unblock(self) -> None:
        """取消批跑时解除所有挂起，避免协程永久等待。"""
        if self.waiting:
            self.approve(skip=True)
        if self.paused:
            self.request_resume()


# =============================================================================
# 统计容器
# =============================================================================


@dataclass
class _BatchStats:
    """批跑/单 case 重复跑的累计统计。execution_success/judged/passed + 首轮响应耗时列表。"""

    execution_success: int = 0
    judged: int = 0
    passed: int = 0
    first_response_list: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.first_response_list is None:
            self.first_response_list = []

    def accumulate(self, outcome: VoiceCaseOutcome) -> None:
        """单 case 跑完后累加统计。repeat 和 batch 共用此逻辑。"""
        if outcome.execution_success:
            self.execution_success += 1
        if outcome.judge_status == JudgeStatus.COMPLETED:
            self.judged += 1
            if outcome.is_passed:
                self.passed += 1
        if outcome.first_response_ms is not None:
            self.first_response_list.append(outcome.first_response_ms)

    def build_done_event(
        self, *, total: int, enable_judge: bool, repeat_n: int = 1
    ) -> BatchDoneEvent:
        """构造批跑完成事件。repeat 和 batch 共用此逻辑。"""
        return BatchDoneEvent(
            total=total,
            execution_success=self.execution_success,
            enable_judge=enable_judge,
            judged=self.judged,
            # 未开启评测时没有"通过"这一业务含义，使用 None 而不是错误地记为 0。
            passed=self.passed if enable_judge else None,
            pass_rate=(self.passed / self.judged) if self.judged else None,
            repeat_n=repeat_n,
            avg_first_response_ms=(
                (sum(self.first_response_list) / len(self.first_response_list))
                if self.first_response_list
                else None
            ),
            first_response_sample_count=len(self.first_response_list),
        )


# =============================================================================
# 单 case 重复跑（只推事件，不入库）
# =============================================================================


async def run_voice_repeat(
    adapter,
    case,
    *,
    target,
    enable_judge: bool,
    repeat_n: int,
    session_config: VoiceAdapterConfig | None = None,
) -> None:
    """单 case 串行跑 N 遍：只推事件，不入库。复用 batch_* 事件方便前端展示。"""
    cfg = session_config or adapter_config
    total = repeat_n
    stats = _BatchStats()

    await adapter.push_event(
        BatchStartedEvent(
            dataset_id="single",
            dataset_name="单用例重复",
            total=total,
            enable_judge=enable_judge,
            batch_pace=BatchPace.AUTO,
            case_ids=[case.case_id],
            repeat_n=repeat_n,
        )
    )

    for repeat_index in range(1, repeat_n + 1):
        await adapter.push_event(
            BatchCaseStartedEvent(
                index=repeat_index,
                total=total,
                case_id=case.case_id,
                repeat_index=repeat_index,
                repeat_n=repeat_n,
            )
        )
        outcome = await run_test_session(
            adapter,
            case,
            target=target,
            enable_judge=enable_judge,
            session_config=cfg,
        )
        stats.accumulate(outcome)
        await adapter.push_event(
            BatchCaseResultEvent(
                index=repeat_index,
                total=total,
                case_id=case.case_id,
                execution_success=outcome.execution_success,
                execution_error=outcome.execution_error,
                judge_status=outcome.judge_status,
                is_passed=outcome.is_passed,
                reason=outcome.reason,
                repeat_index=repeat_index,
                repeat_n=repeat_n,
                first_response_ms=outcome.first_response_ms,
            )
        )
        if (
            repeat_index < total
            and isinstance(adapter, BrowserVoiceAdapter)
            and cfg.run_gap_wait_sec > 0
        ):
            await await_countdown_wait(adapter, cfg.run_gap_wait_sec, "等待下一条用例")

    await adapter.push_event(
        stats.build_done_event(total=total, enable_judge=enable_judge, repeat_n=repeat_n)
    )


# =============================================================================
# 批跑子函数
# =============================================================================


async def _record_skipped_batch_case(
    adapter: BrowserVoiceAdapter,
    task_run: TaskRunDoc,
    case,
    *,
    index: int,
    total: int,
    enable_judge: bool,
    repeat_index: int = 1,
    repeat_n: int = 1,
) -> None:
    """手动批跑跳过当前 case 的某一遍：落库并通知前端。"""
    from projects.mind.test_backend.api.voice_test.case_runner import VoiceCaseOutcome

    outcome = VoiceCaseOutcome(
        execution_success=False,
        execution_error="已跳过",
        judge_status=JudgeStatus.NOT_RUN,
    )
    await save_voice_case_result(
        task_run,
        case,
        outcome,
        repeat_index=repeat_index,
        repeat_n=repeat_n,
        slot=index,
    )
    await update_voice_task_run_progress(
        task_run,
        total=total,
        outcome=outcome,
        enable_judge=enable_judge,
    )
    await adapter.push_event(
        BatchCaseResultEvent(
            index=index,
            total=total,
            case_id=case.case_id,
            execution_success=False,
            execution_error="已跳过",
            judge_status=JudgeStatus.NOT_RUN,
            repeat_index=repeat_index,
            repeat_n=repeat_n,
        )
    )


async def _init_batch_task_run(
    *,
    dataset_id: str,
    dataset_oid: PydanticObjectId,
    dataset_name: str,
    total: int,
    enable_judge: bool,
    repeat_n: int,
    batch_pace: BatchPace,
    cfg: VoiceAdapterConfig,
    existing_task_run: TaskRunDoc | None,
) -> tuple[TaskDoc, TaskRunDoc, _BatchStats]:
    """创建新 task_run 或复用续跑的 task_run，返回 (task, task_run, stats)。

    续跑时从 metadata 恢复累计统计，避免只算续跑部分。
    """
    if existing_task_run is not None:
        # 续跑：复用已有 task_run
        task_run = existing_task_run
        task = await mdb_service.get_by_id(model=TaskDoc, doc_id=task_run.task_id)
        if task is None:
            raise RuntimeError(f"未找到 task: {task_run.task_id}")
        # 续跑：从已有 metadata 恢复累计统计，避免只算续跑部分
        prev_meta = task_run.metadata or {}
        stats = _BatchStats(
            execution_success=int(prev_meta.get("execution_success_num", 0)),
            judged=int(prev_meta.get("judged_case_num", 0)),
            passed=(
                int(prev_meta["passed_case_num"])
                if isinstance(prev_meta.get("passed_case_num"), (int, float))
                else 0
            ),
        )
        # 首轮响应耗时无法从 metadata 恢复（只存了统计值），续跑只算本轮
        return task, task_run, stats

    # 新批跑：创建 task 和 task_run
    task = await get_or_create_voice_task(dataset_oid, dataset_name)
    task_run = await create_voice_task_run(
        task,
        total=total,
        enable_judge=enable_judge,
        repeat_n=repeat_n,
    )
    # 写入批跑参数到 metadata，供续跑使用
    task_run.metadata = {
        **(task_run.metadata or {}),
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "enable_judge": enable_judge,
        "repeat_n": repeat_n,
        "batch_pace": str(batch_pace),
        "adapter_config": cfg.model_dump(mode="json") if cfg else None,
    }
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run.id, data=task_run)
    return task, task_run, _BatchStats()


async def _emit_batch_started_events(
    adapter: BrowserVoiceAdapter,
    *,
    dataset_id: str,
    dataset_name: str,
    total: int,
    enable_judge: bool,
    batch_pace: BatchPace,
    cases: list,
    repeat_n: int,
    task: TaskDoc,
    task_run: TaskRunDoc,
) -> None:
    """推 BatchStartedEvent + TaskRunCreatedEvent。"""
    await adapter.push_event(
        BatchStartedEvent(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            total=total,
            enable_judge=enable_judge,
            batch_pace=batch_pace,
            case_ids=[case.case_id for case in cases],
            repeat_n=repeat_n,
        )
    )
    if task.id is not None and task_run.id is not None:
        await adapter.push_event(
            TaskRunCreatedEvent(
                task_id=str(task.id),
                task_run_id=str(task_run.id),
            )
        )


async def _wait_before_case_or_pause(
    adapter: BrowserVoiceAdapter,
    *,
    slot: int,
    total: int,
    case,
    repeat_index: int,
    repeat_n: int,
    batch_pace: BatchPace,
    step_controller: BatchStepController | None,
    task_run: TaskRunDoc,
    enable_judge: bool,
) -> bool:
    """case 开始前的等待逻辑：MANUAL 等用户确认 + 暂停检查。

    返回 True 表示当前 case 应跳过（用户在 MANUAL 模式点了"跳过"）。
    """
    if batch_pace == BatchPace.MANUAL:
        if step_controller is None:
            raise RuntimeError("手动批跑缺少 step_controller")
        await adapter.push_event(
            BatchCaseWaitingEvent(
                index=slot,
                total=total,
                case_id=case.case_id,
                repeat_index=repeat_index,
                repeat_n=repeat_n,
            )
        )
        if await step_controller.wait_before_case():
            await _record_skipped_batch_case(
                adapter,
                task_run,
                case,
                index=slot,
                total=total,
                enable_judge=enable_judge,
                repeat_index=repeat_index,
                repeat_n=repeat_n,
            )
            return True

    # 暂停检查：当前 case 已跑完，下一个 case 开始前挂起
    if step_controller is not None:
        was_paused = await step_controller.wait_if_paused(
            adapter,
            lambda: BatchPausedEvent(completed=slot - 1, total=total),
        )
        if was_paused:
            await adapter.push_event(BatchResumedEvent())
    return False


async def _run_single_batch_case(
    adapter: BrowserVoiceAdapter,
    *,
    case,
    slot: int,
    total: int,
    repeat_index: int,
    repeat_n: int,
    enable_judge: bool,
    cfg: VoiceAdapterConfig,
    task_run: TaskRunDoc,
) -> VoiceCaseOutcome:
    """执行单个批跑 case：开始事件 → 跑对话 → 落库 → 更新进度 → 推结果事件。"""
    from projects.voice_test.adapter.browser_agent_catalog import VoiceTestTarget

    await adapter.push_event(
        BatchCaseStartedEvent(
            index=slot,
            total=total,
            case_id=case.case_id,
            repeat_index=repeat_index,
            repeat_n=repeat_n,
        )
    )
    outcome = await run_test_session(
        adapter,
        case,
        target=VoiceTestTarget.VOICE,
        enable_judge=enable_judge,
        session_config=cfg,
    )
    item_id = await save_voice_case_result(
        task_run,
        case,
        outcome,
        repeat_index=repeat_index,
        repeat_n=repeat_n,
        slot=slot,
    )
    await update_voice_task_run_progress(
        task_run,
        total=total,
        outcome=outcome,
        enable_judge=enable_judge,
        slot=slot,
        repeat_index=repeat_index,
        case_id=case.case_id,
    )
    await adapter.push_event(
        BatchCaseResultEvent(
            index=slot,
            total=total,
            case_id=case.case_id,
            execution_success=outcome.execution_success,
            execution_error=outcome.execution_error,
            judge_status=outcome.judge_status,
            is_passed=outcome.is_passed,
            reason=outcome.reason,
            repeat_index=repeat_index,
            repeat_n=repeat_n,
            first_response_ms=outcome.first_response_ms,
            task_run_item_id=str(item_id) if item_id else None,
        )
    )
    return outcome


async def _finalize_batch_on_exception(
    *,
    adapter: BrowserVoiceAdapter,
    session: VoiceWsSession | None,
    task_run: TaskRunDoc,
    stats: _BatchStats,
    exc: BaseException,
    is_cancelled: bool = False,
) -> None:
    """批跑异常分支统一处理：USER_STOP→FAILED，其余→PAUSED（可续跑）。

    - is_cancelled=True（CancelledError）：用户主动暂停/停止，消息简洁不带 exc
    - is_cancelled=False（Exception）：真异常，消息带 exc!r 方便排查
    - USER_STOP：用户主动放弃，标 FAILED
    - PAUSE/WS_DISCONNECT/系统崩溃：一律 PAUSED 可续跑
    - PAUSE 时 WS 还连着，额外推 BatchPausedEvent；WS_DISCONNECT 时 WS 已断，push 静默失败
    """
    is_user_stop = (
        session is not None and session.cancel_reason == CancelReason.USER_STOP
    )
    if is_user_stop:
        msg = "批量语音测试已停止" if is_cancelled else f"批量语音测试已停止: {exc!r}"
        await mark_voice_task_run_failed(task_run, msg)
        return

    msg = "批量语音测试已暂停" if is_cancelled else f"批量语音测试已暂停（异常: {exc!r}）"
    await mark_voice_task_run_paused(
        task_run,
        msg,
        execution_success=stats.execution_success,
        judged=stats.judged,
        passed=stats.passed,
    )
    # pause 时 WS 还连着，推 BatchPausedEvent 让前端更新 UI
    # ws_disconnect 时 WS 已断，push_event 会静默失败
    if session is not None and session.cancel_reason == CancelReason.PAUSE:
        try:
            completed = task_run.progress.completed if task_run.progress else 0
            total = task_run.progress.total if task_run.progress else 0
            await adapter.push_event(
                BatchPausedEvent(completed=completed, total=total)
            )
        except Exception as exc:
            _log.debug("push BatchPausedEvent failed (ws likely disconnected): %r", exc)


# =============================================================================
# 批跑主入口
# =============================================================================


async def run_voice_batch(
    adapter: BrowserVoiceAdapter,
    dataset_id: str,
    *,
    enable_judge: bool,
    batch_pace: BatchPace = BatchPace.AUTO,
    step_controller: BatchStepController | None = None,
    session_config: VoiceAdapterConfig | None = None,
    repeat_n: int = 1,
    session: VoiceWsSession | None = None,
    resume_from: int = 0,
    existing_task_run: TaskRunDoc | None = None,
) -> None:
    """在一个浏览器音频会话内串行运行数据集；每 case 可重复 N 遍并入库。

    resume_from: 续跑时跳过前 N 个 slot（从 0 开始计数）。
    existing_task_run: 续跑时传入已有的 TaskRunDoc，避免创建新记录。
    """
    cfg = session_config or adapter.config
    dataset_oid, dataset_name, cases = await load_dataset_cases(dataset_id)
    total = len(cases) * repeat_n

    task, task_run, stats = await _init_batch_task_run(
        dataset_id=dataset_id,
        dataset_oid=dataset_oid,
        dataset_name=dataset_name,
        total=total,
        enable_judge=enable_judge,
        repeat_n=repeat_n,
        batch_pace=batch_pace,
        cfg=cfg,
        existing_task_run=existing_task_run,
    )

    await _emit_batch_started_events(
        adapter,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        total=total,
        enable_judge=enable_judge,
        batch_pace=batch_pace,
        cases=cases,
        repeat_n=repeat_n,
        task=task,
        task_run=task_run,
    )

    # 外层轮次、内层 case：一轮跑完所有 case 再进下一轮，便于横向对比同一 case 多轮表现
    try:
        slot = 0
        for repeat_index in range(1, repeat_n + 1):
            for case in cases:
                slot += 1
                # 续跑：跳过已完成的 slot
                if slot <= resume_from:
                    continue
                if await _wait_before_case_or_pause(
                    adapter,
                    slot=slot,
                    total=total,
                    case=case,
                    repeat_index=repeat_index,
                    repeat_n=repeat_n,
                    batch_pace=batch_pace,
                    step_controller=step_controller,
                    task_run=task_run,
                    enable_judge=enable_judge,
                ):
                    continue

                outcome = await _run_single_batch_case(
                    adapter,
                    case=case,
                    slot=slot,
                    total=total,
                    repeat_index=repeat_index,
                    repeat_n=repeat_n,
                    enable_judge=enable_judge,
                    cfg=cfg,
                    task_run=task_run,
                )
                stats.accumulate(outcome)

                if (
                    slot < total
                    and batch_pace == BatchPace.AUTO
                    and cfg.run_gap_wait_sec > 0
                ):
                    await await_countdown_wait(
                        adapter, cfg.run_gap_wait_sec, "等待下一条用例"
                    )
    except asyncio.CancelledError as exc:
        await _finalize_batch_on_exception(
            adapter=adapter,
            session=session,
            task_run=task_run,
            stats=stats,
            exc=exc,
        )
        raise
    except Exception as exc:
        # cancel 过程中 finally 抛出的二次异常（如 release_s2s 网络错误）会覆盖 CancelledError，
        # 统一交由 _finalize_batch_on_exception 处理
        await _finalize_batch_on_exception(
            adapter=adapter,
            session=session,
            task_run=task_run,
            stats=stats,
            exc=exc,
        )
        raise

    await mark_voice_task_run_complete(
        task_run,
        total=total,
        execution_success=stats.execution_success,
        enable_judge=enable_judge,
        judged=stats.judged,
        passed=stats.passed,
        first_response_list=stats.first_response_list,
    )
    await adapter.push_event(
        stats.build_done_event(
            total=total, enable_judge=enable_judge, repeat_n=repeat_n
        )
    )
