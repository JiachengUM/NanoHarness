from typing import Sequence

from pydantic import BaseModel, Field

from nanoai.utils.nl_repr import nl_repr

from projects.mind.intent.intent_data.category import IntentCategoryLike

__all__ = [
    "IntentClsPrompt",
]


class IntentClsPrompt(BaseModel):
    '''
    意图分类提示。作为system prompt而不是user prompt。
    不能简单的用string template来表示，需要更为复杂的定制化实现。
    '''
    categories: Sequence[IntentCategoryLike] = Field(..., title="各种意图类别", description="各种意图类别")

    expert_role: str = Field(default="用户意图分类专家", title="专家角色", description="意图分类专家角色")

    output_hint: str = Field(default="仅返回类别名称, 不包括任何其它内容。", title="输出提示", description="意图分类输出提示")

    def render(self) -> str:
        '''
        TODO
        '''

        prompt = f"你是{self.expert_role}，需要根据用户的话判断其意图类别。请从以下类别中选择:"
        category_str = nl_repr(self.categories)
        prompt += category_str
        prompt += f"\n输出格式:{self.output_hint}"

        return prompt
