from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class ReportTime(BaseModel):
    avg_time: float = Field(..., ge=0, description="平均耗时")
    p50_time: float = Field(..., ge=0, description="50百分位耗时")
    p90_time: float = Field(..., ge=0, description="90百分位耗时")
    p99_time: float = Field(..., ge=0, description="99百分位耗时")


class IntentResult(BaseModel):
    """Intent result"""
    # name: str = Field(..., title="结果集名称", description="结果集名称")
    status: str = Field(..., title="结果集状态", description="结果集状态，如：执行中、已完成、失败")
    dataset_id: PydanticObjectId = Field(..., title="数据集Id", description="数据集Id")
    task_id: PydanticObjectId = Field(..., title="任务Id", description="任务Id")
    total_time: ReportTime = Field(..., description="总耗时")
