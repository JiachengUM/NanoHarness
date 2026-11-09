from typing import Optional, Any

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from projects.mind.complex_reasoning.task_data.chat_history import AgentChatSession, EvaluationResult
from projects.mind.intent.intent_schemas.base import CreateMixin, OutMixin


class AgentChatSessionCreate(AgentChatSession, CreateMixin):
    """Agent会话-创建"""

    pass


class AgentChatSessionOut(AgentChatSession, OutMixin):
    """Agent会话-输出"""

    pass

class AgentChatSessionFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None
    title: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = {}

        if self.creator:
            filters["creator"] = self.creator
        if self.title:
            filters["title"] = {"$regex": self.title, "$options": "i"}

        return filters

class AgentChatSessionHumanEval(BaseModel):
    id: PydanticObjectId = Field(..., description="会话ID")
    message_index: int = Field(..., description="对话消息索引")
    human_evaluation: Optional[EvaluationResult] = Field(
        None, description="人类评价的内容"
    )