"""
创建新的 skill 记忆工具
"""
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import TaskToolType, create_tool


class CreateNewSkillToolInput(BaseModel):
    """create new skill 工具输入"""

    skill_name: str = Field(..., description="新 skill 的唯一名称（主键）。")
    skill_description: str = Field(..., description="skill 的简要描述，说明适用场景和价值。")
    skill_markdown_content: str = Field(..., description="skill 的完整 markdown 内容，包含步骤、注意事项、边界条件。")


class CreateNewSkillToolOutput(BaseModel):
    """create new skill 工具输出"""

    success: bool = Field(..., description="是否创建成功。")
    messages: str = Field(..., description="执行结果说明。")


CreateNewSkillToolOutputLike = CreateNewSkillToolOutput | str
CreateNewSkillWorker = Callable[..., Awaitable[CreateNewSkillToolOutputLike]]


def create_new_skill_tool(
    worker: CreateNewSkillWorker,
) -> TaskToolType[CreateNewSkillToolInput, CreateNewSkillToolOutputLike, None, ...]:
    """create new skill 工具"""
    return create_tool(
        name="create_new_skill工具",
        description="""创建新skill的工具，用于创建一个新的skill，里面保存你过往执行某些任务时沉淀下来的很有价值的经验和方法。
                        但是使用本工具前你必须严格遵循以下规则：
                        - 创建新的skill前，你必须先使用skill搜索工具，检查是否已存在类似的skill！避免创建大量重复或类似的skill。
                        - skill_name 必须是唯一的，不能与已存在的 skill 重复。
                        - skill_description 必须简洁、清晰，能准确描述 skill 的功能和价值。
                        - skill_markdown_content 必须包含完整的步骤、注意事项、边界条件等，
                           并按照 markdown 格式编写，确保可读性。
                        - 不要动不动就创建skill，只有一个任务需要很多步骤/有一定难度/特别重要/经常出现时，才值得你去沉淀成一个skill。
                        - 得到了用户相对明确的成功反馈后，你才能确认之前为止的步骤是成功的，从而是可能可以创建skill来沉淀下来的。注意只是可能可以，因为有上一条的限制。
                        - 有些时候用户虽然没有明确的成功反馈，那此时你可以凭借你老练的判断能力和经验自行判断是否之前的步骤是成功的。比如你一通操作后，用户没说话，也可能是成功的，因为如果用户不满意那么他会吐槽。
                        """,
        args_schema=CreateNewSkillToolInput,
        worker=worker,
    )
