"""
模型层对外输出的用户和AI助手消息。需要在chat和responses api基础上统一。
它是agent使用的基础数据，会有各种需求。长期持续统一很难。尽量保持极简。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

class BaseMessage(BaseModel):
    content: str
    type: str


class HumanMessage(BaseMessage):
    type: Literal["human"] = Field(default="human", init=False)  # type: ignore


class AIMessage(BaseMessage):
    type: Literal["ai"] = Field(default="ai", init=False)  # type: ignore
