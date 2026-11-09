from pydantic import BaseModel, Field 

class Message(BaseModel):
    """
    对话消息。
    通用的消息格式，极难设计。目前仅限于intent任务使用。
    TODO: 也许应该改名叫MessageBase。为时尚早。
    """
    role: str = Field(..., description="发言人角色")
    
    content: str = Field(..., description="消息内容")
    
    # TODO: time: int | None = Field(default=None, description="发言时间")

    def __nl_repr__(self) -> str:
        """返回消息的NL表示。遵循nl_repr协议。"""
        return f"{self.role}: {self.content}"
