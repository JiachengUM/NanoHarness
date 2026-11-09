from __future__ import annotations

import asyncio
from array import array
from collections.abc import Callable
from typing import Any

import pytest

from aicore.events.agent import (
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.v2.experiments import v2_frontend_duplex_voice as compatibility
from aicore.v2.experiments.duplex_speech_shell.events import (
    AsrCompleted,
    AsrDelta,
    AsrFailed,
    AsrStarted,
    SpeechShellClosed,
    SpeechShellEvent,
    TtsAudioDelta,
    TtsCompleted,
    TtsStarted,
)
from aicore.v2.experiments.duplex_speech_shell.frontend_bridge import (
    DuplexFrontendVoiceBridge,
    pcm_s16le_to_f32le,
)

pytestmark = pytest.mark.asyncio


class FakeSpeechBackend:
    def __init__(
        self,
        *,
        connect_error: Exception | None = None,
        tts_error: Exception | None = None,
    ) -> None:
        self.connect_error = connect_error
        self.tts_error = tts_error
        self.connect_count = 0
        self.close_count = 0
        self.events: asyncio.Queue[SpeechShellEvent | Exception] = asyncio.Queue()
        self.audio_chunks: list[bytes] = []
        self.appended_text: list[tuple[str, str]] = []
        self.committed_text: list[tuple[str, str]] = []

    async def connect(self) -> None:
        self.connect_count += 1
        if self.connect_error is not None:
            raise self.connect_error

    async def close(self) -> None:
        self.close_count += 1

    async def append_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)

    async def append_speech_text(self, speech_id: str, text: str) -> None:
        if self.tts_error is not None:
            raise self.tts_error
        self.appended_text.append((speech_id, text))

    async def commit_speech_text(self, speech_id: str, text: str) -> None:
        if self.tts_error is not None:
            raise self.tts_error
        self.committed_text.append((speech_id, text))

    async def receive_event(self) -> SpeechShellEvent:
        event = await self.events.get()
        if isinstance(event, Exception):
            raise event
        return event


def make_bridge(
    *,
    backend: FakeSpeechBackend | None = None,
    sent_json: list[dict[str, Any]] | None = None,
    sent_audio: list[bytes] | None = None,
    trace: list[str] | None = None,
) -> tuple[DuplexFrontendVoiceBridge, FakeSpeechBackend, list[dict[str, Any]]]:
    speech_backend = backend or FakeSpeechBackend()
    json_messages = sent_json if sent_json is not None else []
    audio_messages = sent_audio if sent_audio is not None else []
    event_trace = trace if trace is not None else []

    async def submit_text(text: str) -> dict[str, str]:
        event_trace.append("prepare")
        return {
            "text": text,
            "turn_id": "turn-1",
            "user_message_id": "user-1",
            "assistant_message_id": "assistant-1",
        }

    async def commit_text(payload: dict[str, str]) -> None:
        event_trace.append("commit")

    def send_json(message: dict[str, Any]) -> None:
        json_messages.append(message)
        phase = message.get("payload", {}).get("phase")
        event_trace.append(
            f"{message['type']}:{phase}" if phase else str(message["type"])
        )

    return (
        DuplexFrontendVoiceBridge(
            submit_text=submit_text,
            commit_text=commit_text,
            send_json=send_json,
            send_audio=audio_messages.append,
            session_id="session-1",
            generation=1,
            speech_backend_factory=lambda: speech_backend,
        ),
        speech_backend,
        json_messages,
    )


async def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0)


async def test_compatibility_module_is_a_thin_public_export() -> None:
    assert compatibility.DuplexFrontendVoiceBridge is DuplexFrontendVoiceBridge


async def test_start_feed_and_stop_keep_browser_contract() -> None:
    bridge, backend, messages = make_bridge()

    ready = await bridge.start()
    await bridge.feed_audio(b"pcm16")
    await bridge.stop()

    assert ready == {
        "input_sample_rate": 16_000,
        "output_sample_rate": 24_000,
        "output_format": "f32le",
    }
    assert backend.connect_count == 1
    assert backend.audio_chunks == [b"pcm16"]
    assert backend.close_count == 1
    assert [message["type"] for message in messages[:2]] == [
        "voice.ready",
        "voice.phase",
    ]
    assert bridge.running is False
    assert bridge.client is None


async def test_concurrent_start_creates_one_backend_session() -> None:
    bridge, backend, _ = make_bridge()

    ready = await asyncio.gather(*(bridge.start() for _ in range(10)))

    assert backend.connect_count == 1
    assert all(payload == ready[0] for payload in ready)
    await bridge.stop()


async def test_failed_start_cleans_backend_and_can_retry() -> None:
    failing = FakeSpeechBackend(connect_error=RuntimeError("connect failed"))
    healthy = FakeSpeechBackend()
    backends = [failing, healthy]
    bridge, _, _ = make_bridge(backend=failing)
    bridge.speech_backend_factory = lambda: backends.pop(0)

    with pytest.raises(RuntimeError, match="connect failed"):
        await bridge.start()

    assert not bridge.running
    assert bridge.backend is None
    assert failing.close_count == 1
    await bridge.start()
    assert bridge.running
    assert healthy.connect_count == 1
    await bridge.stop()


async def test_text_query_goes_directly_to_external_agent() -> None:
    trace: list[str] = []
    bridge, backend, _ = make_bridge(trace=trace)
    await bridge.start()
    trace.clear()

    await bridge.submit_text_query(" 查天气 ")

    assert trace == ["prepare", "commit"]
    assert backend.appended_text == []
    assert backend.committed_text == []
    await bridge.stop()


async def test_asr_final_is_visible_before_external_agent_commit() -> None:
    trace: list[str] = []
    bridge, backend, _ = make_bridge(trace=trace)
    await bridge.start()
    trace.clear()

    backend.events.put_nowait(AsrCompleted("查北京天气"))
    await wait_until(lambda: "commit" in trace)

    assert trace == [
        "prepare",
        "voice.asr.final",
        "voice.phase:processing",
        "commit",
    ]
    await bridge.stop()


async def test_asr_delta_and_failure_keep_external_agent_unsubmitted() -> None:
    trace: list[str] = []
    bridge, backend, messages = make_bridge(trace=trace)
    await bridge.start()
    trace.clear()

    backend.events.put_nowait(AsrStarted())
    backend.events.put_nowait(AsrDelta("半句话"))
    backend.events.put_nowait(AsrFailed("no speech"))
    await wait_until(
        lambda: any(message["type"] == "voice.asr.delta" for message in messages)
    )
    await wait_until(lambda: not bridge.state.user_speaking)

    assert "prepare" not in trace
    assert "commit" not in trace
    assert any(
        message["type"] == "voice.asr.delta"
        and message["payload"] == {"text": "半句话"}
        for message in messages
    )
    await bridge.stop()


async def test_barge_in_filters_old_audio_and_new_agent_tts_starts_immediately() -> None:
    sent_audio: list[bytes] = []
    bridge, backend, messages = make_bridge(sent_audio=sent_audio)
    await bridge.start()
    bridge.on_agent_event(AgentOutTextStartEvent(), message_id="assistant-old")
    backend.events.put_nowait(TtsStarted("response-old", "chat_tts_text"))
    await wait_until(lambda: bridge.state.current_response_id == "response-old")

    backend.events.put_nowait(AsrStarted())
    await wait_until(
        lambda: any(message["type"] == "voice.interrupted" for message in messages)
    )
    backend.events.put_nowait(TtsAudioDelta("response-old", b"\x00\x00"))
    backend.events.put_nowait(AsrCompleted("改成上海天气"))
    await wait_until(
        lambda: any(message["type"] == "voice.asr.final" for message in messages)
    )

    bridge.on_agent_event(
        AgentOutTextDeltaEvent(delta="新的 Agent 回复"),
        message_id="assistant-1",
    )
    bridge.on_agent_event(AgentOutTextDoneEvent(), message_id="assistant-1")
    await wait_until(lambda: len(backend.committed_text) == 1)

    interrupted = [
        message for message in messages if message["type"] == "voice.interrupted"
    ]
    assert len(interrupted) == 1
    assert interrupted[0]["payload"] == {
        "reason": "barge_in",
        "message_id": "assistant-old",
    }
    assert sent_audio == []
    assert backend.committed_text[0][1] == "新的 Agent 回复"
    await bridge.stop()


async def test_only_accepted_custom_tts_is_converted_and_playback_is_explicit() -> None:
    sent_audio: list[bytes] = []
    bridge, backend, messages = make_bridge(sent_audio=sent_audio)
    await bridge.start()
    bridge.on_agent_event(AgentOutTextStartEvent(), message_id="assistant-1")
    pcm16 = array("h", [-32768, 0, 16384, 32767]).tobytes()

    backend.events.put_nowait(TtsStarted("native", "default"))
    backend.events.put_nowait(TtsAudioDelta("native", pcm16))
    backend.events.put_nowait(TtsStarted("custom", "chat_tts_text"))
    backend.events.put_nowait(TtsAudioDelta("custom", pcm16))
    await wait_until(lambda: len(sent_audio) == 1)
    backend.events.put_nowait(TtsCompleted("custom"))
    await wait_until(lambda: not bridge.tts_pump.active)

    assert len(sent_audio) == 1
    converted = array("f")
    converted.frombytes(sent_audio[0])
    assert list(converted) == pytest.approx([-1.0, 0.0, 0.5, 32767 / 32768])
    assert bridge.state.playback_pending
    await bridge.on_playback_ended()
    assert not bridge.state.playback_pending
    assert messages[-1]["payload"] == {"phase": "listening"}
    await bridge.stop()


async def test_zero_delta_tts_finishes_without_provider_command() -> None:
    bridge, backend, messages = make_bridge()
    await bridge.start()

    bridge.on_agent_event(AgentOutTextStartEvent(), message_id="assistant-1")
    bridge.on_agent_event(AgentOutTextDoneEvent(), message_id="assistant-1")
    await wait_until(lambda: bridge.tts_pump is not None and not bridge.tts_pump.active)

    assert backend.appended_text == []
    assert backend.committed_text == []
    assert messages[-1]["payload"] == {"phase": "listening"}
    await bridge.stop()


async def test_autonomous_backend_close_cleans_up_and_allows_restart() -> None:
    backends = [FakeSpeechBackend(), FakeSpeechBackend()]
    bridge, _, _ = make_bridge(backend=backends[0])
    bridge.speech_backend_factory = lambda: backends.pop(0)

    await bridge.start()
    first = bridge.backend
    assert isinstance(first, FakeSpeechBackend)
    first.events.put_nowait(SpeechShellClosed())
    await wait_until(lambda: not bridge.running and bridge.backend is None)

    await bridge.start()
    assert bridge.running
    assert bridge.backend is not first
    assert first.close_count == 1
    await bridge.stop()


async def test_receive_failure_emits_error_and_cleans_background_tasks() -> None:
    bridge, backend, messages = make_bridge()
    await bridge.start()

    backend.events.put_nowait(RuntimeError("receive failed"))
    await wait_until(lambda: not bridge.running and bridge.backend is None)

    errors = [message for message in messages if message["type"] == "voice.error"]
    assert errors[-1]["payload"] == {
        "message": "RuntimeError: receive failed"
    }
    assert backend.close_count == 1


async def test_tts_failure_emits_error_and_cleans_background_tasks() -> None:
    backend = FakeSpeechBackend(tts_error=RuntimeError("TTS write failed"))
    bridge, _, messages = make_bridge(backend=backend)
    await bridge.start()

    bridge.on_agent_event(
        AgentOutTextDeltaEvent(delta="会失败"),
        message_id="assistant-1",
    )
    bridge.on_agent_event(AgentOutTextDoneEvent(), message_id="assistant-1")
    await wait_until(lambda: not bridge.running and bridge.backend is None)

    errors = [message for message in messages if message["type"] == "voice.error"]
    assert errors[-1]["payload"] == {
        "message": "RuntimeError: TTS write failed"
    }
    assert backend.close_count == 1


async def test_backend_and_raw_client_factories_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        DuplexFrontendVoiceBridge(
            submit_text=lambda text: {"text": text},
            commit_text=None,
            send_json=lambda message: None,
            send_audio=lambda payload: None,
            session_id="session-1",
            generation=1,
            speech_backend_factory=FakeSpeechBackend,
            duplex_client_factory=lambda: object(),  # type: ignore[arg-type]
        )


async def test_pcm_conversion_rejects_incomplete_sample() -> None:
    with pytest.raises(ValueError, match="complete 16-bit samples"):
        pcm_s16le_to_f32le(b"\x00")
