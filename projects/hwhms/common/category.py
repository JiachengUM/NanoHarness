from pydantic import BaseModel, Field

class Category(BaseModel):
    name: str = Field(..., title="类别名称", description="类别名称")
    description: str = Field(..., title="类别描述", description="类别的详细定义和描述")
    examples: list[str] = Field(..., title="示例", description="类别的示例")
    notices: list[str] | None = Field(default=None, title="注意事项", description="关于该类别定义的注意事项")
