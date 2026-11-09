"""
本文件是S2S客户端的实现，用于与S2S服务器进行通信。
主要功能包括：
1. 建立WebSocket连接
2. 发送StartConnection请求
3. 发送StartSession请求
4. 发送SayHello请求
5. 发送ChatTextQuery请求
6. 发送ChatTtsText请求
7. 发送ChatRagText请求
"""

import gzip
import json
from enum import IntEnum

import websockets
from websockets.asyncio.client import ClientConnection
from pydantic import BaseModel, Field
import uuid

from projects.experiments.s2s import config as app_config
from projects.experiments.s2s import protocol
from projects.experiments.s2s.event import S2sServerNotify, parse_s2s_protocol_message


class ClientWireCode(IntEnum):
    """客户端发送的二进制帧事件码"""

    StartConnection = 1
    FinishConnection = 2
    StartSession = 100
    FinishSession = 102
    TaskRequest = 200
    SayHello = 300
    ChatTTSText = 500
    ChatTextQuery = 501
    ChatRAGText = 502


class RealtimeClientOptions(BaseModel):
    ws_config: app_config.WsConnectConfigModel = Field(default=app_config.ws_connect_config)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="会话ID")


class RequestEncodeOptions(BaseModel):
    """请求编码选项"""
    include_session_id: bool = True
    message_type: int = protocol.CLIENT_FULL_REQUEST
    serial_method: int = protocol.JSON


class EmptyRequestPayload(BaseModel):
    pass


class SayHelloRequest(BaseModel):
    content: str


class ChatTextQueryRequest(BaseModel):
    content: str


class ChatTtsTextRequest(BaseModel):
    start: bool
    end: bool
    content: str


class ChatRagItem(BaseModel):
    title: str
    content: str


class ChatRagTextRequest(BaseModel):
    # 协议要求 external_rag 是 JSON 数组字符串，数组元素包含 title/content。
    external_rag: str

    @classmethod
    def from_rag_items(cls, rag_items: list[ChatRagItem]) -> "ChatRagTextRequest":
        serialized_items = [item.model_dump() for item in rag_items]
        return cls(external_rag=json.dumps(serialized_items, ensure_ascii=False))


class RealtimeDialogClient:
    def __init__(
        self,
        options: RealtimeClientOptions | None = None,
        start_session_req: app_config.StartSessionReqModel | None = None,
    ) -> None:
        if options is None:
            options = RealtimeClientOptions()
        self.ws_config = options.ws_config
        self.session_id = options.session_id
        self.start_session_req = start_session_req
        self.ws: ClientConnection | None = None

    def _ws(self) -> ClientConnection:
        if self.ws is None:
            raise RuntimeError("WebSocket 连接尚未建立")
        return self.ws

    def _build_request(
        self,
        event_code: ClientWireCode,
        payload: BaseModel | bytes,
        encode_options: RequestEncodeOptions | None = None,
    ) -> bytes:
        options = encode_options or RequestEncodeOptions()
        request = bytearray(
            protocol.generate_header(
                message_type=options.message_type,
                serial_method=options.serial_method,
            )
        )
        request.extend(int(event_code).to_bytes(4, "big"))
        if options.include_session_id:
            session_bytes = self.session_id.encode()
            request.extend(len(session_bytes).to_bytes(4, "big"))
            request.extend(session_bytes)

        if isinstance(payload, bytes):
            payload_bytes = gzip.compress(payload)
        else:
            payload_data = payload.model_dump()
            payload_bytes = gzip.compress(json.dumps(payload_data).encode())
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        return bytes(request)

    async def _send_event(
        self,
        event_code: ClientWireCode,
        payload: BaseModel | bytes,
        encode_options: RequestEncodeOptions | None = None,
    ) -> None:
        request = self._build_request(event_code=event_code, payload=payload, encode_options=encode_options)
        await self._ws().send(request)

    async def open(self) -> None:
        """建立 WebSocket 连接。"""
        headers = self.ws_config.headers.model_dump(by_alias=True)
        self.ws = await websockets.connect(
            self.ws_config.base_url,
            additional_headers=headers,
            ping_interval=None,
        )
        response_headers = getattr(self._ws(), "response_headers", {})
        self.logid = response_headers.get("X-Tt-Logid", "")

    async def start_connection(self) -> None:
        # 初始化连接
        await self._send_event(
            event_code=ClientWireCode.StartConnection,
            payload=EmptyRequestPayload(),
            encode_options=RequestEncodeOptions(include_session_id=False),
        )
        await self._ws().recv()

    async def start_session(self, payload: app_config.StartSessionReqModel | None = None) -> None:
        # 初始化会话
        if payload is None:
            # 使用初始化时传入的配置，如果没有则使用默认配置
            payload = self.start_session_req or app_config.start_session_req
        await self._send_event(event_code=ClientWireCode.StartSession, payload=payload)
        await self._ws().recv()

    async def start(self) -> None:
        # 启动连接和会话
        await self.open()
        await self.start_connection()
        await self.start_session()

    async def send_say_hello(self, payload: SayHelloRequest) -> None:
        """发送播报欢迎语请求,一般用于在会话开始时播报欢迎语"""
        await self._send_event(event_code=ClientWireCode.SayHello, payload=payload)

    async def send_chat_text(self, payload: ChatTextQueryRequest) -> None:
        """文本触发类请求"""
        await self._send_event(event_code=ClientWireCode.ChatTextQuery, payload=payload)

    async def send_chat_tts_text(self, payload: ChatTtsTextRequest) -> None:
        """对话中播报文本请求，用于自定义回复内容"""
        await self._send_event(event_code=ClientWireCode.ChatTTSText, payload=payload)

    async def send_chat_rag_text(self, payload: ChatRagTextRequest) -> None:
        """发送外部RAG结果，服务端会基于内容总结后播报。"""
        await self._send_event(event_code=ClientWireCode.ChatRAGText, payload=payload)

    async def send_audio_chunk(self, chunk: bytes) -> None:
        """发送音频块请求，用于发送音频块数据"""
        await self._send_event(
            event_code=ClientWireCode.TaskRequest,
            payload=chunk,
            encode_options=RequestEncodeOptions(
                include_session_id=True,
                message_type=protocol.CLIENT_AUDIO_ONLY_REQUEST,
                serial_method=protocol.NO_SERIALIZATION,
            ),
        )

    async def receive_event(self) -> S2sServerNotify:
        # 接收服务器响应事件
        response = await self._ws().recv()
        # 协议解析器解析服务器响应内容
        data = protocol.parse_response(response)
        # 解析服务器响应为具体的事件模型
        return parse_s2s_protocol_message(data)

    async def stop_session(self) -> None:
        await self._send_event(event_code=ClientWireCode.FinishSession, payload=EmptyRequestPayload())

    async def stop_connection(self) -> None:
        await self._send_event(
            event_code=ClientWireCode.FinishConnection,
            payload=EmptyRequestPayload(),
            encode_options=RequestEncodeOptions(include_session_id=False),
        )
        await self._ws().recv()

    async def stop(self) -> None:
        await self.stop_session()
        await self.stop_connection()
        await self.close()

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()
