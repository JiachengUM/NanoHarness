from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Literal, assert_never
from rich import print
from rich.text import Text


class AudioBinaryPayload(BaseModel):
    """服务端 ACK 音频二进制载荷。"""
    data: bytes
    codec: str = "pcm"

    @property
    def size(self) -> int:
        return len(self.data)


class SessionStartedPayload(BaseModel):
    dialog_id: str | None = None


class UsagePayload(BaseModel):
    usage: dict[str, int] | None = None


class TtsTextAcceptedPayload(BaseModel):
    enable_v3_loudness_balance: bool | None = None
    model_type: str | None = None
    question_id: str | None = None
    reply_id: str | None = None
    tts_task_id: str | None = None
    tts_type: str | None = None
    text: str | None = None
    model_config = ConfigDict(extra="allow", protected_namespaces=())


class TtsTextFinishedPayload(BaseModel):
    question_id: str | None = None
    reply_id: str | None = None
    text: str | None = None
    speech_alignment_result: str | None = None
    model_config = ConfigDict(extra="allow")


class TtsEndedPayload(BaseModel):
    """TTSEnded（code=359）；含 status_code 时可用于用户退出意图等信号。"""
    extra: dict[str, Any] | None = None
    no_content: bool | None = None
    question_id: str | None = None
    reply_id: str | None = None
    status_code: str | None = None
    model_config = ConfigDict(extra="allow")


class AsrPartialPayload(BaseModel):
    extra: dict[str, Any] | None = None
    # TODO：这里有点复杂，按理说results也应该用basemodel来处理。先记下
    results: list[dict[str, Any]] | None = None
    model_config = ConfigDict(extra="allow")

    def _split(self) -> tuple[str, bool]:
        """``(text, 是否完整文本)``；无首条或无效 text 则 ``("", False)``。"""
        rs = self.results
        if not rs:
            return "", False
        first = rs[0]
        if not isinstance(first, dict):
            return "", False
        t = first.get("text", "")
        if not isinstance(t, str) or t == "":
            return "", False
        interim = bool(first.get("is_interim", True))
        endpoint = isinstance(self.extra, dict) and self.extra.get("endpoint") is True
        is_final = (not interim) or endpoint
        return t, is_final

    @property
    def final_text(self) -> str:
        t, is_final = self._split()
        return t if is_final else ""

    @property
    def interim_text(self) -> str:
        t, is_final = self._split()
        return t if not is_final else ""


class AsrTextPayload(BaseModel):
    """451 拆开后只有 ``text``；来源为 ``results[0].text`` 经 trim。"""

    text: str
    model_config = ConfigDict(extra="ignore")


class AsrInfoPayload(BaseModel):
    """服务端 ASRInfo（code=450）载荷。"""
    asr_task_id: str | None = None
    is_duplex_interrupted: bool | None = None
    local_message_id: str | None = None
    question_id: str | None = None
    round_id: int | None = None
    model_config = ConfigDict(extra="allow")


class ConnectionFailedPayload(BaseModel):
    error: str | None = None
    model_config = ConfigDict(extra="allow")


class SessionFailedPayload(BaseModel):
    error: str | None = None
    model_config = ConfigDict(extra="allow")


class DialogCommonErrorPayload(BaseModel):
    status_code: str | None = None
    message: str | None = None
    model_config = ConfigDict(extra="allow")


class TextDeltaPayload(BaseModel):
    content: str = ""
    question_id: str | None = None
    reply_id: str | None = None


class QuestionStartedPayload(BaseModel):
    question_id: str | None = None


class ReplyFinishedPayload(BaseModel):
    question_id: str | None = None
    reply_id: str | None = None


class UnknownPayload(BaseModel):
    """未建模事件的兜底载荷。"""
    data: dict[str, Any] = Field(default_factory=dict)


class EmptyPayload(BaseModel):
    """文档中 `{}` 类载荷；多余字段忽略。"""
    model_config = ConfigDict(extra="ignore")


# --- 客户端发帧 event 码：realtime_dialog_client.ClientWire（IntEnum）。---
# --- SERVER_FULL_RESPONSE 各 event 码一种 BaseModel；类名与文档「事件定义」一致；
#     经 SERVER_ACK 的二进制音频单独建模为 TTSResponse（文档 code=352）。 ---


class ServerMessageBase(BaseModel):
    """收包公共信封。"""

    model_config = ConfigDict(extra="forbid")
    message_type: str
    session_id: str | None = None
    payload_size: int | None = None


class ConnectionStarted(ServerMessageBase):
    code: Literal[50] = Field(default=50, init=False)
    name: Literal["ConnectionStarted"] = Field(default="ConnectionStarted", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="成功建立连接", init=False)
    type: Literal["ConnectionStarted"] = Field(default="ConnectionStarted", init=False)
    payload: EmptyPayload


class ConnectionFailed(ServerMessageBase):
    code: Literal[51] = Field(default=51, init=False)
    name: Literal["ConnectionFailed"] = Field(default="ConnectionFailed", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="建立连接失败", init=False)
    type: Literal["ConnectionFailed"] = Field(default="ConnectionFailed", init=False)
    payload: ConnectionFailedPayload


class ConnectionFinished(ServerMessageBase):
    code: Literal[52] = Field(default=52, init=False)
    name: Literal["ConnectionFinished"] = Field(default="ConnectionFinished", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="连接结束", init=False)
    type: Literal["ConnectionFinished"] = Field(default="ConnectionFinished", init=False)
    payload: EmptyPayload


class SessionStarted(ServerMessageBase):
    code: Literal[150] = Field(default=150, init=False)
    name: Literal["SessionStarted"] = Field(default="SessionStarted", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="成功启动会话", init=False)
    type: Literal["SessionStarted"] = Field(default="SessionStarted", init=False)
    payload: SessionStartedPayload


class SessionFinished(ServerMessageBase):
    code: Literal[152] = Field(default=152, init=False)
    name: Literal["SessionFinished"] = Field(default="SessionFinished", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="会话已结束", init=False)
    type: Literal["SessionFinished"] = Field(default="SessionFinished", init=False)
    payload: EmptyPayload


class SessionFailed(ServerMessageBase):
    code: Literal[153] = Field(default=153, init=False)
    name: Literal["SessionFailed"] = Field(default="SessionFailed", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="会话失败", init=False)
    type: Literal["SessionFailed"] = Field(default="SessionFailed", init=False)
    payload: SessionFailedPayload


class UsageResponse(ServerMessageBase):
    code: Literal[154] = Field(default=154, init=False)
    name: Literal["UsageResponse"] = Field(default="UsageResponse", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="每一轮交互对应的用量信息", init=False)
    type: Literal["UsageResponse"] = Field(default="UsageResponse", init=False)
    payload: UsagePayload


class ConfigUpdated(ServerMessageBase):
    code: Literal[251] = Field(default=251, init=False)
    name: Literal["ConfigUpdated"] = Field(default="ConfigUpdated", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="UpdateConfig 请求对应的 ack", init=False)
    type: Literal["ConfigUpdated"] = Field(default="ConfigUpdated", init=False)
    payload: EmptyPayload


class TTSSentenceStart(ServerMessageBase):
    code: Literal[350] = Field(default=350, init=False)
    name: Literal["TTSSentenceStart"] = Field(default="TTSSentenceStart", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="合成音频的起始事件", init=False)
    type: Literal["TTSSentenceStart"] = Field(default="TTSSentenceStart", init=False)
    payload: TtsTextAcceptedPayload


class TTSSentenceEnd(ServerMessageBase):
    code: Literal[351] = Field(default=351, init=False)
    name: Literal["TTSSentenceEnd"] = Field(default="TTSSentenceEnd", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="合成音频的分句结束事件", init=False)
    type: Literal["TTSSentenceEnd"] = Field(default="TTSSentenceEnd", init=False)
    payload: TtsTextFinishedPayload


class TTSEnded(ServerMessageBase):
    code: Literal[359] = Field(default=359, init=False)
    name: Literal["TTSEnded"] = Field(default="TTSEnded", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="模型一轮音频合成结束事件", init=False)
    type: Literal["TTSEnded"] = Field(default="TTSEnded", init=False)
    payload: TtsEndedPayload


class ASRInfo(ServerMessageBase):
    code: Literal[450] = Field(default=450, init=False)
    name: Literal["ASRInfo"] = Field(default="ASRInfo", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="识别出音频流中的首字", init=False)
    type: Literal["ASRInfo"] = Field(default="ASRInfo", init=False)
    payload: AsrInfoPayload


class ASRDelta(ServerMessageBase):
    """451 + interim：增量。
    这里的增量和模型输出的不太一样，他是递增式的：
        你
        你好，
        你好啊，今天
        你好啊，今天天气
        你好啊，今天天气怎么样？
    """

    code: Literal[451] = Field(default=451, init=False)
    name: Literal["ASRDelta"] = Field(default="ASRDelta", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="ASR 增量", init=False)
    type: Literal["ASRDelta"] = Field(default="ASRDelta", init=False)
    payload: AsrTextPayload


class ASRFinal(ServerMessageBase):
    """451 + 非 interim：最终完整的识别结果。"""

    code: Literal[451] = Field(default=451, init=False)
    name: Literal["ASRFinal"] = Field(default="ASRFinal", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="ASR 完整文本", init=False)
    type: Literal["ASRFinal"] = Field(default="ASRFinal", init=False)
    payload: AsrTextPayload


class ASRResponse(ServerMessageBase):
    """拆分开来，方便外部使用，只返回 ``ASRDelta`` / ``ASRFinal``"""

    code: Literal[451] = Field(default=451, init=False)
    name: Literal["ASRResponse"] = Field(default="ASRResponse", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="识别出用户说话的文本内容", init=False)
    type: Literal["ASRResponse"] = Field(default="ASRResponse", init=False)
    payload: AsrPartialPayload


class ASREnded(ServerMessageBase):
    code: Literal[459] = Field(default=459, init=False)
    name: Literal["ASREnded"] = Field(default="ASREnded", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="模型认为用户说话结束", init=False)
    type: Literal["ASREnded"] = Field(default="ASREnded", init=False)
    payload: EmptyPayload


class ASR451NoText(ServerMessageBase):
    """451 帧但无可展示文本（流式进度 / 全空 interim 等），非协议错误；业务与日志均可忽略。"""

    code: Literal[451] = Field(default=451, init=False)
    name: Literal["ASR451NoText"] = Field(default="ASR451NoText", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="451 无文本", init=False)
    type: Literal["ASR451NoText"] = Field(default="ASR451NoText", init=False)
    payload: EmptyPayload


class ChatResponse(ServerMessageBase):
    code: Literal[550] = Field(default=550, init=False)
    name: Literal["ChatResponse"] = Field(default="ChatResponse", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="模型回复的文本内容", init=False)
    type: Literal["ChatResponse"] = Field(default="ChatResponse", init=False)
    payload: TextDeltaPayload


class ChatTextQueryConfirmed(ServerMessageBase):
    code: Literal[553] = Field(default=553, init=False)
    name: Literal["ChatTextQueryConfirmed"] = Field(default="ChatTextQueryConfirmed", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="ChatTextQuery 请求对应的 ack", init=False)
    type: Literal["ChatTextQueryConfirmed"] = Field(default="ChatTextQueryConfirmed", init=False)
    payload: QuestionStartedPayload


class ChatEnded(ServerMessageBase):
    code: Literal[559] = Field(default=559, init=False)
    name: Literal["ChatEnded"] = Field(default="ChatEnded", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="模型回复文本结束事件", init=False)
    type: Literal["ChatEnded"] = Field(default="ChatEnded", init=False)
    payload: ReplyFinishedPayload


class ConversationCreated(ServerMessageBase):
    code: Literal[567] = Field(default=567, init=False)
    name: Literal["ConversationCreated"] = Field(default="ConversationCreated", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="增加上下文请求对应的 ack", init=False)
    type: Literal["ConversationCreated"] = Field(default="ConversationCreated", init=False)
    payload: UnknownPayload


class ConversationUpdated(ServerMessageBase):
    code: Literal[568] = Field(default=568, init=False)
    name: Literal["ConversationUpdated"] = Field(default="ConversationUpdated", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="更新上下文请求对应的 ack", init=False)
    type: Literal["ConversationUpdated"] = Field(default="ConversationUpdated", init=False)
    payload: UnknownPayload


class ConversationRetrieved(ServerMessageBase):
    code: Literal[569] = Field(default=569, init=False)
    name: Literal["ConversationRetrieved"] = Field(default="ConversationRetrieved", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="查询上下文请求对应的 ack", init=False)
    type: Literal["ConversationRetrieved"] = Field(default="ConversationRetrieved", init=False)
    payload: UnknownPayload


class ConversationTruncated(ServerMessageBase):
    code: Literal[570] = Field(default=570, init=False)
    name: Literal["ConversationTruncated"] = Field(default="ConversationTruncated", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="截取上下文请求对应的 ack", init=False)
    type: Literal["ConversationTruncated"] = Field(default="ConversationTruncated", init=False)
    payload: EmptyPayload


class ConversationDeleted(ServerMessageBase):
    code: Literal[571] = Field(default=571, init=False)
    name: Literal["ConversationDeleted"] = Field(default="ConversationDeleted", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="删除上下文请求对应的 ack", init=False)
    type: Literal["ConversationDeleted"] = Field(default="ConversationDeleted", init=False)
    payload: UnknownPayload


class DialogCommonError(ServerMessageBase):
    code: Literal[599] = Field(default=599, init=False)
    name: Literal["DialogCommonError"] = Field(default="DialogCommonError", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="实时通话过程中相关错误描述", init=False)
    type: Literal["DialogCommonError"] = Field(default="DialogCommonError", init=False)
    payload: DialogCommonErrorPayload


class TTSResponse(ServerMessageBase):
    """文档 352：二进制音频；经 SERVER_ACK 入站，内部 code=-1 与 JSON 响应区分。"""

    code: Literal[-1] = Field(default=-1, init=False)
    name: Literal["TTSResponse"] = Field(default="TTSResponse", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="返回模型生成的音频数据", init=False)
    type: Literal["TTSResponse"] = Field(default="TTSResponse", init=False)
    wire_event_code: int | None = None
    payload: AudioBinaryPayload


class ServerErrorResponse(ServerMessageBase):
    """message_type=SERVER_ERROR_RESPONSE 时的帧（非文档表格行，与传输层一致命名）。"""

    code: Literal[-2] = Field(default=-2, init=False)
    name: Literal["ServerErrorResponse"] = Field(default="ServerErrorResponse", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="SERVER_ERROR_RESPONSE", init=False)
    type: Literal["ServerErrorResponse"] = Field(default="ServerErrorResponse", init=False)
    payload: UnknownPayload


class UnmappedServerEvent(ServerMessageBase):
    """未在代码中写死映射的 event 码或非标准信封。"""

    code: Literal[-3] = Field(default=-3, init=False)
    name: Literal["UnmappedServerEvent"] = Field(default="UnmappedServerEvent", init=False)
    direction: Literal["server"] = Field(default="server", init=False)
    description: str = Field(default="未映射", init=False)
    type: Literal["UnmappedServerEvent"] = Field(default="UnmappedServerEvent", init=False)
    wire_event_code: int | None = None
    payload: UnknownPayload


def asr451_to_delta_or_final(
    *,
    message_type: str,
    session_id: str | None,
    payload_size: int | None,
    raw: dict[str, Any],
) -> ASRDelta | ASRFinal | ASR451NoText:
    """451 原始 dict → ``ASRDelta`` / ``ASRFinal``；无可用文本则 ``ASR451NoText``（勿用 ``UnmappedServerEvent`` 刷屏）。"""
    # 进行拆分。
    partial = AsrPartialPayload.model_validate(raw)
    final = partial.final_text.strip()
    if final != "":
        return ASRFinal(
            message_type=message_type,
            session_id=session_id,
            payload_size=payload_size,
            payload=AsrTextPayload(text=final),
        )
    interim = partial.interim_text.strip()
    if interim != "":
        return ASRDelta(
            message_type=message_type,
            session_id=session_id,
            payload_size=payload_size,
            payload=AsrTextPayload(text=interim),
        )
    #TODO:未知的
    return ASR451NoText(
        message_type=message_type,
        session_id=session_id,
        payload_size=payload_size,
        payload=EmptyPayload(),
    )


S2sServerNotify = (
    ConnectionStarted
    | ConnectionFailed
    | ConnectionFinished
    | SessionStarted
    | SessionFinished
    | SessionFailed
    | UsageResponse
    | ConfigUpdated
    | TTSSentenceStart
    | TTSSentenceEnd
    | TTSEnded
    | ASRInfo
    | ASRDelta
    | ASRFinal
    | ASR451NoText
    | ASREnded
    | ChatResponse
    | ChatTextQueryConfirmed
    | ChatEnded
    | ConversationCreated
    | ConversationUpdated
    | ConversationRetrieved
    | ConversationTruncated
    | ConversationDeleted
    | DialogCommonError
    | TTSResponse
    | ServerErrorResponse
    | UnmappedServerEvent
)


def parse_s2s_protocol_message(data: dict[str, Any]) -> S2sServerNotify:
    """把 `protocol.parse_response` 得到的 dict 转成具体一种服务端事件模型。

    与二进制帧的对应关系（见 `protocol.parse_response`）：
    - `SERVER_ACK`：常为「下行音频」等无 JSON 体，解压后 `payload_msg` 仍是 **bytes** → 映射为文档里的 **TTSResponse**。
    - `SERVER_ERROR_RESPONSE`：`parse_response` 只填了 `code` / `payload_msg` 等，**历史上不一定带 `message_type` 键**，故下面用 `code in data` 兜底。
    - `SERVER_FULL_RESPONSE`：帧头里带 `event` 时，`payload_msg` 经 `protocol.parse_response` 处理后**期望**是 JSON
      **对象**（`dict`），才能按码 `model_validate`。但下层可能出现非 dict：
      - `serialization_method == JSON` 时 `json.loads` 顶层可以是 **list / str / 数字 / null**（协议约定是对象，服务端或中间层仍可能发错）。
      - `NO_SERIALIZATION` 时体可能是 **bytes**（未再走 JSON）。
      - `THRIFT` / `CUSTOM_TYPE` 等分支会把体解成 **str**，也不是 dict。
      上述一律不强行套具体事件模型，走 **UnmappedServerEvent**，并在载荷里保留 `payload_msg` 便于排查。

    其它组合（缺 event、未知 message_type）不硬猜语义，统一 **UnmappedServerEvent**，避免静默建错模型。
    """
    # --- 从 dict 取公共字段；缺省与类型不对时压成可分支用的形态 ---
    message_type = data.get("message_type")
    # 兼容：SERVER_ERROR 分支在 protocol 里未写入 message_type，但会有数值 code
    if message_type is None and "code" in data:
        message_type = "SERVER_ERROR_RESPONSE"
    # 非 str 无法与协议常量比较，当作「未知类型」走后面的兜底分支
    if not isinstance(message_type, str):
        message_type = ""
    session_id = data.get("session_id")
    payload_size = data.get("payload_size")
    raw = data.get("payload_msg")
    event_code_field = data.get("event")
    # 只有 SERVER_FULL/ACK 且带 MSG_WITH_EVENT 时 parse_response 才会写「event」键（帧内事件码）；否则为 None
    code_int = event_code_field if isinstance(event_code_field, int) else None

    # 二进制 ACK：必须同时满足「声明为 ACK」且 body 仍是 bytes（若走 JSON 解压则已是 dict，不是本分支）
    if message_type == "SERVER_ACK" and isinstance(raw, bytes):
        # TODO:ack的其他情况未知。在下面进行兜底。按理说不会出现。
        return TTSResponse(
            message_type=message_type,
            session_id=session_id,
            payload_size=payload_size,
            wire_event_code=code_int,
            payload=AudioBinaryPayload(data=raw),
        )

    # 传输层错误帧：整帧语义就是「出错」，不按 event 表细分
    if message_type == "SERVER_ERROR_RESPONSE":
        return ServerErrorResponse(
            message_type=message_type,
            session_id=session_id,
            payload_size=payload_size,
            payload=UnknownPayload(
                data={
                    "code": int(data.get("code", 0)),
                    "payload_msg": raw,
                    "raw": data,
                }
            ),
        )

    # 能按「文档 JSON 事件表」解析的前置条件：必须是 FULL_RESPONSE，且头里带了整型 event。
    # 否则包括：空 message_type、ACK 已处理完仍落到这（不应发生）、字符串 event、协议升级等 → 一律兜底。
    if message_type != "SERVER_FULL_RESPONSE" or not isinstance(code_int, int):
        return UnmappedServerEvent(
            message_type=message_type,
            session_id=session_id,
            payload_size=payload_size,
            wire_event_code=code_int,
            payload=UnknownPayload(data=dict(data)),
        )

    # FULL_RESPONSE：见函数 docstring——raw 可能非 dict（协议层多种序列化 + json.loads 顶层类型）。
    if not isinstance(raw, dict):
        return UnmappedServerEvent(
            message_type=message_type,
            session_id=session_id,
            payload_size=payload_size,
            wire_event_code=code_int,
            payload=UnknownPayload(data={"payload_msg": raw}),
        )

    # 以下为「标准 JSON 业务事件」：event 码与文档一致，未列出的码走 default，仍保留 raw 便于排查
    match code_int:
        case 50:
            root = ConnectionStarted(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=EmptyPayload.model_validate(raw),
            )
        case 51:
            root = ConnectionFailed(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=ConnectionFailedPayload.model_validate(raw),
            )
        case 52:
            root = ConnectionFinished(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=EmptyPayload.model_validate(raw),
            )
        case 150:
            root = SessionStarted(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=SessionStartedPayload.model_validate(raw),
            )
        case 152:
            root = SessionFinished(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=EmptyPayload.model_validate(raw),
            )
        case 153:
            root = SessionFailed(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=SessionFailedPayload.model_validate(raw),
            )
        case 154:
            root = UsageResponse(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=UsagePayload.model_validate(raw),
            )
        case 251:
            root = ConfigUpdated(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=EmptyPayload.model_validate(raw),
            )
        case 350:
            root = TTSSentenceStart(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=TtsTextAcceptedPayload.model_validate(raw),
            )
        case 351:
            root = TTSSentenceEnd(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=TtsTextFinishedPayload.model_validate(raw),
            )
        case 359:
            root = TTSEnded(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=TtsEndedPayload.model_validate(raw),
            )
        case 450:
            root = ASRInfo(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=AsrInfoPayload.model_validate(raw),
            )
        case 451:
            # 转换为ASRDelta或ASRFinal
            root = asr451_to_delta_or_final(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                raw=raw,
            )
        case 459:
            root = ASREnded(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=EmptyPayload.model_validate(raw),
            )
        case 550:
            root = ChatResponse(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=TextDeltaPayload.model_validate(raw),
            )
        case 553:
            root = ChatTextQueryConfirmed(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=QuestionStartedPayload.model_validate(raw),
            )
        case 559:
            root = ChatEnded(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=ReplyFinishedPayload.model_validate(raw),
            )
        case 567:
            root = ConversationCreated(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=UnknownPayload(data=dict(raw)),
            )
        case 568:
            root = ConversationUpdated(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=UnknownPayload(data=dict(raw)),
            )
        case 569:
            root = ConversationRetrieved(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=UnknownPayload(data=dict(raw)),
            )
        case 570:
            root = ConversationTruncated(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=EmptyPayload.model_validate(raw),
            )
        case 571:
            root = ConversationDeleted(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=UnknownPayload(data=dict(raw)),
            )
        case 599:
            root = DialogCommonError(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                payload=DialogCommonErrorPayload.model_validate(raw),
            )
        case _:
            # 服务端发了表里有、但本客户端尚未建模的码，或将来新增码：保留整包 raw 方便日志/升级
            root = UnmappedServerEvent(
                message_type=message_type,
                session_id=session_id,
                payload_size=payload_size,
                wire_event_code=code_int,
                payload=UnknownPayload(data=dict(raw)),
            )
    return root


class EventColorMap:
    INFO = "bright_cyan"
    START = "bold green"
    DONE = "bold green"
    STREAM = "bright_blue"
    HINT = "yellow"
    ERROR = "bold red"


class ServerEventPrinter:
    """统一打印服务端事件。
    #TODO：需仔细考虑打印的时机和内容。需要优化，特别是那个asr"""

    def __init__(self, show_audio_binary: bool = True) -> None:
        self.print = print
        self.show_audio_binary = show_audio_binary
        self._in_text_stream = False

    def _close_text_stream_if_needed(self) -> None:
        if self._in_text_stream:
            self.print("")
            self._in_text_stream = False

    def __call__(self, server_notify: S2sServerNotify) -> None:
        def emit(content: str, style: str) -> None:
            self._close_text_stream_if_needed()
            self.print(Text("\n") + Text(content, style=style))

        match server_notify:
            case TTSResponse():
                if not self.show_audio_binary:
                    return
                emit(f"🔊 TTSResponse | size={server_notify.payload.size}", EventColorMap.STREAM)

            case ServerErrorResponse():
                emit(f"❌ ServerErrorResponse | {server_notify.payload}", EventColorMap.ERROR)

            case UnmappedServerEvent():
                if server_notify.message_type not in ("SERVER_FULL_RESPONSE", "SERVER_ERROR_RESPONSE", "SERVER_ACK"):
                    emit(f"ℹ️ 非标准包 | message_type={server_notify.message_type} payload={server_notify.payload}", EventColorMap.HINT)
                else:
                    emit(f"ℹ️ 未映射事件码或载荷异常 | wire_event_code={server_notify.wire_event_code} data={server_notify.payload.data}", EventColorMap.HINT)

            case ConnectionStarted():
                emit("🔗 ConnectionStarted", EventColorMap.START)

            case ConnectionFailed():
                emit(f"❌ ConnectionFailed | error={server_notify.payload.error}", EventColorMap.ERROR)

            case ConnectionFinished():
                emit("🔌 ConnectionFinished", EventColorMap.DONE)

            case SessionStarted():
                emit(f"✅ SessionStarted | dialog_id={server_notify.payload.dialog_id}", EventColorMap.START)

            case SessionFinished():
                emit("🛑 SessionFinished", EventColorMap.DONE)

            case SessionFailed():
                emit(f"❌ SessionFailed | error={server_notify.payload.error}", EventColorMap.ERROR)
            
            case UsageResponse():
                emit(f"📊 UsageResponse | usage={server_notify.payload.usage}", EventColorMap.HINT)

            case ConfigUpdated():
                emit("⚙️ ConfigUpdated", EventColorMap.HINT)

            case TTSSentenceStart():
                emit(f"🗣️ TTSSentenceStart | tts_type={server_notify.payload.tts_type} text={server_notify.payload.text}", EventColorMap.INFO)

            case TTSSentenceEnd():
                emit("🧾 TTSSentenceEnd", EventColorMap.DONE)

            case TTSEnded():
                emit(f"🔚 TTSEnded | no_content={server_notify.payload.no_content}", EventColorMap.DONE)

            case ASRInfo():
                emit(f"🎙️ ASRInfo | question_id={server_notify.payload.question_id}", EventColorMap.START)

            case ASRFinal():
                emit(f"🎤 ASRFinal | {server_notify.payload.text}", EventColorMap.STREAM)
            case ASRDelta():
                emit(f"🎤 ASRDelta | {server_notify.payload.text}", EventColorMap.STREAM)

            case ASREnded():
                emit("⏹️ ASREnded", EventColorMap.DONE)

            case ASR451NoText():
                # TODO：服务端会有451的包，但是没有文本
                return

            case ChatResponse():
                if not self._in_text_stream:
                    self.print(Text("\n") + Text("《S2S内部模型回复的文本》", style=EventColorMap.HINT))
                self._in_text_stream = True
                self.print(Text(str(server_notify.payload.content), style=EventColorMap.STREAM), end="", flush=True)
            
            case ChatTextQueryConfirmed():
                emit(f"🧠 ChatTextQueryConfirmed | question_id={server_notify.payload.question_id}", EventColorMap.INFO)

            case ChatEnded():
                emit(f"✅ ChatEnded | reply_id={server_notify.payload.reply_id}", EventColorMap.DONE)

            case ConversationCreated() | ConversationUpdated() | ConversationRetrieved() | ConversationDeleted():
                emit(f"💬 {server_notify.type} | data={server_notify.payload.data}", EventColorMap.HINT)

            case ConversationTruncated():
                emit("✂️ ConversationTruncated", EventColorMap.HINT)

            case DialogCommonError():
                emit(f"❌ DialogCommonError | {server_notify.payload.status_code} {server_notify.payload.message}", EventColorMap.ERROR)

            case _:
                assert_never(server_notify)
