from pydantic import BaseModel, Field
from typing import Optional
from aicore.agents.experiments.user_profile import UserProfile
from aicore.agents.experiments.memory import (
    MemoryConsumerConfig,
    MemoryProducerConfig,
    UserInfoMetadata,
)
from aicore.models.model_api.types import ModelCallParams
from aicore.agents.experiments.base import SystemPrompt
from projects.mind.intent.intent_schemas.base import CreateMixin
from projects.mind.mem.volc_api.event import EventMemoryResponse
from projects.mind.mem.volc_api.profile import ProfileMemoryResponse


class AgentModel(BaseModel):
    name: str = Field(..., description="模型名称")
    value: str = Field(..., description="模型值")


class MemoryConfig(BaseModel):
    """记忆配置。"""

    user_info: UserInfoMetadata = Field(None, description="用户信息配置")
    producer_config: MemoryProducerConfig = Field(None, description="记忆生产者配置")
    consumer_config: MemoryConsumerConfig = Field(None, description="记忆消费者配置")
    session_size: int = Field(5, description="记忆会话窗口大小")


class ReActAgentConfig(BaseModel):
    """通用ReAct智能体。"""

    model: str = Field(..., description="模型名称")
    params: ModelCallParams | None = Field(None, description="模型参数")
    tools: list[str] = Field(
        default_factory=list, description="工具列表，格式为工具名称字符串"
    )
    max_turns: int = Field(default=5, description="最大轮数")
    system_prompt: Optional[str | SystemPrompt] = Field(..., description="系统提示词")
    memory_config: Optional[MemoryConfig] = Field(None, description="记忆配置")
    user_profile: Optional[UserProfile] = Field(None, description="用户画像信息")


class ReActAgentRequest(CreateMixin):
    query: str = Field(..., description="用户查询")
    session_id: str = Field(..., description="会话ID")
    config: ReActAgentConfig = Field(..., description="智能体配置")
    save_to_db: bool = Field(default=False, description="是否保存到数据库")


class AutoChatConfig(BaseModel):
    """自动对话参数配置。"""

    chat_turns: int = Field(default=5, description="对话轮数")
    chat_scene: Optional[str] = Field(None, description="对话场景")
    user_profile: Optional[str] = Field(None, description="用户画像")


class ReActAgentAutoChatRequest(ReActAgentRequest):
    """自动对话ReAct智能体请求。"""

    auto_chat_config: AutoChatConfig = Field(..., description="自动对话参数配置")


class AgentMemoryResponse(BaseModel):
    """记忆召回结果。"""

    profiles: Optional[ProfileMemoryResponse] = Field(
        None, description="召回的用户画像信息"
    )
    events: Optional[EventMemoryResponse] = Field(None, description="召回的事件信息")
