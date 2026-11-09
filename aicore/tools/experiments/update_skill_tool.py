"""
更新已有 skill 记忆工具
"""
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import TaskToolType, create_tool


class UpdateSkillToolInput(BaseModel):
    """update skill 工具输入"""

    skill_name: str = Field(..., description="要更新的 skill 名称（主键，必须已存在）。")
    skill_description: str = Field(..., description="更新后的 skill 描述。")
    skill_markdown_content: str = Field(..., description="更新后的完整 skill markdown 内容。")


class UpdateSkillToolOutput(BaseModel):
    """update skill 工具输出"""

    success: bool = Field(..., description="是否更新成功。")
    messages: str = Field(..., description="执行结果说明。")


UpdateSkillToolOutputLike = UpdateSkillToolOutput | str
UpdateSkillWorker = Callable[..., Awaitable[UpdateSkillToolOutputLike]]


def update_skill_tool(
    worker: UpdateSkillWorker,
) -> TaskToolType[UpdateSkillToolInput, UpdateSkillToolOutputLike, None, ...]:
    """update skill 工具"""
    return create_tool(
        name="update_skill工具",
        description=(
            "更新已有 skill 记忆。"
            "何时使用：你在实际执行中发现当前 skill 有可改进点（步骤更优、边界更清晰、失败处理更完善）时。"
            "要求：skill_name 必须是记忆库里已存在的 skill 主键；若不存在，不应更新。"
            "更新内容应保持可复用性，明确改进点与适用条件。"
        ),
        args_schema=UpdateSkillToolInput,
        worker=worker,
    )
