"""Local-device CLI for the external-Agent speech shell."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Any

from aicore.models.stream_model_api.duplex.config import (
    DEFAULT_PCM,
    OGG_OPUS,
    DuplexConfig,
)
from aicore.models.stream_model_api.duplex.duplex_client import DuplexClient
from aicore.models.stream_model_api.duplex.websocket_transport import (
    DuplexWebSocketTransport,
)
from aicore.runtime.task import TaskManager
from aicore.v2.agent_runner import AgentRunner
from aicore.v2.experiments.duplex_speech_shell.agent_tts import AgentTtsPump
from aicore.v2.experiments.duplex_speech_shell.backend import (
    RawDuplexSpeechBackend,
)
from aicore.v2.experiments.duplex_speech_shell.local_audio import build_local_audio
from aicore.v2.experiments.duplex_speech_shell.local_frontend import (
    LocalSpeechShell,
)
from aicore.v2.experiments.duplex_speech_shell.local_runtime import (
    LocalAgentRuntime,
    QueueUserDataSource,
    print_non_delta_agent_event,
)
from aicore.v2.experiments.duplex_speech_shell.profile import (
    build_speech_shell_session_config,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Duplex speech transport with the AICore v2 agent.",
    )
    parser.add_argument("--audio", default="")
    parser.add_argument("--chat-id", default="duplex-v2-chat")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--auth-mode",
        choices=("auto", "app-key", "x-api-key", "bearer"),
        default="app-key",
    )
    parser.add_argument("--endpoint-url", default=None)
    parser.add_argument(
        "--mic-mode",
        choices=("space_gate", "continuous"),
        default="space_gate",
    )
    return parser.parse_args(argv)


def build_local_session(args: argparse.Namespace) -> LocalSpeechShell:
    """Composition root retaining the historical Agent model/prompt/tools."""

    config = DuplexConfig()
    config.asr_format = DEFAULT_PCM
    if not config.api_key:
        raise RuntimeError("DuplexConfig.api_key is required")
    if config.tts_format == OGG_OPUS and not args.audio:
        raise RuntimeError(
            'Microphone mode requires tts_format = "pcm_s16le" or "pcm".'
        )
    if args.endpoint_url:
        config.endpoint_url = args.endpoint_url

    transport = DuplexWebSocketTransport.from_config(
        config,
        auth_mode=args.auth_mode,
    )
    client = DuplexClient(transport=transport)
    session, extension = build_speech_shell_session_config(
        config,
        session_id=client.session_id,
    )
    backend = RawDuplexSpeechBackend(
        client,
        session=session,
        extension=extension,
    )

    user_data = QueueUserDataSource()
    runtime_holder: dict[str, LocalAgentRuntime] = {}

    def accept_agent_event(event: Any) -> None:
        runtime_holder["runtime"].accept_agent_event(event)

    runner = _build_agent_runner(
        user_data=user_data,
        client=accept_agent_event,
        chat_id=args.chat_id,
        model=args.model,
    )
    runtime = LocalAgentRuntime(
        runner=runner,
        user_data=user_data,
        tts_pump=AgentTtsPump(backend),
        event_logger=print_non_delta_agent_event,
    )
    runtime_holder["runtime"] = runtime
    audio = build_local_audio(backend, config, file_mode=bool(args.audio))
    return LocalSpeechShell(
        backend=backend,
        runtime=runtime,
        audio=audio,
        audio_file=args.audio,
        mic_mode=args.mic_mode,
    )


def _build_agent_runner(
    *,
    user_data: QueueUserDataSource,
    client: Any,
    chat_id: str,
    model: str | None,
) -> AgentRunner:
    from aicore.models.credentials import ModelName
    from aicore.v2.experiments.react_agent_with_task_runner import (
        create_react_agent_with_task_runner,
    )
    from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
    from projects.experiments.s2s.s2s_agent_config import build_v2_s2s_system_prompt
    from projects.mind.toolset.experiments.async_task_tools import get_async_task_tools

    task_manager = TaskManager()
    tools = [
        *get_async_task_tools(chat_id=chat_id, task_manager=task_manager),
        create_task_cancel_tool(task_manager=task_manager),
    ]
    agent = create_react_agent_with_task_runner(
        model=model or ModelName.SEED_1_8_251228,
        tools=tools,
        system_prompt=build_v2_s2s_system_prompt(),
    )
    return AgentRunner(
        user_data=user_data,
        agent=agent,
        task_manager=task_manager,
        client=client,
    )


async def async_main(argv: list[str] | None = None) -> None:
    await run_local_session(build_local_session(parse_args(argv)))


async def run_local_session(shell: LocalSpeechShell) -> None:
    """Supervise terminal input, signals, and one local speech-shell session."""

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    installed_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
            installed_signals.append(sig)
        except NotImplementedError:
            pass

    stop_task = asyncio.create_task(stop_event.wait(), name="duplex-local-signal")
    wait_task: asyncio.Task[None] | None = None
    keyboard_task: asyncio.Task[None] | None = None
    try:
        await shell.start()
        wait_task = asyncio.create_task(
            shell.wait_finished(),
            name="duplex-local-finished",
        )
        keyboard_task = _start_keyboard_task(shell)
        watched = {wait_task, stop_task}
        if keyboard_task is not None:
            watched.add(keyboard_task)
        done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
        if stop_task in done:
            await shell.stop()
        elif keyboard_task is not None and keyboard_task in done:
            if not wait_task.done() and shell.running:
                error = keyboard_task.exception()
                await shell.stop()
                if error is not None:
                    raise RuntimeError("Microphone keyboard task failed") from error
                raise RuntimeError("Microphone keyboard task stopped unexpectedly")
        await wait_task
    finally:
        await shell.stop()
        tasks = [stop_task]
        for task in (wait_task, keyboard_task):
            if task is not None:
                tasks.append(task)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for sig in installed_signals:
            loop.remove_signal_handler(sig)


def _start_keyboard_task(shell: LocalSpeechShell) -> asyncio.Task[None] | None:
    if shell.file_mode or shell.mic_mode != "space_gate":
        return None
    if not sys.stdin.isatty():
        print("[MIC] 标准输入不是 TTY，空格麦克风触发已禁用")
        return None
    return asyncio.create_task(
        _keyboard_space_loop(shell),
        name="duplex-local-keyboard",
    )


async def _keyboard_space_loop(shell: LocalSpeechShell) -> None:
    """Read Space without blocking the async provider receive loop."""

    print("[MIC] 按空格打开一轮麦克风输入")
    if sys.platform.startswith("win"):
        import msvcrt

        while shell.running:
            if msvcrt.kbhit() and msvcrt.getwch() == " ":
                shell.open_microphone()
            await asyncio.sleep(0.05)
        return

    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    old_settings = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        while shell.running:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if readable and sys.stdin.read(1) == " ":
                shell.open_microphone()
            await asyncio.sleep(0.05)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, old_settings)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()


__all__ = [
    "async_main",
    "build_local_session",
    "main",
    "parse_args",
    "run_local_session",
]
