'''
对于火山记忆库API 记忆库部分的结构化封装  https://www.volcengine.com/docs/84313/1783347?lang=zh
'''

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

from mvms.volc_mem.common.client import internal_request


__all__ = [
    "EventProperty",
    "EventTypeSchema",
    "ProfileProperty",
    "ProfileTypeSchema",
    "Collection",
    "UpdateCollection",
    "create_collection",
    "update_collection",
    "get_collection_info",
    "CollectionInfo",
    "CollectionDelete",
    "CollectionList",
    "delete_collection",
    "list_collections",
]


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


class ProfileProperty(BaseModel):
    PropertyName: str = Field(..., description="属性名称，例如 user_id, total_interactions。")

    PropertyValueType: str = Field(..., description="属性值的类型，可选值包括 ['int64', 'list<int64>', 'string', 'list<string>', 'float32', 'bool']")

    Description: str = Field(..., description="属性的详细描述，最多 10000 个字符。")

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


class Tag(BaseModel):
    Key: str = Field(..., description="标签的键。")
    Value: str = Field(..., description="标签的值。")


class Collection(BaseModel):
    CollectionName: str = Field(..., description="记忆库名称，必须唯一")

    ProjectName: str= Field(default="default", description="项目名称，默认为 'default'")

    CollectionType: str = Field(default="ultimate", description="记忆库类型，可选值包括 ['standard', 'ultimate']")

    CpuQuota: int = Field(default=1, description="CPU 配额，单位为核，范围为 [1, 100]")

    CollectionModelType: str = Field(default="text", description="记忆库模型类型，可选值包括 ['text', 'multimodal']")

    Description: str | None = Field(default=None, description="记忆库描述信息")

    BuiltinEventTypes: list[str] = Field(..., description="内置事件类型列表，如 ['sys_event_v1'] 表示使用系统内置的事件类型")

    BuiltinProfileTypes: list[str] = Field(..., description="内置画像类型列表，如 ['sys_profile_v1'] 表示使用系统内置的画像类型")

    CustomEventTypeSchemas: list[EventTypeSchema] = Field(default_factory=list, description="根据业务需求自定义的事件类型列表。")

    CustomProfileTypeSchemas: list[ProfileTypeSchema] = Field(default_factory=list, description="用户自定义的画像类型模式列表。")

    Tags: list[Tag] = Field(default_factory=list, description="标签列表，用于资源管理和分账。")


class UpdateCollection(BaseModel):
    """更新记忆库配置的模型
    
    注意：更新记忆库时，必须带上全部配置，否则会被覆盖。
    CollectionType, CollectionModelType, EventType, ProfileType, EnableAssistantIsolation 不可编辑。
    """
    CollectionName: str | None = Field(default=None, description="要更新的记忆库的唯一名称。")

    ProjectName: str= Field(default="default", description="项目名称，默认为 'default'")

    ResourceId: str | None = Field(default=None, description="资源 ID。唯一标识符。")

    BuiltinEventTypes: list[str] = Field(default_factory=list, description="新的内置事件类型名称列表。提供此字段会覆盖现有的内置事件类型。")

    BuiltinProfileTypes: list[str] = Field(default_factory=list, description="新的内置画像类型名称列表。提供此字段会覆盖现有的内置画像类型。")

    CustomEventTypeSchemas: list[EventTypeSchema] = Field(default_factory=list, description="新的自定义事件类型模式列表。提供此字段会覆盖现有的自定义事件类型。")

    CustomProfileTypeSchemas: list[ProfileTypeSchema] = Field(default_factory=list, description="新的自定义画像类型模式列表。提供此字段会覆盖现有的自定义画像类型。")

    CpuQuota: int = Field(default=1, description="创建时默认为1核,可支撑100qps。范围[1,100]。")

    Tags: list[Tag] = Field(default_factory=list, description="标签列表，用于资源管理和分账。")


class CollectionInfo(BaseModel):
    CollectionName: str | None = Field(default=None, description="记忆库名称")

    ProjectName: str = Field(default="default", description="项目名称，默认为 'default'")

    ResourceId: str | None = Field(default=None, description="记忆库唯一的资源 id。可选择直接传 resource_id, 或同时传 collection_name 和 project_name")


class CollectionDelete(BaseModel):
    CollectionName: str | None = Field(default=None, description="记忆库名称")

    ProjectName: str = Field(default="default", description="项目名称，默认为 'default'")

    ResourceId: str | None = Field(default=None, description="记忆库唯一的资源 id。可选择直接传 resource_id, 或同时传 collection_name 和 project_name")


class CollectionList(BaseModel): 
    ProjectName: str = Field(default="default", description="项目名称，默认为 'default'")


def create_collection(c: Collection):
    """
    创建新的记忆库（Collection）
    
    功能说明：
        创建一个新的记忆库，用于存储和管理用户记忆数据。
        记忆库定义了可以存储的事件类型（Event Types）和画像类型（Profile Types）。
    
    参数说明：
        - CollectionName: 记忆库名称，必须唯一
        - Description: 记忆库描述信息
        - BuiltinEventTypes: 内置事件类型列表，如 ["sys_event_v1"] 表示使用系统内置的事件类型
        - BuiltinProfileTypes: 内置画像类型列表，如 ["sys_profile_v1"] 表示使用系统内置的画像类型
    
    使用场景：
        - 首次使用 Memory API 时需要创建记忆库
        - 为不同业务场景创建独立的记忆库
    """

    path = "/api/memory/collection/create"
    return internal_request("POST", path, c.model_dump(exclude_none=True))


def update_collection(c: UpdateCollection):
    """
    更新记忆库配置
    
    功能说明：
        更新已存在的记忆库配置，可以修改描述信息、添加自定义事件类型（CustomEventTypeSchemas）
        或自定义画像类型（CustomProfileTypeSchemas）。

    使用场景：
        - 需要添加业务特定的自定义事件类型
        - 需要修改记忆库描述信息
        - 需要更新内置事件类型或画像类型列表
    """
    path = "/api/memory/collection/update"
    return internal_request("POST", path, c.model_dump(exclude_none=True))


def get_collection_info(c: CollectionInfo):
    """
    查询记忆库详细信息
    """
    path = "/api/memory/collection/info"
    return internal_request("POST", path, c.model_dump(exclude_none=True))


def delete_collection(c: CollectionDelete):
    """
    删除记忆库
    """
    path = "/api/memory/collection/delete"
    return internal_request("POST", path, c.model_dump(exclude_none=True))


def list_collections(c: CollectionList):
    """
    列出记忆库
    """
    path = "/api/memory/collection/list"
    return internal_request("POST", path, c.model_dump(exclude_none=True))