from typing import Any, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from projects.mind.advisor.schemas.base import OutMixin, CreateMixin
from projects.mind.complex_reasoning.task_data import ComplexReasoningCase


class ComplexReasoningCaseCreate(ComplexReasoningCase, CreateMixin):
    """complex reasoning input信息创建"""

    dataset_id: PydanticObjectId | None = Field(
        default=None, title="数据集Id", description="所属数据集Id"
    )


class ComplexReasoningCaseOut(ComplexReasoningCase, OutMixin):
    """complex reasoning input信息输出"""

    dataset_id: PydanticObjectId | None = Field(
        default=None, title="数据集Id", description="所属数据集Id"
    )


class ComplexReasoningCaseFilter(BaseModel):
    """查询条件"""

    keyword: Optional[str] = Field(None, description="查询关键词，模糊匹配用")
    creator: Optional[str] = Field(None, description="创建者")
    dataset_id: Optional[PydanticObjectId] = Field(None, description="所属数据集Id")

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.keyword:
            filters["$or"] = [
                {"user_query_lists.content": {"$regex": self.keyword, "$options": "i"}},
                {"expected_script": {"$regex": self.keyword, "$options": "i"}},
                {"case_description": {"$regex": self.keyword, "$options": "i"}},
                {"case_id": {"$regex": self.keyword, "$options": "i"}},
                {"nl_assertion": {"$regex": self.keyword, "$options": "i"}},
                {"tags": {"$regex": self.keyword, "$options": "i"}},
            ]
            del filters["keyword"]
        return filters
