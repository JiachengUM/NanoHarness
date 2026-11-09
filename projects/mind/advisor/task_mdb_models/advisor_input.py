from beanie import PydanticObjectId
from pydantic import Field

from projects.mind.advisor.mdb_models.doc_base import TaskDataDocBase
from projects.mind.advisor.task_data import AdvisorInput


class AdvisorInputDoc(AdvisorInput, TaskDataDocBase):
    """advisor输入信息模型"""
    dataset_id: PydanticObjectId | None = Field(default=None, title="数据集Id", description="所属数据集Id")

    class Settings:
        name = "advisor_input"  # MongoDB 集合名称