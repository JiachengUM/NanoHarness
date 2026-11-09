"""独立流式 ASR 体验：收音 → 火山流式识别 → 文本事件回显。

与主测试 WS（/voice_test/session）完全隔离，独立于 VoiceWsSession / pump_outbound：
- 只依赖 StreamingAsrClient（projects/voice_test/core/asr_client.py）
- 建连即开 ASR 会话；前端二进制 PCM 直推；服务端 AsrEvent 序列化成 JSON 回显
- 收到 {"type":"stop"} 收尾（服务端输出最后一句 + asr_finished）后关闭
- 送给服务端的完整音频用 CaseAudioRecorder 录制，收尾时上传 TOS，下载 url 挂在 asr_finished 上回给前端审核播放

协议（前后端约定）：
- 入站 文本 {"type":"stop"}：结束本次识别
- 入站 二进制：16kHz/16bit/单声道 PCM，可任意分包（内部按 200ms 帧长切开补零；静默超时补静音帧保活）
- 出站 JSON：asr_started / asr_delta / asr_final / asr_finished / asr_error（asr_finished 可选带 audio_url）
"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.adapter.case_audio_recorder import CaseAudioRecorder
from projects.voice_test.core.asr_client import (
    AsrAudioConfig,
    AsrError,
    AsrFinal,
    AsrFinished,
    AsrRequestConfig,
    StreamingAsrClient,
    StreamingAsrConfig,
)

_log = get_vt_logger("asr_demo")

# 与浏览器采集一致：16kHz/16bit/单声道 PCM；200ms 一帧 = 16000*0.2*2 = 6400 字节
_SAMPLE_RATE = 16000
_FRAME_BYTES = 6400
# VAD 判停静音阈值(ms)：静音超过此值输出 definite 最终句
_VAD_TIMEOUT_MS = 1500
# 静音保活帧：长时间收不到前端数据时补发，维持 ASR 连接活跃与 VAD 判停节奏（与跑批补静音同理）
_SILENCE_FRAME = b"\x00" * _FRAME_BYTES
# 前端数据静默超时(sec)：超过该时长未收到音频，补发一帧静音保活（与跑批 _mic_loop 的 0.2s 对齐）
_PAD_TIMEOUT_SEC = 0.2
# stop 后等服务端收尾事件的最长等待，防止服务端不响应导致挂死
_FINISH_TIMEOUT_SEC = 8.0


async def _pump_asr_events(
    client: StreamingAsrClient,
    ws: WebSocket,
    recorder: CaseAudioRecorder,
) -> None:
    """把 StreamingAsrClient 的 AsrEvent 序列化成 JSON 推给前端；收尾时把录音 url 挂在 asr_finished 上。"""
    async for event in client.events():
        if isinstance(event, AsrFinal):
            _log.info("asr final text=%r", event.text)
        elif isinstance(event, AsrError):
            _log.error("asr error code=%s message=%r", event.code, event.message)
        payload = event.model_dump(mode="json")
        if isinstance(event, AsrFinished):
            # 收尾：把本次送给服务端的完整音频上传 TOS，供前端审核播放（同步 IO 放线程池，避免阻塞事件循环）
            _log.info("asr demo finished via pump")
            result = await asyncio.to_thread(recorder.finish)
            if result is not None:
                payload["audio_url"] = result.download_url
        await ws.send_json(payload)


def _split_frames(data: bytes) -> list[bytes]:
    """把入站 PCM 按 200ms 帧长切开（末帧不足补零），对齐服务端分包期望。"""
    if len(data) <= 0:
        return []
    frames: list[bytes] = []
    offset = 0
    while offset < len(data):
        piece = data[offset : offset + _FRAME_BYTES]
        offset += len(piece)
        if len(piece) < _FRAME_BYTES:
            piece = piece + b"\x00" * (_FRAME_BYTES - len(piece))
        frames.append(piece)
    return frames


async def run_asr_stream(ws: WebSocket) -> None:
    """一条 ASR 体验连接：建连即开识别，收 PCM 推流，stop 收尾关闭。"""
    await ws.accept()
    client = StreamingAsrClient(
        config=StreamingAsrConfig(
            audio=AsrAudioConfig(rate=_SAMPLE_RATE),
            request=AsrRequestConfig(end_window_size=_VAD_TIMEOUT_MS),
        ),
        log=_log,
    )
    try:
        await client.open()
    except Exception as exc:
        _log.error("asr demo open failed: %r", exc)
        try:
            await ws.send_json(
                {"type": "asr_error", "code": -1, "message": f"打开 ASR 连接失败: {exc!r}"}
            )
        except (WebSocketDisconnect, RuntimeError):
            pass
        await ws.close()
        return

    # 录制本次送给服务端的完整音频，收尾时上传 TOS 供前端审核播放
    recorder = CaseAudioRecorder.begin(log=_log)
    pump_task = asyncio.create_task(_pump_asr_events(client, ws, recorder))
    try:
        while True:
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=_PAD_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                # 长时间没数据：补一帧静音保活（维持连接活跃 + VAD 判停节奏），不写入录音
                try:
                    await client.send_audio(_SILENCE_FRAME)
                except Exception:
                    break
                continue
            if message.get("type") == "websocket.disconnect":
                break
            bytes_data = message.get("bytes")
            if bytes_data is not None:
                for frame in _split_frames(bytes_data):
                    try:
                        await client.send_audio(frame)
                    except Exception:
                        break
                    recorder.write_mic(frame)
                continue
            text = message.get("text")
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                continue
            if parsed.get("type") == "stop":
                await client.finish()
                # 等 pump 发完服务端收尾事件（最后一句 + asr_finished），防止前端收不到
                try:
                    await asyncio.wait_for(pump_task, timeout=_FINISH_TIMEOUT_SEC)
                except asyncio.TimeoutError:
                    _log.warning("asr demo finish wait timeout, force close")
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        pump_task.cancel()
        await asyncio.gather(pump_task, return_exceptions=True)
        # 兜底：服务端未产出 asr_finished（不回 is_last / 提前断连）时，
        # 仍上传音频并补发一个带 audio_url 的收尾事件，保证前端能审核播放
        if recorder.active:
            result = await asyncio.to_thread(recorder.finish)
            if result is not None and ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_json({"type": "asr_finished", "audio_url": result.download_url})
                except Exception as exc:
                    _log.warning("asr demo fallback send finished failed: %r", exc)
        try:
            await client.close()
        except Exception:
            pass
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close()
