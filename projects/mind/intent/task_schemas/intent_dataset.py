from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.advisor.schemas.base import OutMixin, CreateMixin

__all__ = ["IntentDatasetMetaCreate", "IntentDatasetMetaOut", "IntentDatasetMetaFilter"]

from projects.mind.intent.task_data.intent_dataset import IntentDatasetMeta


class IntentDatasetMetaCreate(IntentDatasetMeta, CreateMixin):
    """Intent Dataset 信息创建"""

    pass


class IntentDatasetMetaOut(IntentDatasetMeta, OutMixin):
    """Intent Dataset 输出信息"""

    pass


class IntentDatasetMetaFilter(BaseModel):
    """查询条件"""

    name: Optional[str] = None
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.name:
            filters["name"] = {"$regex": self.name, "$options": "i"}
        return filters
