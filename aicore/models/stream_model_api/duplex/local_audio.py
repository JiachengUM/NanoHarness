from __future__ import annotations

import asyncio
import importlib
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from aicore.models.stream_model_api.duplex.config import (
    DEFAULT_PCM,
    PCM_S16LE,
    DuplexConfig,
)

SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
MIC_CHUNK = 320


@dataclass(frozen=True, slots=True)
class _PlaybackBoundary:
    """Queue marker consumed only after all preceding PCM was written."""

    generation: int


class AudioInputSink(Protocol):
    """Narrow async sink used by the microphone capture thread."""

    async def input_audio_append(self, data: bytes) -> None: ...


class DuplexLocalAudio:
    def __init__(
        self,
        *,
        client: AudioInputSink,
        config: DuplexConfig,
        mic_chunk: int = MIC_CHUNK,
        input_transform: Callable[[bytes], bytes] | None = None,
        playback_drained_callback: Callable[[], None] | None = None,
        error_callback: Callable[[BaseException], None] | None = None,
        accumulate_output: bool = True,
    ) -> None:
        """
        ``accumulate_output`` controls whether every played byte is also kept
        in :attr:`output_audio` for later file export. Headless file-mode
        sessions accumulate (no device, playback queue is a buffer); realtime
        sessions must not, otherwise memory grows for the whole session.
        """
        self.client = client
        self.config = config
        self.mic_chunk = mic_chunk
        self.input_transform = input_transform
        self.playback_drained_callback = playback_drained_callback
        self.error_callback = error_callback
        self.accumulate_output = accumulate_output
        self.playback_queue: queue.Queue[bytes | _PlaybackBoundary | None] = (
            queue.Queue()
        )
        self.output_audio = bytearray()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.running = False
        self.input_stream: Any | None = None
        self.output_stream: Any | None = None
        self._pyaudio_instance: Any | None = None
        self._mic_thread: threading.Thread | None = None
        self._play_thread: threading.Thread | None = None
        self._playback_generation = 0

    def bind_callbacks(
        self,
        *,
        playback_drained_callback: Callable[[], None],
        error_callback: Callable[[BaseException], None],
    ) -> None:
        self.playback_drained_callback = playback_drained_callback
        self.error_callback = error_callback

    def _load_pyaudio(self) -> Any:
        try:
            return importlib.import_module("pyaudio")
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "PyAudio is required for Duplex microphone input and playback; "
                "install local voice dependencies with `uv sync --group dev`."
            ) from error

    def ensure_realtime_audio_supported(self) -> None:
        self._load_pyaudio()
        if self.config.asr_format != DEFAULT_PCM:
            raise RuntimeError(
                f"unsupported microphone asr_format: {self.config.asr_format}"
            )
        if self.config.tts_format not in (DEFAULT_PCM, PCM_S16LE):
            raise RuntimeError(
                f"unsupported realtime tts_format: {self.config.tts_format}"
            )

    def open_devices(self) -> None:
        pyaudio_module = self._load_pyaudio()
        self._pyaudio_instance = pyaudio_module.PyAudio()
        self.input_stream = self._pyaudio_instance.open(
            format=pyaudio_module.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.mic_chunk,
        )
        output_format = (
            pyaudio_module.paInt16
            if self.config.tts_format == PCM_S16LE
            else pyaudio_module.paFloat32
        )
        self.output_stream = self._pyaudio_instance.open(
            format=output_format,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=1024,
        )

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.running = True
        self.open_devices()
        self._mic_thread = threading.Thread(target=self._mic_worker, daemon=True)
        self._play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self._mic_thread.start()
        self._play_thread.start()

    def stop_capture(self) -> None:
        self.running = False

    def wake_playback(self) -> None:
        self.playback_queue.put(None)

    def join_threads(self) -> None:
        for thread in (self._mic_thread, self._play_thread):
            if thread is not None:
                thread.join(timeout=0.5)

    def close_devices(self) -> None:
        for stream in (self.input_stream, self.output_stream):
            if stream is None:
                continue
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        self.input_stream = None
        self.output_stream = None
        if self._pyaudio_instance is not None:
            self._pyaudio_instance.terminate()
            self._pyaudio_instance = None

    def clear_playback(self) -> None:
        # Invalidate a boundary already dequeued by the playback thread but
        # whose event-loop callback has not run yet.
        self.invalidate_playback_boundary()
        while True:
            try:
                self.playback_queue.get_nowait()
            except queue.Empty:
                return

    def invalidate_playback_boundary(self) -> None:
        """Prevent an earlier reply's drain callback from releasing a new turn."""

        self._playback_generation += 1

    def enqueue_playback(self, data: bytes) -> None:
        self.playback_queue.put(data)
        if self.accumulate_output:
            self.output_audio.extend(data)

    @property
    def realtime_playback_active(self) -> bool:
        """Whether queued PCM is consumed by the local playback thread."""

        return self.running and self.output_stream is not None

    def enqueue_playback_boundary(self) -> None:
        """Notify the event loop after all currently queued PCM is played."""

        self.playback_queue.put(
            _PlaybackBoundary(generation=self._playback_generation)
        )

    def _notify_playback_drained(self, generation: int) -> None:
        if generation != self._playback_generation:
            return
        callback = self.playback_drained_callback
        if callback is not None:
            callback()

    def _report_error(self, error: BaseException) -> None:
        callback = self.error_callback
        if callback is None or self.loop is None:
            return
        self.loop.call_soon_threadsafe(callback, error)

    def _mic_worker(self) -> None:
        if self.input_stream is None or self.loop is None:
            return
        while self.running:
            try:
                data = self.input_stream.read(
                    self.mic_chunk,
                    exception_on_overflow=False,
                )
            except Exception as error:
                if self.running:
                    self._report_error(error)
                break
            if not self.running:
                break
            if self.input_transform is not None:
                data = self.input_transform(data)
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.client.input_audio_append(data),
                    self.loop,
                )
                future.result(timeout=2)
            except Exception as error:
                if self.running:
                    self._report_error(error)
                break

    def _play_worker(self) -> None:
        if self.output_stream is None:
            return
        while self.running:
            try:
                data = self.playback_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if data is None:
                break
            if isinstance(data, _PlaybackBoundary):
                if self.loop is not None:
                    self.loop.call_soon_threadsafe(
                        self._notify_playback_drained,
                        data.generation,
                    )
                continue
            try:
                self.output_stream.write(data)
            except Exception as error:
                if self.running:
                    self._report_error(error)
                break
