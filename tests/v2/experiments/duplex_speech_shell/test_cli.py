from __future__ import annotations

import asyncio
import signal
from argparse import Namespace

import pytest

from aicore.v2.experiments.duplex_speech_shell import cli


def test_parse_args_keeps_local_cli_contract() -> None:
    args = cli.parse_args([])

    assert args == Namespace(
        audio="",
        chat_id="duplex-v2-chat",
        model=None,
        auth_mode="app-key",
        endpoint_url=None,
        mic_mode="space_gate",
    )


@pytest.mark.asyncio
async def test_run_local_session_stops_on_signal_and_removes_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    handlers: dict[signal.Signals, object] = {}
    removed: list[signal.Signals] = []
    monkeypatch.setattr(
        loop,
        "add_signal_handler",
        lambda sig, callback: handlers.setdefault(sig, callback),
    )
    monkeypatch.setattr(
        loop,
        "remove_signal_handler",
        lambda sig: removed.append(sig) or True,
    )

    class FakeShell:
        file_mode = True
        mic_mode = "space_gate"
        running = False

        def __init__(self) -> None:
            self.finished = asyncio.Event()
            self.stop_calls = 0

        async def start(self) -> None:
            self.running = True
            loop.call_soon(handlers[signal.SIGINT])  # type: ignore[arg-type]

        async def wait_finished(self) -> None:
            await self.finished.wait()

        async def stop(self) -> None:
            self.stop_calls += 1
            self.running = False
            self.finished.set()

    shell = FakeShell()

    await cli.run_local_session(shell)  # type: ignore[arg-type]

    assert shell.stop_calls == 2
    assert removed == [signal.SIGINT, signal.SIGTERM]
