"""
按 skill_name 精确加载单个 skill 的完整信息
"""
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import TaskToolType, create_tool


class LoadSkillToolInput(BaseModel):
    """load skill 工具输入参数"""

    skill_name: str = Field(..., description="要加载的 skill 主键 skill_name。")


class LoadedSkill(BaseModel):
    """完整 skill 信息"""

    skill_name: str = Field(..., description="skill 名称（主键）")
    skill_description: str | None = Field(default=None, description="skill 描述")
    skill_markdown_content: str | None = Field(default=None, description="skill markdown 内容")
    last_used_datetime: str = Field(
        default="",
        description=(
            "本次 load 之前记忆库里记录的 last_used_datetime（已规范为 %Y-%m-%d %H:%M:%S），"
            "不含本次调用；从未被 load 过或字段为空则为空字符串。本次 load 成功后记忆库会更新为当前时间。"
        ),
    )


class LoadSkillToolOutput(BaseModel):
    """load skill 输出"""

    skill: LoadedSkill | None = Field(default=None, description="skill 完整信息")
    messages: str | None = Field(default=None, description="提示信息或错误信息")


LoadSkillToolOutputLike = LoadSkillToolOutput | str
LoadSkillWorker = Callable[..., Awaitable[LoadSkillToolOutputLike]]


def load_skill_tool(
    worker: LoadSkillWorker,
) -> TaskToolType[LoadSkillToolInput, LoadSkillToolOutputLike, None, ...]:
    """load skill 工具"""
    return create_tool(
        name="load_skill工具",
        description="根据 skill_name 精确加载单个 skill 的完整信息（含 skill_markdown_content）。注意！！只有当且仅当你确定这个skill_name是必然存在的时候才调用这个工具来加载！一般来说你可能需要先根据你的需要搜索一些相关的skill，然后根据搜索结果来确定是否需要加载某个skill。",
        args_schema=LoadSkillToolInput,
        worker=worker,
    )
