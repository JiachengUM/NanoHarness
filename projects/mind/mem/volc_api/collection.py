from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from projects.mind.mem.volc_api._api import request
from projects.mind.mem.volc_api.event import EventTypeSchema
from projects.mind.mem.volc_api.profile import ProfileTypeSchema

__all__ = [
    "CollectionCreate",
    "create_collection",

    "CollectionManagementCollectionID",
    "CollectionUpdate",
    "update_collection",

    "CollectionInfo",
    "get_collection_info",
    
    "delete_collection",
    "list_collections",
]


class Tag(BaseModel):
    Key: str = Field(..., description="标签的键。")
    Value: str = Field(..., description="标签的值。")


class CollectionTypeEnum(StrEnum):
    STANDARD = "standard"
    ULTIMATE = "ultimate"

class CollectionModelTypeEnum(StrEnum):
    TEXT = "text"
    MULTIMODAL = "multimodal"

class LlmExtractConfigType(BaseModel):
    BuiltinEventTypes: list[str] = Field(default=["sys_event_v1"], description="内置事件类型列表，如 ['sys_event_v1'] 表示使用系统内置的事件类型")

    BuiltinProfileTypes: list[str] = Field(default=["sys_profile_v1"], description="内置画像类型列表，如 ['sys_profile_v1'] 表示使用系统内置的画像类型")

    CustomEventTypeSchemas: list[EventTypeSchema] = Field(default_factory=list, description="根据业务需求自定义的事件类型列表。")

    CustomProfileTypeSchemas: list[ProfileTypeSchema] = Field(default_factory=list, description="用户自定义的画像类型模式列表。")

    Tags: list[Tag] = Field(default_factory=list, description="标签列表，用于资源管理和分账。")


class CollectionCreate(LlmExtractConfigType):
    CollectionName: str = Field(..., description="记忆库名称，必须唯一")

    ProjectName: str= Field(default="default", description="项目名称，默认为 'default'")

    CollectionType: CollectionTypeEnum = Field(default=CollectionTypeEnum.ULTIMATE, description="记忆库类型，可选值包括 ['standard', 'ultimate']")

    CollectionModelType: CollectionModelTypeEnum = Field(default=CollectionModelTypeEnum.TEXT, description="记忆库模型类型，可选值包括 ['text', 'multimodal']")

    Description: str | None = Field(default=None, description="记忆库描述信息")

    CpuQuota: int = Field(default=1, description="CPU 配额，单位为核，范围为 [1, 100]")


def create_collection(c: CollectionCreate | str) -> str:
    """
    创建新的记忆库（Collection）,返回唯一的resource_id
    
    功能说明：
        创建一个新的记忆库，用于存储和管理用户记忆数据。
        记忆库定义了可以存储的事件类型（Event Types）和画像类型（Profile Types）。
    
    使用场景：
        - 首次使用 Memory API 时需要创建记忆库
        - 为不同业务场景创建独立的记忆库
    """

    path = "/api/memory/collection/create"

    if isinstance(c, str):
        c = CollectionCreate(CollectionName=c)
    
    assert isinstance(c, CollectionCreate)

    try:
        rsp = request("POST", path, c.model_dump(exclude_none=True))
        assert isinstance(rsp.data, dict)
        return rsp.data["ResourceId"]
    except Exception as e:
        raise Exception(f"创建记忆库失败: {str(e)}")


class CollectionManagementCollectionID(BaseModel):
    """
    记忆库唯一标识符.
    通过resource_id唯一指定的资源id, 
    或者同时声明collection_name和project_name
    """

    CollectionName: str | None = Field(default=None, description="记忆库名称")

    ProjectName: str | None = Field(default="default", description="项目名称，默认为 'default'")

    ResourceId: str | None = Field(default=None, description="记忆库唯一的资源 id。")

    @model_validator(mode="after")
    def check_collection_id(self):
        """校验记忆库唯一标识符"""
        if not self.ResourceId and not (self.CollectionName and self.ProjectName):
            raise ValueError("必须提供 ResourceId 或同时提供 CollectionName 和 ProjectName")

        return self


class CollectionUpdate(CollectionManagementCollectionID, LlmExtractConfigType):
    """更新记忆库配置的模型
    
    注意：更新记忆库时，必须带上全部配置，否则会被覆盖。
    CollectionType, CollectionModelType, EventType, ProfileType, EnableAssistantIsolation 不可编辑。
    """
    CpuQuota: int = Field(default=1, description="CPU 配额，单位为核，范围为 [1, 100]")


def update_collection(c: CollectionUpdate):
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
    return request("POST", path, c.model_dump(exclude_none=True))


class PipelineConfigType(BaseModel):
    CpuQuota: int = Field(..., description="消耗资源的CPU配额，范围[1,100]。")

    LlmExtractConfig: LlmExtractConfigType = Field(..., description="LLM 提取配置")


class CollectionInfo(BaseModel):
    """记忆库的详细配置信息。"""

    CollectionType: CollectionTypeEnum = Field(..., description="记忆库类型，标准版/旗舰版。")

    CollectionModalType: str = Field(default="", description="记忆库的模态类型，纯文本/多模态。")

    CreatedAt: str = Field(..., description="记忆库创建时间，例如\"2025-06-03T06:35:32\"。")

    CreatedBy: str = Field(..., description="记忆库创建者。")

    DescMsg: str = Field(..., description="记忆库描述信息，例如\"用于记录和分析学生英语学习过程的记忆库\"。")

    PipelineConfig: PipelineConfigType = Field(..., description="管道配置信息。")

    Name: str = Field(..., description="记忆库名称，例如\"english_learning_memory\"。")

    Project: str = Field(..., description="项目名称，例如\"default\"。")

    ResourceId: str = Field(..., description="资源唯一标识符。")

    UpdatedAt: str = Field(..., description="最后更新时间，例如\"2025-06-03T06:35:32\"。")

    EventCount: int = Field(..., description="当前collection事件记忆数量")
    
    ProfileCount: int = Field(..., description="当前collection画像记忆数量")

    CollectionStatus: str = Field(..., description="记忆库状态")


def get_collection_info(c: CollectionManagementCollectionID) -> CollectionInfo:
    """查询记忆库详细信息"""
    path = "/api/memory/collection/info"
    rsp = request("POST", path, c.model_dump(exclude_none=True))

    if rsp.success:
        assert isinstance(rsp.data, dict)
        return CollectionInfo(**rsp.data)
    else:
        raise ValueError


def delete_collection(c: CollectionManagementCollectionID):
    """删除记忆库. """
    path = "/api/memory/collection/delete"
    return request("POST", path, c.model_dump(exclude_none=True))


def list_collections(ProjectName: str | None = None):
    """
    列出记忆库列表
    """
    path = "/api/memory/collection/list"

    payload: dict = {}
    if ProjectName:
        payload = {"ProjectName": ProjectName}
        
    return request("POST", path, payload)
