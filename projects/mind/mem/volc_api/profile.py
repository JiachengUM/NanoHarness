from pydantic import BaseModel, Field
from typing import Literal,Final
from enum import StrEnum
import asyncio
import httpx
from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport
from aicore.utils.volc_client.volc_api import VolcApiClient
from projects.mind.mem.volc_api._api import request
from projects.mind.mem.volc_api.base import (
    CollectionID,
    MemoryContentType,
    StandardResponse,
)

__all__ = [
    "batch_delete_profile",
    "search_profile_memory",
    "add_custom_profile_memory",
    "abatch_delete_profile",
    "asearch_profile_memory",
    "aadd_custom_profile_memory",
]

UpdateTimingDescription: Final[str] = """
画像的更新触发时机。可选值如下：
realtime（默认）：事件产生后立即更新画像记忆。
daily：每日更新画像记忆。在每日 00:00 触发，处理 上次更新后至昨日 23:59 期间产生的事件。
weekly：每周更新画像记忆。在每周一 00:00 触发，处理 上次更新后至上周日 23:59 期间产生的事件。
manual：仅在手动调用 TriggerUpdateProfile 接口时更新画像记忆。
"""

UpdateModeDescription: Final[str] = """
在更新时机为 daily 或 weekly 时，控制画像记忆的更新方式。可选值如下:
"overwrite（默认）：覆盖写入，在原有画像基础上更新内容。
"append：追加写入，每次更新生成一条新记忆。适用于日报、周报等保留历史记录的场景。
"""

class AggregateExpression(BaseModel):
    Op: Literal["SUM", "MAX", "AVG", "COUNT", "LLM_MERGE", "TIME_COMPRESS"] = Field(..., description="聚合操作符，仅限SUM、MAX、AVG、COUNT、LLM_MERGE、TIME_COMPRESS")

    EventType: str = Field(..., description="参与聚合的事件类型名称。")

    EventPropertyName: str = Field(..., description="参与聚合的事件类型中的属性名称。")

class CollectionTypeEnum(StrEnum):
    INT64 = "int64"
    LIST_INT64 = "list<int64>"
    STRING = "string"
    LIST_STRING = "list<string>"
    FLOAT32 = "float32"
    BOOL = "bool"

class ProfileProperty(BaseModel):
    PropertyName: str = Field(..., description="属性名称，例如 user_id, total_interactions。")

    PropertyValueType: CollectionTypeEnum = Field(..., description="属性值的类型")

    Description: str = Field(..., description="属性的详细描述，最多 10000 个字符。", max_length=10000)

    Aggregate: AggregateExpression | None = Field(default=None, description="聚合表达式，定义此属性如何从关联的事件中聚合计算而来。")

    IsPrimaryKey: bool = Field(default=False, description="是否为画像的主键。默认为 false。")


class ProfileTypeSchema(BaseModel):
    ProfileType: str = Field(..., description="画像类型的唯一名称，例如 user_profile, product_summary。")

    Description: str = Field(..., description="画像类型的详细描述，最多 10000 个字符。")

    UpdateTiming: str = Field(default="realtime", description=UpdateTimingDescription)

    UpdateMode: str = Field(default="overwrite", description=UpdateModeDescription)

    EnableAssistantIsolation: bool = Field(default=True, description="画像是否按照 assistant_id 隔离。默认为 True，即隔离。")

    Properties: list[ProfileProperty] = Field(..., description="构成此画像类型的属性列表。")

    Version: str = Field(default="1", description="画像模式版本号，默认为 '1'。")

class ProfileDataResponse(BaseModel):
    '''画像记忆数据响应'''
    profile_id: str = Field(..., description="画像记忆ID")
    primary_key: str = Field(..., description="画像记忆的主键")
    profile_type: str = Field(..., description="画像记忆类型")
    memory_info: dict[str, MemoryContentType] = Field(..., description="画像记忆的内容")
    usage: dict[str, int] = Field(..., description="画像记忆生成的使用量情况")

class ProfileMemoryAddResponse(StandardResponse):
    '''添加画像记忆的响应'''
    data: ProfileDataResponse = Field(..., description="响应数据")

class ProfileMemoryResult(BaseModel):
    """画像记忆检索结果列表元素
    与 MemoryResult 类似，但不包含 session_id 字段（画像搜索不返回会话ID）。
    """
    id: str = Field(..., description="记忆条目（画像实例）的唯一ID。")
    # 把下面的内容变成BaseModel的字段
    score: float | None = Field(default=None, description="与查询的相关性得分。")
    memory_type: str = Field(..., description="画像记忆类型。")
    user_id: list[str] = Field(..., description="关联的用户ID列表。")
    assistant_id: list[str] = Field(..., description="关联的助手ID列表。")
    group_id: str = Field(..., description="关联的群组ID。")
    time: int = Field(..., description="记忆发生或最后更新的时间戳（毫秒）。")
    status: str | None = Field(default=None, description="记忆条目的状态（预留字段）。")
    labels: str | None = Field(default=None, description="记忆条目的标签（预留字段）。")
    memory_info: dict[str, MemoryContentType] = Field(..., description="额外的详细信息。其结构取决于memory_type。")
    # info: dict = Field(default_factory=dict, description="不知道什么字段，文档里没有但实际有")

class ProfileMemoryData(BaseModel):
    """画像记忆搜索响应数据模型"""
    collection_name: str = Field(..., description="被检索的记忆库名称。")
    count: int = Field(..., description="记忆数量。")
    result_list: list[ProfileMemoryResult] = Field(..., description="画像记忆结果列表。")
    token_usage: int = Field(..., description="token使用量。")

class ProfileMemoryResponse(StandardResponse):
    data: ProfileMemoryData = Field(..., description="返回的详细检索结果。")

async def abatch_delete_profile(collection_id: CollectionID,
                                user_id: str | list[str],
                                assistant_id: str | list[str] | None = None,
                                profile_type: str | list[str] | None = None) -> StandardResponse:
    '''批量删除记忆库的画像'''
    path = "/api/memory/profile/batch_delete"
    # 删除参数很简单，不用basemodel封装校验参数
    body = {
        "collection_name": collection_id.collection_name,
        "project_name": collection_id.project_name,
        "resource_id": collection_id.resource_id,
        "filter": {
            "user_id": user_id,
            "assistant_id": assistant_id,
            "profile_type": profile_type,
        }
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, body)
        return StandardResponse.model_validate(rsp.data)

def batch_delete_profile(collection_id: CollectionID,
                         user_id: str | list[str],
                         assistant_id: str | list[str] | None = None,
                         profile_type: str | list[str] | None = None) -> StandardResponse:
    '''批量删除记忆库的画像'''
    rsp = asyncio.run(abatch_delete_profile(collection_id, user_id, assistant_id, profile_type))
    return rsp

class ProfileMemoryFilter(BaseModel):
    """记忆搜索过滤条件基类，包含通用字段"""
    memory_type: str | list[str] = Field(..., description="记忆类型（必需）。可以是事件类型（EventType）或画像类型（ProfileType）的名称，支持单个值或列表")
    
    user_id: str | list[str] | None = Field(default=None, description="用户ID，支持单个ID或ID列表")
    
    assistant_id: str | list[str] | None = Field(default=None, description="助手ID，支持单个ID或ID列表")
    
    primary_key: str | list[str] | None = Field(default=None, description="画像主键表达式，用于过滤。可以是单个值或列表。例如，如果画像主键是 kb_id，要查询 kb_id=1 的数据，搜索条件为 primary_key='kb_id=1'")
    
    group_id: str | list[str] | None = Field(default=None, description="群组ID，用于过滤。支持单个ID或ID列表")

    profile_date: str | None = Field(default=None, description="画像对应的记忆检索时间范围。日报用单日日期（如'2025/12/01'），周报用起止区间（如'2025/12/01~2025/12/07'），用于过滤并检索该周期内自动更新的画像")

class SearchProfileMemoryBody(CollectionID):
    """画像记忆搜索请求模型
    
    与 SearchMemory 几乎相同，但使用 ProfileMemoryFilter 而不是 MemoryFilter。
    ProfileMemoryFilter 包含 profile_date 字段，且不支持 session_id。
    """
    
    query: str | None = Field(default=None, description="用户的搜索查询语句（最多 4000 个字符）。如果提供 query，将基于查询内容进行语义匹配召回记忆，召回数量与 limit 值相关。如果不提供 query，将返回符合 filter 条件的记忆列表，按时间排序（优先最新），召回数量与 limit 值相关")
    
    filter: ProfileMemoryFilter = Field(..., description="搜索过滤条件和返回设置（必需）。注意：画像搜索不支持 session_id 过滤")
    
    limit: int = Field(default=10, description="返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]",ge=1,le=5000)

async def asearch_profile_memory(collection_id: CollectionID,
                                 profile_type: str | list[str],
                                 user_id: str | list[str],
                                 query: str | None = None,
                                 assistant_id: str | list[str] | None = None,
                                 primary_key: str | list[str] | None = None,
                                 profile_date: str | None = None,
                                 group_id: str | list[str] | None = None,
                                 limit: int = 10) -> ProfileMemoryResponse: 
    """
    搜索记忆库中的画像记忆数据
    
    与 search_memory 类似，但专门用于搜索画像类型的记忆，支持通过 profile_date 过滤特定日期范围的画像。
    
    参数说明：
    - collection_id: 必填，记忆库ID信息
    - memory_type: 必填，画像记忆类型
    - query: 搜索查询字符串
    - user_id: 用于过滤的用户ID。可以是单个ID或ID列表。
    - assistant_id: 用于过滤的助手ID。可以是单个ID或ID列表。
    - primary_key: 用于过滤的画像主键表达式。可以是单个或列表，比如画像主键名为kb_id，想查询kb_id为1的数据，则检索条件为 primary_key="kb_id=1"
    - profile_date: 画像记忆的日期范围，格式为 "YYYY/MM/DD" 或 "YYYY/MM/DD~YYYY/MM/DD"。
    - group_id: 用于过滤的群组ID。可以是单个ID或ID列表。
    - limit: 返回结果的最大数量，默认值为 10。
    
    注意：返回的 ProfileMemoryResponse 中的结果不包含 session_id 字段。
    """
    path = "/api/memory/profile/search"
    filter = ProfileMemoryFilter(
        memory_type=profile_type,
        user_id=user_id,
        assistant_id=assistant_id,
        primary_key=primary_key,
        profile_date=profile_date,
        group_id=group_id
    )
    body = SearchProfileMemoryBody(
        collection_name=collection_id.collection_name,
        project_name=collection_id.project_name,
        resource_id=collection_id.resource_id,
        query=query,
        limit=limit,
        filter=filter,
    )
    params = body.model_dump(exclude_none=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, params)
        return ProfileMemoryResponse.model_validate(rsp.data)

def search_profile_memory(collection_id: CollectionID,
                          profile_type: str | list[str],
                          user_id: str | list[str],
                          query: str | None = None,
                          assistant_id: str | list[str] | None = None,
                          primary_key: str | list[str] | None = None,
                          profile_date: str | None = None,
                          group_id: str | list[str] | None = None,
                          limit: int = 10) -> ProfileMemoryResponse:
    """
    搜索记忆库中的画像记忆数据
    
    与 search_memory 类似，但专门用于搜索画像类型的记忆，支持通过 profile_date 过滤特定日期范围的画像。
    
    参数说明：
    - collection_id: 必填，记忆库ID信息
    - memory_type: 必填，画像记忆类型
    - query: 搜索查询字符串
    - user_id: 用于过滤的用户ID。可以是单个ID或ID列表。
    - assistant_id: 用于过滤的助手ID。可以是单个ID或ID列表。
    - primary_key: 用于过滤的画像主键表达式。可以是单个或列表，比如画像主键名为kb_id，想查询kb_id为1的数据，则检索条件为 primary_key="kb_id=1"
    - profile_date: 画像记忆的日期范围，格式为 "YYYY/MM/DD" 或 "YYYY/MM/DD~YYYY/MM/DD"。
    - group_id: 用于过滤的群组ID。可以是单个ID或ID列表。
    - limit: 返回结果的最大数量，默认值为 10。
    
    注意：返回的 ProfileMemoryResponse 中的结果不包含 session_id 字段。
    """
    
    result = asyncio.run(asearch_profile_memory(collection_id, profile_type, user_id, query, assistant_id, primary_key, profile_date, group_id, limit))
    return result

async def aadd_custom_profile_memory(collection_id: CollectionID,
                                     profile_type: str,
                                     memory_content: dict[str, MemoryContentType],
                                     user_id: str,
                                     assistant_id: str | None = None,
                                     group_id: str | None = None,
                                     is_upsert: bool = True,
                                     incremental_update_keys: list[str] | None = None,
                                     keep_other_keys_content: bool = True) -> ProfileMemoryAddResponse:
    '''添加自定义画像记忆到火山记忆平台
    Args:
        collection_id: 记忆库ID信息
        profile_type: 画像记忆类型
        memory_content: 画像记忆的内容，必须确保key在profile里已定义
        user_id: 用户ID
        assistant_id: 助手ID，注意，如果对应的记忆画像记忆与某些assistant有绑定关系，那么必填，否则报错
        group_id: 群组ID
        is_upsert: 已存在记忆是否使用本次写入进行更新，默认为false，即不更新。
                    false：查找是否存在记录，存在则报错，不存在则新增。
                    true：先查找是否存在记录，存在则更新，不存在则新增。
        incremental_update_keys: 增量更新的记忆键值列表，默认None。
            对应的key的值，如果是str类型，那么在原有记忆的基础上，用换行符缀在原有记忆后面；
            如果是list类型，那么在原有记忆的基础上，追加新的记忆list内容在list后面（请确保list内元素的类型与原有的一致，否则会报错）；
            如果是其他类型，那么依然直接覆盖原有记忆。
        keep_other_keys_content: 是否保留其他未指定更新的记忆键值的原有内容，默认True。
    '''
    # 增量更新的属性
    if incremental_update_keys or keep_other_keys_content:
        # 先拿到这些画像键值对应的记忆
        data = await asearch_profile_memory(collection_id, profile_type=profile_type, user_id=user_id, assistant_id=assistant_id, group_id=group_id, limit=5000)
        data = data.data
        # present_memory是一个以profile_memory_key为key，profile_memory_content为value的dict
        if data.result_list and data.result_list[0].memory_info:
            present_memory = {item[0]: item[1] for item in data.result_list[0].memory_info.items()}
        else:
            present_memory = {}
    if incremental_update_keys:
        # is_upsert必须为True
        assert is_upsert, "增量更新记忆时，is_upsert必须为True"
        # 筛选出需要增量更新的记忆
        incremental_update_memory = {mem_key: mem_info for mem_key, mem_info in present_memory.items() if mem_key in incremental_update_keys}
        # 根据不同数据类型进行增量更新处理
        for mem_key, mem_info in incremental_update_memory.items():
            if isinstance(mem_info, str):
                print("增量更新了字符串类型属性的记忆"+mem_key)
                memory_content[mem_key] = mem_info + "\n" + memory_content[mem_key]
            elif isinstance(mem_info, list):
                print("增量更新了列表类型属性的记忆"+mem_key)
                # 在memory_content[mem_key]这个list的前面加上mem_info这个list的内容
                memory_content[mem_key] = mem_info + memory_content[mem_key]
            else:
                print("期望增量更新"+mem_key+"，但记忆内容类型为"+str(type(mem_info))+"，不支持增量更新")
    if keep_other_keys_content:
        # 保留其他未指定更新的记忆键值的原有内容
        memory_content = {**present_memory, **memory_content}
    path = "/api/memory/profile/add"
    params = {
        "collection_name": collection_id.collection_name,
        "project_name": collection_id.project_name,
        "resource_id": collection_id.resource_id,
        "profile_type": profile_type,
        "memory_info": memory_content,
        "user_id": user_id,
        "assistant_id": assistant_id,
        "group_id": group_id,
        "is_upsert": is_upsert
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, params)
        return ProfileMemoryAddResponse.model_validate(rsp.data)

def add_custom_profile_memory(collection_id: CollectionID, 
                              profile_type: str, 
                              memory_content: dict[str, MemoryContentType], 
                              user_id: str, 
                              assistant_id: str | None = None, 
                              group_id: str | None = None, 
                              is_upsert: bool = True, 
                              incremental_update_keys: list[str] | None = None, 
                              keep_other_keys_content: bool = True) -> ProfileMemoryAddResponse:
    '''添加自定义画像记忆到火山记忆平台
    Args:
        collection_id: 记忆库ID信息
        profile_type: 画像记忆类型
        memory_content: 画像记忆的内容，必须确保key在profile里已定义
        user_id: 用户ID
        assistant_id: 助手ID，注意，如果对应的记忆画像记忆与某些assistant有绑定关系，那么必填，否则报错
        group_id: 群组ID
        is_upsert: 已存在记忆是否使用本次写入进行更新，默认为false，即不更新。
                    false：查找是否存在记录，存在则报错，不存在则新增。
                    true：先查找是否存在记录，存在则更新，不存在则新增。
        incremental_update_keys: 增量更新的记忆键值列表，默认None。
            对应的key的值，如果是str类型，那么在原有记忆的基础上，用换行符缀在原有记忆后面；
            如果是list类型，那么在原有记忆的基础上，追加新的记忆list内容在list后面（请确保list内元素的类型与原有的一致，否则会报错）；
            如果是其他类型，那么依然直接覆盖原有记忆。
        keep_other_keys_content: 是否保留其他未指定更新的记忆键值的原有内容，默认True。
    '''
    result = asyncio.run(aadd_custom_profile_memory(collection_id, profile_type, memory_content, user_id, assistant_id, group_id, is_upsert, incremental_update_keys, keep_other_keys_content))
    return result