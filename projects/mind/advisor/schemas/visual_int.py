from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.advisor.domain_data import VisualInterior
from projects.mind.advisor.schemas.base import DomainEntityOutMixin, CreateMixin


class VisualIntCreate(CreateMixin):
    """内部视觉信息创建"""

    entity: VisualInterior


class VisualIntOut(DomainEntityOutMixin):
    """内部视觉信息输出"""

    entity: Optional[VisualInterior] = None


class VisualIntFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
