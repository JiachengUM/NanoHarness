from pydantic import BaseModel, Field

from projects.mind.intent.task_data.message import Message

__all__ = [
    "IntentClsInput",
]

class IntentClsInput(BaseModel):
    '''
    意图分类输入。
    '''
    query: str = Field(default="", title="查询", description="意图分类查询")

    messages: list[Message] | None = Field(default=None, title="历史对话", description="历史对话")
