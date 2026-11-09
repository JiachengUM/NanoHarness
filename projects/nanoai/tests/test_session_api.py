from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from aicore.events.react import ReActTextDeltaEvent, ReActTextDoneEvent
from aicore.models.model_api import ModelParams
from aicore.v1.experiments.agent import AgentContext, AgentState

from projects.nanoai.main import create_app
from projects.nanoai.service import SessionService


class FakeAgent:
    async def astream(self, query: Any, /, **kwargs: Any) -> AsyncIterator[Any]:
        yield ReActTextDeltaEvent(delta=f"{query} ")
        yield ReActTextDoneEvent(text="done")

    async def dump(self) -> tuple[AgentContext, AgentState]:
        return (
            AgentContext(
                system_prompt="你是测试助手。",
                model_params=ModelParams(model="fake-model"),
            ),
            AgentState(),
        )


def test_session_http_lifecycle_and_sse() -> None:
    service = SessionService(
        agent_factory_builder=lambda _: lambda __, ___: FakeAgent()
    )
    client = TestClient(create_app(session_service=service))

    created = client.post(
        "/v1/sessions",
        json={
            "config": {"model": "fake-model"},
            "context": {"user_id": "user-1"},
            "metadata": {"source": "test"},
        },
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    unsupported_update = client.post(
        f"/v1/sessions/{session_id}/turns",
        json={"input": "hello", "state_update": {"car_info": {"battery_percent": 74}}},
    )
    assert unsupported_update.status_code == 422
    assert (
        "does not support dynamic state updates" in unsupported_update.json()["detail"]
    )

    streamed = client.post(f"/v1/sessions/{session_id}/turns", json={"input": "hello"})
    assert streamed.status_code == 200
    assert streamed.headers["x-nanoai-turn-id"].startswith("turn-")
    assert "text/event-stream" in streamed.headers["content-type"]
    assert "event: session.submitted" in streamed.text
    assert "event: session.output" in streamed.text
    assert "event: session.turn.finished" in streamed.text

    session = client.get(f"/v1/sessions/{session_id}")
    assert session.status_code == 200
    turn = session.json()["state"]["history"][0]
    assert turn["status"] == "completed"
    assert turn["input"] == "hello"
    assert turn["traces"][-1]["data"]["type"] == "react.text.done"

    dumped = client.get(f"/v1/sessions/{session_id}/dump")
    assert dumped.status_code == 200
    assert dumped.json()["session_id"] == session_id
    assert "nanoai.v1_agent_snapshot" in dumped.json()["metadata"]

    restored_service = SessionService()
    restored_client = TestClient(create_app(session_service=restored_service))
    restored = restored_client.post("/v1/sessions/restore", json=dumped.json())
    assert restored.status_code == 201
    assert restored.json()["session_id"] == session_id

    restored_view = restored_client.get(f"/v1/sessions/{session_id}")
    assert restored_view.status_code == 200
    assert restored_view.json()["state"]["history"][0]["input"] == "hello"
    assert restored_view.json()["metadata"] == {"source": "test"}
    duplicate_restore = restored_client.post("/v1/sessions/restore", json=dumped.json())
    assert duplicate_restore.status_code == 409

    pending_submission, _ = service.get(session_id).submit("cancel me")
    cancelled = client.post(
        f"/v1/sessions/{session_id}/turns/{pending_submission.turn_id}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["id"] == pending_submission.turn_id
    assert cancelled.json()["status"] == "cancelled"

    closed = client.delete(f"/v1/sessions/{session_id}")
    assert closed.status_code == 204
    assert client.get(f"/v1/sessions/{session_id}").status_code == 404
