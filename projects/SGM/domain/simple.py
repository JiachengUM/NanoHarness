from pydantic import BaseModel, Field

class Category(BaseModel):
    name: str = Field(..., title="类别名称", description="类别名称")
    description: str = Field(..., title="类别描述", description="类别的详细定义和描述")
    examples: list[str] = Field(..., title="示例", description="类别的示例")
    notices: list[str] | None = Field(default=None, title="注意事项", description="关于该类别定义的注意事项")

chat = Category(
    name="闲聊",
    description="用户提出的问题无法归类到其他类别，作为兜底分类。",
    examples=[
        "问候语,如: 你好, 你好呀, 早上好, 晚上好",
        "寒暄对话,如: 随便聊聊, 最近怎么样, 在干嘛呢",
        "无明确意图的表达,如: 嗯, 好的, 知道了, 谢谢"
    ]
)
