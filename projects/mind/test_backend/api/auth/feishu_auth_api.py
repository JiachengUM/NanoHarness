from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from projects.mind.test_backend.mdb_models.auth import FeishuUserDoc
from projects.mind.test_backend.schemas.auth import FeishuUserOut
from projects.mind.test_backend.schemas.response import ApiResponse, ok
from projects.mind.test_backend.service.auth.feishu_auth_service import (
    FEISHU_OAUTH_STATE_COOKIE,
    FEISHU_SESSION_COOKIE,
    FEISHU_SESSION_TTL_SECONDS,
    FeishuAuthError,
    build_code_challenge,
    build_feishu_authorize_url,
    create_oauth_state_cookie,
    create_session_cookie,
    exchange_code_for_user_access_token,
    fetch_feishu_user_info,
    generate_code_verifier,
    generate_oauth_state,
    get_optional_current_feishu_user,
    normalize_redirect_path,
    read_oauth_state_cookie,
    resolve_feishu_auth_config,
    should_secure_cookie,
    upsert_feishu_user,
)
from projects.mind.test_backend.utils.schemas import to_out

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


@router.get("/feishu/login")
async def feishu_login(
    request: Request,
    redirect: str = Query(default="/", description="登录成功后跳回的前端路径"),
):
    try:
        config = resolve_feishu_auth_config(request)
    except FeishuAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    state = generate_oauth_state()
    code_verifier = generate_code_verifier()
    code_challenge = build_code_challenge(code_verifier)
    url = build_feishu_authorize_url(
        config,
        state=state,
        code_challenge=code_challenge,
    )

    response = RedirectResponse(url, status_code=307)
    response.set_cookie(
        FEISHU_OAUTH_STATE_COOKIE,
        create_oauth_state_cookie(
            state=state,
            code_verifier=code_verifier,
            redirect_path=redirect,
            secret=config.cookie_secret,
        ),
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=should_secure_cookie(request),
        path="/",
    )
    return response


@router.get("/feishu/callback", name="feishu_oauth_callback")
async def feishu_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(status_code=400, detail=f"Feishu auth failed: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Feishu auth code or state")

    try:
        config = resolve_feishu_auth_config(request)
    except FeishuAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    state_cookie = read_oauth_state_cookie(
        request.cookies.get(FEISHU_OAUTH_STATE_COOKIE),
        secret=config.cookie_secret,
    )
    if not state_cookie or state_cookie.get("state") != state:
        raise HTTPException(status_code=400, detail="Invalid Feishu auth state")

    try:
        user_access_token = await exchange_code_for_user_access_token(
            config,
            code=code,
            code_verifier=str(state_cookie["code_verifier"]),
        )
        user_info = await fetch_feishu_user_info(user_access_token)
        user = await upsert_feishu_user(user_info)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response = RedirectResponse(
        normalize_redirect_path(str(state_cookie.get("redirect_path") or "/")),
        status_code=302,
    )
    response.delete_cookie(FEISHU_OAUTH_STATE_COOKIE, path="/")
    response.set_cookie(
        FEISHU_SESSION_COOKIE,
        create_session_cookie(user.open_id, secret=config.cookie_secret),
        max_age=FEISHU_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=should_secure_cookie(request),
        path="/",
    )
    return response


@router.get("/me", response_model=ApiResponse[FeishuUserOut | None])
async def get_me(
    current_user: FeishuUserDoc | None = Depends(get_optional_current_feishu_user),
):
    if not current_user:
        return ok(None)
    return ok(to_out(current_user, FeishuUserOut))


@router.post("/logout", response_model=ApiResponse)
async def logout(response: Response):
    response.delete_cookie(FEISHU_SESSION_COOKIE, path="/")
    return ok(message="已退出登录")


__all__ = ["router"]
