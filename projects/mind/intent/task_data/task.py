from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class IntentTask(BaseModel):
    """Intent task"""
    name: str = Field(..., title="任务名称", description="任务名称")
    description: str | None = Field(default=None, title="任务描述", description="任务描述")
    status: str = Field(..., title="任务状态", description="任务状态，如：未开始、执行中、已完成、失败")
    dataset_id: PydanticObjectId= Field(..., title="数据集Id", description="任务需要执行的数据集的Id")