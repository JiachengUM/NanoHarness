from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


from projects.mind.advisor.domain_data.context_log import ContextLog
from projects.mind.advisor.schemas.base import AuditMixin, CreateMixin, IDMixin


class ContextLogCreate(ContextLog, CreateMixin):
    pass


class ContextLogOut(ContextLog, IDMixin, AuditMixin):
    pass


class ContextLogFilter(BaseModel):
    log_id: Optional[str] = None
    log_type: Optional[str] = None
    remark: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = {}
        if self.log_id is not None:
            filters["log_id"] = {"$regex": self.log_id}
        if self.log_type is not None:
            filters["log_type"] = self.log_type
        if self.remark is not None:
            filters["remark"] = {"$regex": self.remark}
        return filters
