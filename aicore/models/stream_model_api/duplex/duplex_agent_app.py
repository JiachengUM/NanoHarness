"""Application composition root and canonical CLI for the Duplex agent.

Provider, model API, AgentSession, tools and TaskManager are assembled here.
Terminal parsing and microphone keyboard control stay in :mod:`.cli`.

NOTE (temporary reverse dependency): concrete tools still live in
``projects.mind.toolset``. The function-local import prevents the reusable
Duplex runtime from depending on ``projects`` when merely imported.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from aicore.models.stream_model_api.duplex.async_agent_prompt import (
    ASYNC_AGENT_SYSTEM_PROMPT,
)
from aicore.models.stream_model_api.duplex.async_backfill import (
    BackfillActivation,
    DuplexAsyncCompatConfig,
)
from aicore.models.stream_model_api.duplex.cli import (
    choose_case_log_path,
    parse_args,
    run_terminal_session,
)
from aicore.models.stream_model_api.duplex.config import (
    DEFAULT_PCM,
    OGG_OPUS,
    PCM_S16LE,
    DuplexConfig,
    build_duplex_session_config,
)
from aicore.models.stream_model_api.duplex.diagnostics import DuplexDiagnostics
from aicore.models.stream_model_api.duplex.duplex_agent_session import (
    DuplexAgentSession,
)
from aicore.models.stream_model_api.duplex.duplex_client import DuplexClient
from aicore.models.stream_model_api.duplex.duplex_stream_model_api import (
    DuplexStreamModelAPI,
)
from aicore.models.stream_model_api.duplex.sync_agent_prompt import (
    SYNC_AGENT_SYSTEM_PROMPT,
)
from aicore.models.stream_model_api.duplex.websocket_transport import (
    DuplexWebSocketTransport,
)
from aicore.models.stream_model_api.protocol import ToolCallMode
from aicore.models.stream_model_api.events import StreamModelEvent
from aicore.models.stream_model_api.duplex.media_port import DuplexMediaPort
from aicore.events.task import TaskEvent
from aicore.runtime.task import TaskManager
from aicore.v2.experiments.task_cancel_tool import create_raw_task_cancel_tool


DESCRIPTION = "Run the Duplex StreamModelAPI agent session."
_browser_logger = logging.getLogger("uvicorn.error")
_SYSTEM_PROMPTS: dict[ToolCallMode, str] = {
    "sync": SYNC_AGENT_SYSTEM_PROMPT,
    "async": ASYNC_AGENT_SYSTEM_PROMPT,
}


def system_prompt_for(tool_call_mode: ToolCallMode) -> str:
    return _SYSTEM_PROMPTS[tool_call_mode]


def _log_browser_runtime_event(message: str) -> None:
    _browser_logger.info("[DUPLEX NATIVE] %s", message)


def _log_browser_provider_event(
    direction: str,
    event: dict[str, object],
    _raw: str,
) -> None:
    event_type = str(event.get("type") or "")
    if event_type.endswith(".delta") or event_type == "input_audio_buffer.append":
        return
    _browser_logger.info(
        "[DUPLEX PROVIDER] %s type=%s event_id=%s question_id=%s response_id=%s",
        direction,
        event_type or "<missing>",
        event.get("event_id"),
        event.get("question_id"),
        event.get("response_id"),
    )


def build_browser_duplex_agent_session(
    *,
    media_port: DuplexMediaPort,
    model_event_observer: Callable[
        [StreamModelEvent], Awaitable[None] | None
    ],
    task_event_observer: Callable[[TaskEvent], None],
    task_manager: TaskManager,
    backfill_activation_observer: Callable[[BackfillActivation], None] | None = None,
    config: DuplexConfig | None = None,
    async_compat: DuplexAsyncCompatConfig | None = None,
) -> DuplexAgentSession:
    """Assemble the native Duplex core for a browser-owned media session."""

    resolved_config = replace(
        config or DuplexConfig(),
        asr_format=PCM_S16LE,
        tts_format=PCM_S16LE,
    )
    resolved_config.instructions = system_prompt_for("async")
    if not resolved_config.api_key:
        raise RuntimeError("DuplexConfig.api_key is required")
    from projects.mind.toolset.experiments.async_task_tools import get_task_tools

    tools = get_task_tools(chat_id="v2-frontend-agent")
    tools.append(create_raw_task_cancel_tool(task_manager=task_manager))
    transport = DuplexWebSocketTransport.from_config(
        resolved_config,
        event_observer=_log_browser_provider_event,
    )
    client = DuplexClient(transport=transport)
    session_config, extension = build_duplex_session_config(
        resolved_config,
        session_id=client.session_id,
    )
    model_api = DuplexStreamModelAPI(
        client=client,
        session=session_config,
        extension=extension,
        tools=tools,
    )
    return DuplexAgentSession(
        model_api=model_api,
        tools=tools,
        task_manager=task_manager,
        tool_call_mode="async",
        config=resolved_config,
        async_compat=async_compat or DuplexAsyncCompatConfig(),
        context_diagnostics=False,
        task_event_observer=task_event_observer,
        model_event_observer=model_event_observer,
        backfill_activation_observer=backfill_activation_observer,
        runtime_event_observer=_log_browser_runtime_event,
        media_port=media_port,
    )


async def run_duplex_agent(
    argv: list[str] | None = None,
    *,
    async_compat: DuplexAsyncCompatConfig | None = None,
) -> None:
    args = parse_args(argv, description=DESCRIPTION)
    tool_call_mode: ToolCallMode = args.tool_call_mode
    case_log_path = choose_case_log_path(
        args.case_log,
        # IDE run consoles may support input even when isatty() is false.
        interactive=not args.audio,
    )
    config = DuplexConfig()
    config.instructions = system_prompt_for(tool_call_mode)
    if args.audio:
        config.asr_format = DEFAULT_PCM
    if args.model:
        config.model = args.model
    if args.endpoint_url:
        config.endpoint_url = args.endpoint_url
    if not config.api_key:
        raise RuntimeError("DuplexConfig.api_key is required")
    if config.tts_format == OGG_OPUS and not args.audio:
        raise RuntimeError(
            'Microphone mode requires tts_format = "pcm_s16le" or "pcm".'
        )

    if tool_call_mode == "async" and args.audio:
        raise ValueError(
            "Duplex async continuation does not support --audio: the first audio reply "
            "is only a placeholder and is not the session terminal"
        )
    if tool_call_mode == "sync" and async_compat is not None:
        raise ValueError("Duplex async compatibility requires tool_call_mode=async")
    if tool_call_mode == "async" and async_compat is None:
        async_compat = DuplexAsyncCompatConfig()

    from projects.mind.toolset.experiments.async_task_tools import get_task_tools

    task_manager = TaskManager(max_concurrency=10)
    tools = get_task_tools(chat_id=args.chat_id)
    if tool_call_mode == "async":
        tools.append(create_raw_task_cancel_tool(task_manager=task_manager))

    with DuplexDiagnostics(case_log_path) as diagnostics:
        diagnostics.record_session(
            model=config.model,
            tool_call_mode=tool_call_mode,
            tool_names=[tool.name for tool in tools],
        )
        transport = DuplexWebSocketTransport.from_config(
            config,
            auth_mode=args.auth_mode,
            event_observer=diagnostics.duplex_event,
        )
        client = DuplexClient(transport=transport)
        session_config, extension = build_duplex_session_config(
            config,
            session_id=client.session_id,
        )
        model_api = DuplexStreamModelAPI(
            client=client,
            session=session_config,
            extension=extension,
            tools=tools,
        )
        agent_session = DuplexAgentSession(
            model_api=model_api,
            tools=tools,
            config=config,
            task_manager=task_manager,
            tool_call_mode=tool_call_mode,
            audio_file=args.audio,
            output_audio_path=Path(args.output_audio),
            async_compat=async_compat,
            task_event_observer=diagnostics.task_event,
            runtime_event_observer=diagnostics.runtime_event,
            mic_mode=args.mic_mode,
        )
        await run_terminal_session(agent_session, args.mic_mode)


async def async_main(argv: list[str] | None = None) -> None:
    await run_duplex_agent(argv)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()


__all__ = [
    "ASYNC_AGENT_SYSTEM_PROMPT",
    "DESCRIPTION",
    "SYNC_AGENT_SYSTEM_PROMPT",
    "async_main",
    "build_browser_duplex_agent_session",
    "main",
    "run_duplex_agent",
    "system_prompt_for",
]
