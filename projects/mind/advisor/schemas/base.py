"""通用 Schema 基类与工具。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from beanie import PydanticObjectId
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ------------------------------- 基础 Mixin -------------------------------


class IDMixin(BaseModel):
    """统一处理 id/_id -> 字符串。

    - 允许输入为 PydanticObjectId / str / None
    - 若上游传 `_id` 且未显式提供 `id`，自动映射
    """

    id: str = Field(description="主键 ID (ObjectId 字符串)")

    @model_validator(mode="before")  # type: ignore[call-arg]
    @classmethod
    def _pull_id(cls, data: Any):  # noqa: D401
        if isinstance(data, dict):
            if "id" not in data and "_id" in data:
                data = {**data, "id": data["_id"]}
        return data

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: Any):  # noqa: D401
        if v is None:
            return v
        # beanie 的 PydanticObjectId / bson.ObjectId / 其他可转 str
        if isinstance(v, PydanticObjectId):
            return str(v)
        return str(v)


class AuditMixin(BaseModel):
    creator: str
    created_time: datetime
    updated_time: datetime


class SoftDeleteMixin(BaseModel):
    deleted: bool
    deleted_time: Optional[datetime] = None


# ----------------------------- 输出组合模型 -----------------------------


class OutMixin(IDMixin, AuditMixin):
    """完整文档输出。"""

    model_config = ConfigDict(from_attributes=True)


class DomainEntityOutMixin(IDMixin, AuditMixin):
    """domain data 完整文档输出。"""

    brief: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaskDataOutMixin(IDMixin, AuditMixin):
    """task data 完整文档输出。"""

    brief: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ------------------------------ 输入 Mixin ------------------------------


class CreateMixin(BaseModel):  # 按需扩展
    """通用创建输入基类（预留扩展点）。"""

    creator: str = Field(default="system", title="创建人", description="创建人")
    brief: str = Field(default="", title="简单总结", description="对业务实体的简单总结")


class UpdateMixin(BaseModel):  # 按需扩展
    """通用更新输入基类（预留扩展点）。所有字段应由子类声明为可选。"""

    pass


__all__ = [
    "IDMixin",
    "AuditMixin",
    "SoftDeleteMixin",
    "OutMixin",
    "DomainEntityOutMixin",
    "CreateMixin",
    "UpdateMixin",
]
