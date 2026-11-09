from __future__ import annotations

from typing import AsyncGenerator, Literal, Union, Callable, Awaitable

from pydantic import BaseModel, Field, field_validator, model_validator

from datetime import datetime

from rich import print

from aicore.core.event import EventBase, EventListener

from projects.mind.mem.volc_api import CollectionID, MessageVolcMem, MessageContent, SessionMetadata, aadd_session
from projects.mind.mem.volc_api.session import ProfileToConnect
from projects.mind.mem.volc_api.profile import asearch_profile_memory, ProfileMemoryResponse, ProfileMemoryData, aadd_custom_profile_memory
from projects.mind.mem.volc_api.event import asearch_event_memory, EventMemoryResponse, EventMemoryData
from projects.mind.mem.volc_api.base import MemoryContentType

from aicore.models.messages import HumanMessage, AIMessage

from aicore.tools.experiments.event_search_tool import EventItem, EventSearchToolOutput
from aicore.tools.experiments.profile_search_tool import ProfileItem, ProfileSearchToolOutput
from aicore.tools.experiments.skill_search_tool import SkillItem, SkillSearchToolOutput
from aicore.tools.experiments.load_skill_tool import LoadedSkill, LoadSkillToolOutput
from aicore.tools.experiments.create_new_skill_tool import CreateNewSkillToolOutput
from aicore.tools.experiments.update_skill_tool import UpdateSkillToolOutput

SKILL_PROFILE_TYPE = "skills"
SKILL_NAME_PRIMARY_KEY = "skill_name"
SKILL_DESCRIPTION_KEY = "skill_description"
SKILL_MARKDOWN_CONTENT_KEY = "skill_markdown_content"
SKILL_LAST_USED_DATETIME_KEY = "last_used_datetime"
SKILL_LAST_USED_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def skill_last_used_datetime_now(when: datetime | None = None) -> str:
    """写入记忆库时统一的 skill 使用时间格式（年月日时分秒）。"""
    dt = datetime.now() if when is None else when
    return dt.strftime(SKILL_LAST_USED_DATETIME_FMT)


def normalize_skill_last_used_datetime(raw: object) -> str:
    """将从记忆库读出的 last_used_datetime 规整为 SKILL_LAST_USED_DATETIME_FMT；空或无法解析则为空字符串。"""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    variants = [s]
    if s.endswith("Z"):
        variants.append(s[:-1])
    fmts = (
        SKILL_LAST_USED_DATETIME_FMT,
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )
    for candidate in variants:
        for fmt in fmts:
            try:
                return datetime.strptime(candidate, fmt).strftime(SKILL_LAST_USED_DATETIME_FMT)
            except ValueError:
                continue
    return ""


def profile_memory_time_ms_to_datetime_str(time_ms: int) -> str:
    """画像检索结果元素 `time` 字段为毫秒时间戳，转为与 last_used 一致的年月日时分秒格式。"""
    return datetime.fromtimestamp(time_ms / 1000.0).strftime(SKILL_LAST_USED_DATETIME_FMT)


# 与 aicore.agents.experiments.base.SKILL_TOOL_USAGE_GUIDANCE_PROMPT 文案保持一致；
# memory 模块不得反向 import base（避免循环依赖），故在此独立定义一份。
SKILL_GOVERNANCE_PROMPT = (
    "多数时候你都可以先搜索一下skill，看看是否已有可复用方法或者过往的经验可以参考着使用。"
    "当你需要解决复杂或可复用任务时，请优先使用 skill 相关工具形成“先检索、再加载、再执行、再沉淀”的闭环："
    "先用 skill搜索工具 查询是否已有可复用方法；若命中候选，再用 load_skill工具 加载完整方法并严格按步骤执行；"
    "若现有 skill 不足以覆盖场景，但你最终成功完成了任务且过程有复用价值，请使用 create_new_skill工具 沉淀新经验；"
    "若你在实践中发现已有 skill 可以优化，请使用 update_skill工具 更新内容。"
    "除非任务非常简单且无复用价值，否则不要跳过这套流程。"
)

SKILL_REMEDIATION_TASK_PROMPT = """\
请先通读下列「skill 清单」：每条包含 skill_name、描述、上次被 load_skill 使用的时间（last_used_datetime），
以及画像记录在服务端最近一次更新的时间（last_updated_time，由检索结果条目的 time 毫秒戳换算）。

你的目标是：在遵守「Skill 工具使用与沉淀原则」的前提下，对 skill 集合提出**可落地的治理方案**——
例如合并高度重叠条目、收敛命名、标注可优先清理或合并的候选，并说明若执行合并应优先保留哪一条、如何迁移 markdown。
修改记忆前请先通过 load_skill 核对全文；写回时优先使用 update_skill。"""


def history_to_volcmessages(history: list[tuple[HumanMessage, AIMessage]]) -> list[MessageVolcMem]:
    """将历史对话转换为火山记忆平台要求的对话记录格式"""
    message_pairs = [
        (
            MessageVolcMem(role="user", content=[MessageContent(type="text", text=h.content)]),
            MessageVolcMem(role="assistant", content=[MessageContent(type="text", text=a.content)])
        )
        for h, a in history
    ]
    return [msg for pair in message_pairs for msg in pair]


def prepend_system_to_volcmessages(
    system_text: str | None,
    dialogue_volc: list[MessageVolcMem],
) -> list[MessageVolcMem]:
    """在会话消息首部插入一条 system，使抽取可见车况/car_info、人设等与模型对齐的上下文。"""
    if system_text is None:
        return dialogue_volc
    stripped = str(system_text).strip()
    if not stripped:
        return dialogue_volc
    head = MessageVolcMem(
        role="system",
        content=[MessageContent(type="text", text=stripped)],
    )
    return [head, *dialogue_volc]


class MemoryAddPendingEvent(EventBase):
    """缓冲区待处理：新对话进入缓冲区"""
    type: Literal["memory.add.pending"] = Field("memory.add.pending", init=False) # type: ignore
    pending_count: int = Field(..., description="缓冲区待处理轮数")
    session_size: int = Field(..., description="触发阈值,window_size")


class MemoryAddProcessingEvent(EventBase):
    """正在处理：开始写入记忆"""
    type: Literal["memory.add.processing"] = Field("memory.add.processing", init=False) # type: ignore
    processed_count: int = Field(..., description="本次处理的轮数")
    content: list[MessageVolcMem] = Field(..., description="本次处理的对话记录")


class MemoryAddCompletedEvent(EventBase):
    """写入成功：记忆写入完成"""
    type: Literal["memory.add.completed"] = Field("memory.add.completed", init=False) # type: ignore
    session_id: str = Field(..., description="会话ID")
    processed_count: int = Field(..., description="本次处理的轮数")
    total_handled: int = Field(..., description="累计处理的总轮数")


class MemoryAddFailedEvent(EventBase):
    """写入失败：记忆写入出错"""
    type: Literal["memory.add.failed"] = Field("memory.add.failed", init=False) # type: ignore
    error: str = Field(..., description="错误信息")
    pending_count: int = Field(..., description="缓冲区待处理轮数")


MemoryEvent = Union[
    MemoryAddPendingEvent,
    MemoryAddProcessingEvent,
    MemoryAddCompletedEvent,
    MemoryAddFailedEvent,
]

MemoryEventListener = EventListener[MemoryEvent]


class MemoryEventPrinter:
    """默认的记忆事件打印器。"""
    
    def __init__(self):
        self.print = print
    
    def __call__(self, event: MemoryEvent) -> None:
        match event:
            case MemoryAddPendingEvent():
                self.print(f"⏳ [Memory] 缓冲区: {event.pending_count} 轮待处理, 触发阈值: {event.session_size}")
            case MemoryAddProcessingEvent():
                self.print(f"🔄 [Memory] 正在写入: {event.processed_count} 轮对话")
                for msg in event.content:
                    self.print(msg)
                self.print()
            case MemoryAddCompletedEvent():
                self.print(f"✅ [Memory] 写入成功: session_id={event.session_id}, 累计处理轮数: {event.total_handled}")
            case MemoryAddFailedEvent():
                self.print(f"❌ [Memory] 写入失败: {event.error}")


class UserInfoMetadata(BaseModel):
    """用户元数据，包含 user_id"""
    # 创建后不可修改
    model_config = {"frozen": True}

    user_id: str = Field(..., description="默认用户ID")

    user_name: str | None = Field(default=None, description="默认用户名称")

    assistant_id: str = Field(..., description="默认助手ID")

    assistant_name: str | None = Field(default=None, description="默认助手名称")

    group_id : str | None = Field(default=None, description="群组ID，用于标记消息所属的业务群组。")
    session_time_ms: int | None = Field(default=None, description="会话写入时间戳（毫秒），为空时使用当前时间")

    def with_mock_time(self, mock_time: str | None) -> "UserInfoMetadata":
        """返回带模拟时间的新元数据对象。"""
        if not mock_time:
            return self.model_copy(update={"session_time_ms": None})
        mock_ts_ms = int(datetime.strptime(mock_time, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
        return self.model_copy(update={"session_time_ms": mock_ts_ms})

    @property
    def create_session_metadata(self) -> SessionMetadata:
        """创建会话元数据，每次调用生成新的 time，userinfo 拥有数据，也由他操作。"""
        event_time_ms = self.session_time_ms if self.session_time_ms is not None else int(datetime.now().timestamp() * 1000)
        return SessionMetadata(
            default_user_id=self.user_id,
            default_user_name=self.user_name,
            default_assistant_id=self.assistant_id,
            default_assistant_name=self.assistant_name,
            time=event_time_ms,
            group_id=self.group_id,
        )


class MemoryProducerConfig(BaseModel):
    """记忆生产者配置，负责写入"""
    collection_id: CollectionID = Field(..., description="记忆库唯一标识 CollectionID（例如 CollectionID(collection_name='SGM')）")
    
    memory_type: list[str] = Field(..., description="抽取的画像类型及事件类型")

    # TODO: 不太清楚具体如何使用,看不懂。需要找梓瑜确认
    profiles: list[ProfileToConnect] | None = Field(default=None, description="需要特别关注或更新的画像信息列表，为extract_memory_type里画像类型的子集")
    """窦：每一个ProfileToConnect是一个画像记忆类型和画像记忆主键的键值对list。画像记忆可以通过定义主键形成组合键来生产出多个画像记忆实例，类似
        数据库里一条条数据。当上传多轮对话记录时，根据官方文档，你可以额外上传你关心的几条画像记忆实例的组合键及其类型，来让该次更新着重关注这几条画像记忆实例。（未确定其他未指定画像是否会受影响，暂未测试）
        一般来说暂时没必要使用这个高级用法，不传这个默认更新所有画像记忆实例。记住，这个只影响画像记忆。"""

    @field_validator('memory_type')
    def validate_memory_type(cls, v: list[str]) -> list[str]:
        """验证规则：且不能为空"""
        if not v:  # 空列表
            raise ValueError('memory_type 不能为空列表，请传入至少一项')
        return v


class MemoryConsumerConfig(BaseModel):
    """记忆消费者配置，负责召回"""
    # TODO: 后续扩展参数较多时，有必要将同类型的配置打包成子模型，profile 和 event 分别有自己的配置。目前比较扁平、散。暂时这样
    collection_id: CollectionID = Field(..., description="记忆库唯一标识 CollectionID（例如 CollectionID(collection_name='SGM')）")

    system_prompt_profile_types: list[str] | None = Field(
        default=None,
        description="以全量方式注入 system_prompt 的画像类型"
    )

    search_profile_types: list[str] | None = Field(
        default=None,
        description="可通过 search_profile（query 检索）消费的画像类型"
    )

    event_types: list[str] | None = Field(default=None, description="召回事件类型")

    # 拆开使用，因为画像记忆和事件记忆可能有不同的召回数量要求
    profile_limit: int = Field(default=10, description="召回画像记忆数量上限")

    event_limit: int = Field(default=10, description="召回事件记忆数量上限")

    @field_validator('system_prompt_profile_types', 'search_profile_types', 'event_types')
    def validate_non_empty_if_provided(cls, v: list[str] | None) -> list[str] | None:
        """验证规则：如果提供了列表字段，则不能是空列表。"""
        if v is not None and not v:
            raise ValueError("列表字段如果提供，不能为空列表")
        return v

    @model_validator(mode="after")
    def validate_consumption_required(self) -> "MemoryConsumerConfig":
        """至少要消费一种记忆：画像或事件不可同时都不消费。"""
        has_profile_consumption = bool(self.system_prompt_profile_types or self.search_profile_types)
        has_event_consumption = bool(self.event_types)
        if not has_profile_consumption and not has_event_consumption:
            raise ValueError(
                "记忆消费者配置非法：画像和事件记忆不能同时都不消费。"
                "可只消费事件记忆，也可只消费画像记忆。"
            )
        return self

class MemoryProducer:
    """记忆生产者。增量输入写入。"""

    def __init__(
        self,
        config: MemoryProducerConfig,
        user_info: UserInfoMetadata,
        session_size: int = 5,
    ):
        self.config = config
        self.user_info = user_info
        self.session_size = session_size
        self._buffer: list[tuple[HumanMessage, AIMessage]] = []
        self._total_handled: int = 0
        #: 最近一次 add_memory 随写携带的完整 system（含车况等），flush / 阈值落库时置于 messages 首部
        self._volc_system_context: str | None = None

    @property
    def pending_count(self) -> int:
        """缓冲区待处理轮数"""
        return len(self._buffer)

    @property
    def total_handled(self) -> int:
        """已处理的轮数"""
        return self._total_handled


    async def add_memory(
        self,
        delta: tuple[HumanMessage, AIMessage],
        *,
        system_context_for_volc: str | None = None,
        event_listeners: list[MemoryEventListener] | None = None,
    ) -> AsyncGenerator[MemoryEvent, None]:
        """
        增量输入一个对话 pair，返回事件流。
        
        Args:
            delta: 单个对话 pair (HumanMessage, AIMessage)
            system_context_for_volc: 若传入非 None，则更新本轮起用于火山落库的 system 快照
               （写入时在 user/assistant 序列前插一条 role=system），便于抽取侧利用车况等上下文。
            event_listeners: 事件监听器列表，用于 log/print 等旁路处理
        
        示例（window_size=3）：
        - 第1次调用：pending_count=1，不触发写入
        - 第2次调用：pending_count=2，不触发写入
        - 第3次调用：pending_count=3，触发写入，清空缓冲区
        - 第4次调用：pending_count=1，不触发写入
        ...
        """
        # 闭包：将事件监听器包装在 emit 函数中，确保在 yield 后调用
        # TODO: 其实可以不需要emit函数，不清楚怎么更好。暂时不重要
        def emit(event: MemoryEvent) -> MemoryEvent:
            for listener in event_listeners or []:
                listener(event)
            return event
        if system_context_for_volc is not None:
            s = str(system_context_for_volc).strip()
            self._volc_system_context = s if s else None
        # 进入缓冲区
        self._buffer.append(delta)
        # 缓冲区待处理轮数 >= 触发阈值时，触发写入
        if len(self._buffer) < self.session_size:
            # 返回缓冲区待处理轮数事件
            yield emit(MemoryAddPendingEvent(pending_count=len(self._buffer), session_size=self.session_size))            
            return
        # 触发写入，返回正在处理事件
        _core_pending = history_to_volcmessages(self._buffer)
        yield emit(
            MemoryAddProcessingEvent(
                processed_count=len(self._buffer),
                content=prepend_system_to_volcmessages(
                    self._volc_system_context, _core_pending
                ),
            )
        )

        try:
            # 转换为火山记忆平台要求的对话记录格式（首部附 system 供抽取）
            messages_volc = prepend_system_to_volcmessages(
                self._volc_system_context,
                history_to_volcmessages(list(self._buffer)),
            )
            session_id = await aadd_session(
                collection_id=self.config.collection_id,
                messages=messages_volc,
                session_id=None, # 记忆库默认会生成session_id
                metadata=self.user_info.create_session_metadata,
                extract_memory_type=self.config.memory_type,
                profiles=self.config.profiles,
            )
            # 累加已处理轮数
            self._total_handled += len(self._buffer)
            # 原地清空缓冲区
            self._buffer.clear()
            # 返回写入成功事件
            yield emit(MemoryAddCompletedEvent(
                session_id=session_id,
                processed_count=self.session_size,
                total_handled=self._total_handled,
            ))

        except Exception as e:
            yield emit(MemoryAddFailedEvent(
                error=str(e),
                pending_count=len(self._buffer),
            ))


    async def flush(self) -> bool:
        """
        强制提交缓冲区。返回是否成功。
        """
        if not self._buffer:
            return True  # 空缓冲区视为成功
        
        try:
            # TODO: 这里的部分是重复的代码，应该提取出来
            messages_volc = prepend_system_to_volcmessages(
                self._volc_system_context,
                history_to_volcmessages(list(self._buffer)),
            )
            await aadd_session(
                collection_id=self.config.collection_id,
                messages=messages_volc,
                session_id=None,
                metadata=self.user_info.create_session_metadata,
                extract_memory_type=self.config.memory_type,
                profiles=self.config.profiles,
            )
            self._total_handled += len(self._buffer)
            self._buffer.clear()
            return True

        except Exception:
            # 写入失败，返回 False
            return False


class MemoryConsumer:
    """记忆消费者。支持召回查询。"""

    def __init__(self, config: MemoryConsumerConfig, user_info: UserInfoMetadata):
        self.config = config
        self.user_info = user_info

    @property
    def has_skill_profile_type(self) -> bool:
        """search_profile_types 中是否包含特殊类型 skill。"""
        return bool(self.config.search_profile_types and SKILL_PROFILE_TYPE in self.config.search_profile_types)

    @property
    def non_skill_search_profile_types(self) -> list[str]:
        """除 skill 以外可用于通用画像搜索的类型。"""
        return [
            profile_type
            for profile_type in (self.config.search_profile_types or [])
            if profile_type != SKILL_PROFILE_TYPE
        ]

    def _resolve_profile_types(self, query: str | None) -> list[str]:
        """根据消费模式解析画像类型：
        - query is None: system_prompt 全量消费
        - query 非空: search_profile 消费
        """
        if query is None:
            configured = self.config.system_prompt_profile_types
        else:
            configured = self.config.search_profile_types
        return configured or []

    def _empty_profile_response(self) -> ProfileMemoryResponse:
        """在某消费模式未配置画像类型时，返回空结果而不是请求远端。"""
        return ProfileMemoryResponse(
            code=0,
            message="无画像记忆",
            request_id="",
            data=ProfileMemoryData(
                collection_name=self.config.collection_id.collection_name or "",
                count=0,
                result_list=[],
                token_usage=0,
            ),
        )

    def _empty_event_response(self) -> EventMemoryResponse:
        """在未配置事件类型时，返回空结果而不是请求远端。"""
        return EventMemoryResponse(
            code=0,
            message="无事件记忆",
            request_id="",
            data=EventMemoryData(
                collection_name=self.config.collection_id.collection_name or "",
                count=0,
                result_list=[],
                token_usage=0,
            ),
        )
        
    async def retrieve_profiles(
        self,
        query: str | None = None,
    ) -> ProfileMemoryResponse:
        """召回画像记忆"""
        profile_types = self._resolve_profile_types(query)
        if not profile_types:
            return self._empty_profile_response()

        try:
            return await asearch_profile_memory(
                collection_id=self.config.collection_id,
                profile_type=profile_types,
                user_id=self.user_info.user_id,
                query=query,
                assistant_id=self.user_info.assistant_id,
                limit=self.config.profile_limit,
            )
        except Exception as e:
            raise RuntimeError(f"召回画像记忆失败: {e}") from e

    async def retrieve_events(
        self,
        query: str | None = None,
    ) -> EventMemoryResponse:
        """召回事件记忆"""
        event_types = self.config.event_types
        if not event_types:
            return self._empty_event_response()

        try:
            return await asearch_event_memory(
                collection_id=self.config.collection_id,
                event_type=event_types,
                user_id=self.user_info.user_id,
                query=query,
                assistant_id=self.user_info.assistant_id,
                limit=self.config.event_limit,
            )
        except Exception as e:
            raise RuntimeError(f"召回事件记忆失败: {e}") from e

    def create_event_search_worker(self) -> Callable[..., Awaitable[EventSearchToolOutput]]:
        """创建事件搜索worker，供 MemoryConsumer 使用。

        Args:

        Returns:
            异步事件搜索worker函数，用于构建 event_search_tool
        """
        async def worker(start_time: str, end_time: str, limit: int = 10) -> EventSearchToolOutput:
            """事件搜索worker
            
            Args:
                start_time: 开始时间
                end_time: 结束时间
                limit: 返回的搜索结果数量
            
            Returns:
                EventSearchToolOutput: 事件搜索工具输出参数
            """
            # 获取必要记忆库配置信息
            collection_id = self.config.collection_id
            event_type = self.config.event_types
            user_id = self.user_info.user_id
            assistant_id = self.user_info.assistant_id
            group_id = self.user_info.group_id
            if not event_type:
                return EventSearchToolOutput(events=[], messages="无事件记忆")

            try:
                start_time_timestamp = int(datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
                end_time_timestamp = int(datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
            
                # 调用asearch_event_memory进行事件搜索
                response = await asearch_event_memory(
                    collection_id=collection_id,
                    event_type=event_type,
                    user_id=user_id,
                    query=None,  # 暂时不使用查询参数
                    assistant_id=assistant_id,
                    group_id=group_id,
                    start_time=start_time_timestamp,
                    end_time=end_time_timestamp,
                    session_id=None,  # 暂时不使用会话ID参数
                    limit=limit,
                    time_decay_weight=None,  # 暂时不使用时间衰减权重
                    no_decay_period=None,  # 暂时不使用无衰减时间周期
                    custom_weight=None  # 暂时不使用自定义权重
                )
            except Exception as e:
                return EventSearchToolOutput(events=[], messages=f"事件搜索失败: {e}")
            
            # 提取result_list并转换为EventItem列表
            event_items = [
                EventItem(**item.model_dump())
                for item in response.data.result_list
            ]

            # TODO：这个输出的内容过多，无关字段太多了，需要优化，暂时不急
            if not event_items:
                return EventSearchToolOutput(events=[], messages="没有找到符合的事件记忆")
            
            return EventSearchToolOutput(events=event_items, messages=f"检索到{len(event_items)}条事件记忆")
        
        return worker

    def create_profile_search_worker(self) -> Callable[..., Awaitable[ProfileSearchToolOutput]]:
        """创建画像搜索 worker，供 profile_search_tool 使用。"""

        async def worker(query: str, limit: int = 10) -> ProfileSearchToolOutput:
            """画像搜索 worker"""
            profile_types = self.non_skill_search_profile_types
            if not profile_types:
                return ProfileSearchToolOutput(profiles=[], messages="无可搜索的画像记忆")

            try:
                response = await asearch_profile_memory(
                    collection_id=self.config.collection_id,
                    profile_type=profile_types,
                    user_id=self.user_info.user_id,
                    query=query,
                    assistant_id=self.user_info.assistant_id,
                    group_id=self.user_info.group_id,
                    limit=limit,
                )
            except Exception as e:
                return ProfileSearchToolOutput(profiles=[], messages=f"画像搜索失败: {e}")

            profile_items = [
                ProfileItem(**item.model_dump())
                for item in response.data.result_list
            ]
            if not profile_items:
                return ProfileSearchToolOutput(profiles=[], messages="没有找到符合条件的画像记忆")

            return ProfileSearchToolOutput(profiles=profile_items, messages=f"检索到{len(profile_items)}条画像记忆")

        return worker

    def create_skill_search_worker(self) -> Callable[..., Awaitable[SkillSearchToolOutput]]:
        """创建 skill 搜索 worker，供 skill_search_tool 使用。"""

        async def worker(query: str, limit: int = 5) -> SkillSearchToolOutput:
            if not self.has_skill_profile_type:
                return SkillSearchToolOutput(skills=[], messages="无可任何skill")

            try:
                response = await asearch_profile_memory(
                    collection_id=self.config.collection_id,
                    profile_type=[SKILL_PROFILE_TYPE],
                    user_id=self.user_info.user_id,
                    query=query,
                    assistant_id=self.user_info.assistant_id,
                    group_id=self.user_info.group_id,
                    limit=limit,
                )
            except Exception as e:
                return SkillSearchToolOutput(skills=[], messages=f"skill搜索失败: {e}")

            skills: list[SkillItem] = []
            for item in response.data.result_list:
                memory_info = item.memory_info or {}
                skill_name = memory_info.get(SKILL_NAME_PRIMARY_KEY)
                if not isinstance(skill_name, str) or not skill_name:
                    # skill_name 是主键，缺失时跳过异常数据
                    continue
                skill_description = memory_info.get(SKILL_DESCRIPTION_KEY)
                skills.append(
                    SkillItem(
                        skill_name=skill_name,
                        skill_description=skill_description if isinstance(skill_description, str) else None,
                        score=item.score,
                    )
                )

            if not skills:
                return SkillSearchToolOutput(skills=[], messages="没有找到符合条件的skill记忆")

            return SkillSearchToolOutput(skills=skills, messages=f"检索到{len(skills)}条skill记忆")

        return worker

    async def _find_skill_by_name(self, skill_name: str):
        """按 skill_name 精确查询 skill。

        优先走 primary_key 过滤；若后端主键过滤偶发不命中，则降级为语义检索后本地精确匹配。
        """
        primary_key = f"{SKILL_NAME_PRIMARY_KEY}={skill_name}"
        response = await asearch_profile_memory(
            collection_id=self.config.collection_id,
            profile_type=[SKILL_PROFILE_TYPE],
            user_id=self.user_info.user_id,
            query=None,
            assistant_id=self.user_info.assistant_id,
            primary_key=primary_key,
            group_id=self.user_info.group_id,
            limit=1,
        )
        if response.data.result_list:
            return response.data.result_list[0]

        fallback_response = await asearch_profile_memory(
            collection_id=self.config.collection_id,
            profile_type=[SKILL_PROFILE_TYPE],
            user_id=self.user_info.user_id,
            query=skill_name,
            assistant_id=self.user_info.assistant_id,
            group_id=self.user_info.group_id,
            limit=20,
        )
        for item in fallback_response.data.result_list:
            memory_info = item.memory_info or {}
            raw_name = memory_info.get(SKILL_NAME_PRIMARY_KEY)
            if isinstance(raw_name, str) and raw_name == skill_name:
                return item
        return None

    def create_load_skill_worker(self) -> Callable[..., Awaitable[LoadSkillToolOutput]]:
        """创建 load skill worker，按 skill_name 精确加载 skill 完整信息。"""

        async def worker(skill_name: str) -> LoadSkillToolOutput:
            if not self.has_skill_profile_type:
                return LoadSkillToolOutput(skill=None, messages="无可加载的skill记忆")

            try:
                matched = await self._find_skill_by_name(skill_name)
            except Exception as e:
                return LoadSkillToolOutput(skill=None, messages=f"load skill失败: {e}")

            if matched is None:
                return LoadSkillToolOutput(skill=None, messages=f"未找到名为 {skill_name} 的skill")

            memory_info = matched.memory_info or {}
            raw_description = memory_info.get(SKILL_DESCRIPTION_KEY)
            raw_markdown = memory_info.get(SKILL_MARKDOWN_CONTENT_KEY)
            # 输出里带回的是「本次 load 之前」记忆里存的上次使用时间；随后在库里写入本次 load 的时刻。
            previous_last_used = normalize_skill_last_used_datetime(
                memory_info.get(SKILL_LAST_USED_DATETIME_KEY)
            )
            loaded = LoadedSkill(
                skill_name=skill_name,
                skill_description=raw_description if isinstance(raw_description, str) else None,
                skill_markdown_content=raw_markdown if isinstance(raw_markdown, str) else None,
                last_used_datetime=previous_last_used,
            )

            payload: dict[str, MemoryContentType] = dict(memory_info)
            payload[SKILL_NAME_PRIMARY_KEY] = skill_name
            payload[SKILL_LAST_USED_DATETIME_KEY] = skill_last_used_datetime_now()

            try:
                await aadd_custom_profile_memory(
                    collection_id=self.config.collection_id,
                    profile_type=SKILL_PROFILE_TYPE,
                    memory_content=payload,
                    user_id=self.user_info.user_id,
                    assistant_id=self.user_info.assistant_id,
                    group_id=self.user_info.group_id,
                    is_upsert=True,
                    keep_other_keys_content=False,
                )
            except Exception as e:
                return LoadSkillToolOutput(skill=None, messages=f"load skill更新时间失败: {e}")

            return LoadSkillToolOutput(skill=loaded, messages="加载成功")

        return worker

    def create_new_skill_worker(self) -> Callable[..., Awaitable[CreateNewSkillToolOutput]]:
        """创建新 skill 的 worker。"""

        async def worker(skill_name: str, skill_description: str, skill_markdown_content: str) -> CreateNewSkillToolOutput:
            if not self.has_skill_profile_type:
                return CreateNewSkillToolOutput(success=False, messages="当前未启用skill记忆消费")

            try:
                existed = await self._find_skill_by_name(skill_name)
            except Exception as e:
                return CreateNewSkillToolOutput(success=False, messages=f"创建前校验失败: {e}")

            if existed is not None:
                return CreateNewSkillToolOutput(success=False, messages=f"skill已存在，请改用update_skill: {skill_name}")

            payload: dict[str, MemoryContentType] = {
                SKILL_NAME_PRIMARY_KEY: skill_name,
                SKILL_DESCRIPTION_KEY: skill_description,
                SKILL_MARKDOWN_CONTENT_KEY: skill_markdown_content,
                SKILL_LAST_USED_DATETIME_KEY: "",
            }
            try:
                await aadd_custom_profile_memory(
                    collection_id=self.config.collection_id,
                    profile_type=SKILL_PROFILE_TYPE,
                    memory_content=payload,
                    user_id=self.user_info.user_id,
                    assistant_id=self.user_info.assistant_id,
                    group_id=self.user_info.group_id,
                    is_upsert=False,
                    keep_other_keys_content=False,
                )
            except Exception as e:
                return CreateNewSkillToolOutput(success=False, messages=f"创建skill失败: {e}")

            return CreateNewSkillToolOutput(success=True, messages=f"创建skill成功: {skill_name}")

        return worker

    def update_skill_worker(self) -> Callable[..., Awaitable[UpdateSkillToolOutput]]:
        """更新已有 skill 的 worker。"""

        async def worker(skill_name: str, skill_description: str, skill_markdown_content: str) -> UpdateSkillToolOutput:
            if not self.has_skill_profile_type:
                return UpdateSkillToolOutput(success=False, messages="当前未启用skill记忆消费")

            try:
                existed = await self._find_skill_by_name(skill_name)
            except Exception as e:
                return UpdateSkillToolOutput(success=False, messages=f"更新前校验失败: {e}")

            if existed is None:
                return UpdateSkillToolOutput(success=False, messages=f"skill不存在，无法更新: {skill_name}")

            # 从当前 skill 读回整包画像；仅改描述与 Markdown，其余（含 last_used_datetime）保持不变。
            # keep_other_keys_content=False 表示不靠 SDK 再拉「profile 搜索结果首条」做键合并（多 skill 时易串行）；
            # 本条 payload 已是本条 skill 的全量 dict，不会因 False 而丢弃未在本次出现的字段。
            payload: dict[str, MemoryContentType] = dict(existed.memory_info or {})
            payload[SKILL_DESCRIPTION_KEY] = skill_description
            payload[SKILL_MARKDOWN_CONTENT_KEY] = skill_markdown_content
            try:
                await aadd_custom_profile_memory(
                    collection_id=self.config.collection_id,
                    profile_type=SKILL_PROFILE_TYPE,
                    memory_content=payload,
                    user_id=self.user_info.user_id,
                    assistant_id=self.user_info.assistant_id,
                    group_id=self.user_info.group_id,
                    is_upsert=True,
                    keep_other_keys_content=False,
                )
            except Exception as e:
                return UpdateSkillToolOutput(success=False, messages=f"更新skill失败: {e}")

            return UpdateSkillToolOutput(success=True, messages=f"更新skill成功: {skill_name}")

        return worker

    async def remediation(self, *, limit: int = 5000) -> str:
        """生成供 Agent 做 skill 合并/清理治理的「一段说明 + 全量 skill 清单」长文本。

        从画像侧拉取当前用户下全部 `skills` 类型条目，汇总每条：
        skill_name、description、memory_info 中的 last_used_datetime，
        以及检索结果元素上的 `time`（毫秒）换算成的 last_updated_time（年月日时分秒）。
        再与 skill 治理任务说明及 SKILL_GOVERNANCE_PROMPT 拼接，便于作为用户消息或伪 skill 正文交给模型。
        """
        if not self.has_skill_profile_type:
            return (
                "当前 MemoryConsumer 未在 search_profile_types 中启用 `skills`，"
                "无法生成 skill 治理简报。"
            )

        cap = min(max(limit, 1), 5000)
        try:
            response = await asearch_profile_memory(
                collection_id=self.config.collection_id,
                profile_type=[SKILL_PROFILE_TYPE],
                user_id=self.user_info.user_id,
                query=None,
                assistant_id=self.user_info.assistant_id,
                group_id=self.user_info.group_id,
                limit=cap,
            )
        except Exception as e:
            return f"拉取全部 skill 画像失败，无法生成治理简报: {e}"

        rows_raw: list[tuple[int, dict[str, object]]] = []
        for item in response.data.result_list:
            mi_any: dict[str, MemoryContentType] = item.memory_info or {}
            name_val = mi_any.get(SKILL_NAME_PRIMARY_KEY)
            if not isinstance(name_val, str) or not name_val.strip():
                continue
            desc_val = mi_any.get(SKILL_DESCRIPTION_KEY)
            description = desc_val if isinstance(desc_val, str) else ("" if desc_val is None else str(desc_val))
            last_used_raw = mi_any.get(SKILL_LAST_USED_DATETIME_KEY, "")
            last_used = normalize_skill_last_used_datetime(
                last_used_raw if isinstance(last_used_raw, str) else str(last_used_raw)
            )
            ts_ms = int(item.time)
            rows_raw.append(
                (
                    ts_ms,
                    {
                        "skill_name": name_val.strip(),
                        "description": description,
                        "last_used_datetime": last_used,
                        "last_updated_time": profile_memory_time_ms_to_datetime_str(ts_ms),
                    },
                )
            )
        rows_raw.sort(key=lambda x: x[0], reverse=True)

        lines: list[str] = []
        lines.append("# Skill 记忆治理快照（全量清单）")
        lines.append("")
        lines.append(
            f"- 记忆库 collection: `{self.config.collection_id.collection_name}`\n"
            f"- user_id: `{self.user_info.user_id}`\n"
            f"- 本次检索命中 **{len(rows_raw)}** 条有效 skill（请求 limit={cap}，接口最多 5000）"
        )
        lines.append("")
        if not rows_raw:
            lines.append("*（未解析到任何带 skill_name 的条目。）*")
            lines.append("")
        else:
            for i, (_, row) in enumerate(rows_raw, start=1):
                lines.append(f"## {i}. `{row['skill_name']}`")
                lines.append("")
                lines.append(f"- **description**: {row['description'] if row['description'] else '（空）'}")
                lines.append(
                    f"- **last_used_datetime**（来自画像字段，已为 load 语义规范化）: "
                    f"`{row['last_used_datetime']}`"
                )
                lines.append(
                    f"- **last_updated_time**（来自检索项 time 毫秒戳 → 本地时区换算）: "
                    f"`{row['last_updated_time']}`"
                )
                lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Skill 治理任务说明")
        lines.append("")
        lines.append(SKILL_REMEDIATION_TASK_PROMPT.strip())
        lines.append("")
        lines.append("## Skill 工具使用与沉淀原则（与 Agent 系统注入对齐）")
        lines.append("")
        lines.append(SKILL_GOVERNANCE_PROMPT)
        lines.append("")
        return "\n".join(lines)

