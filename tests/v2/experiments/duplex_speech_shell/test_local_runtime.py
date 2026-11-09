from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from aicore.v2.experiments.duplex_speech_shell.agent_tts import AgentTtsPump
from aicore.v2.experiments.duplex_speech_shell.local_runtime import (
    LocalAgentRuntime,
    QueueUserDataSource,
)

class FakeRunner:
    def __init__(self) -> None:
        self.cancelled = False

    async def run(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class FakeSink:
    def __init__(self) -> None:
        self.appended: list[tuple[str, str]] = []
        self.committed: list[tuple[str, str]] = []

    async def append_speech_text(self, speech_id: str, text: str) -> None:
        self.appended.append((speech_id, text))

    async def commit_speech_text(self, speech_id: str, text: str) -> None:
        self.committed.append((speech_id, text))


@pytest.mark.asyncio
async def test_runtime_routes_agent_text_and_cleans_tasks() -> None:
    runner = FakeRunner()
    source = QueueUserDataSource()
    sink = FakeSink()
    pump = AgentTtsPump(sink, speech_id_factory=lambda: "speech-1")
    runtime = LocalAgentRuntime(runner=runner, user_data=source, tts_pump=pump)

    await runtime.start()
    runtime.accept_agent_event(SimpleNamespace(type="agent.out.text.start"))
    runtime.accept_agent_event(
        SimpleNamespace(type="agent.out.text.delta", delta="第一段")
    )
    runtime.accept_agent_event(
        SimpleNamespace(type="agent.out.text.delta", delta="第二段")
    )
    runtime.accept_agent_event(SimpleNamespace(type="agent.out.text.done"))
    await asyncio.sleep(0)
    await runtime.stop()

    assert sink.appended == [("speech-1", "第一段")]
    assert sink.committed == [("speech-1", "第二段")]
    assert runner.cancelled is True
    assert pump.task is None


@pytest.mark.asyncio
async def test_queue_source_strips_runtime_input_and_closes_once() -> None:
    source = QueueUserDataSource()
    runner = FakeRunner()
    runtime = LocalAgentRuntime(
        runner=runner,
        user_data=source,
        tts_pump=AgentTtsPump(FakeSink()),
    )

    await runtime.submit_user_text("  查天气  ")
    await source.close()
    await source.close()

    assert source._queue.qsize() == 2
    assert [item async for item in source()] == ["查天气"]
