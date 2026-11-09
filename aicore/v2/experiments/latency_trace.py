from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


def build_latency_trace(
    event: str,
    *,
    command_id: str | None = None,
    command: str | None = None,
    message_id: str | None = None,
    origin_message_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    generation: int | None = None,
    now_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event": event,
        "clock": "backend",
        "monotonic_ns": now_ns(),
    }
    fields = {
        "command_id": command_id,
        "command": command,
        "message_id": message_id,
        "origin_message_id": origin_message_id,
        "task_id": task_id,
        "session_id": session_id,
        "generation": generation,
    }
    record.update({key: value for key, value in fields.items() if value is not None})
    return record


def trace_latency(
    event: str,
    *,
    command_id: str | None = None,
    command: str | None = None,
    message_id: str | None = None,
    origin_message_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    generation: int | None = None,
    logger: logging.Logger = logger,
    now_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    record = build_latency_trace(
        event,
        command_id=command_id,
        command=command,
        message_id=message_id,
        origin_message_id=origin_message_id,
        task_id=task_id,
        session_id=session_id,
        generation=generation,
        now_ns=now_ns,
    )
    logger.info(
        "v2_latency %s",
        json.dumps(record, ensure_ascii=False, separators=(",", ":")),
    )
    return record
