"""
简单实用的意图分类器。基于responses API实现。和core不同。
"""

from typing import Any, Sequence, override

import asyncio

from aicore.models.responses import system_msg, user_msg, ResponseParams, ainvoke, AsyncArk
from aicore.utils.nl_repr import nl_repr

from projects.mind.intent.alg.base import IntentClassifierBase
from projects.mind.intent.alg.prompt import IntentCategoryLike


__all__ = [
    "IntentClassifierLLM",
]    


class IntentClassifierLLM(IntentClassifierBase):
    """意图分类算法基类。
    目前只是关于param的wrapper。以后会逐渐增加通用功能。
    """

    def __init__(
        self, 
        categories: Sequence[IntentCategoryLike],
        /,
        *, 
        client: AsyncArk,
        model: str,
        params: ResponseParams | None = None,
        llm_params: dict[str, Any] | None = None,
    ) -> None:
        """初始化意图分类器。
        """
        self.categories = categories
        self.client  = client
        self.model =  model
        self.params = params
        self.llm_params = llm_params or {}


    @property
    def cls_prompt(self) -> str:
        # TODO: 提供cache和更新机制。不用每次计算。
        prompt = "你需要根据用户的话判断其意图类别。请从以下类别中选择:"
        prompt += nl_repr(self.categories)
        prompt += "\n仅返回类别名称, 不包括任何其它内容。"

        return prompt


    @override
    def run(self, query: str, /,) -> tuple[str, Any]:
        raise NotImplementedError("IntentClassifierLLM.run is not implemented. Use arun instead.")
        # TODO: 必须用syncify替代, 还不work。不知道为何。
        return asyncio.run(self.arun(query))


    @override
    async def arun(self, query: str, /,) -> tuple[str, Any]:

        response = await ainvoke(
            [system_msg(self.cls_prompt), user_msg(query)],
            model=self.model,
            client=self.client,
            params=self.params,
            **self.llm_params,
        )

        result = response.raw_text

        return result, {"query": query, "sys_prompt": self.cls_prompt, "response": response}
