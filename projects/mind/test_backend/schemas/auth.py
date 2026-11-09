from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from projects.mind.test_backend.schemas.base import OutMixin


class FeishuUserOut(OutMixin):
    """当前飞书登录用户。"""

    open_id: str = Field(..., description="飞书应用内用户 open_id")
    union_id: str | None = None
    user_id: str | None = None
    name: str
    avatar_url: str | None = None
    email: str | None = None
    mobile: str | None = None
    tenant_key: str | None = None
    last_login_at: datetime | None = None


class FeishuLoginStatus(BaseModel):
    user: FeishuUserOut | None = None


__all__ = ["FeishuLoginStatus", "FeishuUserOut"]
