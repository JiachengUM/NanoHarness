from typing import Any

from pydantic import BaseModel, Field

class EpisodicMemoryBlock(BaseModel):
    '''
    情景记忆块。包含一个情景事件的详细信息。
    '''
    date_time: str | None = Field(default=None, title="时间", description="事件发生的时间")
    
    location: str | None = Field(default=None, title="地点", description="事件发生的地点")
    
    content: str | None = Field(default=None, title="事件描述", description="事件的详细描述")
    
    feel: str | None = Field(default=None, title="感受", description="当事人对事件的感受")

    details: dict[str, Any] | None = Field(default=None, title="其它细节", description="其它细节")
    '''任意想要记录的内容'''

class EpisodicMemory(BaseModel):
    '''
    情景记忆。对个人亲身经历的、特定时间和地点发生的事件的记忆。包含丰富的情景细节（何时、何地、何人、何事、何种感受）。
    语义记忆：指对一般知识、事实和概念的记忆，与个人经历无关。这两者需要区分开。
    '''
    
    instant: list[EpisodicMemoryBlock] | str | None = Field(default=None, title="瞬时记忆",
                                       description="瞬时记忆包含20分钟内的20条QA对话+事件")

    short: list[EpisodicMemoryBlock] | str | None = Field(default=None, title="短期记忆", description="1天之内的记忆")

    long: list[EpisodicMemoryBlock] | str | None = Field(default=None, title="长期情景记忆",
                                          description="发生的情景事件，1天之前的记忆")
