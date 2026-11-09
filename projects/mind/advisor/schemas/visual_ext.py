from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.advisor.domain_data import VisualExterior
from projects.mind.advisor.schemas.base import DomainEntityOutMixin, CreateMixin


class VisualExtCreate(CreateMixin):
    """内部视觉信息创建"""

    entity: VisualExterior


class VisualExtOut(DomainEntityOutMixin):
    """内部视觉信息输出"""

    entity: Optional[VisualExterior] = None


class VisualExtFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
