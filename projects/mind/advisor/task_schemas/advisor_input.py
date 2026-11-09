from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from projects.mind.advisor.task_data import AdvisorInput
from projects.mind.advisor.schemas.base import TaskDataOutMixin, CreateMixin


class AdvisorInputCreate(AdvisorInput, CreateMixin):
    """advisor输入信息 创建"""

    dataset_id: PydanticObjectId | None = Field(default=None, title="数据集Id", description="所属数据集Id")

class AdvisorInputOut(AdvisorInput, TaskDataOutMixin):
    """advisor输入信息 输出"""

    dataset_id: PydanticObjectId | None = Field(default=None, title="数据集Id", description="所属数据集Id")


class AdvisorInputFilter(BaseModel):
    """用户查询条件"""
    dataset_id: Optional[PydanticObjectId] = None
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
