from __future__ import annotations

from datetime import datetime
from datetime import timezone
from beanie import Document, PydanticObjectId, before_event
from beanie.odm.actions import Insert, Save
from pydantic import Field


__all__ = ["DocBase"]

class DocBase(Document):
    """文档基类，包含审计字段和生命周期钩子。"""

    id: PydanticObjectId | None = Field(default=None, alias="_id")

    creator: str = Field(default="system", title="创建人", description="创建人")

    created_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    updated_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ---- 生命周期钩子 ----
    @before_event(Insert)
    def _on_insert(self):
        now = datetime.now(timezone.utc)
        self.created_time = now
        self.updated_time = now

    @before_event(Save)
    def _on_save(self):
        self.updated_time = datetime.now(timezone.utc)
