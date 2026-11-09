from pydantic import BaseModel, Field

from aicore.models.responses import ResponseParams


class ReActAgentConfig(BaseModel):
    """通用ReAct智能体。"""

    model: str = Field(..., description="模型名称")
    params: ResponseParams | None = Field(None, description="模型参数")
    tools: list[str] = Field(
        default_factory=list, description="工具列表，格式为工具名称字符串"
    )
    max_turns: int = Field(default=5, description="最大轮数")