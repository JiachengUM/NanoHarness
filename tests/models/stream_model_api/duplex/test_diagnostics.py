from __future__ import annotations

import json

import pytest

from aicore.events.task import TaskStartEvent
from aicore.models.stream_model_api.duplex.diagnostics import DuplexDiagnostics
from aicore.models.stream_model_api.duplex.duplex_events import (
    TYPE_INPUT_AUDIO_BUFFER_APPEND,
    TYPE_INPUT_AUDIO_BUFFER_COMMIT,
    TYPE_TRANSCRIPTION_COMPLETED,
)


def test_case_log_records_timed_duplex_and_local_task_events(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "case01.log"
    upstream = {
        "type": TYPE_INPUT_AUDIO_BUFFER_COMMIT,
        "event_id": "event-1",
    }
    downstream = {
        "type": TYPE_TRANSCRIPTION_COMPLETED,
        "transcript": "查一下上海天气",
    }

    with DuplexDiagnostics(path) as diagnostics:
        diagnostics.record_session(
            model="duplex-test",
            tool_call_mode="async",
            tool_names=["websearch"],
        )
        diagnostics.duplex_event(
            "upstream",
            upstream,
            json.dumps(upstream, ensure_ascii=False),
        )
        diagnostics.duplex_event(
            "downstream",
            downstream,
            json.dumps(downstream, ensure_ascii=False),
        )
        diagnostics.task_event(TaskStartEvent(task_id="task-1"))
        diagnostics.runtime_event(
            "async_activation tools=['websearch'] audio=websearch_ready.pcm"
        )

    terminal = capsys.readouterr().out
    assert "[UP -> DUPLEX]" in terminal
    assert "[DOWN <- DUPLEX]" in terminal
    assert "[LOCAL TASK]" in terminal
    assert "async_activation" in terminal

    log = path.read_text(encoding="utf-8")
    assert "=== DUPLEX VOICE CASE LOG ===" in log
    assert '"tool_call_mode":"async"' in log
    assert "[UP -> DUPLEX]" in log
    assert "[DOWN <- DUPLEX]" in log
    assert "查一下上海天气" in log
    assert "[LOCAL TASK]" in log
    assert "task-1" in log
    assert "[LOCAL RUNTIME]" in log
    assert "audio=websearch_ready.pcm" in log
    assert "\033[" not in log
    assert "+00000" in log
    assert "=== DUPLEX VOICE CASE END ===" in log


def test_case_log_filters_raw_audio_append(tmp_path) -> None:
    path = tmp_path / "case02.log"
    event = {
        "type": TYPE_INPUT_AUDIO_BUFFER_APPEND,
        "audio": "large-base64-payload",
    }

    with DuplexDiagnostics(path) as diagnostics:
        diagnostics.duplex_event("upstream", event, json.dumps(event))

    assert "large-base64-payload" not in path.read_text(encoding="utf-8")


def test_case_log_never_overwrites_existing_file(tmp_path) -> None:
    path = tmp_path / "case03.log"
    path.write_text("old case", encoding="utf-8")

    with pytest.raises(FileExistsError):
        DuplexDiagnostics(path)
