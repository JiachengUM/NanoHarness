'''
对于火山记忆库API记忆检索部分的结构化封装  https://www.volcengine.com/docs/84313/1783351
'''

from __future__ import annotations

from pydantic import BaseModel, Field

from mvms.volc_mem.common.client import internal_request


__all__ = [
    "MemoryFilter",
    "SearchMemory",
    "search_memory",
]


class MemoryFilter(BaseModel):
    """记忆搜索过滤条件"""
    memory_type: str | list[str] = Field(..., description="记忆类型（必需）。可以是事件类型（EventType）或画像类型（ProfileType）的名称，支持单个值或列表")
    
    user_id: str | list[str] | None = Field(default=None, description="用户ID，支持单个ID或ID列表")
    
    assistant_id: str | list[str] | None = Field(default=None, description="助手ID，支持单个ID或ID列表")
    
    primary_key: str | list[str] | None = Field(default=None, description="画像主键表达式，用于过滤。可以是单个值或列表。例如，如果画像主键是 kb_id，要查询 kb_id=1 的数据，搜索条件为 primary_key='kb_id=1'")
    
    start_time: int | None = Field(default=None, description="检索记忆的开始时间，毫秒时间戳")
    
    end_time: int | None = Field(default=None, description="检索记忆的结束时间，毫秒时间戳")
    
    group_id: str | list[str] | None = Field(default=None, description="群组ID，用于过滤。支持单个ID或ID列表")
    
    session_id: str | list[str] | None = Field(default=None, description="会话ID，用于过滤。支持单个ID或ID列表")


class SearchMemory(BaseModel):
    """记忆搜索请求模型"""
    collection_name: str | None = Field(default=None, description="要检索的记忆库名称")
    
    project_name: str = Field(default="default", description="记忆库所属项目")
    
    resource_id: str | None = Field(default=None, description="记忆库唯一的资源 id。可选择直接传 resource_id, 或同时传 collection_name 和 project_name")
    
    query: str | None = Field(default=None, description="用户的搜索查询语句（最多 4000 个字符）。如果提供 query，将基于查询内容进行语义匹配召回记忆，召回数量与 limit 值相关。如果不提供 query，将返回符合 filter 条件的记忆列表，按时间排序（优先最新），召回数量与 limit 值相关")
    
    filter: MemoryFilter = Field(..., description="搜索过滤条件和返回设置（必需）")
    
    limit: int = Field(default=10, description="返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]")


def search_memory(request: SearchMemory):
    """
    搜索记忆库中的记忆数据
    """
    path = "/api/memory/search"
    return internal_request("POST", path, request.model_dump(exclude_none=True))
