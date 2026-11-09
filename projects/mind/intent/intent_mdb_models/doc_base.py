from __future__ import annotations

from datetime import datetime
from beanie import Document, before_event
from beanie.odm.actions import Insert, Save
from pydantic import Field


__all__ = ["AuditMixin", "IntentDataDocBase", "TaskDataDocBase"]


class AuditMixin:
    creator: str = Field(default="system", title="创建人", description="创建人")
    created_time: datetime = Field(default_factory=lambda: datetime.now())
    updated_time: datetime = Field(default_factory=lambda: datetime.now())

    # ---- 生命周期钩子 ----
    @before_event(Insert)
    def _on_insert(self):
        now = datetime.now()
        self.created_time = now
        self.updated_time = now

    @before_event(Save)
    def _on_save(self):
        self.updated_time = datetime.now()


class IntentDataDocBase(Document, AuditMixin):
    """Intent data 继承该类"""
    pass

class TaskDataDocBase(Document, AuditMixin):
    """Task data 继承该类"""
    pass