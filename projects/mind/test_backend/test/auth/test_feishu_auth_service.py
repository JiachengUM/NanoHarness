from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from starlette.datastructures import Headers, URL

from projects.mind.test_backend.service.auth.feishu_auth_service import (
    FeishuAuthConfig,
    build_feishu_authorize_url,
    create_signed_cookie,
    exchange_code_for_user_access_token,
    fetch_feishu_user_info,
    read_signed_cookie,
    resolve_feishu_auth_config,
    upsert_feishu_user,
)


def test_build_feishu_authorize_url_uses_state_redirect_and_pkce():
    config = FeishuAuthConfig(
        app_id="cli_xxx",
        app_secret="REDACTED",
        redirect_uri="http://localhost:5173/api/auth/feishu/callback",
        cookie_secret="cookie-secret",
    )

    url = build_feishu_authorize_url(
        config,
        state="state_123",
        code_challenge="challenge_123",
    )

    assert url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?")
    assert "client_id=cli_xxx" in url
    assert "response_type=code" in url
    assert "state=state_123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Fapi%2Fauth%2Ffeishu%2Fcallback" in url
    assert "code_challenge=challenge_123" in url
    assert "code_challenge_method=S256" in url


def test_signed_cookie_rejects_tampered_payload():
    value = create_signed_cookie(
        {"open_id": "ou_user"},
        secret="cookie-secret",
        expires_at=datetime.now() + timedelta(minutes=5),
    )

    assert read_signed_cookie(value, secret="cookie-secret")["open_id"] == "ou_user"
    assert read_signed_cookie(value + "x", secret="cookie-secret") is None


def test_resolve_feishu_auth_config_uses_forwarded_browser_host():
    request = SimpleNamespace(
        headers=Headers(
            {
                "x-forwarded-host": "127.0.0.1:9001",
                "x-forwarded-proto": "http",
            }
        ),
        url=URL("http://127.0.0.1:8000/api/auth/feishu/login"),
        url_for=lambda name: URL(
            "http://127.0.0.1:8000/api/auth/feishu/callback"
        ),
    )

    config = resolve_feishu_auth_config(
        request,
        env={"FEISHU_APP_ID": "cli_xxx", "FEISHU_APP_SECRET": "secret_xxx"},
    )

    assert (
        config.redirect_uri
        == "http://127.0.0.1:9001/api/auth/feishu/callback"
    )


@pytest.mark.asyncio
async def test_exchange_code_and_fetch_user_info_call_feishu_oauth_apis():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            assert request.method == "POST"
            assert request.headers["Content-Type"].startswith("application/json")
            assert request.read() == (
                b'{"grant_type":"authorization_code","client_id":"cli_xxx",'
                b'"client_secret":"secret_xxx","code":"auth_code",'
                b'"redirect_uri":"http://localhost/callback",'
                b'"code_verifier":"verifier_123"}'
            )
            return httpx.Response(
                200,
                json={"code": 0, "data": {"access_token": "user-token"}},
            )

        if request.url.path == "/open-apis/authen/v1/user_info":
            assert request.method == "GET"
            assert request.headers["Authorization"] == "Bearer user-token"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "open_id": "ou_user",
                        "union_id": "on_user",
                        "user_id": "user_1",
                        "name": "Wayne",
                        "avatar_url": "https://example.com/avatar.png",
                        "email": "wayne@example.com",
                        "mobile": "13800138000",
                        "tenant_key": "tenant_1",
                    },
                },
            )

        return httpx.Response(404)

    config = FeishuAuthConfig(
        app_id="cli_xxx",
        app_secret="REDACTED",
        redirect_uri="http://localhost/callback",
        cookie_secret="cookie-secret",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        token = await exchange_code_for_user_access_token(
            config,
            code="auth_code",
            code_verifier="verifier_123",
            client=client,
        )
        user_info = await fetch_feishu_user_info(token, client=client)

    assert token == "user-token"
    assert user_info["open_id"] == "ou_user"
    assert user_info["name"] == "Wayne"
    assert [request.url.path for request in requests] == [
        "/open-apis/authen/v2/oauth/token",
        "/open-apis/authen/v1/user_info",
    ]


@pytest.mark.asyncio
async def test_exchange_code_accepts_v2_top_level_access_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/authen/v2/oauth/token"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "access_token": "user-token",
                "expires_in": 7200,
                "token_type": "Bearer",
            },
        )

    config = FeishuAuthConfig(
        app_id="cli_xxx",
        app_secret="REDACTED",
        redirect_uri="http://localhost/callback",
        cookie_secret="cookie-secret",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        token = await exchange_code_for_user_access_token(
            config,
            code="auth_code",
            client=client,
        )

    assert token == "user-token"


@pytest.mark.asyncio
async def test_upsert_feishu_user_persists_user_info(monkeypatch):
    saved_docs = []

    class FakeQuery:
        async def update(self, payload):
            saved_docs.append(("update", payload))

    class FakeUserDoc:
        @classmethod
        async def find_one(cls, query):
            saved_docs.append(("find_one", query))
            return None

        @classmethod
        def find(cls, query):
            saved_docs.append(("find", query))
            return FakeQuery()

        def __init__(self, **payload):
            self.payload = payload
            self.open_id = payload["open_id"]
            self.name = payload["name"]

        async def insert(self):
            saved_docs.append(("insert", self.payload))
            return self

    monkeypatch.setattr(
        "projects.mind.test_backend.service.auth.feishu_auth_service.FeishuUserDoc",
        FakeUserDoc,
    )

    doc = await upsert_feishu_user(
        {
            "open_id": "ou_user",
            "union_id": "on_user",
            "user_id": "user_1",
            "name": "Wayne",
            "avatar_url": "https://example.com/avatar.png",
            "email": "wayne@example.com",
            "mobile": "13800138000",
            "tenant_key": "tenant_1",
        }
    )

    assert doc.open_id == "ou_user"
    assert doc.name == "Wayne"
    assert saved_docs[0] == ("find_one", {"open_id": "ou_user"})
    assert saved_docs[1][0] == "insert"
    assert saved_docs[1][1]["email"] == "wayne@example.com"
