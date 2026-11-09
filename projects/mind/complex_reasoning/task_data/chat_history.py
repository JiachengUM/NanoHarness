from __future__ import annotations

from typing import Any, List, Literal, Optional
from pydantic import Field, BaseModel

from aicore.v1.experiments.agent import AgentContext, AgentState
from aicore.agents.experiments.base import AgentDumpPayload, AgentEvent
from aicore.models.messages import AIMessage, HumanMessage


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    reason: str | None = None


class HumanMessageEvent(BaseModel):
    type: Literal["human_message"] = "human_message"
    content: str | None = None


class ChatMetric(BaseModel):
    """评价指标"""

    metric_name: Optional[str] = Field(None, description="指标名称")
    score: Optional[float] = Field(None, description="指标得分")
    reason: Optional[str] = Field(None, description="评分原因")


class EvaluationResult(BaseModel):
    """评价结果"""

    overall_score: Optional[float] = Field(None, description="总体评分")
    overall_reason: Optional[str] = Field(None, description="总体评分原因")
    metrics: Optional[List[ChatMetric]] = Field(None, description="具体指标评分")


class TimeMetric(BaseModel):
    """时间指标"""

    first_time: Optional[float] = Field(None, description="首帧时间")
    total_time: Optional[float] = Field(None, description="总耗时")


class AgentHumanChatMessage(HumanMessage):
    pass


class AgentAIChatMessage(AIMessage):
    events: Optional[List[AgentEvent | ErrorEvent | Any]] = Field(
        None, description="消息事件列表"
    )
    human_evaluation: Optional[EvaluationResult] = Field(
        None, description="消息人工评价"
    )
    # time_metrics: Optional[TimeMetric] = Field(None, description="时间指标")


class AgentV1DumpPayload(BaseModel):
    """v1 Agent 持久化结构。"""

    context: AgentContext
    state: AgentState


class AgentChatSession(BaseModel):
    """Chatbox会话"""

    title: str = Field(..., description="会话标题")
    session_id: Optional[str] = Field(
        None, description="会话ID"
    )  # 前端生成UUID，后端使用该字段关联会话记录
    agent_instance_dump: (
        AgentDumpPayload | AgentV1DumpPayload | None
    ) = Field(default=None, description="会话使用的Agent实例dump")
    messages: List[AgentHumanChatMessage | AgentAIChatMessage | HumanMessageEvent] = (
        Field(default_factory=list, description="会话消息列表")
    )

    model_config = {"arbitrary_types_allowed": True}


__all__ = [
    "AgentHumanChatMessage",
    "AgentAIChatMessage",
    "AgentChatSession",
    "EvaluationResult",
    "AgentV1DumpPayload",
    "ChatMetric",
    "TimeMetric",
]
