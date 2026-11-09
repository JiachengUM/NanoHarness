from typing import Any, Optional
from beanie import PydanticObjectId
from projects.mind.complex_reasoning.task_schemas.case import ComplexReasoningCaseCreate
from pydantic import BaseModel, Field
from projects.mind.advisor.schemas.base import OutMixin, CreateMixin

__all__ = [
    "ComplexReasoningDatasetMetaCreate",
    "ComplexReasoningDatasetMetaOut",
    "ComplexReasoningDatasetMetaFilter",
]

from projects.mind.complex_reasoning.task_data.dataset import (
    ComplexReasoningDatasetMeta,
)


class ComplexReasoningDatasetMetaCreate(ComplexReasoningDatasetMeta, CreateMixin):
    """Complex Reasoning Dataset 信息创建"""

    pass


class ComplexReasoningDatasetMetaOut(ComplexReasoningDatasetMeta, OutMixin):
    """Complex Reasoning Dataset 输出信息"""

    pass

class ComplexReasoningDatasetMetaCopy(BaseModel):
    """Complex Reasoning Dataset 复制"""

    dataset_id: PydanticObjectId
    dataset_item_ids: Optional[list[PydanticObjectId]] = None

class ComplexReasoningDatasetMetaFilter(BaseModel):
    """查询条件"""

    name: Optional[str] = None
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.name:
            filters["name"] = {"$regex": self.name, "$options": "i"}
        return filters

class DatasetBuildParams(BaseModel):
    """数据集构建参数"""

    dataset_id: Optional[PydanticObjectId] = Field(default = None, description="数据集ID")
    dataset: Optional[ComplexReasoningDatasetMetaCreate] = Field(default = None, description="数据集信息")
    task_run_item_ids: Optional[list[PydanticObjectId]] = Field(default_factory=list, description="要构建的数据集项ID列表")
    dataset_item_ids: Optional[list[PydanticObjectId]] = Field(default_factory=list, description="要构建的数据集项ID列表")
    dataset_items: Optional[list[ComplexReasoningCaseCreate]] = Field(default_factory=list, description="要构建的数据集项列表")

