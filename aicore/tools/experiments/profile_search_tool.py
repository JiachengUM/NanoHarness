"""
画像搜索工具，按 query 检索用户画像记忆
"""
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import TaskToolType, create_tool

MemoryContentType = str | list[str] | int | list[int] | float | bool | None


class ProfileSearchToolInput(BaseModel):
    """画像搜索工具输入参数"""

    query: str = Field(
        ...,
        description="你需要检索用户画像时必须提供的查询语句，例如：用户喜欢什么音乐、用户住在哪里。",
    )
    limit: int = Field(
        default=10,
        le=5000,
        ge=1,
        description="返回搜索结果数量上限。默认值为 10，允许范围 [1, 5000]。",
    )


class ProfileItem(BaseModel):
    """画像记忆检索结果列表元素"""

    id: str = Field(..., description="记忆条目（画像实例）的唯一ID。")
    score: float | None = Field(default=None, description="记忆匹配度分数，范围 [0, 1]。")
    memory_type: str = Field(..., description="画像记忆类型。")
    user_id: list[str] = Field(..., description="用户ID列表。")
    assistant_id: list[str] = Field(..., description="助手ID列表。")
    group_id: str | None = Field(default=None, description="群组ID，可能为空。")
    time: int = Field(..., description="记忆时间，毫秒时间戳。")
    status: str | None = Field(default=None, description="记忆状态，可能为空。")
    labels: str | None = Field(default=None, description="记忆标签，可能为空。")
    memory_info: dict[str, MemoryContentType] = Field(..., description="画像详细内容。")


class ProfileSearchToolOutput(BaseModel):
    """画像搜索工具输出参数"""

    profiles: list[ProfileItem] = Field(..., description="画像记忆结果列表")
    messages: str | None = Field(default=None, description="报错信息以及提示信息。")


ProfileSearchToolOutputLike = ProfileSearchToolOutput | str

ProfileSearchWorker = Callable[..., Awaitable[ProfileSearchToolOutputLike]]


def profile_search_tool(
    worker: ProfileSearchWorker,
) -> TaskToolType[ProfileSearchToolInput, ProfileSearchToolOutputLike, None, ...]:
    """画像搜索工具"""

    return create_tool(
        name="画像搜索工具",
        description="根据query检索用户画像记忆，适用于查询用户偏好、习惯、背景信息。",
        args_schema=ProfileSearchToolInput,
        worker=worker,
    )
