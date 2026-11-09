"""WebSocket 入站消息分发与处理。

从 voice_test_api.py 拆分。包含：
- _parse_ws_run_params
- _handle_ws_start / _handle_ws_start_batch / _handle_ws_batch_step
- _handle_ws_resume_confirm / _resume_voice_batch
- _dispatch_ws_inbound / _summarize_inbound
"""

from __future__ import annotations

import asyncio
from typing import assert_never

from beanie import PydanticObjectId
from pydantic import ValidationError

from projects.mind.test_backend.enums.task import TaskRunStatus
from projects.mind.test_backend.mdb_models.task import TaskRunDoc
from projects.mind.test_backend.repositories import mdb_service
from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.adapter.browser_agent_catalog import (
    is_voice_target,
)
from projects.voice_test.schemas.browser_schemas import (
    BatchPace,
    BatchResumedEvent,
    OutMessage,
    VoiceTestWsRunParams,
    WsControlMessage,
    WsResumeConfirmMessage,
    WsStartBatchMessage,
    WsStartMessage,
    parse_browser_ws_inbound,
)
from projects.voice_test.config.adapter_config import (
    VoiceAdapterConfig,
    adapter_config,
    resolve_adapter_config,
)

from projects.mind.test_backend.api.voice_test.batch_runner import (
    BatchStepController,
    CancelReason,
    run_voice_batch,
    run_voice_repeat,
)
from projects.mind.test_backend.api.voice_test.case_runner import (
    VoiceRunParams,
    run_test_session,
)
from projects.mind.test_backend.api.voice_test.persistence import (
    cleanup_orphan_task_run_items,
)
from projects.mind.test_backend.api.voice_test.ws_session import (
    VoiceWsSession,
    push_ws_error,
)

_log = get_vt_logger("ws_handlers")


async def _parse_ws_run_params(
    out_queue: asyncio.Queue[OutMessage],
    msg: VoiceTestWsRunParams,
) -> VoiceRunParams | None:
    """解析运行参数；失败时已向客户端回错误，返回 None。"""
    try:
        return VoiceRunParams(
            session_config=resolve_adapter_config(msg.adapter_config),
            enable_judge=msg.enable_judge,
            target=msg.agent_type,
        )
    except ValidationError as exc:
        await push_ws_error(out_queue, f"运行参数无效: {exc}")
        return None


async def _handle_ws_start(session: VoiceWsSession, msg: WsStartMessage) -> None:
    if await session.reject_if_busy():
        return
    run_params = await _parse_ws_run_params(session.out_queue, msg)
    if run_params is None:
        return
    adapter = session.adapter_for(run_params.test_mode)
    if msg.repeat_n > 1:
        session.start_run(
            run_voice_repeat(
                adapter,
                msg.case,
                target=run_params.target,
                enable_judge=run_params.enable_judge,
                repeat_n=msg.repeat_n,
                session_config=run_params.session_config,
            ),
            session_config=run_params.session_config,
            test_mode=run_params.test_mode,
        )
        return
    session.start_run(
        run_test_session(
            adapter,
            msg.case,
            target=run_params.target,
            enable_judge=run_params.enable_judge,
            session_config=run_params.session_config,
        ),
        session_config=run_params.session_config,
        test_mode=run_params.test_mode,
    )


async def _handle_ws_start_batch(
    session: VoiceWsSession, msg: WsStartBatchMessage
) -> None:
    if await session.reject_if_busy():
        return
    run_params = await _parse_ws_run_params(session.out_queue, msg)
    if run_params is None:
        return
    if not is_voice_target(run_params.target):
        await session.send_error("不支持批量")
        return

    step_controller = BatchStepController()
    session.batch_step = step_controller
    session.start_run(
        run_voice_batch(
            session.voice_adapter,
            msg.dataset_id,
            enable_judge=run_params.enable_judge,
            batch_pace=msg.batch_pace,
            step_controller=step_controller,
            session_config=run_params.session_config,
            repeat_n=msg.repeat_n,
            session=session,
        ),
        session_config=run_params.session_config,
        test_mode="voice",
    )


async def _handle_ws_batch_step(
    session: VoiceWsSession,
    *,
    skip: bool,
) -> None:
    if session.batch_step is None or not session.batch_step.waiting:
        await session.send_error("当前没有等待确认的用例")
        return
    session.batch_step.approve(skip=skip)


async def _handle_ws_resume_confirm(
    session: VoiceWsSession,
    msg: WsResumeConfirmMessage,
) -> None:
    """处理续跑确认：从断点续跑 PAUSED 状态的 task_run。"""
    if session.busy():
        await session.send_error("当前有任务正在运行")
        return
    try:
        task_run_id = PydanticObjectId(msg.task_run_id)
    except Exception:
        await session.send_error(f"无效的 task_run_id: {msg.task_run_id}")
        return
    task_run = await mdb_service.get_by_id(model=TaskRunDoc, doc_id=task_run_id)
    if task_run is None:
        await session.send_error(f"未找到 task_run: {msg.task_run_id}")
        return
    if task_run.status != TaskRunStatus.PAUSED:
        await session.send_error(f"task_run 状态为 {task_run.status}，无法续跑")
        return

    # 清理孤儿记录（仅 slot > completed），从断点续跑
    resume_from = task_run.progress.completed if task_run.progress else 0
    await cleanup_orphan_task_run_items(task_run_id, resume_from=resume_from)
    # 恢复状态为 RUNNING
    task_run.status = TaskRunStatus.RUNNING
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run_id, data=task_run)
    # 推送 BatchResumedEvent，让前端清除 batchPaused 状态、恢复"暂停"按钮
    completed = task_run.progress.completed if task_run.progress else 0
    total = task_run.progress.total if task_run.progress else 0
    await session.out_queue.put(
        BatchResumedEvent(completed=completed, total=total)
    )
    # 从断点续跑（从 progress.completed 处继续）
    await _resume_voice_batch(session, task_run)


async def _resume_voice_batch(session: VoiceWsSession, task_run: TaskRunDoc) -> None:
    """从断点续跑批跑任务。

    加载 dataset，跳过 progress.completed 个 slot，从断点处重跑。
    """
    if task_run.progress is None:
        await session.send_error("task_run 缺少 progress，无法续跑")
        return
    if task_run.id is None:
        await session.send_error("task_run 缺少 id")
        return

    # 从 metadata 获取批跑参数
    metadata = task_run.metadata or {}
    dataset_id = metadata.get("dataset_id")
    enable_judge = metadata.get("enable_judge", False)
    repeat_n = metadata.get("repeat_n", 1)
    batch_pace_str = metadata.get("batch_pace", BatchPace.AUTO)
    batch_pace = BatchPace(batch_pace_str) if isinstance(batch_pace_str, str) else BatchPace.AUTO

    if not dataset_id:
        await session.send_error("task_run metadata 缺少 dataset_id，无法续跑")
        return

    # 解析 adapter 配置
    adapter_config_dict = metadata.get("adapter_config")
    if adapter_config_dict:
        try:
            session_config = resolve_adapter_config(adapter_config_dict)
        except Exception as exc:
            _log.warning("resolve adapter_config failed, fallback to default: %r", exc)
            session_config = adapter_config
    else:
        session_config = adapter_config

    step_controller = BatchStepController()
    session.batch_step = step_controller
    completed = task_run.progress.completed
    session.start_run(
        run_voice_batch(
            session.voice_adapter,
            dataset_id,
            enable_judge=enable_judge,
            batch_pace=batch_pace,
            step_controller=step_controller,
            session_config=session_config,
            repeat_n=repeat_n,
            session=session,
            resume_from=completed,
            existing_task_run=task_run,
        ),
        session_config=session_config,
        test_mode="voice",
    )


async def dispatch_ws_inbound(session: VoiceWsSession, data: object) -> bool:
    """解析并分发入站 JSON。返回 True 表示应结束 WebSocket 循环（stop）。"""
    try:
        msg = parse_browser_ws_inbound(data)
    except ValidationError as exc:
        await session.send_error(f"参数无效: {exc}")
        return False

    # 入站业务消息摘要（音频帧走 bytes 通道，不在这里）
    _inbound_summary = _summarize_inbound(msg)
    if _inbound_summary:
        session.voice_adapter._log.info("ws recv %s", _inbound_summary)

    match msg:
        case WsStartMessage():
            await _handle_ws_start(session, msg)
        case WsStartBatchMessage():
            await _handle_ws_start_batch(session, msg)
        case WsControlMessage():
            match msg.type:
                case "next_case":
                    await _handle_ws_batch_step(session, skip=False)
                case "skip_case":
                    await _handle_ws_batch_step(session, skip=True)
                case "stop":
                    await session.cancel_run(reason=CancelReason.USER_STOP)
                    return True
                case "playback_drained":
                    if session.test_mode == "voice":
                        session.voice_adapter.on_playback_drained()
                case "pause":
                    # 立即中断当前 case（无结果写入），标 PAUSED；resume 由阶段 1 续跑
                    await session.cancel_run(reason=CancelReason.PAUSE)
                case _ as unreachable:
                    assert_never(unreachable)
        case WsResumeConfirmMessage():
            await _handle_ws_resume_confirm(session, msg)
        case _ as unreachable:
            assert_never(unreachable)
    return False


def _summarize_inbound(msg: object) -> str:
    """入站业务消息摘要（不含音频），用于全链路日志。"""
    match msg:
        case WsStartMessage():
            return f"start agent={msg.agent_type}"
        case WsStartBatchMessage():
            return f"start_batch dataset={msg.dataset_id} repeat={msg.repeat_n}"
        case WsControlMessage():
            return f"control type={msg.type}"
        case WsResumeConfirmMessage():
            return f"resume_confirm task_run_id={msg.task_run_id} action={msg.action}"
        case _:
            return ""
