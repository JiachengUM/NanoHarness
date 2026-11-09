'''
对于火山记忆库API会话部分的结构化封装  https://www.volcengine.com/docs/84313/1783353?lang=zh
'''

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from mvms.volc_mem.common.client import internal_request


__all__ = [
    "MessageContent",
    "Message",
    "SessionMetadata",
    "AddSession",
    "SessionInfo",
    "add_session",
    "get_session_info",
]


class MessageContent(BaseModel):
    """消息内容，支持文本和图片"""
    type: Literal["text", "image_url", "input_image"] = Field(..., description="内容类型")
    
    # 当 type 为 "text" 时使用
    text: str | None = Field(default=None, description="文本内容（当 type 为 'text' 时使用）")
    
    # 当 type 为 "image_url" 或 "input_image" 时使用
    image_url: str | None = Field(default=None, description="图片URL对象（当type为 'image_url'时使用）")


class Message(BaseModel):
    """对话消息"""
    role: Literal["user", "assistant", "system"] = Field(..., description="发言人角色，可选值为 'user', 'assistant', 'system'")
    
    content: list[MessageContent] = Field(..., description="消息内容列表。对象列表（标准格式，支持文本和图片混合）")
    
    role_id: str | None = Field(default=None, description="发言人ID（群聊场景）。如果该发言人的ID与 default_user_id 或 default_assistant_id 相同，则不需要传递")
    
    role_name: str | None = Field(default=None, description="发言人名称（群聊场景）。如果该发言人的名称与 default_user_name 或 default_assistant_name 相同，则不需要传递")
    
    time: int | None = Field(default=None, description="发言时间，毫秒时间戳")


class SessionMetadata(BaseModel):
    """会话元数据"""
    default_user_id: str = Field(..., description="默认用户ID")

    default_user_name: str | None = Field(default=None, description="默认用户名称")

    default_assistant_id: str = Field(..., description="默认助手ID")

    default_assistant_name: str | None = Field(default=None, description="默认助手名称")

    time: int = Field(..., description="发言时间，毫秒时间戳")


class AddSession(BaseModel):
    """会话模型，用于添加会话信息"""
    collection_name: str = Field(default="", description="目标记忆库的名称")
    
    project_name: str = Field(default="default", description="记忆库所属项目，默认为 'default'")
    
    resource_id: str = Field(default="", description="记忆库唯一的资源 id。可选择直接传 resource_id, 或同时传 collection_name 和 project_name")
    
    session_id: str = Field(default="", description="会话 ID。长度要求: [1, 128], 只能使用英文字母、数字、下划线，并以英文字母开头")
    
    messages: list[Message] = Field(..., description="要添加的多轮对话消息列表（必需）")
    
    store_file: bool = Field(default=False, description="是否存储原始文件，默认为 False")

    metadata: SessionMetadata | None = Field(default=None, description="会话元数据")

    # TODO: 还没实现下面的属性
    # profiles, extract_memory_type

class SessionInfo(BaseModel):
    """会话信息模型，用于查询会话信息"""
    collection_name: str = Field(default="", description="目标记忆库的名称")
    
    project_name: str = Field(default="default", description="记忆库所属项目，默认为 'default'")
    
    resource_id: str = Field(default="", description="记忆库唯一的资源 id。可选择直接传 resource_id, 或同时传 collection_name 和 project_name")
    
    session_id: str = Field(..., description="会话 ID。长度要求: [1, 128], 只能使用英文字母、数字、下划线，并以英文字母开头")


def add_session(session: AddSession):
    """
    添加会话记录到记忆库
    """
    path = "/api/memory/session/add"
    return internal_request("POST", path, session.model_dump(exclude_none=True))


def get_session_info(session: SessionInfo):
    """
    查询会话的详细信息
    """
    path = "/api/memory/session/info"
    return internal_request("POST", path, session.model_dump(exclude_none=True))