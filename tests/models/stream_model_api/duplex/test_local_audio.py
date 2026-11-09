from __future__ import annotations

import asyncio
import importlib
import threading

import pytest

from aicore.models.stream_model_api.duplex.local_audio import DuplexLocalAudio
from aicore.models.stream_model_api.duplex.config import DuplexConfig


def test_local_audio_import_is_hardware_independent() -> None:
    module = importlib.import_module(
        "aicore.models.stream_model_api.duplex.local_audio"
    )

    assert "pyaudio" not in module.__dict__


def test_microphone_mode_reports_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import_module = importlib.import_module

    def import_module(name: str):
        if name == "pyaudio":
            raise ModuleNotFoundError("No module named 'pyaudio'")
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", import_module)
    manager = DuplexLocalAudio(
        client=object(),
        config=DuplexConfig(api_key="key"),
    )

    with pytest.raises(RuntimeError, match="uv sync --group dev"):
        manager.ensure_realtime_audio_supported()


@pytest.mark.asyncio
async def test_playback_boundary_notifies_after_preceding_pcm() -> None:
    writes: list[bytes] = []
    drained = asyncio.Event()

    class OutputStream:
        def write(self, data: bytes) -> None:
            writes.append(data)

    manager = DuplexLocalAudio(
        client=object(),
        config=DuplexConfig(api_key="key"),
        playback_drained_callback=drained.set,
    )
    manager.loop = asyncio.get_running_loop()
    manager.running = True
    manager.output_stream = OutputStream()
    manager.enqueue_playback(b"first")
    manager.enqueue_playback(b"second")
    manager.enqueue_playback_boundary()
    worker = threading.Thread(target=manager._play_worker, daemon=True)
    worker.start()
    try:
        await asyncio.wait_for(drained.wait(), timeout=1)
        assert writes == [b"first", b"second"]
    finally:
        manager.running = False
        manager.wake_playback()
        worker.join(timeout=1)
        assert not worker.is_alive()


def test_clear_playback_invalidates_dequeued_boundary() -> None:
    drained: list[None] = []
    manager = DuplexLocalAudio(
        client=object(),
        config=DuplexConfig(api_key="key"),
        playback_drained_callback=lambda: drained.append(None),
    )
    manager.enqueue_playback_boundary()
    boundary = manager.playback_queue.get_nowait()

    manager.clear_playback()
    manager._notify_playback_drained(boundary.generation)  # type: ignore[union-attr]

    assert drained == []
