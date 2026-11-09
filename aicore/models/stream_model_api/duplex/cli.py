"""Command-line parsing and terminal interaction for Duplex agent apps."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aicore.models.stream_model_api.duplex.duplex_agent_session import (
    DEFAULT_OUTPUT_AUDIO_PATH,
    DuplexAgentSession,
    MicMode,
)


def parse_args(
    argv: list[str] | None = None,
    *,
    description: str = "Run a Duplex StreamModelAPI agent session.",
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--tool-call-mode",
        choices=("sync", "async"),
        default="async",
        help=(
            "tool-result continuation policy; async returns receipts first "
            "and backfills completed facts (default)"
        ),
    )
    parser.add_argument("--audio", default="")
    parser.add_argument("--chat-id", default="duplex-stream-model-chat")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--auth-mode",
        choices=("auto", "app-key", "x-api-key", "bearer"),
        default="app-key",
    )
    parser.add_argument("--endpoint-url", default=None)
    parser.add_argument("--output-audio", default=str(DEFAULT_OUTPUT_AUDIO_PATH))
    parser.add_argument(
        "--mic-mode",
        choices=("space_gate", "continuous"),
        default="continuous",
        help=(
            "microphone policy: continuous always forwards microphone audio "
            "(default); space_gate starts muted and opens one turn with Space"
        ),
    )
    parser.add_argument(
        "--case-log",
        default=None,
        help=(
            "write this isolated voice case to a new .log file; when omitted "
            "in microphone/TTY mode, prompt for a filename before connecting"
        ),
    )
    return parser.parse_args(argv)


def choose_case_log_path(
    configured: str | None,
    *,
    interactive: bool | None = None,
    input_func: Callable[[str], str] | None = None,
    print_func: Callable[..., Any] = print,
) -> Path | None:
    """Resolve one exclusive case log path without overwriting an old case."""

    if configured is not None:
        return _validate_new_case_log_path(configured)
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        return None

    read = input_func or input
    while True:
        try:
            prompt = "本次语音测试日志文件（例如 case01.log，直接回车则不记录）："
            raw = read(prompt).strip()
        except EOFError:
            return None
        if not raw:
            return None
        try:
            return _validate_new_case_log_path(raw)
        except (FileExistsError, ValueError) as error:
            print_func(f"无法使用该日志文件：{error}")


def _validate_new_case_log_path(raw: str) -> Path | None:
    value = raw.strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if path.suffix == "":
        path = path.with_suffix(".log")
    elif path.suffix.lower() != ".log":
        raise ValueError("日志文件必须使用 .log 后缀")
    if not path.parent.is_dir():
        raise ValueError(f"父目录不存在：{path.parent}")
    if path.exists():
        raise FileExistsError(f"文件已存在，请换一个 case 名称：{path}")
    return path


async def run_terminal_session(
    session: DuplexAgentSession,
    mic_mode: MicMode,
) -> None:
    """Run one session with terminal signals and optional keyboard mic gate."""

    current_task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda task=current_task: task.cancel() if task is not None else None,
            )
            installed_signals.append(sig)
        except NotImplementedError:
            pass
    try:
        await _run_session_with_keyboard(session, mic_mode)
    except asyncio.CancelledError:
        pass
    finally:
        for sig in installed_signals:
            loop.remove_signal_handler(sig)


async def _run_session_with_keyboard(
    session: DuplexAgentSession,
    mic_mode: MicMode,
) -> None:
    """Supervise the default space-gate input together with the agent session."""

    keyboard_task = _start_microphone_keyboard(session, mic_mode)
    if keyboard_task is None:
        await session.run()
        return

    session_task = asyncio.create_task(session.run(), name="duplex-agent-session")
    try:
        done, _ = await asyncio.wait(
            {session_task, keyboard_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if session_task in done:
            await session_task
            return
        if keyboard_task.cancelled():
            raise RuntimeError("Duplex microphone keyboard task was cancelled")
        error = keyboard_task.exception()
        if error is not None:
            raise RuntimeError("Duplex microphone keyboard task failed") from error
        raise RuntimeError("Duplex microphone keyboard task ended unexpectedly")
    finally:
        for task in (session_task, keyboard_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(session_task, keyboard_task, return_exceptions=True)


def _start_microphone_keyboard(
    session: DuplexAgentSession,
    mic_mode: MicMode,
) -> asyncio.Task[None] | None:
    if session.audio_file or mic_mode != "space_gate":
        return None
    return asyncio.create_task(
        _keyboard_space_loop(session),
        name="duplex-microphone-space-gate",
    )


async def _keyboard_space_loop(session: DuplexAgentSession) -> None:
    """Read a single Space in a TTY without blocking the model event loop."""

    if sys.platform.startswith("win"):
        import msvcrt

        print("[MIC] 按空格打开一轮麦克风输入")
        while True:
            if msvcrt.kbhit() and msvcrt.getwch() == " ":
                session.open_microphone_for_user_input()
            await asyncio.sleep(0.05)

    import select

    file_descriptor = sys.stdin.fileno()
    old_settings: list[Any] | None = None
    if sys.stdin.isatty():
        import termios
        import tty

        old_settings = termios.tcgetattr(file_descriptor)
        tty.setcbreak(file_descriptor)
        print("[MIC] 按空格打开一轮麦克风输入")
    else:
        print(
            "[MIC] 当前标准输入不是 TTY；"
            "输入空格后回车可打开一轮麦克风"
        )
    try:
        while True:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if readable and sys.stdin.read(1) == " ":
                session.open_microphone_for_user_input()
            await asyncio.sleep(0.05)
    finally:
        if old_settings is not None:
            import termios

            termios.tcsetattr(file_descriptor, termios.TCSADRAIN, old_settings)


__all__ = ["choose_case_log_path", "parse_args", "run_terminal_session"]
