"""Injectable media hosts for a Duplex Agent session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol


class DuplexMediaPort(Protocol):
    """Environment-owned microphone/playback lifecycle used by the session."""

    output_audio: bytearray

    def bind_callbacks(
        self,
        *,
        playback_drained_callback: Callable[[], None],
        error_callback: Callable[[BaseException], None],
    ) -> None: ...

    def ensure_realtime_audio_supported(self) -> None: ...

    def start(self, loop: asyncio.AbstractEventLoop) -> None: ...

    def stop_capture(self) -> None: ...

    def wake_playback(self) -> None: ...

    def join_threads(self) -> None: ...

    def close_devices(self) -> None: ...

    def clear_playback(self) -> None: ...

    def invalidate_playback_boundary(self) -> None: ...

    def enqueue_playback(self, data: bytes) -> None: ...

    @property
    def realtime_playback_active(self) -> bool: ...

    def enqueue_playback_boundary(self) -> None: ...


class BrowserDuplexMediaPort:
    """Thread-free playback-drain state for a browser-owned audio device."""

    def __init__(self) -> None:
        self.output_audio = bytearray()
        self.running = False
        self._playback_active = False
        self._boundary_pending = False
        self._playback_generation = 0
        self._boundary_generation: int | None = None
        self._playback_drained_callback: Callable[[], None] | None = None
        self._error_callback: Callable[[BaseException], None] | None = None

    def bind_callbacks(
        self,
        *,
        playback_drained_callback: Callable[[], None],
        error_callback: Callable[[BaseException], None],
    ) -> None:
        self._playback_drained_callback = playback_drained_callback
        self._error_callback = error_callback

    def ensure_realtime_audio_supported(self) -> None:
        return

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.running = True

    def stop_capture(self) -> None:
        self.running = False

    def wake_playback(self) -> None:
        return

    def join_threads(self) -> None:
        return

    def close_devices(self) -> None:
        return

    def clear_playback(self) -> None:
        self.invalidate_playback_boundary()
        self._playback_active = False
        self._boundary_pending = False

    def invalidate_playback_boundary(self) -> None:
        self._playback_generation += 1
        self._boundary_generation = None
        self._boundary_pending = False

    def enqueue_playback(self, data: bytes) -> None:
        if data:
            self._playback_active = True

    @property
    def realtime_playback_active(self) -> bool:
        return self.running and self._playback_active

    def enqueue_playback_boundary(self) -> None:
        self._boundary_pending = True
        self._boundary_generation = self._playback_generation

    def playback_ended(self) -> bool:
        """Release the current reply only after the browser reports drain."""

        generation = self._boundary_generation
        if not self._boundary_pending or generation != self._playback_generation:
            return False
        self._boundary_pending = False
        self._boundary_generation = None
        self._playback_active = False
        callback = self._playback_drained_callback
        if callback is not None:
            callback()
        return True


__all__ = ["BrowserDuplexMediaPort", "DuplexMediaPort"]
