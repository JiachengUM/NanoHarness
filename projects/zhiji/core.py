from __future__ import annotations

import asyncio
from typing import Any, Optional

from jinja2 import Template
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from nanoai.model.llm import allm
from nanoai.utils.nl_repr import nl_repr

from projects.zhiji.common.client import get_openai_client
from projects.zhiji.common.engine_api import (
    DebugInfo,
    HistoryItem,
    VolcengineIntentResult,
    volcengine_intent,
)
from projects.zhiji.domain.simple import chat
from projects.zhiji.domain.complex import complex_navigation

class ClassificationResult(BaseModel):
    api_result: VolcengineIntentResult = Field(..., description="火山接口原始结果")
    prompt_result: str | None = Field(default=None, description="最终使用的分类结果（类别名称）")
    llm_raw_result: str | None = Field(default=None, description="LLM原始分类结果（类别名称）")

CLASSIFICATION_PROMPT_TEMPLATE = """
你是{{ expert_role }}，判断用户意图类别。从以下分类选择最合适的一项：

{% for item in categories_text %}
{{ item }}

{% endfor %}
若不匹配，选择"闲聊"。

{% if history %}
【历史对话说明】历史对话仅用于补全当前query中的指代词（如：这个、那个、它、第一个、前排的等），不要被历史对话中的其他信息干扰分类判断。
如果当前query没有指代词，应忽略历史对话，直接对当前query进行分类。

历史对话：
{% for turn in history %}
{{ turn }}
{% endfor %}
{% endif %}

{{ output_hint }}
"""

PROMPT_TEMPLATE = Template(CLASSIFICATION_PROMPT_TEMPLATE)

DEFAULT_LLM_PARAMS: dict[str, Any] = {
    "model": "ep-20251212115142-zk7z2",
    "stream": False,
    "temperature": 0.3,  # 降低temperature以加快响应速度
    "top_p": 0.7,
    "max_tokens": 512,  # 分类任务不需要2048，减少到512可显著加快速度
    "extra_body": {
        "thinking": {
            "type": "disabled",  # 不使用深度思考能力
        }
    },
}


async def intent_cls(
    query: str,
    intent_categories: list,
    /,
    *,
    history: list[str] | None = None,
    client: AsyncOpenAI | None = None,
    expert_role: str = "车联网意图分类专家",
    **llm_params: Any,
) -> str:
    """意图分类函数，返回类别名称。"""
    history_list = history or []

    categories_text = [nl_repr(category) for category in intent_categories]
    
    # 获取所有有效类别名称
    valid_categories = {cat.name for cat in intent_categories}
    categories_list = "、".join(sorted(valid_categories))
    
    output_hint = (
        "【核心原则】历史对话仅用于指代补全，不要被历史对话中的其他信息干扰。\n"
        "1. 如果当前query包含指代词（如：这个、那个、它、第一个、前排的、后排的、左边的、右边的等），"
        "必须结合历史对话补全完整意图后再分类。\n"
        "2. 如果当前query没有指代词，应忽略历史对话，直接对当前query进行分类。\n"
        "3. 不要被历史对话中的无关信息（如车控技术细节、其他话题等）影响分类判断。\n"
        "4. 只关注当前query的核心意图，历史对话仅用于补全指代。\n\n"
        f"【输出格式】请严格按照以下要求输出：\n"
        f"1. 只能输出以下类别名称之一：{categories_list}\n"
        f"2. 不要包含任何其他文字、标点符号、引号、括号等\n"
        f"3. 如果不匹配任何类别，输出：闲聊\n"
    )

    sys_prompt = PROMPT_TEMPLATE.render(
        expert_role=expert_role,
        categories_text=categories_text,
        output_hint=output_hint,
        history=history_list,
    )

    client = client or get_openai_client()

    # 新模型不支持结构化输出，使用文本输出并手动解析
    response = await allm(
        query,
        sys_prompt,
        client=client,
        **llm_params,
    )
    
    # 从文本中提取类别名称（prompt已强制要求只输出类别名称）
    category = response.output.strip()
    
    # 移除可能的引号、括号等（虽然prompt已要求不要包含，但为了容错还是处理一下）
    category = category.strip('"\'()[]{}').strip()
    
    # 验证类别名称是否在有效类别中
    valid_categories = {cat.name for cat in intent_categories}
    if category not in valid_categories:
        # 如果不在有效类别中，默认使用"闲聊"
        category = chat.name
    
    return category




class IntentClassifier:
    """意图分类器，2分类：闲聊或复杂导航。"""

    def __init__(self, *, client: AsyncOpenAI | None = None, **llm_params: Any) -> None:
        self.client = client or get_openai_client()
        # 2分类：闲聊和复杂导航
        self.intent_categories = [
            complex_navigation,
            chat,
        ]
        self.complex_category_names = {
            complex_navigation.name,
        }
        self.llm_params: dict[str, Any] = {**DEFAULT_LLM_PARAMS, **llm_params}

    @staticmethod
    def _prepare_history(
        history: list[HistoryItem] | None,
    ) -> tuple[list[str], list[HistoryItem] | None]:
        """将 HistoryItem 列表转换为文本列表和原始列表"""
        if not history:
            return [], None
        
        history_text: list[str] = []
        for item in history:
            history_text.append(f"用户: {item.q}")
            if item.a:
                history_text.append(f"助手: {item.a}")
        
        return history_text, history

    async def run(
        self,
        query: str,
        *,
        history: list[HistoryItem] | None = None,
        car_info: dict[str, Any] | None = None,
        expert_role: str = "车联网意图分类专家",
        longitude: Optional[float] = None,
        latitude: Optional[float] = None,
        vehicle_id: Optional[str] = None,
        vehicle_name: Optional[str] = None,
        function_call_version: Optional[str] = None,
    ) -> ClassificationResult:
        """并行执行 prompt 分类和火山接口调用。"""
        history_text, history_items = self._prepare_history(history)

        # 两个任务并行执行：LLM 分类、火山接口调用
        prompt_task = asyncio.create_task(
            intent_cls(
                query,
                self.intent_categories,
                history=history_text,
                client=self.client,
                expert_role=expert_role,
                **self.llm_params,
            )
        )
        api_task = asyncio.create_task(
            volcengine_intent(
                query=query,
                history=history_items,
                car_info=car_info,
                longitude=longitude,
                latitude=latitude,
                vehicle_id=vehicle_id,
                vehicle_name=vehicle_name,
                function_call_version=function_call_version,
            )
        )

        # 等待所有任务并行完成
        prompt_result, api_result = await asyncio.gather(
            prompt_task, api_task, return_exceptions=True
        )
        
        prompt_cls: str | None
        if isinstance(prompt_result, Exception):
            prompt_cls = None
        else:
            # 类型断言：prompt_result 此时一定是 str
            prompt_cls = prompt_result  # type: ignore[assignment]

        # 类型断言：确保 api_result 是 VolcengineIntentResult
        if isinstance(api_result, Exception):
            api_result = VolcengineIntentResult(
                intent=None,
                question_id=None,
                reject=True,
                debug_info=DebugInfo(),
                byte_intent_type=None,
            )
        # 类型断言：此时 api_result 一定是 VolcengineIntentResult
        assert isinstance(api_result, VolcengineIntentResult)

        # 保存 LLM 的原始分类结果（用于调试和分析）
        llm_raw_result = prompt_cls

        # 如果 LLM 判定为"闲聊"，清除分类，交给 API 处理
        if prompt_cls and prompt_cls == chat.name:
            prompt_cls = None
        # 如果 LLM 判定为"复杂导航"，需要覆盖或创建 intent
        elif prompt_cls and prompt_cls == complex_navigation.name:
            if not api_result.reject and api_result.intent is not None:
                # API 有返回 intent，直接覆盖 intent_type
                api_result.intent.intent_type = prompt_cls
            else:
                # API 拒识或 intent 为 None，但 LLM 分类为复杂导航，需要创建 intent
                from projects.zhiji.common.engine_api import IntentData
                api_result.intent = IntentData(
                    message=None,
                    domain=None,
                    intent_type=prompt_cls,
                    input=query,
                    slot_data=None,
                    origin_intent_type=None,
                    next_process=None,
                )
                api_result.reject = False

        if not api_result.reject and api_result.intent is not None and not api_result.intent.input:
            api_result.intent.input = query

        return ClassificationResult(
            api_result=api_result,
            prompt_result=prompt_cls,
            llm_raw_result=llm_raw_result,
        )
