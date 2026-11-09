"""
奔驰 S2S WebSocket 语音服务适配器（AnyBotToTest 实现）。

将 ``S2S.py`` 中的文本注入 + dm.output 流式拼接逻辑封装为可被
``AutoTestAndRLDataGenerator`` 调用的 bot：单次 ``achat(query)`` 对应一次
asr.speech.sentence 请求，合并该轮全部流式文本后作为 assistant 回复返回。
"""

import asyncio
import json
import uuid
import websockets
from asgiref.sync import async_to_sync

from projects.mind.test_backend.service.task.base_agent_bot import AgentDumpTrace

DEFAULT_WS_URL = "ws://101.126.11.190/voice-manager-benz/voice/ws"
DEFAULT_X_APP_ID = "extour-inc"
DEFAULT_X_ACCESS_KEY = "REDACTED"
DEFAULT_X_DEVICE_ID = "LE4AG4CB2SL611680"
DEFAULT_VOICE_PRINT_ID = "test_user_stream"
DEFAULT_RESPONSE_TIMEOUT_SEC = 45.0
DEFAULT_TTS_AUDIO_QUIET_SEC = 2.0
# 基础 TTS 尾段预算；长故事会再按文本长度 / 已收音频包数追加（见 _calc_tail_budget）
DEFAULT_TTS_TAIL_BUDGET_SEC = 15.0
DEFAULT_TTS_TAIL_MAX_BUDGET_SEC = 120.0
DEFAULT_ROUND_GAP_SEC = 1.0
DEFAULT_GOODBYE_RESPONSE_TIMEOUT_SEC = 5.0
GOODBYE_QUERY_MARKERS = ("退下", "再见", "拜拜")

# 与 S2S 调试脚本共用：文本增量规整打印开关
NEAT_STREAM_OUTPUT = True


def _as_dict(parent: dict, key: str) -> dict:
    val = parent.get(key)
    return val if isinstance(val, dict) else {}


def _json_text(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _extract_nlg_text(dm: dict) -> str:
    """NLG 原样：字符串直出，dict/list 用 JSON。"""
    pieces = []
    nlg = dm.get("nlg")
    if nlg is not None and nlg != "":
        pieces.append(_json_text(nlg))
    custom_nlg = dm.get("customNlg")
    if custom_nlg is not None:
        pieces.append(json.dumps(custom_nlg, ensure_ascii=False))
    return "\n".join(pieces)


def _is_stream_only_command(cmd: dict) -> bool:
    """仅 aiSprite 流式片段，不算最终车控/技能指令。"""
    param = _as_dict(cmd, "param")
    if "aiSprite" not in param:
        return False
    other_keys = set(param.keys()) - {"aiSprite", "customInnerType", "mvaReaction"}
    return not other_keys


def _extract_command_text(dm: dict) -> str:
    """指令块原样 JSON（整段 command）；流式中间包跳过。"""
    cmd = dm.get("command")
    if not isinstance(cmd, dict) or not cmd:
        intent_api = dm.get("intentApi", "")
        param = dm.get("param")
        if intent_api or param is not None:
            return json.dumps(
                {"intentApi": intent_api, "param": param},
                ensure_ascii=False,
            )
        return ""
    if _is_stream_only_command(cmd):
        return ""
    return json.dumps(cmd, ensure_ascii=False)


def _extract_stream_fields(dm: dict) -> tuple[str, str]:
    """大模型流式片段：仅处理 aiSprite。"""
    param = _as_dict(_as_dict(dm, "command"), "param")
    ai_sprite = _as_dict(param, "aiSprite")
    stream_type = ai_sprite.get("streamType", "")
    data_obj = _as_dict(ai_sprite, "data")
    chunk = data_obj.get("content") or data_obj.get("speakText") or ""
    return stream_type, chunk


class S2SReplyCollector:
    """累积单轮 dm.output：流式文本 + 多条指令 JSON + NLG（多意图按序拼接）。"""

    def __init__(self):
        self.parts = []
        self.command_texts = []
        self.nlg_texts = []
        self.reply_segments = []
        self.input_text = ""
        self.stream_done = False
        self.streaming_multi_intent = False
        self.dm_output_received = False
        self.last_msg_time = 0.0
        self.last_dm_time = 0.0
        self.audio_count = 0
        self.raw_messages = []

    @staticmethod
    def _append_unique(items: list, value: str):
        if value and (not items or items[-1] != value):
            items.append(value)

    def _track_segment(self, bucket: list, text: str):
        self._append_unique(bucket, text)
        if text:
            self._append_unique(self.reply_segments, text)

    def feed(self, data):
        # TODO：topic 的类型全集未知，且无规范，目前只关心 dm.output 和 tts.audio。这里需要根据实际情况进行修改。
        topic = data.get("topic", "")
        if topic == "tts.audio":
            self.audio_count += 1
            return
        if topic != "dm.output":
            return

        self.dm_output_received = True
        self.raw_messages.append(data)
        dm = _as_dict(data, "dm")
        if dm.get("streamingMultiIntent"):
            self.streaming_multi_intent = True

        stream_type, chunk = _extract_stream_fields(dm)
        self.last_dm_time = asyncio.get_event_loop().time()

        input_text = dm.get("orthography", "") or dm.get("input", "")
        if not self.input_text and input_text:
            self.input_text = input_text

        self._track_segment(self.command_texts, _extract_command_text(dm))
        self._track_segment(self.nlg_texts, _extract_nlg_text(dm))

        if stream_type == "prestart":
            self.parts = []
        if chunk and stream_type in ("start", "intermediate"):
            self.parts.append(chunk)
        if stream_type in ("done", "streamDone") or data.get("end"):
            self.stream_done = True

    def build_answer(self, *, goodbye_query: bool = False) -> str:
        segments = []
        stream_text = "".join(self.parts)
        if stream_text:
            segments.append(stream_text)
        segments.extend(self.reply_segments)
        if segments:
            return "\n".join(segments)
        if goodbye_query or self.dm_output_received:
            return "（助手已结束会话）"
        return "（助手返回为空）"

    def has_answer_content(self) -> bool:
        return bool("".join(self.parts) or self.reply_segments)

    def print_neat_if_enabled(self):
        if not NEAT_STREAM_OUTPUT:
            return
        print("\n" + "-" * 60)
        print("[SERVER] dm.output")
        if self.input_text:
            print(f"  input: {self.input_text}")
        stream_text = "".join(self.parts)
        if stream_text:
            print(f"  AI回复: {stream_text}")
        for i, cmd in enumerate(self.command_texts, 1):
            print(f"  指令{i}: {cmd}")
        for i, nlg in enumerate(self.nlg_texts, 1):
            print(f"  NLG{i}: {nlg}")
        if self.audio_count:
            print(f"[SERVER] 收到音频 x{self.audio_count}")
        print("-" * 60)


class S2SVoiceBot:
    """奔驰 S2S WebSocket 被测 Bot，实现 AnyBotToTest 协议。

    连接生命周期：
    - 同一 case（同一 bot 实例）内所有 ``achat`` 共用一条 WebSocket；
    - 框架每次 ``aauto_chat_test`` 会换 ``session_id``，此处**不重连**，仅清空本段对话的
      ``turn_records``；
    - 下一个 case ``create()`` 新实例前，会关闭上一条 WS。
    """

    _active_bot: "S2SVoiceBot | None" = None
    _pending_ws_close_tasks: list[asyncio.Task] = []

    def __init__(self, context_config: dict):
        self._context_config = dict(context_config)
        self.ws_url = str(
            context_config.get("s2s_ws_url", DEFAULT_WS_URL)
        ).strip()
        self.x_app_id = str(
            context_config.get("s2s_x_app_id", DEFAULT_X_APP_ID)
        ).strip()
        self.x_access_key = str(
            context_config.get("s2s_x_access_key", DEFAULT_X_ACCESS_KEY)
        ).strip()
        self.x_device_id = str(
            context_config.get("s2s_x_device_id", DEFAULT_X_DEVICE_ID)
        ).strip()
        self.voice_print_id = str(
            context_config.get("voice_print_id")
            or context_config.get("user_id")
            or DEFAULT_VOICE_PRINT_ID
        ).strip()
        self.response_timeout_sec = float(
            context_config.get("s2s_response_timeout_sec", DEFAULT_RESPONSE_TIMEOUT_SEC)
        )
        self.tts_audio_quiet_sec = float(
            context_config.get("s2s_tts_audio_quiet_sec", DEFAULT_TTS_AUDIO_QUIET_SEC)
        )
        self.tts_tail_budget_sec = float(
            context_config.get("s2s_tts_tail_budget_sec", DEFAULT_TTS_TAIL_BUDGET_SEC)
        )
        self.tts_tail_max_budget_sec = float(
            context_config.get(
                "s2s_tts_tail_max_budget_sec", DEFAULT_TTS_TAIL_MAX_BUDGET_SEC
            )
        )
        self.round_gap_sec = float(
            context_config.get("s2s_round_gap_sec", DEFAULT_ROUND_GAP_SEC)
        )
        self.goodbye_response_timeout_sec = float(
            context_config.get(
                "s2s_goodbye_response_timeout_sec",
                DEFAULT_GOODBYE_RESPONSE_TIMEOUT_SEC,
            )
        )

        # 框架 aauto_chat_test 的 session_id（每段多轮会变）
        self.framework_session_id = None
        # 奔驰 S2S WS sessionId（整个 case 内固定）
        self.s2s_session_id = None
        self.session_id = None
        self.query = None
        self.last_answer = None

        self.turn_records: list[dict[str, str]] = []
        self.state_trace: list[dict] = []

        self._ws = None
        self._chat_lock = asyncio.Lock()
        self._record_id = (
            "89b2732723d143528451acab860352b1:e5fc8865216a44099f54b61774928278:"
            "0615e89724094ab6973e93edd140044f"
        )

    def _ws_connect_kwargs(self) -> dict:
        return {
            "additional_headers": {
                "X-App-ID": self.x_app_id,
                "X-Access-Key": self.x_access_key,
                "X-Device-ID": self.x_device_id,
            }
        }

    def _reset_dialogue_block_records(self):
        """新一段 aauto_chat_test 开始时清空本段 adump_history，但不关 WS。"""
        self.turn_records = []
        self.last_answer = None

    @staticmethod
    def _is_goodbye_query(query: str) -> bool:
        return any(marker in query for marker in GOODBYE_QUERY_MARKERS)

    def _is_audio_quiet(self, collector: S2SReplyCollector) -> bool:
        loop = asyncio.get_event_loop()
        now = loop.time()
        if collector.streaming_multi_intent:
            return now - collector.last_dm_time >= self.tts_audio_quiet_sec
        return now - collector.last_msg_time >= self.tts_audio_quiet_sec

    def _calc_tail_budget(self, collector: S2SReplyCollector) -> float:
        """长文 / 多音频包时放宽 TTS 尾段，避免文本已齐仍被 8s 默认预算误判超时。"""
        budget = self.tts_tail_budget_sec
        if collector.streaming_multi_intent:
            budget += 4.0
        stream_text = "".join(collector.parts)
        # 朗读约 4~6 字/秒，按 5 字/秒估时长并加缓冲
        budget += min(len(stream_text) / 5.0, 90.0)
        # 已在途 tts.audio 包，粗估 ~80ms/包
        budget += min(collector.audio_count * 0.08, 60.0)
        return min(budget, self.tts_tail_max_budget_sec)

    async def aclose_ws_connection(self) -> None:
        """关闭 WS（下一个 case create 前或 case 结束时调用）。"""
        await self._close_ws()
        self.s2s_session_id = None
        self.framework_session_id = None
        self.session_id = None

    async def _close_ws(self):
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _open_ws_and_start_session(self, s2s_session_id: str):
        self._ws = await websockets.connect(
            self.ws_url,
            **self._ws_connect_kwargs(),
        )
        start_msg = {
            "topic": "recorder.stream.start",
            "recordId": uuid.uuid4().hex,
            "sessionId": s2s_session_id,
            "asrParams": {"realBack": True},
            "nluParams": {
                "enableNLPEmotion": True,
                "enableEarlyResult": True,
                "enableNBest": True,
            },
            "audio": {
                "audioType": "ogg_opus",
                "sampleRate": 16000,
                "sampleBytes": 2,
                "channel": 1,
            },
            "context": {
                "attributes": {"voicePrintId": self.voice_print_id},
            },
        }
        await self._ws.send(json.dumps(start_msg, ensure_ascii=False))

    def _build_query_msg(self, query: str, s2s_session_id: str) -> dict:
        return {
            "contextId": s2s_session_id,
            "pinyin": "jin tian tian qi zen me yang",
            "sentenceBeginTime": 0,
            "recordId": self._record_id,
            "topic": "asr.speech.sentence",
            "sentenceEndTime": 1640,
            "nbest": [{"text": query}],
            "languageClass": "putonghua",
            "context": {
                "cloudVadEnd": 1774928279558,
                "cloudVadBegin": 1774928278381,
                "asrLastDuration": 187,
                "wordsEnd": True,
                "rec": query,
                "asrChoice": "mix",
            },
            "sentence": query,
            "requestId": uuid.uuid4().hex,
            "conf": 0.715,
            "sessionId": s2s_session_id,
            "ortho": 0,
            "nbest_formatted": [query],
        }

    def _handle_ws_message(self, response, collector: S2SReplyCollector) -> bool:
        """处理单条 WS 消息；若协议层 end=true 则返回 True 表示可结束。"""
        collector.last_msg_time = asyncio.get_event_loop().time()

        if not isinstance(response, str):
            if not NEAT_STREAM_OUTPUT:
                print(f"[SERVER] 二进制数据: {len(response)} bytes")
            return False

        data = json.loads(response)
        if not NEAT_STREAM_OUTPUT:
            topic = data.get("topic", "")
            if topic == "tts.audio":
                print("[SERVER] 收到音频")
            else:
                print(f"[SERVER] 收到响应: {response}")

        collector.feed(data)
        return bool(data.get("end", False))

    async def _recv_until_deadline(
        self,
        deadline: float,
        collector: S2SReplyCollector,
        *,
        recv_chunk_timeout: float = 1.0,
        stop_on_stream_done: bool = False,
        wait_for_quiet: bool = False,
        stop_on_dm_received: bool = False,
    ) -> bool:
        """在 deadline 前收消息；可选 streamDone / 静默 / end=true 作为结束条件。"""
        assert self._ws is not None, "WebSocket 未连接"
        loop = asyncio.get_event_loop()
        while loop.time() < deadline:
            if stop_on_stream_done and collector.stream_done:
                return True
            if stop_on_dm_received and collector.dm_output_received:
                return True
            if wait_for_quiet and self._is_audio_quiet(collector):
                return True

            timeout = min(recv_chunk_timeout, deadline - loop.time())
            if timeout <= 0:
                break

            try:
                response = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                if wait_for_quiet and self._is_audio_quiet(collector):
                    return True
                continue

            if self._handle_ws_message(response, collector):
                return True
            if stop_on_stream_done and collector.stream_done:
                return True
            if stop_on_dm_received and collector.dm_output_received:
                return True

        if wait_for_quiet:
            return self._is_audio_quiet(collector)
        return False

    async def _collect_response(
        self, collector: S2SReplyCollector, *, goodbye_query: bool = False
    ) -> tuple[bool, bool]:
        """
        两阶段等待：
        1) 文本阶段：等 dm.output / streamDone（预算 response_timeout_sec）；
        2) TTS 尾段：streamDone 后再等音频静默（预算随文本/音频包动态放大）。

        告别语轮次用短超时且跳过 TTS 尾段（服务端常不回 dm.output）。

        返回 (整体是否成功, TTS 尾段是否在预算内等到静默)。
        """
        loop = asyncio.get_event_loop()
        text_timeout = (
            self.goodbye_response_timeout_sec
            if goodbye_query
            else self.response_timeout_sec
        )
        await self._recv_until_deadline(
            loop.time() + text_timeout,
            collector,
            stop_on_stream_done=not goodbye_query,
            stop_on_dm_received=goodbye_query,
        )

        if goodbye_query:
            return True, True

        if not collector.dm_output_received:
            return False, False

        if not collector.stream_done:
            return True, True

        tail_budget = self._calc_tail_budget(collector)
        tail_ok = await self._recv_until_deadline(
            loop.time() + tail_budget,
            collector,
            recv_chunk_timeout=0.5,
            wait_for_quiet=True,
        )
        if tail_ok:
            return True, True

        # 文本已齐：追加 drain，尽量收完残留 tts.audio，避免污染下一轮 WS
        if collector.has_answer_content():
            drain_ok = await self._recv_until_deadline(
                loop.time() + min(60.0, self.tts_tail_max_budget_sec),
                collector,
                recv_chunk_timeout=0.5,
                wait_for_quiet=True,
            )
            return True, drain_ok

        return False, False

    async def _send_query_and_collect(self, query: str) -> str:
        assert self._ws is not None, "WebSocket 未连接"
        assert self.s2s_session_id is not None, "S2S session 未初始化"
        # 解析器。
        collector = S2SReplyCollector()
        query_msg = self._build_query_msg(query, self.s2s_session_id)
        await self._ws.send(json.dumps(query_msg, ensure_ascii=False))

        goodbye_query = self._is_goodbye_query(query)
        ok, tts_tail_quiet = await self._collect_response(
            collector, goodbye_query=goodbye_query
        )
        if NEAT_STREAM_OUTPUT:
            collector.print_neat_if_enabled()

        if not ok:
            answer = (
                "（助手已结束会话）" if goodbye_query else "（S2S 等待响应超时）"
            )
        else:
            answer = collector.build_answer(goodbye_query=goodbye_query)

        self.state_trace.append(
            {
                "query": query,
                "answer": answer,
                "stream_done": collector.stream_done,
                "streaming_multi_intent": collector.streaming_multi_intent,
                "dm_output_received": collector.dm_output_received,
                "tts_tail_quiet": tts_tail_quiet,
                "audio_count": collector.audio_count,
                "command_texts": list(collector.command_texts),
                "nlg_texts": list(collector.nlg_texts),
                "raw_dm_messages": collector.raw_messages,
            }
        )
        return answer

    async def aupdate_context(self, context_config: dict) -> None:
        self._context_config.update(context_config)
        voice_print_id = context_config.get("voice_print_id") or context_config.get(
            "user_id"
        )
        if voice_print_id:
            self.voice_print_id = str(voice_print_id).strip()

    async def achat(self, query: str, session_id: str) -> str:
        self.query = query
        self.session_id = session_id

        async with self._chat_lock:
            await self._await_pending_ws_closes()

            if self._ws is None:
                self.framework_session_id = session_id
                self.s2s_session_id = uuid.uuid4().hex
                await self._open_ws_and_start_session(self.s2s_session_id)
            else:
                if (
                    self.framework_session_id is not None
                    and self.framework_session_id != session_id
                ):
                    self.framework_session_id = session_id
                    self._reset_dialogue_block_records()
                if self.round_gap_sec > 0 and not self._is_goodbye_query(query):
                    await asyncio.sleep(self.round_gap_sec)

            answer = await self._send_query_and_collect(query)
            if self._is_goodbye_query(query):
                await self.aclose_ws_connection()
            self.last_answer = answer
            self.turn_records.append({"role": "user", "content": query})
            self.turn_records.append({"role": "assistant", "content": answer})
            return answer

    def chat(self, query: str, session_id: str) -> str:
        return async_to_sync(self.achat)(query, session_id)

    async def adump_history(self) -> list[dict[str, str]]:
        return list(self.turn_records)

    def dump_history(self) -> list[dict[str, str]]:
        return async_to_sync(self.adump_history)()

    async def adump_state_trace(self) -> dict:
        trace = AgentDumpTrace(
            system_prompt=None,
            session_id=self.session_id or "",
            query=self.query or "",
            answer=self.last_answer or "",
            traces=self.state_trace,
            metadata={
                "s2s_session_id": self.s2s_session_id,
                "voice_print_id": self.voice_print_id,
                "ws_url": self.ws_url,
            },
        )
        return trace.model_dump()

    async def dump_state_trace(self) -> dict:
        return await self.adump_state_trace()

    @classmethod
    def _release_active_bot_ws(cls) -> None:
        """同步 create() 内释放上一个 case 的 WS（评测在 async 循环里调 create，不能 async_to_sync）。"""
        if cls._active_bot is None:
            return
        old = cls._active_bot
        ws = old._ws
        old._ws = None
        old.s2s_session_id = None
        old.framework_session_id = None
        old.session_id = None
        if ws is None:
            return

        async def _close_ws_task() -> None:
            await ws.close()

        try:
            loop = asyncio.get_running_loop()
            cls._pending_ws_close_tasks.append(loop.create_task(_close_ws_task()))
        except RuntimeError:
            async_to_sync(_close_ws_task)()

    @classmethod
    async def _await_pending_ws_closes(cls) -> None:
        pending = list(cls._pending_ws_close_tasks)
        cls._pending_ws_close_tasks.clear()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    @classmethod
    def create(cls, context_config: dict, *args, **kwargs) -> "S2SVoiceBot":
        cls._release_active_bot_ws()
        merged = {**context_config, **kwargs}
        bot = cls(merged)
        cls._active_bot = bot
        return bot

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict | None = None,
        except_skills: bool = False,
    ) -> None:
        # S2S 远端记忆由 voicePrintId / deviceId 管理，评测侧无需清火山库
        return None
