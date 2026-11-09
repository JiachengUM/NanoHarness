from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.advisor.domain_data import EpisodicMemory
from projects.mind.advisor.schemas.base import CreateMixin, DomainEntityOutMixin


class EpisodicMemoryCreate(CreateMixin):
    """内部视觉信息创建"""

    entity: EpisodicMemory


class EpisodicMemoryOut(DomainEntityOutMixin):
    """内部视觉信息输出"""

    entity: Optional[EpisodicMemory] = None


class EpisodicMemoryFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
