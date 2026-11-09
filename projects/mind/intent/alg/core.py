from typing import Any, Sequence, override

import asyncio


from nanoai.model.llm import allm_output_by_schema, AsyncOpenAI
from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.data_concept import ClsResult
from nanoai.model.config import ModelName, create_client

from projects.mind.intent.alg.base import IntentClassifierBase
from projects.mind.intent.alg.prompt import IntentClsPrompt, IntentCategoryLike
from projects.mind.intent.task_data.message import Message

__all__ = [
    "_intent_cls",
    "IntentClassifierLLM",
]

async def _intent_cls(
    prompt: IntentClsPrompt,
    query: str,
    messages: list[Message] | None = None,
    *,
    model: str,
    client: AsyncOpenAI,
    **llm_params: Any,
) -> tuple[ClsResult, tuple[str, str]]:
    """意图分类函数，返回结构化分类结果。
    
    Args:
        query: 用户输入的查询文本
        prompt: 意图分类提示配置
        client: OpenAI 客户端
        sys_prompt_extra: 可选的额外系统提示（如历史对话），会追加到基础提示后
        **llm_params: LLM 参数（必须包含 model，以及其他参数如 temperature 等）
        
    Returns:
        tuple[ClsResult, tuple[str, str]]: 包含分类结果和(原始查询, 系统提示)的元组
    """
    # 构建系统提示
    sys_prompt = prompt.render()

    if messages:
        # messages进入user prompt而不是system prompt。
        # TODO: 将来可能正式引入messages参数输入到llm。
        query = f"对话消息历史: {nl_repr(messages, use_numbering=False)}\n用户当前消息: {query}"

    response = await allm_output_by_schema(
        query,
        sys_prompt,
        output_type=ClsResult,
        model=model,
        client=client,
        **llm_params,
    )

    result = response.output
    assert isinstance(result, ClsResult)
    return result, (query, sys_prompt)


class IntentClassifierLLM:
    """意图分类算法基类。
    目前只是关于param的wrapper。以后会逐渐增加通用功能。
    """

    def __init__(
        self, 
        prompt_or_category: IntentClsPrompt | Sequence[IntentCategoryLike],
        /,
        *, 
        model: ModelName,
        llm_params: dict[str, Any] | None = None
    ) -> None:
        """初始化意图分类器。
        
        Args:
            prompt_or_category: 意图分类提示配置或类别列表
            model: 用于分类的模型名称
            llm_params: 可选的 LLM 参数（如 temperature 等）
        """

        if isinstance(prompt_or_category, IntentClsPrompt):
            self.prompt = prompt_or_category
        else:
            self.prompt = IntentClsPrompt(categories=prompt_or_category)

        self.client, self.model = create_client(model, client_class=AsyncOpenAI)
        self.llm_params = llm_params or {}


    def run(self, prompt: str, messages: list[Message] | None = None) -> tuple[str, Any]:
        #res, prompts = syncify(self._run_cls)(prompt)
        res, prompts = asyncio.run(self._run_cls(prompt, messages))
        
        return res.category, res.reason


    async def _run_cls(
        self,
        query: str,
        messages: list[Message] | None = None,
    ) -> tuple[ClsResult, tuple[str, str]]:
        """执行意图分类，返回分类结果。
        
        Args:
            query: 用户输入的查询文本
            history: 可选的历史对话列表，用于指代补全
            
        Returns:
            ClsResult: 包含类别名称和判断原因的分类结果
        """
        
        return await _intent_cls(
            self.prompt,
            query,
            messages,
            model=self.model,
            client=self.client,
            **self.llm_params,
        )