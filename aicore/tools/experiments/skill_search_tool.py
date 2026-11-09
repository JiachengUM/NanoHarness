"""
skill 记忆搜索工具，根据 query 召回最匹配的 skill
"""
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import TaskToolType, create_tool


class SkillSearchToolInput(BaseModel):
    """skill 搜索工具输入参数"""

    query: str = Field(
        ...,
        description="用于匹配最合适 skill 的查询语句，例如：我需要一个能按我的习惯导航的技能。",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="返回 skill 数量上限，默认 5，范围 [1, 50]。",
    )


class SkillItem(BaseModel):
    """skill 记忆结构"""

    skill_name: str = Field(..., description="skill 名称（主键）")
    skill_description: str | None = Field(default=None, description="skill 描述")
    score: float | None = Field(default=None, description="匹配分数")


class SkillSearchToolOutput(BaseModel):
    """skill 搜索输出"""

    skills: list[SkillItem] = Field(..., description="匹配到的 skill 列表")
    messages: str | None = Field(default=None, description="提示信息或错误信息")


SkillSearchToolOutputLike = SkillSearchToolOutput | str
SkillSearchWorker = Callable[..., Awaitable[SkillSearchToolOutputLike]]


def skill_search_tool(
    worker: SkillSearchWorker,
) -> TaskToolType[SkillSearchToolInput, SkillSearchToolOutputLike, None, ...]:
    """skill 搜索工具"""
    return create_tool(
        name="skill搜索工具",
        description="根据 query 检索最合适的 skill，返回 skill_name 和 skill_description（可返回多条）。很多时候你觉得可能需要查看一些过往处理问题的经验时就使用这个工具看看有没有合适的skill可以参考。",
        args_schema=SkillSearchToolInput,
        worker=worker,
    )
