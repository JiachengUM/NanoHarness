"""火山引擎大模型流式 ASR WebSocket 客户端（完全独立，不依赖 S2S 链路）。

接口：wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async（双向流式优化版）
协议：火山二进制帧（header + 可选 seq/event + payload_size + payload）
     本模块自实现协议常量与解析，不依赖 projects.voice_test.core.protocol / config

只提供最原始的能力：音频进，服务端响应出。
_receive_loop 收到服务端帧后立即解析成 AsrEvent 数据模型入队（parse_asr_frame），
events() 直接对外暴露 AsrEvent，业务层只需消费数据模型，无需自己区分 delta/final、解析 definite 判停。

核心流程（对齐官方 demo sauc_websocket_demo.py）：
1. open()       建 WS → 发 full client request（带 seq=1）→ 标记会话已建立
2. send_audio() 推 PCM（200ms/包，带递增 seq，最后一包用负 seq 标记音频流结束）
3. events()     异步迭代服务端事件（AsrEvent），直到 AsrFinished/AsrError / 关闭
4. finish()     发空音频负包（标记音频流结束）
5. close()      关 WS

使用示例：
    client = StreamingAsrClient()
    await client.open()
    async def pump():
        while has_audio:
            await client.send_audio(pcm_chunk)
        await client.finish()
    pump_task = asyncio.create_task(pump())
    async for event in client.events():
        match event:
            case AsrDelta(text=text) | AsrFinal(text=text):
                print(f"识别: {text}")
            case AsrFinished():
                break
    await pump_task
    await client.close()
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import struct
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
_log = logging.getLogger("vt.streaming_asr")
if not _log.handlers:
    import sys
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
_NO_SEQUENCE = 0b0000      # 无 seq
_POS_SEQUENCE = 0b0001     # 有正 seq
_NEG_SEQUENCE = 0b0010     # 最后一包（无 seq）
_NEG_SEQUENCE_1 = 0b0011   # 最后一包 + 有负 seq
_MSG_WITH_EVENT = 0b0100   # 带 event

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
    """解析服务端二进制帧（对齐 demo 的 ResponseParser，不读 session_id）。

    帧格式：
    - header(4) + [optional seq(4)] + [optional event(4)] + payload_size(4) + payload
    - message_type: 0b1001=SERVER_FULL_RESPONSE, 0b1011=SERVER_ACK, 0b1111=SERVER_ERROR_RESPONSE
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
        # POS_SEQUENCE(0b0001) 或 NEG_SEQUENCE_1(0b0011) 都带 seq
        if flags & _POS_SEQUENCE:
            result["seq"] = int.from_bytes(payload[:4], "big", signed=True)
            start += 4
        # NEG_SEQUENCE(0b0010) 或 NEG_SEQUENCE_1(0b0011) 都表示最后一包
        if flags & _NEG_SEQUENCE:
            result["is_last"] = True
        if flags & _MSG_WITH_EVENT:
            result["event"] = int.from_bytes(payload[start:start + 4], "big", signed=False)
            start += 4
        payload = payload[start:]
        payload_size = int.from_bytes(payload[:4], "big", signed=False)
        payload_msg = payload[4:4 + payload_size]
    elif message_type == _SERVER_ERROR_RESPONSE:
        result["message_type"] = "SERVER_ERROR_RESPONSE"
        result["code"] = int.from_bytes(payload[:4], "big", signed=True)
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

# 默认音频参数（16kHz/16bit/单声道 PCM，与浏览器采集一致）
_DEFAULT_SAMPLE_RATE = 16000
_DEFAULT_BITS = 16
_DEFAULT_CHANNEL = 1
_DEFAULT_CHUNK_MS = 200

# ASR 专用账号（运维提供，与 S2S/TTS 不是同一账号）
# 旧版控制台鉴权：X-Api-App-Key=APP ID, X-Api-Access-Key=Access Token
_DEFAULT_APP_KEY = "8343623480"
_DEFAULT_ACCESS_KEY = "REDACTED"

# 服务地址与资源
_DEFAULT_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
_DEFAULT_RESOURCE_ID = "volc.bigasr.sauc.duration"  # 豆包流式语音识别模型 1.0 小时版


# --- full client request 三段子模型（对齐 S2S config.py 的嵌套风格）---


class AsrUserConfig(BaseModel):
    """user 段：用户/设备标识（全可选，服务端用于日志过滤）。"""

    model_config = ConfigDict(protected_namespaces=())

    uid: str | None = None       # 未填则客户端自动生成 asr-{8hex}
    did: str | None = None
    platform: str | None = None
    sdk_version: str | None = None
    app_version: str | None = None


class AsrAudioConfig(BaseModel):
    """audio 段：音频格式（默认 16kHz/16bit/单声道 PCM，与浏览器采集一致）。"""

    model_config = ConfigDict(protected_namespaces=())

    format: str = "pcm"          # pcm / wav / ogg / mp3
    codec: str = "raw"           # raw / opus（ogg 必须 opus）
    rate: int = _DEFAULT_SAMPLE_RATE
    bits: int = _DEFAULT_BITS
    channel: int = _DEFAULT_CHANNEL
    language: str | None = None  # 仅流式输入模式(bigmodel_nostream)支持


class AsrRequestConfig(BaseModel):
    """request 段：识别业务参数（全部可选，None 字段不下发）。

    字段对齐官方文档 https://docs.volcengine.com/docs/6561/1354869#发送-full-client-request
    """

    model_config = ConfigDict(protected_namespaces=())

    # 基础
    model_name: str = Field(default="bigmodel", description="模型名称，目前只有 bigmodel")
    enable_itn: bool = Field(default=True, description="逆文本归一化（一九七零年→1970年）")
    enable_punc: bool = Field(default=True, description="自动加标点")
    enable_ddc: bool = Field(default=False, description="语义顺滑（去停顿词/语气词/重复词）")
    show_utterances: bool = Field(default=True, description="返回 utterances 分句（业务方判断句尾依赖此字段）")
    enable_nonstream: bool = Field(default=False, description="二遍识别（流式+nostream，提升准确率，仅双向流式优化版支持）")
    result_type: Literal["full", "single"] | None = Field(default="single", description="结果返回方式：full=全量(默认), single=增量")
    output_zh_variant: Literal["traditional", "tw", "hk"] | None = Field(default=None, description="繁体中文输出：traditional=大陆繁体, tw=台湾正体, hk=香港繁体")
    # 强制判停 / VAD
    end_window_size: int | None = Field(default=5000, ge=200, description="强制判停静音阈值(ms)，服务端默认 800，最小 200；静音超过此值直接判停输出 definite")
    vad_segment_duration: int | None = Field(default=None, ge=100, description="语义切句最大静音(ms)，服务端默认 3000；配置 end_window_size 后此参数失效")
    force_to_speech_time: int | None = Field(default=None, ge=1, description="最小判停音频时长(ms)，音频超过此值才尝试判停，需配合 end_window_size，推荐 1000")
    # 首字加速
    enable_accelerate_text: bool | None = Field(default=None, description="启用首字返回加速（会降低首字准确率）")
    accelerate_score: int | None = Field(default=None, ge=0, le=20, description="首字加速率，0=不加速，越大首字越快，范围 [0, 20]")
    # 增强检测（需开启 enable_nonstream=true）
    enable_speaker_info: bool | None = Field(default=None, description="说话人聚类分离（需 enable_nonstream=true 且 ssd_version=200，建议 ASR 2.0）")
    ssd_version: Literal["200"] | None = Field(default=None, description="SSD 版本，200=启用大模型 SSD（建议 ASR 2.0）")
    show_speech_rate: bool | None = Field(default=None, description="分句携带语速（token/s，需 enable_nonstream=true）")
    show_volume: bool | None = Field(default=None, description="分句携带音量（分贝，需 enable_nonstream=true）")
    enable_lid: bool | None = Field(default=None, description="语种检测（需 enable_nonstream=true）")
    enable_emotion_detection: bool | None = Field(default=None, description="情绪检测：angry/happy/neutral/sad/surprise（需 enable_nonstream=true）")
    enable_gender_detection: bool | None = Field(default=None, description="性别检测：male/female（需 enable_nonstream=true）")
    # Function call（需开启 enable_nonstream=true）
    enable_poi_fc: bool | None = Field(default=None, description="POI 地名辅助识别（需 enable_nonstream=true，配合 corpus.context 传城市）")
    enable_music_fc: bool | None = Field(default=None, description="音乐曲名辅助识别（需 enable_nonstream=true）")
    # 热词/替换词/上下文
    boosting_table_name: str | None = Field(default=None, description="自学习平台热词词表名称")
    boosting_table_id: str | None = Field(default=None, description="自学习平台热词词表 ID")
    correct_table_name: str | None = Field(default=None, description="自学习平台替换词词表名称")
    correct_table_id: str | None = Field(default=None, description="自学习平台替换词词表 ID")
    context: str | None = Field(default=None, description="热词或上下文（JSON string，调用方序列化；双向流式限 100 tokens）")
    sensitive_words_filter: str | None = Field(default=None, description="敏感词过滤配置（JSON string，调用方序列化）")


class StreamingAsrConfig(BaseModel):
    """流式 ASR 客户端配置（顶层：连接相关 + 嵌套 user/audio/request 三段）。"""

    model_config = ConfigDict(protected_namespaces=())

    # 连接
    url: str = _DEFAULT_URL
    resource_id: str = _DEFAULT_RESOURCE_ID
    chunk_ms: int = _DEFAULT_CHUNK_MS        # 单包音频毫秒数（建议值，实际由调用方控制发包节奏）
    # 鉴权覆盖（None → 用 _DEFAULT_APP_KEY / _DEFAULT_ACCESS_KEY）
    app_key: str | None = None
    access_key: str | None = None
    connect_id: str | None = None
    # full client request 三段
    user: AsrUserConfig = Field(default_factory=AsrUserConfig)
    audio: AsrAudioConfig = Field(default_factory=AsrAudioConfig)
    request: AsrRequestConfig = Field(default_factory=AsrRequestConfig)


def _build_headers(config: StreamingAsrConfig) -> dict[str, str]:
    """鉴权头（对齐 demo：X-Api-App-Key + X-Api-Access-Key + X-Api-Resource-Id + X-Api-Request-Id）。"""
    return {
        "X-Api-App-Key": config.app_key or _DEFAULT_APP_KEY,
        "X-Api-Access-Key": config.access_key or _DEFAULT_ACCESS_KEY,
        "X-Api-Resource-Id": config.resource_id,
        "X-Api-Request-Id": config.connect_id or str(uuid.uuid4()),
    }


def _build_full_request_payload(config: StreamingAsrConfig) -> dict[str, Any]:
    """full client request 的 JSON payload（直接 dump user/audio/request 三段）。

    - user.uid 未填时自动生成 asr-{8hex}
    - 所有 None 字段被 exclude_none 过滤，不下发到服务端
    """
    user = config.user.model_dump(exclude_none=True)
    if not user.get("uid"):
        user["uid"] = f"asr-{uuid.uuid4().hex[:8]}"
    return {
        "user": user,
        "audio": config.audio.model_dump(exclude_none=True),
        "request": config.request.model_dump(exclude_none=True),
    }


# ===========================================================================
# 服务端事件模型（业务层消费的数据模型：以服务端判停为标准切分句子）
# 一次长连接中可能多次判停，用 index区分：
# delta 与最终对应的 final 共享同一 index。
# ===========================================================================


class AsrStarted(BaseModel):
    """会话已建立，可开始推音频。"""
    model_config = ConfigDict(protected_namespaces=())
    type: Literal["asr_started"] = "asr_started"
    raw: dict[str, Any] | None = None  # 服务端原始 payload_msg，原样保留


def _fmt_span(index: int, end_time: int) -> str:
    """展示用区间 [start→end]（毫秒转秒，1 位小数）。"""
    return f"[{index / 1000:.1f}→{end_time / 1000:.1f}s]"


class AsrDelta(BaseModel):
    """增量中间结果：未发生新判停，文本可能继续变化。"""
    model_config = ConfigDict(protected_namespaces=())
    type: Literal["asr_delta"] = "asr_delta"
    text: str = Field(description="当前句文本")
    index: int = Field(description="当前句起始时间戳（毫秒，取自服务端 utterance.start_time）")
    end_time: int = Field(description="当前识别进度终点时间戳（毫秒，取自服务端 utterance.end_time）")
    raw: dict[str, Any] = Field(description="服务端原始 payload_msg，原样保留")

    @property
    def span(self) -> str:
        """展示用区间，如 [4.9→5.8s]。"""
        return _fmt_span(self.index, self.end_time)


class AsrFinal(BaseModel):
    """VAD 判停帧：新判停（definite=True）的句子。"""
    model_config = ConfigDict(protected_namespaces=())
    type: Literal["asr_final"] = "asr_final"
    text: str = Field(description="判停完成的句子文本")
    index: int = Field(description="判停句子起始时间戳（毫秒，取自服务端 utterance.start_time）")
    end_time: int = Field(description="判停句子终点时间戳（毫秒，取自服务端 utterance.end_time）")
    gap_ms: int | None = Field(default=None, description="与上一个 delta 的 end_time 差值（毫秒），即 VAD 判停等待的静音时长；无前置 delta 时为 None")
    raw: dict[str, Any] = Field(description="服务端原始 payload_msg，原样保留")

    @property
    def span(self) -> str:
        """展示用区间 + 判停差值，如 [4.9→11.3s] (+4.1s)。"""
        gap = f" (+{self.gap_ms / 1000:.1f}s)" if self.gap_ms is not None else ""
        return f"{_fmt_span(self.index, self.end_time)}{gap}"


class AsrFinished(BaseModel):
    """会话正常结束。"""
    model_config = ConfigDict(protected_namespaces=())
    type: Literal["asr_finished"] = "asr_finished"
    raw: dict[str, Any] | None = None  # 最后一帧的完整 payload_msg（含所有 utterances + words）


class AsrError(BaseModel):
    """服务端错误。"""
    model_config = ConfigDict(protected_namespaces=())
    type: Literal["asr_error"] = "asr_error"
    code: int
    message: str
    raw: dict[str, Any] | None = None  # 服务端原始 payload_msg，原样保留


AsrEvent = Union[AsrStarted, AsrDelta, AsrFinal, AsrFinished, AsrError]


def parse_asr_frame(frame: dict) -> list[AsrEvent]:
    """把一条服务端原始帧 dict 解析为 AsrEvent 列表。

    切分规则：
    - started：初始化/ack 帧（无 result 内容）→ AsrStarted
    - final：utterances 中 definite=True 且有文本的句子，index 取服务端时间戳 start_time（毫秒）
    - delta：最后一个未判停句子（当前句），index 同上
    - 已判停的句子不混进 delta —— definite 之间的内容互不拼凑
    - is_last 帧追加 AsrFinished；错误帧产出 AsrError
    index 直接用服务端时间戳区分句子，不做跨帧去重，逻辑简单。
    """
    mtype = frame.get("message_type")
    payload = frame.get("payload_msg") or {}
    if mtype == "SERVER_ERROR_RESPONSE":
        return [AsrError(code=frame.get("code", 0), message=str(payload.get("message", payload)), raw=payload)]
    events: list[AsrEvent] = []
    result = payload.get("result") or {}
    utts = result.get("utterances") or []
    # 会话初始化/ack 帧：无 text 且无 utterances → AsrStarted
    if not result.get("text") and not utts:
        return [AsrStarted(raw=payload)]
    # final：所有已判停句子
    for u in utts:
        if u.get("definite") and u.get("text"):
            events.append(AsrFinal(text=u["text"], index=u.get("start_time", 0), end_time=u.get("end_time", 0), raw=payload))
    # delta：最后一个未判停句子（当前句）
    for u in reversed(utts):
        if not u.get("definite") and u.get("text"):
            events.append(AsrDelta(text=u["text"], index=u.get("start_time", 0), end_time=u.get("end_time", 0), raw=payload))
            break
    if frame.get("is_last"):
        events.append(AsrFinished(raw=payload))
    return events


# ===========================================================================
# 客户端
# ===========================================================================


class StreamingAsrClient:
    """流式 ASR WebSocket 客户端：建连 → 推音频 → 收服务端事件（AsrEvent）。

    音频进（send_audio），事件出（events）；_receive_loop 收到服务端帧即解析成 AsrEvent（parse_asr_frame），
    definite 判停等业务语义已收敛到本模块，业务层只消费 AsrEvent。

    线程安全性：单 WS 连接，建议单协程使用 send_audio，events() 用单独协程并行消费。
    """

    def __init__(
        self,
        config: StreamingAsrConfig | None = None,
        *,
        log: logging.Logger | logging.LoggerAdapter | None = None,
    ) -> None:
        self.config = config or StreamingAsrConfig()
        self._log = log if log is not None else _log
        self._ws: ClientConnection | None = None
        self._logid: str = ""
        # 接收任务控制：open 时启动，close 时停止
        self._recv_task: asyncio.Task[None] | None = None
        # AsrEvent 队列（_receive_loop 收到服务端帧即解析成模型后入队）
        self._event_queue: asyncio.Queue[AsrEvent] = asyncio.Queue()
        # 上一个 delta 的 end_time，用于给 AsrFinal 计算 gap_ms（与上一帧 delta 的差值）
        self._last_delta_end: int | None = None
        self._closed = asyncio.Event()
        self._session_started = asyncio.Event()
        # seq 机制（对齐 demo）：full request 用 seq=1，后续 audio 递增
        self._seq = 1
    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """建连 → 发 full client request（带 seq=1）→ 标记会话已建立。

        无 StartConnection/StartSession 握手，直接发一个 full client request 即可。
        """
        headers = _build_headers(self.config)
        self._log.info("asr open url=%s resource=%s", self.config.url, self.config.resource_id)
        self._ws = await websockets.connect(
            self.config.url,
            additional_headers=headers,
            ping_interval=None,
            max_size=10 * 1024 * 1024,
        )
        resp_headers = getattr(self._ws, "response_headers", {}) or {}
        self._logid = resp_headers.get("X-Tt-Logid", "")
        self._log.info("asr connected logid=%s", self._logid)

        # 启动接收循环
        self._recv_task = asyncio.create_task(self._receive_loop())

        # 发 full client request（POS_SEQUENCE + seq=1）
        self._seq = 1
        await self._send_full_request(
            payload=_build_full_request_payload(self.config),
            sequence=self._seq,
        )
        self._seq += 1
        self._session_started.set()
        self._log.info("asr session started")

    async def finish(self) -> None:
        """发空音频负包（标记音频流结束）。

        不需要发 FinishSession/FinishConnection，
        只需发一个 is_last=True 的空音频包（NEG_WITH_SEQUENCE + 负 seq）。
        调用后服务端会返回最终识别结果，events() 会收到带 is_last 的最后一帧。
        """
        if self._ws is None:
            return
        await self._send_audio_only(b"", is_last=True)
        self._log.info("asr finish sent (last empty audio)")

    async def close(self) -> None:
        """关闭连接并停止接收循环。"""
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
        self._log.info("asr closed")

    # ------------------------------------------------------------------
    # 数据收发
    # ------------------------------------------------------------------

    async def send_audio(self, pcm: bytes) -> None:
        """推一包 PCM 音频（建议 200ms，16kHz/16bit/单声道）。"""
        if self._ws is None or self._closed.is_set():
            raise RuntimeError("ASR 客户端未连接或已关闭")
        await self._send_audio_only(pcm, is_last=False)

    async def events(self) -> AsyncIterator[AsrEvent]:
        """异步迭代服务端事件（AsrEvent），直到 AsrFinished/AsrError/连接关闭。

        _receive_loop 收到服务端帧即解析成 AsrEvent 入队（parse_asr_frame），
        本方法只从队列取出模型并 yield，业务层无需接触原始帧：
        - AsrStarted  会话已建立（初始化/ack 帧）
        - AsrDelta    当前句中间结果（index 区分句子）
        - AsrFinal    VAD 判停完成的句子（index 区分句子，gap_ms 为与上一帧 delta 的差值）
        - AsrFinished 会话正常结束（is_last 帧）
        - AsrError    服务端错误
        """
        while not self._closed.is_set():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if self._recv_task is not None and self._recv_task.done():
                    if self._event_queue.empty():
                        break
                continue
            yield event
            if isinstance(event, (AsrFinished, AsrError)):
                return

    # ------------------------------------------------------------------
    # 内部：协议帧构造
    # ------------------------------------------------------------------

    async def _send_full_request(self, payload: dict[str, Any], *, sequence: int) -> None:
        """发送 full client request（JSON payload，gzip 压缩，带 seq）。

        flags = POS_SEQUENCE，帧格式 = header(4) + seq(4) + payload_size(4) + payload
        """
        if self._ws is None:
            raise RuntimeError("WebSocket 未建立")
        header = _generate_header(
            message_type=_CLIENT_FULL_REQUEST,
            flags=_POS_SEQUENCE,
            serial=_JSON,
            compression=_GZIP,
        )
        payload_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False).encode())
        frame = bytearray(header)
        frame.extend(sequence.to_bytes(4, "big", signed=True))
        frame.extend(len(payload_bytes).to_bytes(4, "big"))
        frame.extend(payload_bytes)
        await self._ws.send(bytes(frame))

    async def _send_audio_only(self, audio: bytes, *, is_last: bool) -> None:
        """发送 audio only request（原始 PCM，gzip 压缩，带 seq）。

        - 普通包：flags = POS_SEQUENCE，seq 正数递增
        - 最后一包：flags = NEG_SEQUENCE_1(0b0011)，seq 取负值
        """
        if self._ws is None:
            raise RuntimeError("WebSocket 未建立")
        if is_last:
            flags = _NEG_SEQUENCE_1
            seq_value = -self._seq
        else:
            flags = _POS_SEQUENCE
            seq_value = self._seq
            self._seq += 1
        header = _generate_header(
            message_type=_CLIENT_AUDIO_ONLY_REQUEST,
            flags=flags,
            serial=_NO_SERIALIZATION,
            compression=_GZIP,
        )
        payload_bytes = gzip.compress(audio)
        frame = bytearray(header)
        frame.extend(seq_value.to_bytes(4, "big", signed=True))
        frame.extend(len(payload_bytes).to_bytes(4, "big"))
        frame.extend(payload_bytes)
        await self._ws.send(bytes(frame))
        self._log.debug("send_audio %d bytes is_last=%s seq=%d", len(audio), is_last, seq_value)

    async def _receive_loop(self) -> None:
        """接收循环：解析服务端帧 → 立即转成 AsrEvent（parse_asr_frame）→ 入队。"""
        assert self._ws is not None
        while not self._closed.is_set():
            try:
                raw = await self._ws.recv()
            except websockets.exceptions.ConnectionClosed:
                self._log.info("asr ws closed by server")
                break
            except Exception as exc:
                self._log.warning("asr recv error: %r", exc)
                await self._event_queue.put(
                    AsrError(code=-1, message=f"recv error: {exc!r}", raw={"message": f"recv error: {exc!r}"})
                )
                break
            if isinstance(raw, str):
                continue  # 忽略文本帧（ASR 协议不发送文本）
            try:
                frame = _parse_response(raw)
            except Exception as exc:
                # 解析失败 → 入队 AsrError，让 events() 终止、业务收到错误（不静默丢弃）
                self._log.warning("asr parse error: %r", exc)
                await self._event_queue.put(
                    AsrError(code=-1, message=f"parse error: {exc!r}", raw={"message": f"parse error: {exc!r}"})
                )
                break
            if not self._session_started.is_set():
                self._session_started.set()
            # 收到即转换：parse_asr_frame 可能一次产出多个事件（如 final + finished）
            # 同时维护 last_delta_end，给 AsrFinal 注入 gap_ms（与上一帧 delta 的 end_time 差值）
            for event in parse_asr_frame(frame):
                if isinstance(event, AsrDelta):
                    self._last_delta_end = event.end_time
                elif isinstance(event, AsrFinal) and self._last_delta_end is not None:
                    event.gap_ms = event.end_time - self._last_delta_end
                await self._event_queue.put(event)
