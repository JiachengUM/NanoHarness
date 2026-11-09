from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from aicore.events.agent import (
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.v2.experiments.v2_frontend_voice import FrontendVoiceBridge
from projects.voice_test.schemas.events import (
    ASRDelta,
    ASREnded,
    ASRFinal,
    ASRInfo,
    AudioBinaryPayload,
    AsrInfoPayload,
    AsrTextPayload,
    EmptyPayload,
    TTSSentenceStart,
    TTSEnded,
    TTSResponse,
    TtsEndedPayload,
    TtsTextAcceptedPayload,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeRealtimeClient:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_session_count = 0
        self.stop_connection_count = 0
        self.close_count = 0
        self.audio_chunks: list[bytes] = []
        self.events: asyncio.Queue[Any] = asyncio.Queue()
        self.chat_tts_text_requests: list[Any] = []
        self.chat_text_query_requests: list[Any] = []

    async def start(self) -> None:
        self.start_count += 1

    async def send_audio_chunk(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)

    async def send_chat_tts_text(self, payload: Any) -> None:
        self.chat_tts_text_requests.append(payload)

    async def send_chat_text(self, payload: Any) -> None:
        self.chat_text_query_requests.append(payload)

    async def receive_event(self) -> Any:
        return await self.events.get()

    async def stop_session(self) -> None:
        self.stop_session_count += 1

    async def stop_connection(self) -> None:
        self.stop_connection_count += 1

    async def close(self) -> None:
        self.close_count += 1


def make_bridge(
    *,
    client: FakeRealtimeClient | None = None,
    sent_json: list[dict[str, Any]] | None = None,
    sent_audio: list[bytes] | None = None,
    submit_text: Callable[[str], Any] | None = None,
    commit_text: Callable[[dict[str, Any]], Any] | None = None,
) -> FrontendVoiceBridge:
    client = client or FakeRealtimeClient()
    sent_json = sent_json if sent_json is not None else []
    sent_audio = sent_audio if sent_audio is not None else []
    if submit_text is None:
        submit_text = lambda text: {
            "turn_id": "voice-turn-1",
            "text": text,
            "user_message_id": "voice-user-1",
            "assistant_message_id": "voice-assistant-1",
        }
    return FrontendVoiceBridge(
        submit_text=submit_text,
        send_json=sent_json.append,
        send_audio=sent_audio.append,
        session_id=lambda: "frontend-session",
        generation=lambda: 7,
        realtime_client_factory=lambda session_id: client,
        commit_text=commit_text,
    )


def asr_info() -> ASRInfo:
    return ASRInfo(message_type="server", payload=AsrInfoPayload())


def asr_delta(text: str) -> ASRDelta:
    return ASRDelta(message_type="server", payload=AsrTextPayload(text=text))


def asr_final(text: str) -> ASRFinal:
    return ASRFinal(message_type="server", payload=AsrTextPayload(text=text))


def asr_ended() -> ASREnded:
    return ASREnded(message_type="server", payload=EmptyPayload())


def tts_response(data: bytes) -> TTSResponse:
    return TTSResponse(message_type="server", payload=AudioBinaryPayload(data=data))


def tts_sentence_start(tts_type: str) -> TTSSentenceStart:
    return TTSSentenceStart(
        message_type="server",
        payload=TtsTextAcceptedPayload(tts_type=tts_type),
    )


def tts_ended() -> TTSEnded:
    return TTSEnded(
        message_type="server",
        payload=TtsEndedPayload(extra={}),
    )


async def wait_until(predicate: Callable[[], bool], *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    assert predicate()


async def submit_asr(bridge: FrontendVoiceBridge, text: str) -> None:
    await bridge._handle_server_event(asr_final(text))
    await bridge._handle_server_event(asr_ended())


@pytest.mark.anyio
async def test_start_and_stop_own_the_realtime_client() -> None:
    client = FakeRealtimeClient()
    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(client=client, sent_json=sent_json)

    ready = await bridge.start()

    assert ready == {
        "input_sample_rate": 16000,
        "output_sample_rate": 24000,
        "output_format": "f32le",
    }
    assert sent_json[0]["type"] == "voice.ready"
    await bridge.stop()
    assert (client.stop_session_count, client.stop_connection_count, client.close_count) == (
        1,
        1,
        1,
    )


@pytest.mark.anyio
async def test_microphone_forwards_audio_without_closing_between_turns() -> None:
    client = FakeRealtimeClient()
    bridge = make_bridge(client=client)

    await bridge.open_microphone()
    await bridge.feed_audio(b"first")
    await bridge.feed_audio(b"second")
    await wait_until(lambda: b"second" in client.audio_chunks)

    assert bridge.listening
    assert b"first" in client.audio_chunks
    await bridge.stop()


@pytest.mark.anyio
async def test_agent_text_is_queued_for_tts() -> None:
    client = FakeRealtimeClient()
    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(client=client, sent_json=sent_json)
    await bridge.start()

    bridge.on_agent_event(AgentOutTextStartEvent(), message_id="agent-1")
    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="你好"), message_id="agent-1")
    bridge.on_agent_event(AgentOutTextDoneEvent(), message_id="agent-1")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 2)

    assert [item.content for item in client.chat_tts_text_requests] == ["你好", ""]
    assert any(
        message["type"] == "voice.phase"
        and message["payload"] == {"phase": "speaking"}
        for message in sent_json
    )
    await bridge.stop()


@pytest.mark.anyio
async def test_barge_in_clears_queued_tts_and_frontend_playback() -> None:
    client = FakeRealtimeClient()
    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(client=client, sent_json=sent_json)
    await bridge.start()
    bridge.on_agent_event(AgentOutTextStartEvent(), message_id="agent-1")
    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="旧回复"), message_id="agent-1")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 1)
    bridge._frontend_playback_pending = True

    await bridge._handle_server_event(asr_info())

    assert not bridge._frontend_playback_pending
    assert bridge._active_tts_message_id is None
    assert any(
        message["type"] == "voice.interrupted"
        and message["payload"]["reason"] == "barge_in"
        for message in sent_json
    )
    await bridge.stop()


@pytest.mark.anyio
async def test_tts_interruption_closes_the_open_server_text_stream() -> None:
    client = FakeRealtimeClient()
    bridge = make_bridge(client=client)
    await bridge.start()
    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="旧回复"), message_id="agent-1")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 1)

    await bridge.interrupt_tts_output(reason="barge_in")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 2)

    end_request = client.chat_tts_text_requests[-1]
    assert end_request.start is False
    assert end_request.end is True
    assert end_request.content == ""
    await bridge.stop()


@pytest.mark.anyio
async def test_tts_after_interruption_plays_without_waiting_for_old_tts_ended() -> None:
    client = FakeRealtimeClient()
    sent_audio: list[bytes] = []
    bridge = make_bridge(client=client, sent_audio=sent_audio)
    await bridge.start()
    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="旧回复"), message_id="agent-1")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 1)
    await bridge._handle_server_event(tts_sentence_start("chat_tts_text"))
    await bridge._handle_server_event(tts_response(b"old"))

    await bridge.interrupt_tts_output(reason="barge_in")
    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="新回复"), message_id="agent-2")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 3)
    await bridge._handle_server_event(tts_sentence_start("chat_tts_text"))
    await bridge._handle_server_event(tts_response(b"new"))

    assert sent_audio == [b"old", b"new"]
    await bridge.stop()


@pytest.mark.anyio
async def test_late_interrupted_tts_end_does_not_stop_new_or_following_rounds() -> None:
    client = FakeRealtimeClient()
    sent_audio: list[bytes] = []
    bridge = make_bridge(client=client, sent_audio=sent_audio)
    await bridge.start()

    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="旧回复"), message_id="agent-1")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 1)
    await bridge._handle_server_event(tts_sentence_start("chat_tts_text"))
    await bridge._handle_server_event(tts_response(b"old"))
    await bridge.interrupt_tts_output(reason="barge_in")

    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="新回复"), message_id="agent-2")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 3)
    await bridge._handle_server_event(tts_sentence_start("chat_tts_text"))
    await bridge._handle_server_event(tts_ended())
    await bridge._handle_server_event(tts_response(b"new"))
    await bridge._handle_server_event(tts_ended())

    bridge.on_agent_event(
        AgentOutTextDeltaEvent(delta="后续回复"),
        message_id="agent-3",
    )
    await wait_until(
        lambda: any(
            request.content == "后续回复"
            for request in client.chat_tts_text_requests
        )
    )
    await bridge._handle_server_event(tts_sentence_start("chat_tts_text"))
    await bridge._handle_server_event(tts_response(b"later"))

    assert sent_audio == [b"old", b"new", b"later"]
    await bridge.stop()


@pytest.mark.anyio
async def test_only_agent_chat_tts_audio_is_forwarded() -> None:
    sent_audio: list[bytes] = []
    client = FakeRealtimeClient()
    bridge = make_bridge(client=client, sent_audio=sent_audio)
    await bridge.start()
    bridge.on_agent_event(AgentOutTextDeltaEvent(delta="回复"), message_id="agent-1")
    await wait_until(lambda: len(client.chat_tts_text_requests) == 1)

    await bridge._handle_server_event(tts_sentence_start("default"))
    await bridge._handle_server_event(tts_response(b"default"))
    await bridge._handle_server_event(tts_sentence_start("chat_tts_text"))
    await bridge._handle_server_event(tts_response(b"agent"))

    assert sent_audio == [b"agent"]
    await bridge.stop()


@pytest.mark.anyio
async def test_each_non_empty_final_is_committed_directly_in_order() -> None:
    committed: list[dict[str, Any]] = []
    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(
        sent_json=sent_json,
        commit_text=committed.append,
    )

    await submit_asr(bridge, "帮我查天气")
    await submit_asr(bridge, "好的")

    assert [item["text"] for item in committed] == ["帮我查天气", "好的"]
    assert sum(message["type"] == "voice.asr.final" for message in sent_json) == 2
    await bridge.stop()


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["豆包。", "好的", "不对不对，别说了。"])
async def test_former_control_phrases_are_submitted_as_agent_input(text: str) -> None:
    committed: list[dict[str, Any]] = []
    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(sent_json=sent_json, commit_text=committed.append)

    await submit_asr(bridge, text)

    assert [item["text"] for item in committed] == [text]
    assert not any(message["type"] == "voice.interrupted" for message in sent_json)
    await bridge.stop()


@pytest.mark.anyio
async def test_asr_delta_is_visible_while_listening() -> None:
    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(sent_json=sent_json)

    await bridge._handle_server_event(asr_delta("正在说话"))

    assert any(
        message["type"] == "voice.asr.delta"
        and message["payload"] == {"text": "正在说话"}
        for message in sent_json
    )
    await bridge.stop()


@pytest.mark.anyio
async def test_submit_failure_is_reported_and_bridge_keeps_listening() -> None:
    async def fail_commit(payload: dict[str, Any]) -> None:
        raise RuntimeError("agent unavailable")

    sent_json: list[dict[str, Any]] = []
    bridge = make_bridge(sent_json=sent_json, commit_text=fail_commit)

    await submit_asr(bridge, "查天气")
    assert sum(m["type"] == "voice.submit.failed" for m in sent_json) == 1
    assert sent_json[-1]["payload"] == {"phase": "listening"}
    await bridge.stop()
