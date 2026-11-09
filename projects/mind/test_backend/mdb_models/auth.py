from __future__ import annotations

from datetime import datetime

from pydantic import Field

from projects.mind.test_backend.mdb_models.doc_base import DocBase


class FeishuUserDoc(DocBase):
    """飞书登录用户。"""

    open_id: str = Field(..., description="飞书应用内用户 open_id")
    union_id: str | None = Field(default=None, description="飞书用户 union_id")
    user_id: str | None = Field(default=None, description="飞书通讯录 user_id")
    name: str = Field(..., description="飞书用户名")
    avatar_url: str | None = Field(default=None, description="头像 URL")
    email: str | None = Field(default=None, description="邮箱")
    mobile: str | None = Field(default=None, description="手机号")
    tenant_key: str | None = Field(default=None, description="租户 key")
    last_login_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "feishu_user"


__all__ = ["FeishuUserDoc"]
