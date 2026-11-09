"""
本文件是音频管理器的实现，用于管理音频设备和音频队列,并处理服务器响应事件,状态切换等。
主要功能包括：
音频设备管理：输入流和输出流
    打开和关闭音频输入输出流
音频队列管理：
    将音频数据添加到队列中，并从队列中获取音频数据
服务器响应事件处理：
    处理服务器响应事件，并根据事件类型切换状态

数据链路（与本文件强相关）：
    上行麦克：process_microphone_input → RealtimeDialogClient.send_audio_chunk → WebSocket 二进制帧。
    下行事件：receive_loop recv → protocol.parse_response + parse_s2s_protocol_message → S2sServerNotify
              → handle_server_response（可选 ServerEventPrinter 打日志）。
    下行 PCM：TTSResponse.payload.data → audio_queue → _audio_player_loop → output_stream 扬声器。
    自定义 ChatTTSText 演示：见 _send_custom_tts_text 与 handle_server_response 内 ASREnded / TTSResponse / TTSSentenceStart 注释。
"""
import asyncio
import queue
import signal
import threading
import time
import uuid

import pyaudio
from pydantic import BaseModel, Field
from rich import print

from projects.experiments.s2s.config import AudioConfig, WsConnectConfigModel, input_audio_config, output_audio_config, ws_connect_config
from projects.experiments.s2s.event import (
    ASREnded,
    ASRInfo,
    ServerEventPrinter,
    ServerErrorResponse,
    SessionFailed,
    SessionFinished,
    S2sServerNotify,
    TTSEnded,
    TTSSentenceStart,
    TTSResponse,
)
from projects.experiments.s2s.realtime_dialog_client import (
    ChatTtsTextRequest,
    SayHelloRequest,
    RealtimeClientOptions,
    RealtimeDialogClient,
)

class AudioDeviceManager:
    """音频设备管理。"""

    def __init__(self, input_config: AudioConfig = input_audio_config, output_config: AudioConfig = output_audio_config) -> None:
        self.input_config = input_config
        self.output_config = output_config
        self.pyaudio = pyaudio.PyAudio()
        self.input_stream: pyaudio.Stream | None = None
        self.output_stream: pyaudio.Stream | None = None

    def open_input_stream(self) -> pyaudio.Stream:
        self.input_stream = self.pyaudio.open(
            format=self.input_config.bit_size,
            channels=self.input_config.channels,
            rate=self.input_config.sample_rate,
            input=True,
            frames_per_buffer=self.input_config.chunk,
        )
        return self.input_stream

    def open_output_stream(self) -> pyaudio.Stream:
        self.output_stream = self.pyaudio.open(
            format=self.output_config.bit_size,
            channels=self.output_config.channels,
            rate=self.output_config.sample_rate,
            output=True,
            frames_per_buffer=self.output_config.chunk,
        )
        return self.output_stream

    def cleanup(self) -> None:
        for stream in (self.input_stream, self.output_stream):
            if stream is not None:
                stream.stop_stream()
                stream.close()
        self.pyaudio.terminate()


class DialogSessionOptions(BaseModel):
    ws_config: WsConnectConfigModel = Field(default=ws_connect_config)
    use_event_printer: bool = Field(default=True)
    use_custom_text_tts_only: bool = Field(default=False, description="只使用自定义文本转TTS，不使用S2S内部闲聊文本和音频")


class SessionState(BaseModel):
    is_running: bool = Field(default=True, description="是否运行")
    is_recording: bool = Field(default=True, description="是否录音")
    is_playing: bool = Field(default=True, description="是否播放")
    is_session_finished: bool = Field(default=False, description="是否会话结束")
    is_user_querying: bool = Field(
        default=False,
        description="服务端 ASRInfo 置 True（用户正在说）；ASREnded 置 False。用于拦住 _send_custom_tts_text 与「说话中」互斥。",
    )
    is_sending_chat_tts_text: bool = Field(
        default=False,
        description="True：本端正在发 ChatTTSText 演示包，且 TTSResponse 一律丢弃直至 TTSSentenceStart(chat_tts_text) 对齐轨后清 False。",
    )


class DialogSession:
    """对话会话管理，仅支持麦克风输入。"""

    def __init__(
        self,
        ws_config: WsConnectConfigModel = ws_connect_config,
        use_event_printer: bool = True,
        use_custom_text_tts_only: bool = False,
        audio_device: AudioDeviceManager | None = None,
    ) -> None:
        self.options = DialogSessionOptions(
            ws_config=ws_config,
            use_event_printer=use_event_printer,
            use_custom_text_tts_only=use_custom_text_tts_only,
        )
        self.session_id = str(uuid.uuid4())
        self.client = RealtimeDialogClient(
            options=RealtimeClientOptions(
                ws_config=self.options.ws_config,
                session_id=self.session_id,
            )
        )

        self.state = SessionState()
        # 音频队列，用于存储音频数据
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        # 用于等待say_hello事件结束
        self.say_hello_over_event = asyncio.Event()
        # 仅 receive_loop 等业务路径上的服务端事件；握手调试打印在 RealtimeDialogClient 内
        self.event_printer = ServerEventPrinter(show_audio_binary=False) if self.options.use_event_printer else None

        self.audio_device: AudioDeviceManager = audio_device or AudioDeviceManager(input_audio_config, output_audio_config)
        self.audio_device.open_output_stream()
        # 初始化音频队列和输出流
        # True表示守护线程，当主线程结束时，守护线程也会结束
        self.player_thread = threading.Thread(target=self._audio_player_loop, daemon=True)
        self.player_thread.start()

        signal.signal(signal.SIGINT, self._keyboard_signal)

    def _keyboard_signal(self, sig, frame) -> None:
        print("receive keyboard Ctrl+C")
        self.stop()

    def stop(self) -> None:
        self.state.is_running = False
        self.state.is_recording = False
        self.state.is_playing = False

    def _clear_audio_queue(self) -> None:
        while not self.audio_queue.empty():
            # 清空整个音频队列
            self.audio_queue.get_nowait()

    def _audio_player_loop(self) -> None:
        while self.state.is_playing:
            try:
                # 从音频队列获取音频数据
                audio_data = self.audio_queue.get(timeout=1.0)
                if self.audio_device.output_stream is not None:
                    self.audio_device.output_stream.write(audio_data)
            except queue.Empty:
                # 队列为空时等待一小段时间
                time.sleep(0.1)
            except Exception as e:
                print(f"音频播放错误: {e}")
                time.sleep(0.1)

    async def _send_custom_tts_text(self, custom_contents: list[str] | None = None) -> None:
        """演示「只走自定义 ChatTTSText」时的数据链（与 handle_server_response 成对阅读）。

        触发：ASREnded 且 options.use_custom_text_tts_only → create_task 进入本协程。
        前置：is_sending_chat_tts_text 与 _clear_audio_queue 已在 ASREnded 分支同步完成，避免 create_task 与下一条
            TTSResponse 竞态导致旧 PCM 入队（尾音串音）。
        若首行发现 is_user_querying 已为 True（例如 ASRInfo 紧插在调度前），则 is_sending_chat_tts_text=False 后 return。

        链路：
            1) ASREnded 同步置 True + 清队列 → 此后下行 TTSResponse 一律丢弃，直到 TTSSentenceStart(chat_tts_text)。
            2) 连续 send_chat_tts_text → WebSocket 上行 JSON（ClientWireCode.ChatTTSText）→ 服务端合成。
            3) 服务端随后可能下发闲聊/其它 TTS 二进制；因步骤 1 仍丢弃，直到步骤 4。
            4) 服务端发 TTSSentenceStart 且 payload.tts_type == 'chat_tts_text' → handle_server_response 清队列并把
               is_sending_chat_tts_text=False → 后续 TTSResponse 恢复入队，扬声器播这条自定义轨的 PCM。

        风险：若服务端始终不发带 chat_tts_text 的 TTSSentenceStart，标志不会清，下行 PCM 会一直丢（demo 未兜底）。
        """
        if self.state.is_user_querying:
            self.state.is_sending_chat_tts_text = False
            return

        await self.client.send_chat_tts_text(ChatTtsTextRequest(start=True, end=False, content="这是第一轮TTS的开始和中间包事件，这两个合而为一了。"))

        await self.client.send_chat_tts_text(ChatTtsTextRequest(start=False, end=True, content="这是第一轮TTS的结束事件。"))
        # 模拟等待5秒
        await asyncio.sleep(5)
        await self.client.send_chat_tts_text(ChatTtsTextRequest(start=True, end=False, content="这里模拟agent1推理后，等待5秒,agent又开始返回内容了。"))
        await self.client.send_chat_tts_text(ChatTtsTextRequest(start=False, end=True, content="这里模拟agent2推理后,agent又开始返回内容了。"))

    def handle_server_response(self, server_notify: S2sServerNotify) -> None:
        """把「已解析的一条服务端通知」接到状态机 + 播放队列（与 receive_loop 串在同一条异步链路上）。"""
        if self.event_printer is not None:
            self.event_printer(server_notify)

        match server_notify:
            case TTSResponse():
                # 数据：server_notify.payload.data 为一段 PCM bytes。
                # 链路 A（自定义演示窗口）：is_sending_chat_tts_text True → 不入队直接 return（丢弃服务端任意下行音频，无法按帧区分轨）。
                # 链路 B（正常）：入 audio_queue → _audio_player_loop 写出扬声器；并累加到 audio_buffer 便于会话结束落盘。
                if self.state.is_sending_chat_tts_text:
                    return
                data = server_notify.payload.data
                self.audio_queue.put(data)

            case ServerErrorResponse():
                # 数据：错误信息在 payload（UnknownPayload）；播放侧无数据可清，直接停会话循环。
                self.stop()

            case ASRInfo():
                # 数据：服务端判定用户开始发声（首字等）；与下行 PCM 无直接字节关系，只驱动状态。
                # 链路：置 is_user_querying=True → _send_custom_tts_text 若已开丢弃窗会因互斥回滚标志并 return；清队列避免旧 PCM 与新轮次叠播。
                self.state.is_user_querying = True
                self._clear_audio_queue()

            case TTSSentenceStart():
                # TODO：这里的chat_tts_text状态是为了演示自定义文本场景，如果用S2S闲聊功能，可忽略。
                # 数据：payload 含 tts_type/text 等，标志服务端「这一句 TTS」的业务来源。
                # 链路（仅自定义演示）：is_sending_chat_tts_text 且 tts_type==chat_tts_text → 说明服务端已对齐到
                #   本端刚发的 ChatTTSText 合成句 → 清残留队列 → 关丢弃开关，使后续 TTSResponse 走「链路 B」入队播放。
                if self.state.is_sending_chat_tts_text and server_notify.payload.tts_type == "chat_tts_text":
                    self._clear_audio_queue()
                    self.state.is_sending_chat_tts_text = False

            case ASREnded():
                # 数据：一轮用户发声结束（无文本载荷也可）；标志可触发下游业务。
                # 链路：is_user_querying=False → 若 use_custom_text_tts_only：须同步 _clear_audio_queue + is_sending_chat_tts_text=True
                #   再 create_task，避免协程尚未运行时上一轮 TTSResponse 仍入队串音。
                self.state.is_user_querying = False
                if self.options.use_custom_text_tts_only:
                    self._clear_audio_queue()
                    self.state.is_sending_chat_tts_text = True
                    asyncio.create_task(self._send_custom_tts_text())

            case SessionFinished() | SessionFailed():
                self.state.is_session_finished = True
                self.stop()

            case TTSEnded():
                # 数据：一轮服务端 TTS 合成结束；与 say_hello 流程配合，释放 process_microphone_input 前的 wait。
                if not self.say_hello_over_event.is_set():
                    self.say_hello_over_event.set()

            case _:
                # ChatResponse、ConnectionStarted 等：与本音频管理无关，忽略即可。
                pass

    async def receive_loop(self) -> None:
        """WebSocket 下行：字节 → 模型 → handle_server_response；与麦克风上行 send_audio_chunk 并行。"""
        while self.state.is_running:
            server_notify = await self.client.receive_event()
            # 准备处理对应的事件
            self.handle_server_response(server_notify)

    async def process_microphone_input(self) -> None:
        # 用于等待say_hello事件结束
        await self.client.send_say_hello(SayHelloRequest(content="你好，我是豆包，有什么可以帮助你的？"))
        await self.say_hello_over_event.wait()
        input_stream = self.audio_device.open_input_stream()
        print("已打开麦克风，请讲话...")

        while self.state.is_recording:
            audio_data = input_stream.read(input_audio_config.chunk, exception_on_overflow=False)
            await self.client.send_audio_chunk(audio_data)
            await asyncio.sleep(0.01)

    async def start(self) -> None:
        await self.client.start()
        # 同时跑麦克风输入和接收服务器响应事件两个协程
        mic_task = asyncio.create_task(self.process_microphone_input())
        recv_task = asyncio.create_task(self.receive_loop())

        # 等待麦克风输入或接收服务器响应事件任意一个完成
        await asyncio.wait([mic_task, recv_task], return_when=asyncio.FIRST_COMPLETED)
        self.stop()

        # 先停掉收发任务，避免 stop_connection 与 receive_loop 并发 recv。
        mic_task.cancel()
        recv_task.cancel()
        await asyncio.gather(mic_task, recv_task, return_exceptions=True)

        await self.client.stop_session()
        await self.client.stop_connection()
        await self.client.close()
        self.audio_device.cleanup()
