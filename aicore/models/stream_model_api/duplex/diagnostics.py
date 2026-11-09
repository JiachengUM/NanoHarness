"""Terminal and per-case file diagnostics for Duplex experiments."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

from aicore.events.task import TaskEvent
from aicore.models.stream_model_api.duplex.duplex_events import (
    TYPE_CONVERSATION_ITEM_RETRIEVE,
    TYPE_CONVERSATION_ITEM_RETRIEVED,
    TYPE_INPUT_AUDIO_BUFFER_APPEND,
    TYPE_TRANSCRIPTION_DELTA,
)

_ANSI_BOLD_GREEN = "\033[1;32m"
_ANSI_BOLD_BLUE = "\033[1;34m"
_ANSI_BOLD_MAGENTA = "\033[1;35m"
_ANSI_BOLD_YELLOW = "\033[1;33m"
_ANSI_RESET = "\033[0m"
_UPSTREAM_LABEL = f"{_ANSI_BOLD_GREEN}[UP -> DUPLEX]{_ANSI_RESET}"
_DOWNSTREAM_LABEL = f"{_ANSI_BOLD_BLUE}[DOWN <- DUPLEX]{_ANSI_RESET}"
_CONTEXT_LABEL = f"{_ANSI_BOLD_MAGENTA}[DUPLEX CONTEXT]{_ANSI_RESET}"
_LOCAL_TASK_LABEL = f"{_ANSI_BOLD_YELLOW}[LOCAL TASK]{_ANSI_RESET}"

_PLAIN_UPSTREAM_LABEL = "[UP -> DUPLEX]"
_PLAIN_DOWNSTREAM_LABEL = "[DOWN <- DUPLEX]"
_PLAIN_CONTEXT_LABEL = "[DUPLEX CONTEXT]"
_PLAIN_LOCAL_TASK_LABEL = "[LOCAL TASK]"
_PLAIN_LOCAL_RUNTIME_LABEL = "[LOCAL RUNTIME]"


class DuplexDiagnostics:
    """Mirror selected Duplex diagnostics into one exclusive case log.

    The terminal keeps its ANSI colors. The file uses plain labels plus an
    absolute timestamp and elapsed seconds so several asynchronous task and
    provider lanes can be reconstructed as one timeline. Raw microphone and
    output-audio delta frames remain filtered out; they carry base64/binary
    volume but no useful semantic evidence.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path
        self._started_at = datetime.now().astimezone()
        self._started_monotonic = time.monotonic()
        self._lock = threading.Lock()
        self._stream = None
        if log_path is not None:
            self._stream = log_path.open("x", encoding="utf-8", buffering=1)
            self._stream.write("=== DUPLEX VOICE CASE LOG ===\n")
            self._stream.write(
                f"started_at={self._started_at.isoformat(timespec='milliseconds')}\n"
            )
            self._stream.write(f"log_file={log_path}\n")
            self._stream.write("=== EVENTS ===\n")
            print(f"{_CONTEXT_LABEL} recording={log_path}")

    def __enter__(self) -> DuplexDiagnostics:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def record_session(
        self,
        *,
        model: str,
        tool_call_mode: str,
        tool_names: list[str],
    ) -> None:
        self._write(
            "[SESSION] "
            + json.dumps(
                {
                    "model": model,
                    "tool_call_mode": tool_call_mode,
                    "tools": tool_names,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    def duplex_event(
        self,
        direction: Literal["upstream", "downstream"],
        event: dict[str, Any],
        payload: str,
    ) -> None:
        terminal_text = _format_duplex_event(
            direction,
            event,
            payload,
            colored=True,
        )
        if terminal_text is None:
            return
        print(terminal_text)
        file_text = _format_duplex_event(
            direction,
            event,
            payload,
            colored=False,
        )
        assert file_text is not None
        self._write(file_text)

    def task_event(self, event: TaskEvent) -> None:
        print_duplex_task_event(event)
        self._write(f"{_PLAIN_LOCAL_TASK_LABEL} {event}")

    def runtime_event(self, message: str) -> None:
        """Record a semantic local scheduler boundary omitted from event logs."""

        terminal = f"{_CONTEXT_LABEL} {message}"
        print(terminal)
        self._write(f"{_PLAIN_LOCAL_RUNTIME_LABEL} {message}")

    def close(self) -> None:
        stream = self._stream
        if stream is None:
            return
        self._write("=== DUPLEX VOICE CASE END ===")
        self._stream = None
        stream.close()

    def _write(self, text: str) -> None:
        stream = self._stream
        if stream is None:
            return
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        elapsed = time.monotonic() - self._started_monotonic
        prefix = f"{timestamp} +{elapsed:09.3f}s "
        indented = text.replace("\n", "\n" + " " * len(prefix))
        with self._lock:
            stream.write(f"{prefix}{indented}\n")


def print_duplex_event(
    direction: Literal["upstream", "downstream"],
    event: dict[str, Any],
    payload: str,
) -> None:
    """Print selected Duplex events without coupling transport to terminal UI."""

    text = _format_duplex_event(direction, event, payload, colored=True)
    if text is not None:
        print(text)


def print_duplex_task_event(event: TaskEvent) -> None:
    """Print a local tool/task event with its stable terminal label."""

    print(f"{_LOCAL_TASK_LABEL} {event}")


def _format_duplex_event(
    direction: Literal["upstream", "downstream"],
    event: dict[str, Any],
    payload: str,
    *,
    colored: bool,
) -> str | None:
    event_type = str(event.get("type") or "")
    if event_type in {
        TYPE_CONVERSATION_ITEM_RETRIEVE,
        TYPE_CONVERSATION_ITEM_RETRIEVED,
    }:
        label = _CONTEXT_LABEL if colored else _PLAIN_CONTEXT_LABEL
        return _format_context_event(label, event, payload)
    if direction == "upstream":
        if event_type == TYPE_INPUT_AUDIO_BUFFER_APPEND:
            return None
        label = _UPSTREAM_LABEL if colored else _PLAIN_UPSTREAM_LABEL
        return _format_duplex_event_line(label, event_type, payload)
    if event_type == TYPE_TRANSCRIPTION_DELTA or not event_type.endswith(".delta"):
        label = _DOWNSTREAM_LABEL if colored else _PLAIN_DOWNSTREAM_LABEL
        return _format_duplex_event_line(label, event_type, payload)
    return None


def _format_duplex_event_line(label: str, event_type: str, payload: str) -> str:
    payload_bytes = len(payload.encode("utf-8"))
    return f"{label} type={event_type or 'unknown'} bytes={payload_bytes} {payload}"


def _format_context_event(
    label: str,
    event: dict[str, Any],
    payload: str,
) -> str:
    event_type = str(event.get("type") or "unknown")
    payload_bytes = len(payload.encode("utf-8"))
    pretty_payload = json.dumps(event, ensure_ascii=False, indent=2)
    return (
        f"{_CONTEXT_LABEL} type={event_type} bytes={payload_bytes}\n"
        f"{pretty_payload}"
    ).replace(_CONTEXT_LABEL, label, 1)


__all__ = [
    "DuplexDiagnostics",
    "print_duplex_task_event",
    "print_duplex_event",
]
