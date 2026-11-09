from __future__ import annotations
from typing import Any, Literal, Type, TypeVar
import asyncio
import httpx
from pydantic import BaseModel, Field, field_validator

from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport
from aicore.utils.volc_client.volc_api import VolcApiClient
from projects.mind.intent.task_data.message import Message as TaskDataMessage
from projects.mind.mem.volc_api._api import request
from projects.mind.mem.volc_api.base import CollectionID, StandardResponse
from projects.mind.mem.volc_api.event import EventMemoryFilter, TimeDecayConfig
from projects.mind.mem.volc_api.profile import ProfileMemoryFilter
__all__ = [
    "MessageContent",
    "Message",
    "SessionMetadata",

    "CollectionID",
    "SessionCreate",
    "add_session",
    "aadd_session",

    "SessionID",
    "get_session_info",
    "aget_session_info",
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

def _msg_to_volc_format(msgs: list[TaskDataMessage]) -> list[Message]:
    """将 TaskDataMessage 转换为 Message"""
    return [
        Message(
            role=msg.role, # type: ignore
            content=[MessageContent(type="text",text=msg.content)],
        )
        for msg in msgs
    ]

class SessionMetadata(BaseModel):
    """会话元数据"""
    default_user_id: str = Field(..., description="默认用户ID")

    default_user_name: str | None = Field(default=None, description="默认用户名称")

    default_assistant_id: str = Field(..., description="默认助手ID")

    default_assistant_name: str | None = Field(default=None, description="默认助手名称")

    time: int = Field(..., description="这批消息的统一发生时间，毫秒级时间戳。（如果单条消息中也包含time，则单条消息的 time 优先。）")

    group_id : str | None = Field(default=None, description="群组ID，用于标记消息所属的业务群组。")


class ProfileScope(BaseModel):
    """"画像Scope实例的基类，可以继承后增加各个画像各自的属性及其值，但新增的属性必须为MemoryContentType。这玩意儿只Session更新这里用，所以先放在这里。"""
    user_id: str = Field(..., description="用户ID，必须是记忆库中已定义的用户ID，用于唯一标识画像实例。默认一定有。")

    @field_validator('*') # 监听所有字段
    @classmethod
    def validate_memory_content(cls, v: Any) -> Any:
        """
        验证字段值是否符合 MemoryContentType 定义。
        这是一个运行时检查，确保数据合规。
        """
        if v is None:
            return v  # 允许 None（如果字段定义为 Optional）
        # 检查具体类型
        if isinstance(v, bool): 
            # 注意：必须放在 int 之前，因为 bool 是 int 的子类
            return v
        elif isinstance(v, int):
            return v
        elif isinstance(v, float):
            return v
        elif isinstance(v, str):
            return v
        elif isinstance(v, list):
            # 检查列表内容是否全是 str 或 int
            if all(isinstance(item, str) for item in v):
                return v
            elif all(isinstance(item, int) for item in v):
                return v
            else:
                raise ValueError("列表内容必须全为字符串或全为整数")
        else:
            raise ValueError(f"类型错误，值必须是字符串、数字、布尔值或字符串/数字列表，当前类型: {type(v)}")

T = TypeVar('T', bound=ProfileScope)

class ProfileToConnect(BaseModel):
    profile_type: str = Field(..., description="画像类型名称，必须是记忆库中已定义的画像类型。")

    profile_scope: list[Type[T]] = Field(..., description="画像实例列表。每个对象包含用于唯一标识和定义该画像实例的属性，例如: {\"id\": 1, \"knowledge_point_name\": \"taco\"}")


class SessionCreate(CollectionID):
    """会话模型，用于添加会话信息"""
    
    session_id: str | None = Field(default=None, description="会话 ID。长度要求: [1, 128], 只能使用英文字母、数字、下划线，并以英文字母开头。未填写则由服务端自动生成。")
    
    messages: list[Message] = Field(..., description="要添加的多轮对话消息列表（必需）")
    
    store_file: bool = Field(default=False, description="是否存储原始文件，默认为 False")

    metadata: SessionMetadata | None = Field(default=None, description="会话元数据")

    extract_memory_type: list[str] | None = Field(default=None, description="此次数据写入需要抽取的记忆类型。填写事件或画像类型的名称，可以是多个值。不传时默认会抽取所有类型的记忆。")

    profiles : list[ProfileToConnect] | None = Field(default=None, description="需要特别关注或更新的画像信息列表。系统会尝试将处理后的事件与这些画像关联。")

    ttl_absolute : int | None = Field(default=None, description="事件记忆的过期时间，绝对时间，填写时间戳，精确到毫秒级。")

    ttl_relative: int | None = Field(default=None, description="事件记忆的过期时间，相对时间，单位为秒。限制: (0, 315576000]")

async def aadd_session(collection_id: CollectionID,
                       messages: list[Message],
                       session_id: str | None = None,
                       store_file: bool = False,
                       metadata: SessionMetadata | None = None,
                       extract_memory_type: list[str] | None = None,
                       profiles: list[ProfileToConnect] | None = None) -> str:
    """
    异步添加会话记录到记忆库。
    调用 add_session 接口时，若使用相同的 session_id，会覆盖该对话之前生成的事件版本，并从画像中撤回之前生成的事件。
    建议使用 UUID 动态生成 session_id，确保每次会话独立；只有在确实需要覆盖时才重复使用。
    profile_type需要为extract_memory_type里画像类型的子集。
    只有在 messages 中同时传入 user 和 assistant 的消息时，画像和事件才会正确归属用户和助手。接口不会仅依赖 metadata 中的 ID 进行关联；
    如果只传 user 消息，事件不会关联到 metadata 中的 assistant。
    记忆的隔离机制：
    事件：不同assistant、group相关的 message 生成的事件，会带上对应的标识，检索时可使用对应的参数进行过滤。
    画像：画像的隔离分为两层：
    group：不同group生成的画像是完全隔离的（注意，group不代表群聊，只有在需要做画像隔离时，才建议使用group）
    assistant：如果画像选择了按照 assistant 隔离，那么在同一group下，不同 assistant 和用户的消息生成的画像是完全隔离的；如果原始消息中没有传入 assistant，那么就会生成不关联 assistant 的画像（assistant_id=""）。
    extract_memory_type：此次数据写入需要抽取的记忆类型。填写事件或画像类型的名称，可以是多个值。不传时默认会抽取所有类型的记忆。
    profiles：需要特别关注或更新的画像信息列表。系统会尝试将处理后的事件与这些画像关联。不传时默认关联所有画像。
    """
    path = "/api/memory/session/add"
    body = SessionCreate(
        collection_name=collection_id.collection_name,
        project_name=collection_id.project_name,
        resource_id=collection_id.resource_id,
        session_id=session_id,
        messages=messages,
        store_file=store_file,
        metadata=metadata,
        extract_memory_type=extract_memory_type,
        profiles=profiles,
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, body.model_dump(exclude_none=True))  
        assert isinstance(rsp.data, dict)
        return rsp.data['data']['session_id']

def add_session(collection_id: CollectionID,
                messages: list[Message],
                session_id: str | None = None,
                store_file: bool = False,
                metadata: SessionMetadata | None = None,
                extract_memory_type: list[str] | None = None,
                profiles: list[ProfileToConnect] | None = None) -> str:
    """
    添加会话记录到记忆库。
    调用 add_session 接口时，若使用相同的 session_id，会覆盖该对话之前生成的事件版本，并从画像中撤回之前生成的事件。
    建议使用 UUID 动态生成 session_id，确保每次会话独立；只有在确实需要覆盖时才重复使用。
    profile_type需要为extract_memory_type里画像类型的子集。
    只有在 messages 中同时传入 user 和 assistant 的消息时，画像和事件才会正确归属用户和助手。接口不会仅依赖 metadata 中的 ID 进行关联；
    如果只传 user 消息，事件不会关联到 metadata 中的 assistant。
    记忆的隔离机制：
    事件：不同assistant、group相关的 message 生成的事件，会带上对应的标识，检索时可使用对应的参数进行过滤。
    画像：画像的隔离分为两层：
    group：不同group生成的画像是完全隔离的（注意，group不代表群聊，只有在需要做画像隔离时，才建议使用group）
    assistant：如果画像选择了按照 assistant 隔离，那么在同一group下，不同 assistant 和用户的消息生成的画像是完全隔离的；如果原始消息中没有传入 assistant，那么就会生成不关联 assistant 的画像（assistant_id=""）。
    extract_memory_type：此次数据写入需要抽取的记忆类型。填写事件或画像类型的名称，可以是多个值。不传时默认会抽取所有类型的记忆。
    profiles：需要特别关注或更新的画像信息列表。系统会尝试将处理后的事件与这些画像关联。不传时默认关联所有画像。
    """
    result = asyncio.run(aadd_session(collection_id, messages, session_id, store_file, metadata, extract_memory_type, profiles))
    return result

class SessionID(CollectionID):
    """会话信息模型，用于查询会话信息"""
    
    session_id: str = Field(..., description="会话 ID。长度要求: [1, 128], 只能使用英文字母、数字、下划线，并以英文字母开头", min_length=1, max_length=128)
    '''查询时必须有值，而create时可以没有值。因此SessionID并不是SessionCreate的一部分。'''


class MemoryInfo(BaseModel):
    original_messages: str

    summary: str


class EventMemoryBlock(BaseModel):
    assistant_id: list[str]
    
    event_id: str

    event_type: str

    memory_info: MemoryInfo

    time: int

    user_id: list[str]

class SessionData(BaseModel):
    """
    这部分的定义是根据实际api输出手撸的。关于session部分的官方文档不正确。
    """

    assistant_ids: list[str]

    collection_name: str = Field(..., description="被检索的记忆库名称。")

    event_memory: list[EventMemoryBlock] = Field(..., description="事件记忆列表。")

    id: str = Field(..., description="记忆条目（事件或画像实例）的唯一ID。")

    last_update_logid: str

    messages: list[Message]

    session_id: str = Field(..., description="关联的会话ID。")

    status: str

    store_file: bool

    time: int

    usage: dict

    user_ids: list[str]


class SessionInfo(StandardResponse):
    data: SessionData = Field(..., description="返回的详细检索结果。")

async def aget_session_info(session: SessionID) -> SessionInfo:
    """
    异步查询会话的详细信息
    """
    path = "/api/memory/session/info"
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, session.model_dump(exclude_none=True))
        assert isinstance(rsp.data, dict)
        return SessionInfo(**rsp.data)

def get_session_info(session: SessionID) -> SessionInfo:
    """
    查询会话的详细信息
    """
    result = asyncio.run(aget_session_info(session))
    return result

class EventSearchConfig(BaseModel):
    filter: EventMemoryFilter = Field(..., description="事件记忆过滤条件。")
    limit: int = Field(default=10, description="返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]",ge=1,le=5000)
    time_decay_config: TimeDecayConfig | None = Field(default=None, description="时间衰减配置。")
    custom_weight: float | None = Field(default=None, description="用于调节业务字段的重要程度，取值范围 [0, 1)。",ge=0, lt=1)

class ProfileSearchConfig(BaseModel):
    filter: ProfileMemoryFilter = Field(..., description="画像记忆过滤条件。")
    limit: int = Field(default=10, description="返回的搜索结果数量。默认值为 10，允许范围 [1, 5000]",ge=1,le=5000)

class GetContextRequest(CollectionID):
    """查询会话上下文请求模型"""
    conversation_id: str = Field(..., description="会话 ID。长度要求: [1, 128], 只能使用英文字母、数字、下划线，并以英文字母开头。几乎等价于session_id", min_length=1, max_length=128)
    query: str = Field(..., description="用户的检索查询语句。")
    event_search_config: EventSearchConfig | None = Field(default=None, description="事件搜索配置。")
    profile_search_config: ProfileSearchConfig | None = Field(default=None, description="画像搜索配置。")
    
class ConversationId(BaseModel):
    conversation_id: str = Field(..., description="会话 ID。长度要求: [1, 128], 只能使用英文字母、数字、下划线，并以英文字母开头。几乎等价于session_id", min_length=1, max_length=128)

class GetContextData(BaseModel):
    collection_name: str = Field(..., description="被检索的记忆库名称。")
    context: str = Field(..., description="检索返回的context，可以直接拼接到prompt。")
    token_usage: int = Field(..., description="本次检索消耗的token数量。")
    session_id: str | None = Field(default=None, description="记忆库服务自动生成session ID，仅对于触发了记忆抽取的写入轮次会返回。")

class GetContextResponse(StandardResponse):
    data: GetContextData = Field(..., description="返回的详细检索结果。")

async def aget_context(collection_id: CollectionID,
                 conversation_id: str,
                 query: str,
                 event_type: str | list[str] | None = None,
                 event_search_user_id: str | list[str] | None = None,
                 event_search_assistant_id: str | list[str] | None = None,
                 event_search_group_id: str | list[str] | None = None,
                 event_search_start_time: int | None = None,
                 event_search_end_time: int | None = None,
                 event_search_limit: int = 10,
                 event_search_time_decay_weight: float | None = None,
                 event_search_no_decay_period : int | None = None,
                 event_search_custom_weight: float | None = None,
                 profile_type: str | list[str] | None = None,
                 profile_search_limit: int = 10,
                 profile_user_id: str | list[str] | None = None,
                 profile_assistant_id: str | list[str] | None = None,
                 profile_primary_key: str | list[str] | None = None,
                 profile_group_id: str | list[str] | None = None,
                 profile_date: str | None = None,
                 ) -> GetContextResponse:
    """
    根据 conversation_id，同时获取短期和长期记忆，且可直接拼接到对话模型的 prompt 内使用。包括：1）该 conversation_id 下最近 N 轮原始消息；2）该 conversation_id 下的事件记忆，全部返回；3）该 conversation 外的事件记忆，通过检索返回；4）用户画像记忆，通过检索返回。
    Args:
        collection_id: 记忆库 ID
        conversation_id: 会话 ID
        query: 用户检索查询语句
        其余请参考搜索事件和搜索画像的参数说明，太多了不写了。
    """
    path = "/api/memory/get_context"
    if event_search_time_decay_weight and event_search_no_decay_period:
        time_decay_config = TimeDecayConfig(
            weight=event_search_time_decay_weight,
            no_decay_period=event_search_no_decay_period,
        )
    else:
        time_decay_config = None
    if event_type:
        event_searh_config = EventSearchConfig(
            filter=EventMemoryFilter(
                memory_type=event_type,
                user_id=event_search_user_id,
                assistant_id=event_search_assistant_id,
                group_id=event_search_group_id,
                start_time=event_search_start_time,
                end_time=event_search_end_time,
            ),
            time_decay_config=time_decay_config,
            custom_weight=event_search_custom_weight,
            limit=event_search_limit,
        )
    else:
        event_searh_config = None
    if profile_type:
        profile_search_config = ProfileSearchConfig(
                filter=ProfileMemoryFilter(
                memory_type=profile_type,
                user_id=profile_user_id,
                assistant_id=profile_assistant_id,
                primary_key=profile_primary_key,
                group_id=profile_group_id,
                profile_date=profile_date,
            ),
            limit=profile_search_limit,
        )
    else:
        profile_search_config = None
    a_conversation_id = ConversationId(conversation_id=conversation_id)
    body = GetContextRequest(
        collection_name=collection_id.collection_name,
        project_name=collection_id.project_name,
        resource_id=collection_id.resource_id,
        conversation_id=a_conversation_id.conversation_id,
        query=query,
        event_search_config=event_searh_config,
        profile_search_config=profile_search_config,
    )
    params = body.model_dump(exclude_none=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))
        rsp = await client.post(path, params)
        return GetContextResponse.model_validate(rsp.data)

def get_context(collection_id: CollectionID,
                 conversation_id: str,
                 query: str,
                 event_type: str | list[str] | None = None,
                 event_search_user_id: str | list[str] | None = None,
                 event_search_assistant_id: str | list[str] | None = None,
                 event_search_group_id: str | list[str] | None = None,
                 event_search_start_time: int | None = None,
                 event_search_end_time: int | None = None,
                 event_search_limit: int = 10,
                 event_search_time_decay_weight: float | None = None,
                 event_search_no_decay_period : int | None = None,
                 event_search_custom_weight: float | None = None,
                 profile_type: str | list[str] | None = None,
                 profile_search_limit: int = 10,
                 profile_user_id: str | list[str] | None = None,
                 profile_assistant_id: str | list[str] | None = None,
                 profile_primary_key: str | list[str] | None = None,
                 profile_group_id: str | list[str] | None = None,
                 profile_date: str | None = None,
                 ) -> GetContextResponse:
    """
    根据 conversation_id，同时获取短期和长期记忆，且可直接拼接到对话模型的 prompt 内使用。包括：1）该 conversation_id 下最近 N 轮原始消息；2）该 conversation_id 下的事件记忆，全部返回；3）该 conversation 外的事件记忆，通过检索返回；4）用户画像记忆，通过检索返回
    Args:
        collection_id: 记忆库 ID
        conversation_id: 会话 ID
        query: 用户检索查询语句
        其余请参考搜索事件和搜索画像的参数说明，太多了不写了。
    """
    result = asyncio.run(aget_context(collection_id, conversation_id, query,event_type,event_search_user_id,event_search_assistant_id,event_search_group_id,event_search_start_time,event_search_end_time,event_search_limit,event_search_time_decay_weight,event_search_no_decay_period,event_search_custom_weight,profile_type,profile_search_limit,profile_user_id,profile_assistant_id,profile_primary_key,profile_group_id,profile_date))
    return result
   
