from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from aicore.v2.experiments.duplex_speech_shell.agent_tts import AgentTtsPump


class FakeSpeechTextSink:
    def __init__(self) -> None:
        self.appended: list[tuple[str, str]] = []
        self.committed: list[tuple[str, str]] = []

    async def append_speech_text(self, speech_id: str, text: str) -> None:
        self.appended.append((speech_id, text))

    async def commit_speech_text(self, speech_id: str, text: str) -> None:
        self.committed.append((speech_id, text))


async def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_single_delta_is_committed_without_append() -> None:
    sink = FakeSpeechTextSink()
    pump = AgentTtsPump(sink, speech_id_factory=lambda: "speech-1")
    pump.start()

    pump.accept_agent_event("agent.out.text.start", message_id="message-1")
    pump.accept_agent_event(
        "agent.out.text.delta",
        message_id="message-1",
        text="完整一句",
    )
    pump.accept_agent_event("agent.out.text.done", message_id="message-1")
    await wait_until(lambda: len(sink.committed) == 1)

    assert sink.appended == []
    assert sink.committed == [("speech-1", "完整一句")]
    await pump.stop()


@pytest.mark.asyncio
async def test_multiple_deltas_append_n_minus_one_and_commit_last() -> None:
    sink = FakeSpeechTextSink()
    pump = AgentTtsPump(sink, speech_id_factory=lambda: "speech-1")
    pump.start()

    for text in ("第一段", "第二段", "第三段"):
        pump.accept_agent_event(
            "agent.out.text.delta",
            message_id="message-1",
            text=text,
        )
    pump.accept_agent_event("agent.out.text.done", message_id="message-1")
    await wait_until(lambda: len(sink.committed) == 1)

    assert sink.appended == [
        ("speech-1", "第一段"),
        ("speech-1", "第二段"),
    ]
    assert sink.committed == [("speech-1", "第三段")]
    await pump.stop()


@pytest.mark.asyncio
async def test_zero_delta_finishes_generation_without_provider_command() -> None:
    sink = FakeSpeechTextSink()
    finished = 0

    def on_finished() -> None:
        nonlocal finished
        finished += 1

    pump = AgentTtsPump(sink, on_generation_finished=on_finished)
    pump.start()

    pump.accept_agent_event("agent.out.text.start", message_id="message-1")
    pump.accept_agent_event("agent.out.text.done", message_id="message-1")
    await wait_until(lambda: finished == 1)

    assert not pump.active
    assert sink.appended == []
    assert sink.committed == []
    await pump.stop()


@pytest.mark.asyncio
async def test_interrupt_drops_old_generation_and_allows_new_message() -> None:
    sink = FakeSpeechTextSink()
    ids = iter(("speech-old", "speech-new"))
    created_ids: list[str] = []

    def create_speech_id() -> str:
        speech_id = next(ids)
        created_ids.append(speech_id)
        return speech_id

    pump = AgentTtsPump(sink, speech_id_factory=create_speech_id)
    pump.start()

    pump.accept_agent_event(
        "agent.out.text.delta",
        message_id="message-old",
        text="旧回复",
    )
    await wait_until(lambda: created_ids == ["speech-old"])
    assert pump.interrupt() == "message-old"
    pump.accept_agent_event(
        "agent.out.text.delta",
        message_id="message-old",
        text="不能复活",
    )
    pump.accept_agent_event(
        "agent.out.text.delta",
        message_id="message-new",
        text="新回复",
    )
    pump.accept_agent_event("agent.out.text.done", message_id="message-new")
    await wait_until(lambda: len(sink.committed) == 1)

    assert sink.appended == []
    assert sink.committed == [("speech-new", "新回复")]
    assert "message-old" in pump.interrupted_message_ids
    await pump.stop()


@pytest.mark.asyncio
async def test_late_old_message_cannot_replace_new_generation() -> None:
    sink = FakeSpeechTextSink()
    pump = AgentTtsPump(sink, speech_id_factory=lambda: "speech-new")
    pump.start()

    pump.accept_agent_event(
        "agent.out.text.delta",
        message_id="message-old",
        text="旧回复",
    )
    pump.accept_agent_event("agent.out.text.start", message_id="message-new")
    pump.accept_agent_event(
        "agent.out.text.delta",
        message_id="message-new",
        text="新回复",
    )
    pump.accept_agent_event("agent.out.text.done", message_id="message-old")
    pump.accept_agent_event("agent.out.text.done", message_id="message-new")

    await wait_until(lambda: len(sink.committed) == 1)
    assert sink.appended == []
    assert sink.committed == [("speech-new", "新回复")]
    await pump.stop()


@pytest.mark.asyncio
async def test_stop_completes_worker_without_orphan_task() -> None:
    pump = AgentTtsPump(FakeSpeechTextSink())
    task = pump.start()

    await pump.stop()

    assert task.done()
