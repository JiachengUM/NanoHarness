from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.advisor.task_data import AdvisorDatasetMeta
from projects.mind.advisor.schemas.base import OutMixin, CreateMixin


class AdvisorDatasetMetaCreate(AdvisorDatasetMeta, CreateMixin):
    """advisor输入信息创建"""

    pass


class AdvisorDatasetMetaOut(AdvisorDatasetMeta, OutMixin):
    """advisor输入信息"""

    pass


class AdvisorDatasetMetaFilter(BaseModel):
    """查询条件"""

    name: Optional[str] = None
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.name:
            filters["name"] = {"$regex": self.name, "$options": "i"}
        return filters
