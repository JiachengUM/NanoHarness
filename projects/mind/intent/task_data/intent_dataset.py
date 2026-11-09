from pydantic import BaseModel, Field


class IntentDatasetMeta(BaseModel):
    """Intent的输入数据集"""
    name: str = Field(..., title="数据集名称", description="数据集名称")
    description: str | None = Field(default=None, title="数据集描述", description="数据集描述")