"""Compatibility FastAPI app for the legacy Duplex ASR/TTS v2 voice bridge.

The application remains under ``aicore.v2.experiments`` for its existing mount
path, but it is an application composition root and may depend on project tools;
it must not be treated as part of the Duplex provider core.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from aicore.runtime.task import TaskManager
from aicore.v2.experiments.v2_frontend_backend import (
    AgentMode,
    CHAT_ID,
    WebSocketAgentSession,
    _build_agent as _build_base_agent,
    handle_client_command,
    hello_message,
    parse_client_command,
)
from aicore.v2.experiments.v2_frontend_duplex_voice import (
    DuplexFrontendVoiceBridge,
)


class _SuppressDocsHeadAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        method = str(args[1])
        path = str(args[2]).partition("?")[0]
        return method != "HEAD" or path != "/docs"


def _suppress_docs_head_access_logs() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if any(
        isinstance(existing, _SuppressDocsHeadAccessFilter)
        for existing in access_logger.filters
    ):
        return
    access_logger.addFilter(_SuppressDocsHeadAccessFilter())


def _build_duplex_voice_bridge(**kwargs: Any) -> DuplexFrontendVoiceBridge:
    return DuplexFrontendVoiceBridge(**kwargs)


def _build_duplex_agent(task_manager: TaskManager, mode: AgentMode):
    if mode == "plact":
        return _build_base_agent(task_manager, mode)

    from aicore.models.credentials import ModelName
    from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT
    from aicore.v2.experiments.react_agent_with_task_runner import (
        create_react_agent_with_task_runner,
        render_active_task_context,
    )
    from aicore.v2.experiments.react_task_tool import (
        NAVIGATION_REACT_TASK_SYSTEM_PROMPT,
        REACT_TASK_SELECTION_PROMPT,
        create_react_task_tool,
    )
    from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
    from aicore.v2.tools.async_task import AsyncableTaskTool
    from projects.mind.toolset.experiments.async_task_tools import (
        get_async_task_tools,
    )

    business_tools = get_async_task_tools(
        CHAT_ID,
        task_manager,
        asyncable="dynamic",
    )
    business_tools_by_name = {tool.name: tool for tool in business_tools}

    raw_tool_registry = {}
    for tool_name in ("地点搜索工具", "navigation"):
        wrapped_tool = business_tools_by_name[tool_name]
        if not isinstance(wrapped_tool, AsyncableTaskTool):
            raise TypeError(f"{tool_name} 不是 AsyncableTaskTool")
        raw_tool_registry[tool_name] = wrapped_tool.inner_tool

    react_task_tool = create_react_task_tool(
        task_manager=task_manager,
        model=ModelName.SEED_2_0_PRO_260215,
        tool_registry=raw_tool_registry,
        system_prompt=NAVIGATION_REACT_TASK_SYSTEM_PROMPT,
        max_turns=4,
    )
    tools = [
        react_task_tool,
        *business_tools,
        create_task_cancel_tool(task_manager=task_manager),
    ]
    return create_react_agent_with_task_runner(
        model=ModelName.SEED_2_0_PRO_260215,
        tools=tools,
        system_prompt=(
            f"{ASYNC_REACT_SYSTEM_PROMPT}\n\n{REACT_TASK_SELECTION_PROMPT}"
        ),
        max_turns=5,
        ambient_context_provider=lambda: render_active_task_context(task_manager),
    )


class DuplexWebSocketAgentSession(WebSocketAgentSession):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("agent_factory", _build_duplex_agent)
        kwargs.setdefault("runtime_profile", "duplex_native")
        super().__init__(**kwargs)


def create_app(
    session_factory: type[WebSocketAgentSession] = DuplexWebSocketAgentSession,
) -> FastAPI:
    app = FastAPI(
        title="v2 Agent Duplex Frontend Backend",
        description="Existing v2 frontend protocol backed by the Duplex speech shell.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.frontend_session_factory = session_factory

    @app.websocket("/v2/frontend/ws")
    async def frontend_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        session = app.state.frontend_session_factory()
        writer_task = asyncio.create_task(session.write_to(websocket))
        await session.send(
            hello_message(
                connection_id=session.connection_id,
                session_id=session.session_id,
                generation=session.generation,
                runtime_profile=session.runtime_profile,
                capabilities=session.capabilities,
            )
        )

        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break

                raw = message.get("text")
                if raw is not None:
                    command = await parse_client_command(raw, session=session)
                    if command is not None:
                        await handle_client_command(session, command)
                    continue

                chunk = message.get("bytes")
                if chunk is not None:
                    await session.feed_voice_audio(chunk)
        except WebSocketDisconnect:
            pass
        finally:
            await session.stop()
            await session.close_outbound()
            writer_task.cancel()
            with suppress(asyncio.CancelledError):
                await writer_task

    return app


app = create_app()
_suppress_docs_head_access_logs()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("V2_FRONTEND_HOST", "127.0.0.1"),
        port=int(os.environ.get("V2_FRONTEND_PORT", "8799")),
    )
