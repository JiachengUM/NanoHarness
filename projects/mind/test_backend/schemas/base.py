from datetime import datetime, timezone
from typing import Any
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


# ------------------------------- 基础 Mixin -------------------------------


class IDMixin(BaseModel):
    """统一处理 id/_id -> 字符串。

    - 允许输入为 PydanticObjectId / bson.ObjectId / str / None
    - 若上游传 `_id` 且未显式提供 `id`，自动映射
    """

    id: str = Field(description="主键 ID (ObjectId 字符串)")

    @model_validator(mode="before")
    @classmethod
    def _pull_id(cls, data: Any):
        if isinstance(data, dict):
            if "id" not in data and "_id" in data:
                data = {**data, "id": data["_id"]}
        return data

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: Any):
        if v is None:
            return v
        
        return str(v)
    
class AuditMixin(BaseModel):
    creator: str | None = Field(default=None, title="创建人", description="创建人")

    created_time: datetime | None = Field(default=None, title="创建时间", description="创建时间")

    updated_time: datetime | None = Field(default=None, title="更新时间", description="更新时间")

    @field_serializer("created_time", "updated_time")
    def _serialize_with_tz(self, v: datetime | None) -> datetime | None:
        # MongoDB/Motor 默认把 BSON 日期读成 naive UTC；输出前补上 UTC 时区，
        # 让前端能拿到带时区（+00:00）的时间，避免被当成本地无时区时间解析
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

class OutMixin(IDMixin, AuditMixin):
    """输出模型基类，包含 ID 和审计信息"""
    
    model_config= ConfigDict(from_attributes=True)