from __future__ import annotations

import json
import logging

from aicore.v2.experiments.latency_trace import (
    build_latency_trace,
    trace_latency,
)


def test_backend_latency_trace_uses_monotonic_clock_and_correlation_fields() -> None:
    record = build_latency_trace(
        "ws.command.received",
        command_id="cmd-1",
        command="agent.run",
        message_id="agent-1",
        origin_message_id="agent-origin",
        task_id="task-1",
        session_id="sess-1",
        generation=7,
        now_ns=lambda: 123456,
    )

    assert record == {
        "event": "ws.command.received",
        "clock": "backend",
        "monotonic_ns": 123456,
        "command_id": "cmd-1",
        "command": "agent.run",
        "message_id": "agent-1",
        "origin_message_id": "agent-origin",
        "task_id": "task-1",
        "session_id": "sess-1",
        "generation": 7,
    }


def test_backend_latency_trace_writes_structured_json(caplog) -> None:
    logger = logging.getLogger("test.v2.latency")

    with caplog.at_level(logging.INFO, logger=logger.name):
        record = trace_latency(
            "task.cancelled",
            task_id="task-1",
            logger=logger,
            now_ns=lambda: 99,
        )

    assert json.loads(caplog.records[0].message.removeprefix("v2_latency ")) == record
