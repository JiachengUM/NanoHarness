"""火山引擎大模型流式 TTS（单向流式 V3）WebSocket 客户端（完全独立，不依赖 S2S 链路）。

接口：wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream
协议：火山二进制帧（header + 可选 seq/event + session_id + payload_size + payload）
     本模块自实现协议常量与解析，不依赖 projects.voice_test.core.protocol / config

核心流程（无 StartConnection/StartSession 握手）：
1. open(text)  建 WS → 发 SendText（Full-client request，无 event，payload={user, req_params}）
2. events()    异步迭代服务端事件：TtsAudioChunk（PCM） / TtsFinished / TtsError
3. close()     发 FinishConnection（event=2）→ 关 WS

使用示例（一次性合成）：
    client = StreamingTtsClient()
    pcm_bytes = await client.synthesize("你好，今天天气真好。")
    await client.close()

使用示例（流式播放）：
    client = StreamingTtsClient()
    await client.open(text="你好，今天天气真好。")
    async for event in client.events():
        match event:
            case TtsAudioChunk(data=pcm):  play(pcm)
            case TtsFinished():            break
    await client.close()
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import sys
import uuid
from typing import Any, AsyncIterator, Literal, Union

import websockets
from pydantic import BaseModel, ConfigDict, Field
from websockets.asyncio.client import ClientConnection

# ---------------------------------------------------------------------------
# 日志（独立挂 StreamHandler，不落盘，避免 llm.log 无限增长）
# ---------------------------------------------------------------------------

_LOG_FMT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_log = logging.getLogger("vt.streaming_tts")
if not _log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter(_LOG_FMT, datefmt=_DATEFMT))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False


# ===========================================================================
# 协议常量（火山二进制帧，自实现，不依赖 S2S 的 protocol.py）
# ===========================================================================

# Message Type
_CLIENT_FULL_REQUEST = 0b0001
_CLIENT_AUDIO_ONLY_REQUEST = 0b0010
_SERVER_FULL_RESPONSE = 0b1001
_SERVER_ACK = 0b1011
_SERVER_ERROR_RESPONSE = 0b1111

# Message Type Specific Flags
_NO_SEQUENCE = 0b0000
_POS_SEQUENCE = 0b0001
_NEG_SEQUENCE = 0b0010
_NEG_SEQUENCE_1 = 0b0011
_MSG_WITH_EVENT = 0b0100

# Message Serialization
_NO_SERIALIZATION = 0b0000
_JSON = 0b0001

# Message Compression
_NO_COMPRESSION = 0b0000
_GZIP = 0b0001


def _generate_header(
    message_type: int = _CLIENT_FULL_REQUEST,
    flags: int = _NO_SEQUENCE,
    serial: int = _JSON,
    compression: int = _GZIP,
) -> bytes:
    """生成 4 字节协议头。"""
    header = bytearray()
    header.append((0b0001 << 4) | 0b0001)  # version=1, header_size=1
    header.append((message_type << 4) | flags)
    header.append((serial << 4) | compression)
    header.append(0x00)  # reserved
    return bytes(header)


def _parse_response(raw: bytes) -> dict[str, Any]:
    """解析服务端二进制帧。

    TTS 单向流式协议：服务端响应帧带 session_id（与 ASR 不同）。
    帧格式：
    - header(4) + [optional seq(4)] + [optional event(4)] + session_id_size(4) + session_id + payload_size(4) + payload
    """
    if isinstance(raw, str):
        return {}
    header_size = raw[0] & 0x0f
    message_type = raw[1] >> 4
    flags = raw[1] & 0x0f
    serial_method = raw[2] >> 4
    compression = raw[2] & 0x0f

    payload = raw[header_size * 4:]
    result: dict[str, Any] = {}
    payload_msg: Any = None
    payload_size = 0
    start = 0

    if message_type in (_SERVER_FULL_RESPONSE, _SERVER_ACK):
        result["message_type"] = "SERVER_FULL_RESPONSE" if message_type == _SERVER_FULL_RESPONSE else "SERVER_ACK"
        if flags & _NEG_SEQUENCE:
            result["seq"] = int.from_bytes(payload[:4], "big", signed=False)
            start += 4
        if flags & _MSG_WITH_EVENT:
            result["event"] = int.from_bytes(payload[:4], "big", signed=False)
            start += 4
        payload = payload[start:]
        # TTS 响应带 session_id
        session_id_size = int.from_bytes(payload[:4], "big", signed=True)
        session_id = payload[4:session_id_size + 4]
        result["session_id"] = str(session_id)
        payload = payload[4 + session_id_size:]
        payload_size = int.from_bytes(payload[:4], "big", signed=False)
        payload_msg = payload[4:4 + payload_size]
    elif message_type == _SERVER_ERROR_RESPONSE:
        result["message_type"] = "SERVER_ERROR_RESPONSE"
        result["code"] = int.from_bytes(payload[:4], "big", signed=False)
        payload_size = int.from_bytes(payload[4:8], "big", signed=False)
        payload_msg = payload[8:8 + payload_size]
    else:
        result["message_type"] = "UNKNOWN"
        return result

    if payload_msg is None:
        return result

    # 解压
    if compression == _GZIP:
        payload_msg = gzip.decompress(payload_msg)

    # 反序列化
    if serial_method == _JSON:
        payload_msg = json.loads(payload_msg.decode("utf-8"))
    elif serial_method != _NO_SERIALIZATION:
        payload_msg = payload_msg.decode("utf-8")

    result["payload_msg"] = payload_msg
    result["payload_size"] = payload_size
    return result


# ===========================================================================
# 配置（BaseModel，默认值内置，不依赖 config.py）
# ===========================================================================

# 默认音频参数（24kHz/16bit/单声道 PCM，TTS 输出）
_DEFAULT_SAMPLE_RATE = 24000
_DEFAULT_FORMAT = "pcm"
_DEFAULT_LOUDNESS = 50
_DEFAULT_SPEAKER = "zh_female_vv_uranus_bigtts"  # seed-tts-2.0 用 uranus 系列

# TTS 用的账号（与 S2S 同一账号，复用 ws_connect_config 的鉴权信息）
# 旧版控制台鉴权：X-Api-App-Key = APP ID, X-Api-Access-Key = Access Token
_DEFAULT_APP_KEY = "7620217375"
_DEFAULT_ACCESS_KEY = "REDACTED"

# 服务地址与资源
_DEFAULT_URL = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
_DEFAULT_RESOURCE_ID = "seed-tts-2.0"

# FinishConnection event 码（单向流式唯一的客户端上行 event）
_TTS_EVENT_FINISH_CONNECTION = 2

# TTS 单向流式服务端事件码
_TTS_EVENT_TTS_SENTENCE_START = 350
_TTS_EVENT_TTS_RESPONSE = 352
_TTS_EVENT_TTS_SENTENCE_END = 351
_TTS_EVENT_SESSION_FINISHED = 152
_TTS_EVENT_CONNECTION_FINISHED = 52


class StreamingTtsConfig(BaseModel):
    """流式 TTS 客户端配置。"""

    model_config = ConfigDict(protected_namespaces=())

    url: str = _DEFAULT_URL
    resource_id: str = _DEFAULT_RESOURCE_ID
    # 音色（seed-tts-2.0 用 uranus 系列；jupiter 是 S2S-Omni 专用）
    speaker: str = _DEFAULT_SPEAKER
    # 音频格式
    format: str = _DEFAULT_FORMAT
    sample_rate: int = _DEFAULT_SAMPLE_RATE
    # 语速/音量（默认 0=不变）
    speech_rate: int = 0
    loudness_rate: int = _DEFAULT_LOUDNESS
    # 鉴权覆盖（默认用 TTS 专用账号）
    app_key: str | None = None
    access_key: str | None = None
    connect_id: str | None = None
    # 会话超时（秒）—— 等首个服务端响应的最长时间
    session_timeout: float = 30.0


def _build_headers(config: StreamingTtsConfig) -> dict[str, str]:
    """鉴权头（旧版控制台：X-Api-App-Key + X-Api-Access-Key + X-Api-Resource-Id + X-Api-Connect-Id）。"""
    return {
        "X-Api-App-Key": config.app_key or _DEFAULT_APP_KEY,
        "X-Api-Access-Key": config.access_key or _DEFAULT_ACCESS_KEY,
        "X-Api-Resource-Id": config.resource_id,
        "X-Api-Connect-Id": config.connect_id or str(uuid.uuid4()),
    }


def _build_send_text_payload(text: str, config: StreamingTtsConfig) -> dict[str, Any]:
    """SendText 的 JSON payload：user + req_params（含完整 text/speaker/audio_params）。"""
    return {
        "user": {"uid": f"tts-{uuid.uuid4().hex[:8]}"},
        "req_params": {
            "text": text,
            "speaker": config.speaker,
            "audio_params": {
                "format": config.format,
                "sample_rate": config.sample_rate,
                "speech_rate": config.speech_rate,
                "loudness_rate": config.loudness_rate,
                "enable_timestamp": False,
            },
            "additions": json.dumps(
                {
                    "explicit_language": "zh",
                    "disable_markdown_filter": True,
                },
                ensure_ascii=False,
            ),
        },
    }


# ===========================================================================
# 服务端事件模型（已脱离传输层）
# ===========================================================================


class TtsStarted(BaseModel):
    """收到首个服务端响应（TTSSentenceStart），合成已开始。"""
    type: Literal["tts_started"] = "tts_started"


class TtsAudioChunk(BaseModel):
    """一包 PCM 音频数据（int16 或 f32le，由配置决定）。"""
    type: Literal["tts_audio"] = "tts_audio"
    data: bytes


class TtsFinished(BaseModel):
    """合成全部结束（收到 SessionFinished）。"""
    type: Literal["tts_finished"] = "tts_finished"


class TtsError(BaseModel):
    """服务端错误。"""
    type: Literal["tts_error"] = "tts_error"
    code: int
    message: str


TtsEvent = Union[TtsStarted, TtsAudioChunk, TtsFinished, TtsError]


# ===========================================================================
# 事件解析 helper
# ===========================================================================


def _parse_event(data: dict[str, Any]) -> TtsEvent | None:
    """把 _parse_response 的结果转成 TtsEvent。

    返回 None 表示该事件可被业务忽略（如 TTSSentenceEnd）。

    - 二进制音频帧（SERVER_ACK + bytes payload，event=352）→ TtsAudioChunk
    - JSON 事件帧（SERVER_FULL_RESPONSE）→ 按事件码映射
    - 错误帧（SERVER_ERROR_RESPONSE）→ TtsError

    注意：_parse_response 在 SERVER_ERROR_RESPONSE 分支不设 message_type 字段，
    但会设 code 字段，所以用 code 字段存在性作为错误帧的判据。
    """
    message_type = data.get("message_type")
    raw = data.get("payload_msg")
    event_code = data.get("event")

    # 错误帧
    if message_type == "SERVER_ERROR_RESPONSE" or "code" in data:
        code = int(data.get("code", 0))
        msg_text = ""
        if isinstance(raw, dict):
            msg_text = str(raw.get("message", "")) or str(raw.get("error", ""))
        elif isinstance(raw, str):
            msg_text = raw
        return TtsError(code=code, message=msg_text)

    # 二进制音频帧：SERVER_ACK + bytes payload（event=352 TTSResponse）
    if message_type == "SERVER_ACK" and isinstance(raw, (bytes, bytearray)):
        return TtsAudioChunk(data=bytes(raw))

    # JSON 事件帧
    if message_type == "SERVER_FULL_RESPONSE":
        code_int = event_code if isinstance(event_code, int) else 0
        # 首个分句开始 → TtsStarted
        if code_int == _TTS_EVENT_TTS_SENTENCE_START:
            return TtsStarted()
        # 会话结束 → TtsFinished
        if code_int == _TTS_EVENT_SESSION_FINISHED:
            return TtsFinished()
        # 分句结束（351）/连接结束（52）业务不关心，忽略
        return None

    # 未知帧类型
    return TtsError(code=-2, message=f"unknown message_type {message_type}")


# ===========================================================================
# 客户端
# ===========================================================================


class StreamingTtsClient:
    """流式 TTS WebSocket 客户端：建连 → 发文本 → 收音频流 → 结束。

    线程安全性：单 WS 连接，建议单协程使用。
    """

    def __init__(
        self,
        config: StreamingTtsConfig | None = None,
        *,
        log: logging.Logger | logging.LoggerAdapter | None = None,
    ) -> None:
        self.config = config or StreamingTtsConfig()
        self._log = log if log is not None else _log
        self._ws: ClientConnection | None = None
        self._logid: str = ""
        self._recv_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[TtsEvent] = asyncio.Queue()
        self._closed = asyncio.Event()
        self._text_sent = False
        self._first_response = asyncio.Event()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def open(self, *, text: str) -> None:
        """建 WS → 发 SendText（payload 含完整文本）→ 等首个服务端响应。

        单向流式协议：建连后直接发一次 SendText 即可，服务端会流式返回音频。
        """
        if not text or not text.strip():
            raise ValueError("TTS 合成文本不能为空")

        headers = _build_headers(self.config)
        self._log.info("tts open url=%s resource=%s", self.config.url, self.config.resource_id)
        self._ws = await websockets.connect(
            self.config.url,
            additional_headers=headers,
            ping_interval=None,
            max_size=10 * 1024 * 1024,
        )
        resp_headers = getattr(self._ws, "response_headers", {}) or {}
        self._logid = resp_headers.get("X-Tt-Logid", "")
        self._log.info("tts connected logid=%s", self._logid)

        # 启动接收循环
        self._recv_task = asyncio.create_task(self._receive_loop())

        # 发 SendText：Full-client request，无 event number（NO_SEQUENCE + 无 MSG_WITH_EVENT）
        payload = _build_send_text_payload(text, self.config)
        await self._send_full_request(payload, flags=_NO_SEQUENCE)
        self._text_sent = True
        # 等首个服务端响应（TTSSentenceStart 或音频帧），确认链路通畅
        try:
            await asyncio.wait_for(self._first_response.wait(), timeout=self.config.session_timeout)
        except asyncio.TimeoutError as exc:
            await self.close()
            raise RuntimeError("TTS 等待首个响应超时") from exc
        self._log.info("tts streaming started, receiving audio...")

    async def close(self) -> None:
        """发 FinishConnection 并关闭连接。"""
        if self._ws is not None and self._text_sent:
            try:
                # FinishConnection：Full-client request，flags=MSG_WITH_EVENT，payload 含 event=2
                await self._send_full_request(
                    payload={"event": _TTS_EVENT_FINISH_CONNECTION},
                    flags=_MSG_WITH_EVENT,
                )
            except Exception:
                pass
        if self._recv_task is not None and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recv_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._closed.set()
        self._log.info("tts closed")

    # ------------------------------------------------------------------
    # 数据收发
    # ------------------------------------------------------------------

    async def events(self) -> AsyncIterator[TtsEvent]:
        """异步迭代服务端事件，直到收到 TtsFinished / TtsError 或连接关闭。"""
        while not self._closed.is_set():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if self._recv_task is not None and self._recv_task.done():
                    if self._event_queue.empty():
                        break
                continue
            yield event
            if event.type in ("tts_finished", "tts_error"):
                break

    async def synthesize(self, text: str) -> bytes:
        """高级接口：建连 → 收完整音频流 → 自动关闭，返回 PCM bytes。"""
        await self.open(text=text)
        audio = bytearray()
        try:
            async for event in self.events():
                if event.type == "tts_audio":
                    audio.extend(event.data)
                elif event.type == "tts_error":
                    raise RuntimeError(f"TTS 合成失败: code={event.code} message={event.message}")
        finally:
            await self.close()
        if not audio:
            raise RuntimeError("TTS 未返回音频数据")
        self._log.info("tts synthesize done %d bytes", len(audio))
        return bytes(audio)

    # ------------------------------------------------------------------
    # 内部：协议帧构造
    # ------------------------------------------------------------------

    async def _send_full_request(self, payload: dict[str, Any], *, flags: int) -> None:
        """发送 full client request（JSON payload，gzip 压缩）。

        单向流式协议：
        - SendText: flags=NO_SEQUENCE（无 event number）
        - FinishConnection: flags=MSG_WITH_EVENT（4字节 event 在 payload 前）
        """
        if self._ws is None:
            raise RuntimeError("WebSocket 未建立")
        header = _generate_header(
            message_type=_CLIENT_FULL_REQUEST,
            flags=flags,
            serial=_JSON,
            compression=_GZIP,
        )
        payload_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False).encode())
        frame = bytearray(header)
        frame.extend(len(payload_bytes).to_bytes(4, "big"))
        frame.extend(payload_bytes)
        await self._ws.send(bytes(frame))

    async def _receive_loop(self) -> None:
        """接收循环：解析服务端帧 → TtsEvent → 入队。"""
        assert self._ws is not None
        while not self._closed.is_set():
            try:
                raw = await self._ws.recv()
            except websockets.exceptions.ConnectionClosed:
                self._log.info("tts ws closed by server")
                break
            except Exception as exc:
                self._log.warning("tts recv error: %r", exc)
                await self._event_queue.put(TtsError(code=-1, message=f"recv error: {exc!r}"))
                break
            if isinstance(raw, str):
                continue
            try:
                data = _parse_response(raw)
                event = _parse_event(data)
            except Exception as exc:
                self._log.warning("tts parse error: %r", exc)
                await self._event_queue.put(TtsError(code=-1, message=f"parse error: {exc!r}"))
                continue
            if event is None:
                continue  # 忽略业务不关心的事件
            if not self._first_response.is_set():
                self._first_response.set()
            await self._event_queue.put(event)
