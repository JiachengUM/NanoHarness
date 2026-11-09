from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aicore.events.task import TaskStartEvent
from aicore.models.stream_model_api.duplex import (
    cli as duplex_cli,
    duplex_agent_app,
)
from aicore.models.stream_model_api.duplex.cli import choose_case_log_path, parse_args
from aicore.models.stream_model_api.duplex.config import DuplexConfig
from aicore.models.stream_model_api.duplex.duplex_agent_session import (
    DuplexAgentSession,
)
from aicore.models.stream_model_api.duplex.diagnostics import (
    print_duplex_task_event,
)
from aicore.models.stream_model_api.duplex.duplex_stream_model_api import (
    DuplexStreamModelAPI,
)
from aicore.models.stream_model_api.duplex.async_agent_prompt import (
    ASYNC_AGENT_SYSTEM_PROMPT,
)
from aicore.models.stream_model_api.duplex.sync_agent_prompt import (
    SYNC_AGENT_SYSTEM_PROMPT,
)
from aicore.models.stream_model_api.events import (
    StreamAudioStartEvent,
    StreamTranscriptionDeltaEvent,
    StreamTranscriptionDoneEvent,
    StreamTranscriptionStartEvent,
)
from aicore.models.stream_model_api.protocol import ToolCallMode
from aicore.runtime.task import TaskManager


class FakeDuplexClient:
    session_id = "session-1"

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.audio_committed = asyncio.Event()

    async def connect(self) -> None:
        pass

    async def session_create(
        self, session: dict[str, Any], extension: dict[str, Any]
    ) -> None:
        pass

    async def input_audio_append(self, data: bytes) -> None:
        self.sent.append(("audio_append", data))

    async def input_audio_commit(self) -> None:
        self.sent.append(("audio_commit", None))
        self.audio_committed.set()

    async def conversation_item_create(self, items: list[dict[str, Any]]) -> None:
        self.sent.append(("item_create", items))

    async def conversation_item_update(self, items: list[dict[str, Any]]) -> None:
        self.sent.append(("item_update", items))

    async def conversation_item_retrieve(
        self, items: list[dict[str, Any]] | None
    ) -> None:
        self.sent.append(("item_retrieve", items))

    async def recv_event(self) -> dict[str, Any]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def close(self) -> None:
        pass


def test_duplex_agent_app_supports_direct_file_execution(tmp_path: Path) -> None:
    app_path = Path(duplex_agent_app.__file__).resolve()

    completed = subprocess.run(
        [sys.executable, str(app_path), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--tool-call-mode {sync,async}" in completed.stdout


@pytest.mark.asyncio
async def test_unified_async_main_delegates_cli_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str] | None] = []

    async def fake_run_duplex_agent(
        argv: list[str] | None,
    ) -> None:
        captured.append(argv)

    monkeypatch.setattr(
        duplex_agent_app,
        "run_duplex_agent",
        fake_run_duplex_agent,
    )

    await duplex_agent_app.async_main(["--tool-call-mode", "sync"])

    assert captured == [["--tool-call-mode", "sync"]]


def test_cli_defaults_to_async_and_accepts_explicit_sync() -> None:
    assert parse_args([]).tool_call_mode == "async"
    assert parse_args(["--tool-call-mode", "sync"]).tool_call_mode == "sync"


@pytest.mark.parametrize(
    ("tool_call_mode", "expected_prompt"),
    [
        ("async", ASYNC_AGENT_SYSTEM_PROMPT),
        ("sync", SYNC_AGENT_SYSTEM_PROMPT),
    ],
)
def test_tool_call_mode_selects_its_system_prompt(
    tool_call_mode: ToolCallMode,
    expected_prompt: str,
) -> None:
    assert duplex_agent_app.system_prompt_for(tool_call_mode) == expected_prompt


def test_async_prompt_explains_duplex_async_compat_trigger() -> None:
    prompt = ASYNC_AGENT_SYSTEM_PROMPT

    assert prompt == duplex_agent_app.ASYNC_AGENT_SYSTEM_PROMPT
    assert "与本问题关联的异步工具结果" in prompt
    assert "结果区块中尚未出现的工具仍在执行" in prompt
    assert "不得根据原始用户问题" in prompt


def test_sync_prompt_describes_real_result_continuation() -> None:
    prompt = SYNC_AGENT_SYSTEM_PROMPT

    assert prompt == duplex_agent_app.SYNC_AGENT_SYSTEM_PROMPT

    assert "真实结果" in prompt
    assert "自然作答" in prompt
    assert "占位回执" not in prompt


def test_local_task_event_has_distinct_console_label(
    capsys: pytest.CaptureFixture[str],
) -> None:
    event = TaskStartEvent(task_id="call-1")

    print_duplex_task_event(event)

    assert capsys.readouterr().out == (
        f"\033[1;33m[LOCAL TASK]\033[0m {event}\n"
    )


def test_parse_args_exposes_case_log() -> None:
    assert parse_args([]).case_log is None
    assert parse_args(["--case-log", "case01.log"]).case_log == "case01.log"


def test_parse_args_defaults_to_continuous_microphone() -> None:
    assert parse_args([]).mic_mode == "continuous"
    assert parse_args(["--mic-mode", "space_gate"]).mic_mode == "space_gate"


def test_choose_case_log_path_prompts_again_instead_of_overwriting(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "case01.log").write_text("existing", encoding="utf-8")
    answers = iter(("case01.log", "case02"))
    messages: list[str] = []

    path = choose_case_log_path(
        None,
        interactive=True,
        input_func=lambda _: next(answers),
        print_func=lambda message: messages.append(str(message)),
    )

    assert path == Path("case02.log")
    assert messages and "文件已存在" in messages[0]


def test_choose_case_log_path_accepts_noninteractive_eof() -> None:
    def eof(_: str) -> str:
        raise EOFError

    assert (
        choose_case_log_path(None, interactive=True, input_func=eof)
        is None
    )


@pytest.mark.asyncio
async def test_agent_session_exposes_context_retrieve_to_placeholder() -> None:
    client = FakeDuplexClient()
    model_api = DuplexStreamModelAPI(
        client=client,  # type: ignore[arg-type]
        tools=(),
    )
    session = DuplexAgentSession(
        model_api=model_api,
        tools=(),
        task_manager=TaskManager(),
        tool_call_mode="sync",
        config=DuplexConfig(),
    )

    await session.submit_context_retrieve()

    assert client.sent == [("item_retrieve", None)]


def test_space_gate_opens_one_microphone_turn_and_closes_on_asr_done() -> None:
    session = DuplexAgentSession(
        model_api=SimpleNamespace(),
        tools=(),
        task_manager=TaskManager(),
        tool_call_mode="sync",
        config=DuplexConfig(),
        mic_mode="space_gate",
    )

    assert session._filter_microphone_audio(b"voice") == b"\x00" * 5
    assert session.open_microphone_for_user_input() is True
    assert session._filter_microphone_audio(b"voice") == b"voice"

    session._handle_audio_event(
        StreamTranscriptionDoneEvent(
            session_id="session-1",
            item_id="question-1",
            transcript="你好",
        )
    )

    assert session._filter_microphone_audio(b"voice") == b"\x00" * 5


@pytest.mark.asyncio
async def test_local_rule_vad_commits_when_transcription_has_no_delta() -> None:
    client = FakeDuplexClient()
    model_api = DuplexStreamModelAPI(
        client=client,  # type: ignore[arg-type]
        tools=(),
    )
    session = DuplexAgentSession(
        model_api=model_api,
        tools=(),
        task_manager=TaskManager(),
        tool_call_mode="sync",
        config=DuplexConfig(local_rule_vad_timeout_ms=10),
    )

    session._handle_audio_event(
        StreamTranscriptionStartEvent(
            session_id="session-1",
            item_id="question-1",
        )
    )
    await asyncio.wait_for(client.audio_committed.wait(), timeout=1)

    assert client.sent == [("audio_commit", None)]


@pytest.mark.asyncio
async def test_local_rule_vad_is_cancelled_by_transcription_delta() -> None:
    client = FakeDuplexClient()
    model_api = DuplexStreamModelAPI(
        client=client,  # type: ignore[arg-type]
        tools=(),
    )
    session = DuplexAgentSession(
        model_api=model_api,
        tools=(),
        task_manager=TaskManager(),
        tool_call_mode="sync",
        config=DuplexConfig(local_rule_vad_timeout_ms=30),
    )

    session._handle_audio_event(
        StreamTranscriptionStartEvent(session_id="session-1")
    )
    session._handle_audio_event(
        StreamTranscriptionDeltaEvent(session_id="session-1", delta="你")
    )
    await asyncio.sleep(0)

    assert client.sent == []


def test_new_audio_start_invalidates_previous_playback_boundary() -> None:
    session = DuplexAgentSession(
        model_api=SimpleNamespace(),
        tools=(),
        task_manager=TaskManager(),
        tool_call_mode="sync",
        config=DuplexConfig(),
    )
    session.local_audio.enqueue_playback_boundary()
    boundary = session.local_audio.playback_queue.get_nowait()
    session._reply_idle.set()

    session._handle_audio_event(
        StreamAudioStartEvent(
            session_id="session-1",
            response_id="new-response",
        )
    )
    session.local_audio._notify_playback_drained(
        boundary.generation  # type: ignore[union-attr]
    )

    assert not session._reply_idle.is_set()


@pytest.mark.asyncio
async def test_keyboard_failure_cancels_the_agent_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_started = asyncio.Event()
    session_cancelled = asyncio.Event()

    class FakeSession:
        audio_file = ""

        async def run(self) -> None:
            session_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                session_cancelled.set()

    async def fail_keyboard() -> None:
        await session_started.wait()
        raise OSError("stdin unavailable")

    def start_keyboard(*_: Any) -> asyncio.Task[None]:
        return asyncio.create_task(fail_keyboard())

    monkeypatch.setattr(
        duplex_cli,
        "_start_microphone_keyboard",
        start_keyboard,
    )

    with pytest.raises(RuntimeError, match="keyboard task failed") as caught:
        await duplex_cli._run_session_with_keyboard(  # type: ignore[arg-type]
            FakeSession(),
            "space_gate",
        )

    assert isinstance(caught.value.__cause__, OSError)
    assert session_cancelled.is_set()
