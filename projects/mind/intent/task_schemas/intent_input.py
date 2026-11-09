from typing import Any, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from projects.mind.intent.intent_schemas.base import OutMixin, CreateMixin
from projects.mind.intent.task_data import IntentClsInput


class IntentInputCreate(IntentClsInput, CreateMixin):
    """intent input信息创建"""

    dataset_id: PydanticObjectId | None = Field(default=None, title="数据集Id", description="所属数据集Id")


class IntentInputOut(IntentClsInput, OutMixin):
    """intent input信息输出"""

    dataset_id: PydanticObjectId | None = Field(default=None, title="数据集Id", description="所属数据集Id")


class IntentInputFilter(BaseModel):
    """查询条件"""

    query: Optional[str] = None
    creator: Optional[str] = None
    dataset_id: Optional[PydanticObjectId] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.query:
            filters["query"] = {"$regex": self.query, "$options": "i"}
        return filters
