from pydantic import BaseModel, Field

class EventBase(BaseModel):
    """事件模型"""
    event: str = Field(title="触发事件", description="触发advisor的事件描述")
