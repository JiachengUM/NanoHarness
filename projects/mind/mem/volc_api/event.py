from pydantic import BaseModel, Field, model_validator
import httpx
import asyncio
from projects.mind.mem.volc_api._api import request
from projects.mind.mem.volc_api.base import (
    CollectionID,
    MemoryContentType,
    StandardResponse,
)
from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport
from aicore.utils.volc_client.volc_api import VolcApiClient
__all__ = [
    "batch_delete_event",
    "search_event_memory",
    "add_custom_event_memory",
    "abatch_delete_event",
    "asearch_event_memory",
    "aadd_custom_event_memory",
    "ProfileAndPrimaryKey"
]


class EventDataResponse(BaseModel):
    '''增加自定义事件记忆的数据响应'''
    event_id: str = Field(..., description="事件记忆ID")
    event_type: str = Field(..., description="事件记忆类型")
    memory_info: dict[str, MemoryContentType] = Field(..., description="事件记忆的内容")
    usage: dict[str, int] = Field(..., description="事件记忆生成的使用量情况")

class EventMemoryAddResponse(StandardResponse):
    '''添加事件记忆的响应'''
    data: EventDataResponse = Field(..., description="响应数据")

class EventProperty(BaseModel):
    """事件属性定义"""
    PropertyName: str = Field(..., description="属性名称，例如 score, total_interactions。")
    PropertyValueType: str = Field(..., description="属性值的类型，可选值包括 ['int64', 'list<int64>', 'string', 'list<string>', 'float32', 'bool']")
    Description: str = Field(..., description="属性的详细描述，最多 10000 个字符。")


class EventTypeSchema(BaseModel):
    """事件类型 Schema 定义"""
    EventType: str = Field(..., description="事件类型的唯一名称，例如 'customer_feedback', 'learning_progress'。")
    Description: str = Field(..., description="事件类型的详细描述，最多 10000 个字符。")
    Properties: list[EventProperty] = Field(..., description="构成此事件类型的属性列表。")
    Version: str = Field(default="1", description="事件模式版本号，默认为 '1'。")
    ValidationExpression: str | None = Field(default=None, description="可选的校验表达式，用于验证事件内容的有效性，例如 \"field_a == '1'\"。")

class BatchDeleteEventFilter(BaseModel):
    '''批量删除记忆的过滤条件'''
    user_id: str | list[str] | None = Field(default=None, description="用户ID，支持单个ID或ID列表。和assistant_id至少填写一个，也可以同时填写。")
    assistant_id: str | list[str] | None = Field(default=None, description="助手ID，支持单个ID或ID列表。和user_id至少填写一个，也可以同时填写。")
    group_id: str | list[str] | None = Field(default=None, description="群组ID，支持单个ID或ID列表。")
    event_type: str | list[str] | None = Field(default=None, description="事件类型，支持单个类型或类型列表。")
    @model_validator(mode="after")
    def check_filter(self):
        """校验过滤条件"""
        if not self.user_id and not self.assistant_id:
            raise ValueError("必须提供 user_id 或 assistant_id")
        return self

class BatchDeleteEvent(CollectionID): 
    '''用于批量删除已写入记忆库的事件记忆'''
    filter: BatchDeleteEventFilter = Field(..., description="过滤条件")
    delete_type: str = Field(default="full", description="记忆的删除方式。默认是full模式")

class EventMemoryFilter(BaseModel):
    """记忆搜索过滤条件基类，包含通用字段"""
    memory_type: str | list[str] = Field(..., description="记忆类型（必需）。是事件类型（EventType），支持单个值或列表")
    user_id: str | list[str] | None = Field(default=None, description="用户ID，支持单个ID或ID列表")
    assistant_id: str | list[str] | None = Field(default=None, description="助手ID，支持单个ID或ID列表")
    start_time: int | None = Field(default=None, description="检索记忆的开始时间，毫秒时间戳")
    end_time: int | None = Field(default=None, description="检索记忆的结束时间，毫秒时间戳")
    group_id: str | list[str] | None = Field(default=None, description="群组ID，用于过滤。支持单个ID或ID列表")
    session_id: str | list[str] | None = Field(default=None, description="会话ID，用于过滤。支持单个ID或ID列表")

class TimeDecayConfig(BaseModel):
    """时间衰减配置
    仅针对事件检索，对画像不生效。
    """
    weight: float = Field(..., description="用于调节时间衰减影响力的权重，取值范围 [0, 1)。", ge=0, lt=1)
    no_decay_period: int | None = Field(default=0, description="无衰减期。即多长时间内的记忆权重相同，不衰减。配置单位为天，范围 [0, 10000]。默认值为 0。", ge=0, le=10000)

class EventMemoryResult(BaseModel):
    """事件记忆检索结果列表元素"""
    """记忆检索结果基类，包含通用字段"""
    id: str = Field(..., description="记忆条目（事件或画像实例）的唯一ID。")
    score: float | None = Field(default=None, description="记忆匹配度分数，范围 [0, 1]。如果 query 为空，该字段为空")
    memory_type: str = Field(..., description="记忆类型。")
    user_id: list[str] = Field(..., description="用户ID列表。")
    assistant_id: list[str] = Field(..., description="助手ID列表。")
    group_id: str | None = Field(default=None, description="群组ID，可能为空。")
    time: int = Field(..., description="记忆时间，毫秒时间戳。")
    status: str | None = Field(default=None, description="记忆状态，可能为空")
    labels: str | None = Field(default=None, description="记忆标签，可能为空")
    memory_info: dict[str, MemoryContentType] = Field(..., description="额外的详细信息。其结构取决于memory_type。")
    session_id: str = Field(..., description="会话ID。")
    origin_score: float | None = Field(default=None, description="原始的向量检索分数。当提供了 time_decay_config 或 custom_weight 时返回。")
    time_score: float | None = Field(default=None, description="时间衰减分数。当提供了 time_decay_config 时返回。")
    custom_weight_score: float | None = Field(default=None, description="自定义权重分数。当提供了 custom_weight 时返回。")

class EventMemoryData(BaseModel):
    """事件记忆搜索响应数据模型"""
    collection_name: str = Field(..., description="被检索的记忆库名称。")

    count: int = Field(..., description="记忆数量。")
    
    result_list: list[EventMemoryResult] = Field(..., description="事件记忆结果列表。")

    token_usage: int = Field(..., description="token使用量。")


class EventMemoryResponse(StandardResponse):
    """事件记忆搜索响应模型"""
    data: EventMemoryData = Field(..., description="返回的详细检索结果。")

class SearchEventMemory(CollectionID):
    """事件记忆搜索请求模型
    与 SearchMemory 类似，但：
    - filter 使用 EventMemoryFilter（继承 BaseMemoryFilter 并支持 session_id）
    - 添加了 time_decay_config 字段用于时间衰减配置
    - 添加了 custom_weight 字段用于调节业务字段的重要程度
    """
    
    query: str | None = Field(default=None, description="用户的搜索查询语句（最多 4000 个字符）。如果提供 query，将基于查询内容进行语义匹配召回记忆，召回数量与 limit 值相关。如果不提供 query，将返回符合 filter 条件的记忆列表，按时间排序（优先最新），召回数量与 limit 值相关")
    
    filter: EventMemoryFilter = Field(..., description="搜索过滤条件和返回设置（必需）。事件搜索支持 session_id 过滤")
    
    limit: int = Field(default=10, description="返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]", ge=0, le=5000)
    
    time_decay_config: TimeDecayConfig | None = Field(default=None, description="时间衰减配置。")
    
    custom_weight: float | None = Field(default=None, description="用于调节业务字段的重要程度，取值范围 [0, 1)。",ge=0, lt=1)

class ProfileAndPrimaryKey(BaseModel):
    '''需要更新的画像信息列表'''
    profile_id: str = Field(..., description="画像类型名称")
    primary_key: str = Field(..., description="画像记忆的主键。对于没有另外设置主键的画像（默认的user_id主键），primary_key 不需要填写。单一主键：“primary_key1=1”联合主键：“primary_key1=1&primary_key2=1”")

async def abatch_delete_event(collection_id: CollectionID,
                              event_type: str | list[str] | None = None,
                              user_id: str |list[str]| None = None,
                              assistant_id: str | list[str] | None = None,
                              group_id: str | list[str] | None = None,
                              delete_type: str = "full") -> StandardResponse:
    '''批量删除事件记忆
    Args:
        collection_id: 记忆库ID信息
        event_type: 事件记忆类型
        user_id: 用户ID
        assistant_id: 助手ID
        group_id: 群组ID
        delete_type: 记忆的删除方式。默认是full模式。暂时也不知道有什么其他模式，也不知道这些模式具体区别，官方文档没写。
    '''
    path = "/api/memory/event/batch_delete"
    filter = BatchDeleteEventFilter(
        event_type=event_type,
        user_id=user_id,
        assistant_id=assistant_id,
        group_id=group_id,
    )
    params = {
        "collection_name": collection_id.collection_name,
        "project_name": collection_id.project_name,
        "resource_id": collection_id.resource_id,
        "filter": filter.model_dump(exclude_none=True),
        "delete_type": delete_type,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, params)
        return StandardResponse.model_validate(rsp.data)

def batch_delete_event(collection_id: CollectionID, 
                       user_id: str | list[str] | None = None,
                       assistant_id: str | list[str] | None = None,
                       group_id: str | list[str] | None = None,
                       event_type: str | list[str] | None = None,
                       delete_type: str = "full") -> StandardResponse:
    '''批量删除已写入记忆库的事件记忆
    参数说明：
        - user_id: 用户ID，支持单个ID或ID列表。和assistant_id至少填写一个，也可以同时填写。
        - assistant_id: 助手ID，支持单个ID或ID列表。和user_id至少填写一个，也可以同时填写。
        - group_id: 群组ID，支持单个ID或ID列表。
        - event_type: 事件类型，支持单个类型或类型列表。
        - delete_type: 记忆的删除方式。默认是full模式。暂时也不知道有什么其他模式，官方文档没写。
    '''
    result = asyncio.run(abatch_delete_event(collection_id, event_type, user_id, assistant_id, group_id, delete_type))
    return result

async def aadd_custom_event_memory(collection_id: CollectionID, 
                                    event_type: str, 
                                    memory_content: dict[str, MemoryContentType],
                                    user_id: str , 
                                    time: int | None = None,
                                    update_profiles: list[ProfileAndPrimaryKey] | None = None, 
                                    assistant_id: str | None = None, 
                                    group_id: str | None = None) -> EventMemoryAddResponse:
    '''添加自定义事件记忆到火山记忆平台，会不停新增事件而不会像画像记忆一样可选覆盖更新。
    Args:
        collection_id: 记忆库ID信息
        event_type: 事件记忆类型
        memory_content: 事件记忆的内容
        time: 记忆生成的时间戳（毫秒）。不传将以请求时间作为记忆生成时间。
        update_profiles: 需要更新的画像信息列表
        user_id: 用户ID
        assistant_id: 助手ID，注意，如果对应的记忆画像记忆与某些assistant有绑定关系，那么必填，否则报错
        group_id: 群组ID
    '''
    path = "/api/memory/event/add"
    params = {
        "event_type": event_type,
        "memory_info": memory_content,
        "time": time,
        "update_profiles": [a_profile.model_dump(exclude_none=True) for a_profile in update_profiles] if update_profiles else None,
        "user_id": user_id,
        "assistant_id": assistant_id,
        "group_id": group_id
    }
    params.update(collection_id.model_dump(exclude_none=True))
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, params)
        return EventMemoryAddResponse.model_validate(rsp.data)

def add_custom_event_memory(collection_id: CollectionID, 
                            event_type: str, 
                            memory_content: dict[str, MemoryContentType],
                            user_id: str , 
                            time: int | None = None,
                            update_profiles: list[ProfileAndPrimaryKey] | None = None, 
                            assistant_id: str | None = None, 
                            group_id: str | None = None) -> EventMemoryAddResponse:
    '''添加自定义事件记忆到火山记忆平台，会不停新增事件而不会像画像记忆一样可选覆盖更新。
    Args:
        collection_id: 记忆库ID信息
        event_type: 事件记忆类型
        memory_content: 事件记忆的内容
        time: 记忆生成的时间戳（毫秒）。不传将以请求时间作为记忆生成时间。
        update_profiles: 需要更新的画像信息列表
        user_id: 用户ID
        assistant_id: 助手ID，注意，如果对应的记忆画像记忆与某些assistant有绑定关系，那么必填，否则报错
        group_id: 群组ID
    '''
    result = asyncio.run(aadd_custom_event_memory(collection_id, event_type, memory_content, user_id, time, update_profiles, assistant_id, group_id))
    return EventMemoryAddResponse.model_validate(result)

async def asearch_event_memory(collection_id: CollectionID,
                               event_type: str | list[str],
                               user_id: str | list[str],
                               query: str | None = None,
                               assistant_id: str | list[str] | None = None,
                               group_id: str | list[str] | None = None,
                               start_time: int | None = None,
                               end_time: int | None = None,
                               session_id: str | list[str] | None = None,
                               limit: int = 10,
                               time_decay_weight: float | None = None,
                               no_decay_period : int | None = None,
                               custom_weight: float | None = None) -> EventMemoryResponse:
    """
    搜索记忆库中的事件记忆数据
    
    与 search_memory 类似，但专门用于搜索事件类型的记忆，支持时间衰减配置和自定义权重。
    
    参数说明：
    - collection_id: 必填，记忆库唯一标识符组合
    - memory_type: 必填，记忆类型，支持单个类型或类型列表。
    - query: 可选，用户的搜索查询语句（最多 4000 个字符）。如果提供 query，将基于查询内容进行语义匹配召回记忆，召回数量与 limit 值相关。如果不提供 query，将返回符合 filter 条件的记忆列表，按时间排序（优先最新），召回数量与 limit 值相关
    - user_id: 用户ID，支持单个ID或ID列表。和assistant_id至少填写一个，也可以同时填写。
    - assistant_id: 助手ID，支持单个ID或ID列表。和user_id至少填写一个，也可以同时填写。
    - group_id: 群组ID，支持单个ID或ID列表。
    - start_time: 开始时间，Unix 时间戳（毫秒级）。
    - end_time: 结束时间，Unix 时间戳（毫秒级）。
    - session_id: 会话ID，支持单个ID或ID列表。
    - limit: 返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]
    - time_decay_weight: 时间衰减权重，范围 [0, 1)，默认不传不衰减。
    - no_decay_period: 无衰减时间周期，单位为秒。默认值为 0，即不开启无衰减时间周期。
    - custom_weight: 自定义权重，范围 [0, 1)
    - filter: 使用 BaseMemoryFilter，支持 session_id 过滤
    
    注意：返回的 EventMemoryResponse 中的结果包含额外的分数字段：
    - origin_score: 原始的向量检索分数
    - time_score: 时间衰减分数
    - custom_weight_score: 自定义权重分数
    """
    path = "/api/memory/event/search"
    # 利用构造体声明进行入参合法性检查
    time_decay_config = None
    if time_decay_weight:
        time_decay_config = TimeDecayConfig(
            weight=time_decay_weight,
            no_decay_period=no_decay_period,
        )
    body = SearchEventMemory(
        collection_name = collection_id.collection_name,
        project_name = collection_id.project_name,
        resource_id = collection_id.resource_id,
        query=query,
        filter=EventMemoryFilter(
            memory_type=event_type,
            user_id=user_id,
            assistant_id=assistant_id,
            group_id=group_id,
            start_time=start_time,
            end_time=end_time,
            session_id=session_id,
        ),
        limit=limit,
        time_decay_config=time_decay_config,
        custom_weight=custom_weight,
    )
    params = body.model_dump(exclude_none=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, params)
        return EventMemoryResponse.model_validate(rsp.data)

def search_event_memory(collection_id: CollectionID,
                        event_type: str | list[str],
                        user_id: str | list[str],
                        query: str | None = None,
                        assistant_id: str | list[str] | None = None,
                        group_id: str | list[str] | None = None,
                        start_time: int | None = None,
                        end_time: int | None = None,
                        session_id: str | list[str] | None = None,
                        limit: int = 10,
                        time_decay_weight: float | None = None,
                        no_decay_period : int | None = None,
                        custom_weight: float | None = None) -> EventMemoryResponse:
    """
    搜索记忆库中的事件记忆数据
    
    与 search_memory 类似，但专门用于搜索事件类型的记忆，支持时间衰减配置和自定义权重。
    
    参数说明：
    - collection_id: 必填，记忆库唯一标识符组合
    - memory_type: 必填，记忆类型，支持单个类型或类型列表。
    - query: 可选，用户的搜索查询语句（最多 4000 个字符）。如果提供 query，将基于查询内容进行语义匹配召回记忆，召回数量与 limit 值相关。如果不提供 query，将返回符合 filter 条件的记忆列表，按时间排序（优先最新），召回数量与 limit 值相关
    - user_id: 用户ID，支持单个ID或ID列表。和assistant_id至少填写一个，也可以同时填写。
    - assistant_id: 助手ID，支持单个ID或ID列表。和user_id至少填写一个，也可以同时填写。
    - group_id: 群组ID，支持单个ID或ID列表。
    - start_time: 开始时间，Unix 时间戳（秒级）。
    - end_time: 结束时间，Unix 时间戳（秒级）。
    - session_id: 会话ID，支持单个ID或ID列表。
    - limit: 返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]
    - time_decay_weight: 时间衰减权重，范围 [0, 1)，默认不传不衰减。
    - no_decay_period: 无衰减时间周期，单位为秒。默认值为 0，即不开启无衰减时间周期。
    - custom_weight: 自定义权重，范围 [0, 1)
    - filter: 使用 BaseMemoryFilter，支持 session_id 过滤
    
    注意：返回的 EventMemoryResponse 中的结果包含额外的分数字段：
    - origin_score: 原始的向量检索分数
    - time_score: 时间衰减分数
    - custom_weight_score: 自定义权重分数
    """
    result = asyncio.run(asearch_event_memory(collection_id, event_type, user_id, query, assistant_id, group_id, start_time, end_time, session_id, limit, time_decay_weight, no_decay_period, custom_weight))
    return EventMemoryResponse.model_validate(result)
