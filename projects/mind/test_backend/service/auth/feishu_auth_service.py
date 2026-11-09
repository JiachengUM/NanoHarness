from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx
from starlette.requests import Request
from starlette.datastructures import URL

from projects.mind.test_backend.config import get_feishu_config
from projects.mind.test_backend.mdb_models.auth import FeishuUserDoc
from projects.mind.test_backend.service.task.feishu_notify_service import (
    _read_feishu_response,
)

FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_USER_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

FEISHU_OAUTH_STATE_COOKIE = "mind_feishu_oauth_state"
FEISHU_SESSION_COOKIE = "mind_feishu_session"
FEISHU_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
FEISHU_STATE_TTL_SECONDS = 60 * 10


class FeishuAuthError(RuntimeError):
    """Raised when Feishu login cannot be completed."""


@dataclass(frozen=True)
class FeishuAuthConfig:
    app_id: str
    app_secret: str
    redirect_uri: str
    cookie_secret: str


def resolve_feishu_auth_config(
    request: Request,
    *,
    env: Mapping[str, str] | None = None,
) -> FeishuAuthConfig:
    env = env if env is not None else os.environ
    feishu_config = get_feishu_config()
    app_id = feishu_config.app_id
    app_secret = feishu_config.app_secret
    cookie_secret = app_secret
    redirect_uri = feishu_config.oauth_redirect_uri or _resolve_redirect_uri(
        request
    )

    missing = [
        name
        for name, value in {
            "FEISHU_APP_ID": app_id,
            "FEISHU_APP_SECRET": app_secret,
            "FEISHU_LOGIN_COOKIE_SECRET or FEISHU_APP_SECRET": cookie_secret,
        }.items()
        if not value
    ]
    if missing:
        raise FeishuAuthError(f"Missing Feishu auth config: {', '.join(missing)}")

    return FeishuAuthConfig(
        app_id=str(app_id),
        app_secret=str(app_secret),
        redirect_uri=redirect_uri,
        cookie_secret=str(cookie_secret),
    )


def resolve_feishu_cookie_secret() -> str | None:
    feishu_config = get_feishu_config()
    return feishu_config.app_secret


def build_feishu_authorize_url(
    config: FeishuAuthConfig,
    *,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "client_id": config.app_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{FEISHU_AUTHORIZE_URL}?{urlencode(params)}"


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(48)


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def create_signed_cookie(
    data: Mapping[str, Any],
    *,
    secret: str,
    expires_at: datetime,
) -> str:
    payload = {**data, "exp": int(expires_at.timestamp())}
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_b64 = _base64_url_encode(payload_json.encode("utf-8"))
    signature = _sign(payload_b64, secret)
    return f"{payload_b64}.{signature}"


def read_signed_cookie(value: str | None, *, secret: str) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    payload_b64, signature = value.rsplit(".", 1)
    expected = _sign(payload_b64, secret)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload = json.loads(_base64_url_decode(payload_b64))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    return payload


def create_oauth_state_cookie(
    *,
    state: str,
    code_verifier: str,
    redirect_path: str,
    secret: str,
) -> str:
    return create_signed_cookie(
        {
            "state": state,
            "code_verifier": code_verifier,
            "redirect_path": normalize_redirect_path(redirect_path),
        },
        secret=secret,
        expires_at=datetime.now() + timedelta(seconds=FEISHU_STATE_TTL_SECONDS),
    )


def read_oauth_state_cookie(
    value: str | None,
    *,
    secret: str,
) -> dict[str, Any] | None:
    data = read_signed_cookie(value, secret=secret)
    if not data or not isinstance(data.get("state"), str):
        return None
    if not isinstance(data.get("code_verifier"), str):
        return None
    return data


def create_session_cookie(open_id: str, *, secret: str) -> str:
    return create_signed_cookie(
        {"open_id": open_id},
        secret=secret,
        expires_at=datetime.now() + timedelta(seconds=FEISHU_SESSION_TTL_SECONDS),
    )


def read_session_cookie(
    value: str | None,
    *,
    secret: str,
) -> dict[str, Any] | None:
    data = read_signed_cookie(value, secret=secret)
    if not data or not isinstance(data.get("open_id"), str):
        return None
    return data


def normalize_redirect_path(path: str | None) -> str:
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    return path


def _resolve_redirect_uri(request: Request) -> str:
    callback_url = URL(str(request.url_for("feishu_oauth_callback")))
    forwarded_host = request.headers.get("x-forwarded-host")
    if not forwarded_host:
        return str(callback_url)

    forwarded_proto = (
        request.headers.get("x-forwarded-proto")
        or request.url.scheme
        or callback_url.scheme
    )
    host = forwarded_host.split(",", 1)[0].strip()
    scheme = forwarded_proto.split(",", 1)[0].strip()
    return str(callback_url.replace(scheme=scheme, netloc=host))


async def exchange_code_for_user_access_token(
    config: FeishuAuthConfig,
    *,
    code: str,
    code_verifier: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> str:
    async def _exchange(active_client: httpx.AsyncClient) -> str:
        payload = {
            "grant_type": "authorization_code",
            "client_id": config.app_id,
            "client_secret": config.app_secret,
            "code": code,
            "redirect_uri": config.redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        response = await active_client.post(FEISHU_USER_TOKEN_URL, json=payload)
        data = _read_feishu_response(response)
        token_data = data.get("data") if isinstance(data.get("data"), dict) else data
        token = token_data.get("access_token")
        if not token:
            keys = ", ".join(sorted(str(key) for key in data.keys()))
            raise FeishuAuthError(
                f"Feishu OAuth response missing access_token; response keys: {keys}"
            )
        return str(token)

    if client:
        return await _exchange(client)

    async with httpx.AsyncClient(timeout=10.0) as active_client:
        return await _exchange(active_client)


async def fetch_feishu_user_info(
    user_access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    async def _fetch(active_client: httpx.AsyncClient) -> dict[str, Any]:
        response = await active_client.get(
            FEISHU_USER_INFO_URL,
            headers={
                "Authorization": f"Bearer {user_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        data = _read_feishu_response(response)
        user_info = data.get("data") or {}
        if not isinstance(user_info, dict):
            raise FeishuAuthError(f"Feishu user_info is not an object: {user_info!r}")
        if not user_info.get("open_id"):
            raise FeishuAuthError("Feishu user_info response missing open_id")
        return dict(user_info)

    if client:
        return await _fetch(client)

    async with httpx.AsyncClient(timeout=10.0) as active_client:
        return await _fetch(active_client)


async def upsert_feishu_user(user_info: Mapping[str, Any]) -> FeishuUserDoc:
    payload = _build_feishu_user_payload(user_info)
    existing = await FeishuUserDoc.find_one({"open_id": payload["open_id"]})
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.last_login_at = datetime.now()
        await existing.save()
        return existing

    doc = FeishuUserDoc(**payload, last_login_at=datetime.now())
    return await doc.insert()


async def get_current_feishu_user_from_cookie(
    cookie_value: str | None,
    *,
    secret: str | None = None,
) -> FeishuUserDoc | None:
    secret = secret or resolve_feishu_cookie_secret()
    if not secret:
        return None
    session = read_session_cookie(cookie_value, secret=secret)
    if not session:
        return None
    return await FeishuUserDoc.find_one({"open_id": session["open_id"]})


async def get_optional_current_feishu_user(request: Request) -> FeishuUserDoc | None:
    return await get_current_feishu_user_from_cookie(
        request.cookies.get(FEISHU_SESSION_COOKIE)
    )


def should_secure_cookie(request: Request) -> bool:
    feishu_config = get_feishu_config()
    value = feishu_config.auth_cookie_secure
    if value is not None:
        return value
    return request.url.scheme == "https"


def _build_feishu_user_payload(user_info: Mapping[str, Any]) -> dict[str, Any]:
    open_id = user_info.get("open_id")
    if not open_id:
        raise FeishuAuthError("Feishu user_info response missing open_id")
    name = user_info.get("name") or user_info.get("en_name") or str(open_id)
    return {
        "open_id": str(open_id),
        "union_id": _optional_str(user_info.get("union_id")),
        "user_id": _optional_str(user_info.get("user_id")),
        "name": str(name),
        "avatar_url": _optional_str(user_info.get("avatar_url")),
        "email": _optional_str(
            user_info.get("email") or user_info.get("enterprise_email")
        ),
        "mobile": _optional_str(user_info.get("mobile")),
        "tenant_key": _optional_str(user_info.get("tenant_key")),
    }


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _base64_url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64_url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def _sign(value: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("ascii"), hashlib.sha256)
    return _base64_url_encode(digest.digest())


__all__ = [
    "FEISHU_OAUTH_STATE_COOKIE",
    "FEISHU_SESSION_COOKIE",
    "FEISHU_SESSION_TTL_SECONDS",
    "FeishuAuthConfig",
    "FeishuAuthError",
    "build_code_challenge",
    "build_feishu_authorize_url",
    "create_oauth_state_cookie",
    "create_session_cookie",
    "create_signed_cookie",
    "exchange_code_for_user_access_token",
    "fetch_feishu_user_info",
    "generate_code_verifier",
    "generate_oauth_state",
    "get_current_feishu_user_from_cookie",
    "get_optional_current_feishu_user",
    "normalize_redirect_path",
    "read_oauth_state_cookie",
    "read_session_cookie",
    "read_signed_cookie",
    "resolve_feishu_auth_config",
    "resolve_feishu_cookie_secret",
    "should_secure_cookie",
    "upsert_feishu_user",
]
