"""文件上传下载接口测试（默认 mock TOS，可切换真实集成测试）。"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from projects.mind.test_backend.api.routers import api_router
from projects.mind.test_backend.api.file import file_api


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    return app


_FAKE_STORAGE: dict[str, tuple[bytes, str]] = {}


class FakeTosClient:
    """Mock TOS 客户端：用内存 dict 模拟对象存储（共享存储）。"""

    def __init__(self, config=None):
        self._storage = _FAKE_STORAGE
        self.config = config or SimpleNamespace(bucket_name="fake", base_path="dev/mind_test")

    def build_object_key(self, *parts: str) -> str:
        prefix = getattr(self.config, "base_path", "").strip("/")
        suffix = "/".join(part.strip("/") for part in parts if part)
        if prefix and suffix:
            return f"{prefix}/{suffix}"
        return prefix or suffix

    def upload_bytes(
        self,
        object_key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = object_key.lstrip("/")
        self._storage[key] = (body, content_type)
        return key

    def download_bytes(self, object_key: str) -> bytes:
        key = object_key.lstrip("/")
        if key not in self._storage:
            raise RuntimeError(f"object not found: {key}")
        return self._storage[key][0]

    def presigned_get_url(self, object_key: str, *, expires_sec: int = 3600) -> str:
        key = object_key.lstrip("/")
        if key not in self._storage:
            raise RuntimeError(f"object not found: {key}")
        return f"https://fake-tos.example.com/{key}?expires={expires_sec}"


@pytest.fixture
def client(monkeypatch):
    _FAKE_STORAGE.clear()
    monkeypatch.setattr(file_api, "_get_client", lambda: FakeTosClient())
    app = _build_app()
    with TestClient(app) as c:
        yield c


def test_upload_file_success(client: TestClient):
    content = b"hello world"
    response = client.post(
        "/api/file/upload",
        files={"file": ("test.txt", BytesIO(content), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["filename"] == "test.txt"
    assert body["data"]["size"] == len(content)
    assert body["data"]["content_type"] == "text/plain"
    assert body["data"]["object_key"].endswith(".txt")
    assert "dev/mind_test/" in body["data"]["object_key"]


def test_upload_file_with_folder(client: TestClient):
    content = b"folder test"
    response = client.post(
        "/api/file/upload",
        files={"file": ("data.csv", BytesIO(content), "text/csv")},
        data={"folder": "uploads/reports"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert "dev/mind_test/uploads/reports/" in body["data"]["object_key"]
    assert body["data"]["object_key"].endswith(".csv")


def test_download_file_success(client: TestClient):
    content = b"download me"
    upload_resp = client.post(
        "/api/file/upload",
        files={"file": ("download.txt", BytesIO(content), "text/plain")},
    )
    object_key = upload_resp.json()["data"]["object_key"]

    download_resp = client.get(f"/api/file/download/{object_key}")
    assert download_resp.status_code == 200
    assert download_resp.content == content
    assert "attachment" in download_resp.headers["Content-Disposition"]
    assert ".txt" in download_resp.headers["Content-Disposition"]


def test_download_file_inline(client: TestClient):
    content = b"inline content"
    upload_resp = client.post(
        "/api/file/upload",
        files={"file": ("inline.txt", BytesIO(content), "text/plain")},
    )
    object_key = upload_resp.json()["data"]["object_key"]

    download_resp = client.get(
        f"/api/file/download/{object_key}",
        params={"download": False},
    )
    assert download_resp.status_code == 200
    assert download_resp.content == content
    assert "inline" in download_resp.headers["Content-Disposition"]


def test_download_file_not_found(client: TestClient, monkeypatch):
    fake = FakeTosClient()
    monkeypatch.setattr(file_api, "_get_client", lambda: fake)
    response = client.get(
        "/api/file/download/dev/mind_test/nonexistent.txt",
    )
    assert response.status_code == 500
    body = response.json()
    assert "下载失败" in body["detail"]


def test_presigned_url_success(client: TestClient):
    content = b"presigned test"
    upload_resp = client.post(
        "/api/file/upload",
        files={"file": ("presign.txt", BytesIO(content), "text/plain")},
    )
    object_key = upload_resp.json()["data"]["object_key"]

    presign_resp = client.get(
        "/api/file/presigned_url",
        params={"object_key": object_key, "expires_sec": 7200},
    )
    assert presign_resp.status_code == 200
    body = presign_resp.json()
    assert body["code"] == 200
    assert body["data"]["object_key"] == object_key
    assert body["data"]["expires_sec"] == 7200
    assert body["data"]["url"].startswith("https://")
    assert "expires=7200" in body["data"]["url"]


def test_presigned_url_missing_key(client: TestClient):
    response = client.get("/api/file/presigned_url", params={"object_key": ""})
    assert response.status_code == 400
