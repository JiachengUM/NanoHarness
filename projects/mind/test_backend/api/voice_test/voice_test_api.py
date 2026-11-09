"""浏览器语音/文本测试：HTTP 路由 + WebSocket endpoint（薄层）。

业务逻辑已拆分到：
- case_runner.py：单 case 编排（prepare → dialogues → judge → outcome）
- batch_runner.py：批跑编排（数据集串行 + 单 case 重复）
- persistence.py：DB 落库（task_run CRUD + case result save）
- ws_session.py：VoiceWsSession + pump_outbound（出站推送）
- ws_handlers.py：WS 入站消息分发与处理

本文件只保留：
- HTTP 路由（health, adapter_config, agent_options, tts, download, task_run 查询）
- WebSocket endpoint（voice_test_session）：接收消息 → 分发 → 推送
"""

from __future__ import annotations

import asyncio
import json
import time

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.responses import Response
from starlette.websockets import WebSocketState

from projects.mind.test_backend.enums.task import TaskRunStatus
from projects.mind.test_backend.mdb_models.task import TaskRunDoc
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.response import ApiResponse, ok
from projects.voice_test.adapter._logger import (
    get_vt_logger,
    new_session_id,
)
from projects.voice_test.schemas.browser_schemas import (
    LogEvent,
    OutMessage,
    TtsSynthesizeRequest,
    VoiceTestHealthData,
)
from projects.voice_test.adapter.browser_text_adapter import BrowserTextAdapter
from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.adapter.browser_agent_catalog import (
    voice_test_agent_options_payload,
)
from projects.voice_test.config.adapter_config import (
    VoiceAdapterConfig,
    adapter_config,
    resolve_http_tts_speaker,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.voice_test.core.tts_client import synthesize_playback_f32le
from projects.voice_test.scripts.local_recorder_bundle import build_local_recorder_zip

from projects.mind.test_backend.api.voice_test.asr_demo import run_asr_stream
from projects.mind.test_backend.api.voice_test.batch_runner import CancelReason
from projects.mind.test_backend.api.voice_test.ws_handlers import dispatch_ws_inbound
from projects.mind.test_backend.api.voice_test.ws_session import (
    VoiceWsSession,
    pump_outbound,
)

_log = get_vt_logger("ws")

router = APIRouter(
    prefix="/voice_test",
    tags=["Voice Test"],
)

# WS 接收超时：前端 ping 间隔 10s，连续 3 次（~30s）无任何消息视为断开
# 覆盖 pump 盲区（MANUAL 等下一题/run_gap_wait=0 时队列空，pump 不调 send 无法感知断网）
_WS_RECV_TIMEOUT_SEC = 35.0
# remaining 下限 1s，避免极小值导致 asyncio.wait 空转
_WS_RECV_REMAINING_MIN_SEC = 1.0


# =============================================================================
# WebSocket endpoint
# =============================================================================


@router.websocket("/session")
async def voice_test_session(ws: WebSocket) -> None:
    await ws.accept()
    session_id = new_session_id()
    event_queue: asyncio.Queue[OutMessage] = asyncio.Queue()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    voice_adapter = BrowserVoiceAdapter()
    voice_adapter.out_queue = event_queue
    voice_adapter.set_sid(session_id)
    # ws 级日志复用 adapter 的 logger，自动带 [sid=xxx] 前缀
    wlog = voice_adapter._log
    wlog.info("ws connect")
    # 立即把 sid 推到前端，前端断线后可凭此 id 在 llm.log 中查全链路日志
    await event_queue.put(LogEvent(message=f"[sid={session_id}] session connected"))
    voice_adapter.audio_out_queue = audio_queue
    text_adapter = BrowserTextAdapter(out_queue=event_queue)
    session = VoiceWsSession(
        ws=ws,
        out_queue=event_queue,
        voice_adapter=voice_adapter,
        text_adapter=text_adapter,
    )
    session._vt_sid = session_id  # type: ignore[attr-defined]
    stopped = asyncio.Event()
    pump_exited = asyncio.Event()
    pump_task = asyncio.create_task(
        pump_outbound(event_queue, audio_queue, ws, stopped, pump_exited)
    )

    try:
        last_recv_time = time.monotonic()
        while not pump_exited.is_set():
            # 同时等待 WS 消息和 pump 退出；pump 退出（send 失败）即视为断连
            receive_task = asyncio.create_task(ws.receive())
            # 剩余等待时间 = 超时阈值 - 距上次收到消息的时长，下限 1s 避免极小值空转
            remaining = max(_WS_RECV_REMAINING_MIN_SEC, _WS_RECV_TIMEOUT_SEC - (time.monotonic() - last_recv_time))
            pump_wait_task = asyncio.create_task(pump_exited.wait())
            done, pending = await asyncio.wait(
                [receive_task, pump_wait_task],
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            # 清理本轮未完成的任务，避免协程泄漏
            for task in pending:
                task.cancel()
            if pump_exited.is_set():
                break
            if receive_task in done:
                message = receive_task.result()
            else:
                # timeout 触发且 receive_task 未完成：检查是否真的超过接收超时
                if time.monotonic() - last_recv_time >= _WS_RECV_TIMEOUT_SEC:
                    wlog.warning(
                        "ws recv timeout %.0fs no message, treat as disconnected",
                        _WS_RECV_TIMEOUT_SEC,
                    )
                    break
                continue

            if message.get("type") == "websocket.disconnect":
                wlog.info("ws disconnect")
                break

            # 收到任意消息（ping/业务/音频）刷新接收时间，重置超时计时
            last_recv_time = time.monotonic()

            text_data = message.get("text")
            if text_data is not None:
                parsed = json.loads(text_data)
                # 应用层 ping/pong：主循环空闲，直接 ws.send_json 秒回 pong
                # 不走 event_queue，避免与业务事件排队、保证 pong 响应延迟 <50ms
                if isinstance(parsed, dict) and parsed.get("type") == "ping":
                    wlog.debug("recv ping ts=%s", parsed.get("ts"))
                    try:
                        await ws.send_json({"type": "pong", "ts": parsed.get("ts")})
                    except (WebSocketDisconnect, RuntimeError):
                        break
                    continue
                if await dispatch_ws_inbound(session, parsed):
                    break
                continue

            bytes_data = message.get("bytes")
            if bytes_data is not None and session.test_mode == "voice":
                await session.voice_adapter.feed_mic(bytes_data)

    except WebSocketDisconnect:
        wlog.info("ws WebSocketDisconnect")
    finally:
        stopped.set()
        wlog.info("ws finally: cancel_run reason=WS_DISCONNECT busy=%s", session.busy())
        await session.cancel_run(reason=CancelReason.WS_DISCONNECT)
        await session.voice_adapter.close()
        await session.text_adapter.close()
        pump_task.cancel()
        await asyncio.gather(pump_task, return_exceptions=True)
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close()
        wlog.info("ws closed")


@router.websocket("/asr_stream")
async def asr_stream(ws: WebSocket) -> None:
    """独立流式 ASR 体验：收音 → 火山 ASR → 文本事件回显（与主测试 WS 隔离）。

    协议见 asr_demo.run_asr_stream：建连即开识别，二进制 PCM 直推，
    {"type":"stop"} 收尾后关闭。不含 Task 执行/评测等业务逻辑。
    """
    await run_asr_stream(ws)


# =============================================================================
# HTTP 路由
# =============================================================================


@router.get("/health", response_model=ApiResponse[VoiceTestHealthData])
async def voice_test_health() -> ApiResponse[VoiceTestHealthData]:
    """探测 Voice Test API 是否可用：核心 schema 可校验、适配层配置可读。"""
    TestCase.model_validate(
        {
            "id": "health_probe",
            "case_id": "health_probe",
            "context_config": {},
            "user_query_lists": [[{"role": "user", "content": "ping"}]],
            "nl_assertion": ["health check"],
            "max_round": 1,
        }
    )
    VoiceAdapterConfig.model_validate(adapter_config.model_dump())
    return ok(VoiceTestHealthData())


@router.get("/adapter_config", response_model=ApiResponse[dict])
async def get_adapter_config() -> ApiResponse[dict]:
    """返回语音适配层默认配置（VoiceAdapterConfig schema）。"""
    return ok(adapter_config.model_dump(mode="json"))


@router.get("/local_recorder/download")
async def download_local_recorder_bundle() -> Response:
    """下载本地记录工具压缩包（local_recorder.py + test + README）。"""
    payload = build_local_recorder_zip()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="voice_local_recorder.zip"'
        },
    )


@router.get("/agent_options", response_model=ApiResponse[list[dict]])
async def get_voice_test_agent_options() -> ApiResponse[list[dict]]:
    """返回 voice-test 页面可选的被测 Agent 列表（含默认语音链路）。"""
    return ok(voice_test_agent_options_payload())


@router.get("/paused_runs", response_model=ApiResponse[list[dict]])
async def list_paused_voice_test_runs() -> ApiResponse[list[dict]]:
    """查询最近 PAUSED 状态的 voice 测试 task_run（按更新时间倒序，最多 10 条）。

    供前端页面加载时 HTTP 查询，弹"恢复未完成任务"通知；避免 WS 查询的副作用。
    过滤规则（任一不满足即排除）：
    - status == PAUSED
    - metadata 含 dataset_id（续跑必备字段）
    - progress 存在 且 completed < total（排除"暂停但已跑完"的脏数据）
    """
    paused_runs = await mdb_service.get_list(
        model=TaskRunDoc,
        query={"status": TaskRunStatus.PAUSED},
        sort="-updated_time",
    )
    runs = []
    for r in paused_runs[:10]:
        metadata = r.metadata or {}
        if not metadata.get("dataset_id"):
            continue
        # 排除"已跑完但状态错为 PAUSED"的脏数据
        if r.progress is None or r.progress.completed >= r.progress.total:
            continue
        runs.append({
            "task_run_id": str(r.id),
            "task_id": str(r.task_id) if r.task_id else None,
            "progress": r.progress.model_dump() if r.progress else None,
            "metadata": r.metadata,
            "updated_time": r.updated_time.isoformat() if r.updated_time else None,
        })
    return ok(runs)


@router.get("/task_run/{task_run_id}", response_model=ApiResponse[dict])
async def get_voice_test_task_run(task_run_id: str) -> ApiResponse[dict]:
    """查询单个 task_run 的状态/进度/metadata，供前端恢复前校验是否可续跑。

    - 404：task_run 不存在
    - 200：返回状态信息和 resumable 标志，前端按 resumable 判断是否继续恢复流程
    - resumable=True：status=PAUSED 且 metadata 含 dataset_id（续跑必备）
    """
    try:
        doc_id = PydanticObjectId(task_run_id)
    except Exception:
        raise HTTPException(status_code=404, detail="无效的 task_run_id")
    task_run = await mdb_service.get_by_id(model=TaskRunDoc, doc_id=doc_id)
    if task_run is None:
        raise HTTPException(status_code=404, detail="未找到 task_run")
    metadata = task_run.metadata or {}
    # 可恢复：status=PAUSED + metadata 有 dataset_id + progress 未跑完
    progress = task_run.progress
    resumable = (
        task_run.status == TaskRunStatus.PAUSED
        and bool(metadata.get("dataset_id"))
        and progress is not None
        and progress.completed < progress.total
    )
    return ok(
        {
            "task_run_id": str(task_run.id),
            "status": task_run.status,
            "progress": task_run.progress.model_dump() if task_run.progress else None,
            "metadata": task_run.metadata,
            "updated_time": task_run.updated_time.isoformat() if task_run.updated_time else None,
            "resumable": resumable,
        }
    )


@router.post("/tts")
async def synthesize_tts_audio(body: TtsSynthesizeRequest) -> Response:
    """按需 TTS：text + voice(male/female)，返回 24kHz f32le mono。"""
    speaker = resolve_http_tts_speaker(body.voice)
    try:
        playback = await asyncio.to_thread(
            synthesize_playback_f32le,
            body.text,
            speaker,
        )
    except RuntimeError as exc:
        return Response(status_code=502, content=str(exc))
    if not playback:
        return Response(status_code=500, content="TTS 未生成音频")
    return Response(content=playback, media_type="application/octet-stream")
