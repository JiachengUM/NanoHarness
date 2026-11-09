from __future__ import annotations

import logging
from fastapi.testclient import TestClient

from aicore.runtime.task import TaskManager
from aicore.v2.experiments.v2_frontend_backend import (
    PROTOCOL_VERSION,
    WebSocketAgentSession,
)
from aicore.v2.experiments.v2_frontend_duplex_backend import (
    DuplexWebSocketAgentSession,
    _SuppressDocsHeadAccessFilter,
    _build_duplex_agent,
    create_app,
)


class FakeSession(WebSocketAgentSession):
    stopped = False

    def __init__(self) -> None:
        super().__init__()

    async def stop(self) -> None:
        type(self).stopped = True


def test_duplex_backend_keeps_existing_frontend_websocket_contract() -> None:
    app = create_app(FakeSession)
    FakeSession.stopped = False

    with TestClient(app) as client:
        with client.websocket_connect("/v2/frontend/ws") as websocket:
            hello = websocket.receive_json()

    assert hello["kind"] == "hello"
    assert hello["v"] == PROTOCOL_VERSION
    assert FakeSession.stopped is True


def test_docs_head_access_filter_only_suppresses_keepalive() -> None:
    access_filter = _SuppressDocsHeadAccessFilter()

    docs_head = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:12345", "HEAD", "/docs", "1.1", 200),
        None,
    )
    docs_get = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:12345", "GET", "/docs", "1.1", 200),
        None,
    )
    health_head = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:12345", "HEAD", "/health", "1.1", 200),
        None,
    )

    assert access_filter.filter(docs_head) is False
    assert access_filter.filter(docs_get) is True
    assert access_filter.filter(health_head) is True


def test_duplex_react_agent_exposes_fixed_async_react_task() -> None:
    agent = _build_duplex_agent(TaskManager(), "react")
    tools = {tool.name: tool for tool in agent.tools}

    assert "react_task" in tools
    react_task_schema = tools["react_task"].args_schema
    assert set(react_task_schema.model_fields) == {"sub_goal", "tools"}
    assert "with_async" not in react_task_schema.model_fields

    poi_schema = tools["地点搜索工具"].args_schema
    assert {"with_async", "reason"}.issubset(poi_schema.model_fields)

    tool_items = react_task_schema.model_json_schema()["properties"]["tools"]["items"]
    assert tool_items["enum"] == ["地点搜索工具", "navigation"]

    session = DuplexWebSocketAgentSession()
    assert session.runtime_profile == "duplex_native"
    assert session._agent_factory is _build_duplex_agent
