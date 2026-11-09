from __future__ import annotations

from fastapi.testclient import TestClient

from projects.sgm_prod.api import app


def test_simple_complex_arbitration_hides_trace_by_default() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/simple_complex_arbitration",
        json={
            "query": "打开左前车窗",
            "chat_id": "test_chat",
            "question_id": "test_question",
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errno"] == 0
    assert body["data"] == "simple"
    assert body["source"] in {"exact_simple", "parser_simple"}
    assert body["trace"] is None


def test_simple_complex_arbitration_returns_trace_in_debug_mode() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/simple_complex_arbitration",
        json={
            "query": "打开左前车窗",
            "chat_id": "test_chat",
            "question_id": "test_question",
            "history": [],
            "debug": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errno"] == 0
    assert body["data"] == "simple"
    assert body["source"] in {"exact_simple", "parser_simple"}
    assert body["trace"]["normalized_query"] == "打开左前车窗"
    assert body["trace"]["matched_candidates"]
    assert body["trace"]["decision_path"]


def test_simple_complex_arbitration_accepts_project_and_returns_trace_project() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/simple_complex_arbitration",
        json={
            "query": "打开左前车窗",
            "chat_id": "test_chat",
            "question_id": "test_question",
            "project": "SGM",
            "history": [],
            "debug": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errno"] == 0
    assert body["trace"]["project"] == "SGM"


def test_simple_complex_arbitration_rejects_unknown_project() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/simple_complex_arbitration",
        json={
            "query": "打开左前车窗",
            "chat_id": "test_chat",
            "question_id": "test_question",
            "project": "MISSING",
            "history": [],
            "debug": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errno"] == 400
    assert body["msg"] == "unknown router project: MISSING"
    assert body["data"] == ""
    assert body["source"] == "config_error"
    assert body["trace"] is None
