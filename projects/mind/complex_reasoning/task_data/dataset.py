from pydantic import BaseModel, Field


class ComplexReasoningDatasetMeta(BaseModel):
    """复杂推理的数据集"""

    name: str = Field(..., title="数据集名称", description="数据集名称")
    description: str | None = Field(
        default=None, title="数据集描述", description="数据集描述"
    )
    item_count: int | None = Field(default=None, title="数据集包含的测试用例数量")
