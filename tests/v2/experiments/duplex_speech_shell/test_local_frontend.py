from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from aicore.v2.experiments.duplex_speech_shell.events import (
    AsrCompleted,
    AsrFailed,
    AsrStarted,
    SpeechShellClosed,
    SpeechShellError,
    TtsAudioDelta,
    TtsCompleted,
    TtsStarted,
)
from aicore.v2.experiments.duplex_speech_shell.local_frontend import (
    LocalSpeechShell,
)

class FakeBackend:
    def __init__(
        self,
        events: list[object],
        *,
        lifecycle: list[str] | None = None,
        connect_error: BaseException | None = None,
    ) -> None:
        self.events: asyncio.Queue[object] = asyncio.Queue()
        for event in events:
            self.events.put_nowait(event)
        self.chunks: list[bytes] = []
        self.commits = 0
        self.connected = 0
        self.closed = 0
        self.lifecycle = lifecycle
        self.connect_error = connect_error
        self.committed = asyncio.Event()

    async def connect(self) -> None:
        self.connected += 1
        if self.connect_error is not None:
            raise self.connect_error

    async def close(self) -> None:
        self.closed += 1
        if self.lifecycle is not None:
            self.lifecycle.append("backend")

    async def append_audio(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def commit_audio(self) -> None:
        self.commits += 1
        self.committed.set()

    async def receive_event(self) -> object:
        await self.committed.wait()
        return await self.events.get()


class FakeRuntime:
    def __init__(
        self,
        *,
        lifecycle: list[str] | None = None,
        zero_delta_done: bool = False,
    ) -> None:
        self.submitted: list[str] = []
        self.started = 0
        self.stopped = 0
        self.interrupted = 0
        self.output_active = False
        self.runner_task = None
        self.tts_pump = SimpleNamespace(finish_response=self._finish)
        self.tts_pump.task = None
        self.tts_pump.on_generation_finished = None
        self.lifecycle = lifecycle
        self.zero_delta_done = zero_delta_done
        self.agent_events: list[object] = []

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def stop_tts(self) -> None:
        self.stopped += 1
        if self.lifecycle is not None:
            self.lifecycle.append("pump")

    async def stop_runner(self) -> None:
        if self.lifecycle is not None:
            self.lifecycle.append("runner")

    async def submit_user_text(self, text: str) -> None:
        self.submitted.append(text)
        self.output_active = True
        if self.zero_delta_done:
            self.output_active = False
            self.tts_pump.on_generation_finished()

    def interrupt_speech(self) -> None:
        self.interrupted += 1
        self.output_active = False

    def accept_agent_event(self, event: object) -> None:
        self.agent_events.append(event)

    def _finish(self) -> None:
        self.output_active = False


class FakeAudio:
    def __init__(self, *, lifecycle: list[str] | None = None) -> None:
        self.output_audio = bytearray()
        self.playback: list[bytes] = []
        self.input_transform = None
        self.playback_drained_callback = None
        self.calls: list[str] = []
        self.lifecycle = lifecycle

    def ensure_realtime_audio_supported(self) -> None:
        self.calls.append("ensure")

    def start(self, loop: object) -> None:
        self.calls.append("start")

    def stop_capture(self) -> None:
        self.calls.append("stop")

    def wake_playback(self) -> None:
        self.calls.append("wake")

    def join_threads(self) -> None:
        self.calls.append("join")

    def close_devices(self) -> None:
        self.calls.append("close")
        if self.lifecycle is not None:
            self.lifecycle.append("audio")

    def clear_playback(self) -> None:
        self.playback.clear()

    def enqueue_playback(self, data: bytes) -> None:
        self.playback.append(data)
        self.output_audio.extend(data)

    def enqueue_playback_boundary(self) -> None:
        self.calls.append("boundary")


async def _no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_file_mode_sends_pcm_commits_and_saves_only_tts(tmp_path: Path) -> None:
    pcm = b"a" * 700
    input_path = tmp_path / "input.pcm"
    input_path.write_bytes(pcm)
    output_path = tmp_path / "output.pcm"
    backend = FakeBackend(
        [
            AsrStarted(),
            AsrCompleted("查天气"),
            TtsStarted("response-1", "chat_tts_text"),
            TtsAudioDelta("response-1", b"voice"),
            TtsCompleted("response-1"),
        ]
    )
    runtime = FakeRuntime()
    audio = FakeAudio()
    session = LocalSpeechShell(
        backend=backend,  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=audio,
        audio_file=str(input_path),
        output_audio_path=output_path,
        sleep=_no_sleep,
    )

    await session.start()
    await session.wait_finished()

    assert backend.chunks == [b"a" * 640, b"a" * 60]
    assert backend.commits == 1
    assert runtime.submitted == ["查天气"]
    assert output_path.read_bytes() == b"voice"
    assert backend.connected == backend.closed == 1
    assert runtime.started == runtime.stopped == 1
    assert audio.calls == ["stop", "wake", "join", "close"]


def test_space_gate_starts_silent_and_open_interrupts_output() -> None:
    runtime = FakeRuntime()
    runtime.output_active = True
    audio = FakeAudio()
    session = LocalSpeechShell(
        backend=FakeBackend([]),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=audio,
    )

    assert session._transform_microphone_audio(b"\x01\x02") == b"\x00\x00"
    assert session.open_microphone() is True
    assert session._transform_microphone_audio(b"\x01\x02") == b"\x01\x02"
    assert runtime.interrupted == 1


@pytest.mark.asyncio
async def test_continuous_microphone_starts_open_without_manual_gate() -> None:
    runtime = FakeRuntime()
    audio = FakeAudio()
    shell = LocalSpeechShell(
        backend=FakeBackend([]),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=audio,
        mic_mode="continuous",
    )

    await shell.start()
    try:
        assert shell.state.listening is True
        assert shell._transform_microphone_audio(b"\x01\x02") == b"\x01\x02"
        assert shell.open_microphone() is False
        assert audio.calls[:2] == ["ensure", "start"]
    finally:
        await shell.stop()


@pytest.mark.asyncio
async def test_local_output_accepts_only_current_external_agent_tts() -> None:
    runtime = FakeRuntime()
    runtime.output_active = True
    audio = FakeAudio()
    shell = LocalSpeechShell(
        backend=FakeBackend([]),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=audio,
    )

    await shell._handle_event(TtsStarted("native", "default"))
    await shell._handle_event(TtsAudioDelta("native", b"native"))
    await shell._handle_event(TtsStarted("custom", "chat_tts_text"))
    await shell._handle_event(TtsAudioDelta("custom", b"accepted"))
    await shell._handle_event(TtsCompleted("custom"))
    await shell._handle_event(TtsAudioDelta("custom", b"late"))

    assert audio.playback == [b"accepted"]
    assert audio.calls == ["boundary"]
    assert shell.state.playback_pending is True


@pytest.mark.asyncio
async def test_microphone_asr_failure_closes_one_turn_space_gate() -> None:
    runtime = FakeRuntime()
    shell = LocalSpeechShell(
        backend=FakeBackend([]),  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=FakeAudio(),
    )

    assert shell.open_microphone() is True
    await shell._handle_event(AsrFailed("no speech"))

    assert shell.microphone_gate.is_open is False
    assert shell.state.listening is False
    assert runtime.submitted == []


@pytest.mark.asyncio
async def test_shutdown_order_and_public_agent_callback(tmp_path: Path) -> None:
    lifecycle: list[str] = []
    input_path = tmp_path / "input.pcm"
    input_path.write_bytes(b"\x00\x00")
    backend = FakeBackend(
        [AsrCompleted("query")],
        lifecycle=lifecycle,
    )
    runtime = FakeRuntime(lifecycle=lifecycle, zero_delta_done=True)
    shell = LocalSpeechShell(
        backend=backend,  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=FakeAudio(lifecycle=lifecycle),
        audio_file=str(input_path),
        sleep=_no_sleep,
    )
    event = object()

    shell.on_agent_event(event)
    await shell.start()
    await shell.wait_finished()

    assert runtime.agent_events == [event]
    assert lifecycle == ["audio", "pump", "backend", "runner"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal", "message"),
    [
        (AsrCompleted(""), "empty ASR"),
        (AsrFailed("bad asr"), "bad asr"),
        (SpeechShellClosed(), "closed before"),
        (SpeechShellError("provider error"), "provider error"),
    ],
)
async def test_file_terminal_failures_do_not_hang(
    tmp_path: Path,
    terminal: object,
    message: str,
) -> None:
    input_path = tmp_path / "input.pcm"
    input_path.write_bytes(b"\x00\x00")
    shell = LocalSpeechShell(
        backend=FakeBackend([terminal]),  # type: ignore[arg-type]
        runtime=FakeRuntime(),  # type: ignore[arg-type]
        audio=FakeAudio(),
        audio_file=str(input_path),
        sleep=_no_sleep,
    )

    await shell.start()
    with pytest.raises(RuntimeError, match=message):
        async with asyncio.timeout(1):
            await shell.wait_finished()


@pytest.mark.asyncio
async def test_connect_failure_still_closes_backend_and_runtime() -> None:
    backend = FakeBackend([], connect_error=RuntimeError("connect failed"))
    runtime = FakeRuntime()
    shell = LocalSpeechShell(
        backend=backend,  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        audio=FakeAudio(),
    )

    with pytest.raises(RuntimeError, match="connect failed"):
        await shell.start()

    assert backend.closed == 1
    assert runtime.stopped == 1
