from __future__ import annotations

import asyncio

import pytest

from aicore.models.stream_model_api import (
    StreamAudioDeltaEvent,
    StreamAudioDoneEvent,
    StreamAudioStartEvent,
)
from aicore.models.stream_model_api.duplex import (
    BrowserDuplexMediaPort,
    DuplexAgentSession,
    DuplexConfig,
)
from aicore.runtime.task import TaskManager


class FiniteModelAPI:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def submit(self, input: object) -> None:
        return None

    async def events(self):
        yield StreamAudioStartEvent(session_id="native")
        yield StreamAudioDeltaEvent(session_id="native", delta=b"\x01\x00")
        yield StreamAudioDoneEvent(session_id="native", status="completed")

    async def aclose(self) -> None:
        self.closed = True


def test_browser_media_port_releases_only_current_playback_boundary() -> None:
    drained: list[str] = []
    port = BrowserDuplexMediaPort()
    port.bind_callbacks(
        playback_drained_callback=lambda: drained.append("done"),
        error_callback=lambda error: None,
    )
    loop = asyncio.new_event_loop()
    port.start(loop)
    port.enqueue_playback(b"audio")
    port.enqueue_playback_boundary()
    port.invalidate_playback_boundary()

    assert port.playback_ended() is False
    assert drained == []

    port.enqueue_playback(b"new-audio")
    port.enqueue_playback_boundary()
    assert port.playback_ended() is True
    assert drained == ["done"]
    loop.close()


@pytest.mark.asyncio
async def test_agent_session_awaits_observer_and_browser_playback_drain() -> None:
    model_api = FiniteModelAPI()
    port = BrowserDuplexMediaPort()
    observed: list[str] = []

    async def observe(event: object) -> None:
        await asyncio.sleep(0)
        observed.append(str(getattr(event, "type", "")))

    session = DuplexAgentSession(
        model_api=model_api,  # type: ignore[arg-type]
        tools=(),
        task_manager=TaskManager(),
        tool_call_mode="sync",
        config=DuplexConfig(),
        context_diagnostics=False,
        media_port=port,
        model_event_observer=observe,
    )

    await session.run()

    assert observed == [
        "stream_model.audio.start",
        "stream_model.audio.delta",
        "stream_model.audio.done",
    ]
    assert not session._reply_idle.is_set()
    assert port.playback_ended() is True
    assert session._reply_idle.is_set()
    assert model_api.started is True
    assert model_api.closed is True
