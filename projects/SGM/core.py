from __future__ import annotations

import asyncio
from typing import Any

from jinja2 import Template
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from nanoai.model.llm import allm
from nanoai.utils.nl_repr import nl_repr

from projects.SGM.common.client import get_openai_client
from projects.SGM.common.engine_api import (
    DebugInfo,
    HistoryItem,
    VolcengineIntentResult,
    volcengine_intent,
)
from projects.SGM.domain.simple import chat
from projects.SGM.domain.complex import car_control, FUZZY_VEHICLE_CONTROL_LABEL, MULTI_INTENT_LABEL
from projects.SGM.domain.custom import ai_content, life_service, vqa
from projects.SGM.common.rag import rag_search_multi_intent, RagSearchResult

class ClassificationResult(BaseModel):
    api_result: VolcengineIntentResult = Field(..., description="火山接口原始结果")
    prompt_result: str | None = Field(default=None, description="最终使用的分类结果（类别名称）")
    llm_raw_result: str | None = Field(default=None, description="LLM原始分类结果（类别名称）")
    vehicle_check: bool | None = Field(default=None, description="车控清晰度检查结果，True表示动作和实体都清晰，False表示不清晰")
    rag_result: RagSearchResult | None = Field(default=None, description="RAG多意图检索结果")

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
        "【指代补全示例】\n"
        "历史：用户说'帮我打开座椅加热'\n"
        "当前query：'帮我打开前排的'\n"
        "补全后：'帮我打开前排的座椅加热' → 分类为'车控'\n\n"
        "【无指代词示例】\n"
        "历史：用户说'你接受到车门打开了，你就要把信号发给我'\n"
        "当前query：'帮我搜搜上海比较好吃的小笼包的餐厅吧'\n"
        "处理：当前query没有指代词，忽略历史对话中的车控信息，直接分类为'闲聊'（让API处理餐厅推荐）\n\n"
        f"【输出格式】请严格按照以下要求输出：\n"
        f"1. 只能输出以下类别名称之一：{categories_list}\n"
        f"2. 不要包含任何其他文字、标点符号、引号、括号等\n"
        f"3. 如果不匹配任何类别，输出：闲聊\n"
        f"4. 输出示例：车控（正确）或 \"车控\"（错误，不要引号）"
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


async def check_vehicle_control_clarity(
    query: str,
    *,
    history: list[str] | None = None,
    client: AsyncOpenAI | None = None,
    **llm_params: Any,
) -> bool:
    """分析车控指令的动作和实体清晰度。
    
    此函数仅在 LLM 已判定为"车控"类别后调用。
    如果query包含指代词，会结合历史对话补全后再分析清晰度。
    """
    history_text = history or []
    history_section = ""
    if history_text:
        history_section = "\n历史对话：\n" + "\n".join(history_text) + "\n"
    
    vehicle_check_prompt = f"""你是一个语义分析专家，需要分析车控指令中动作和实体的清晰度。

【核心原则】提取核心车控指令，忽略干扰信息：
- 忽略条件状语（如"如果...就..."、"当...时"、"等...时候"等）
- 忽略背景信息（如"外面下雪了"、"热死了"、"小朋友睡着了"等）
- 忽略原因说明（如"因为..."、"由于..."等）
- 只关注核心的车控动作和控制对象

【重要】指代补全规则：
如果当前指令包含指代词（如：这个、那个、它、第一个、前排的、后排的、左边的、右边的等），
必须结合历史对话补全完整意图后再分析清晰度。
例如：历史中用户说"帮我打开座椅加热"，当前指令是"帮我打开前排的"，
应补全为"帮我打开前排的座椅加热"后再分析，此时实体清晰（座椅加热），而不是实体模糊。

{history_section}
判断标准：
- 动作清晰：核心动作明确，如"打开"、"关闭"、"调到"、"调高"、"调低"、"调小"、"调大"等
- 动作模糊：核心动作不明确，如"搞一下"、"弄一下"、"给我氛围"、"来点"、"暖和起来"等
- 实体清晰：控制对象明确，如"空调"、"天窗"、"车窗"、"温度"、"座椅加热"、"灯"等
- 实体模糊：控制对象不明确，如"头顶那个盖子"、"能照路的灯"、"对应氛围"、"那个东西"等
（注意：如果可以通过历史对话补全指代，补全后实体明确，则判定为实体清晰）

示例分析：
- "空调温度调到25度" → 核心指令："调到空调温度"，动作清晰（调到），实体清晰（空调温度）→ true
- "打开天窗" → 核心指令："打开天窗"，动作清晰（打开），实体清晰（天窗）→ true
- "如果小朋友睡着了，把空调调低一点" → 核心指令："调低空调"（忽略"如果小朋友睡着了"），动作清晰（调低），实体清晰（空调）→ true
- "外面下雪了，把温度调高" → 核心指令："调高温度"（忽略"外面下雪了"），动作清晰（调高），实体清晰（温度）→ true
- "热死了搞一下空调" → 核心指令："搞一下空调"（忽略"热死了"），动作模糊（搞一下），实体清晰（空调）→ false
- 历史："帮我打开座椅加热"，当前："帮我打开前排的" → 补全为"帮我打开前排的座椅加热"，动作清晰（打开），实体清晰（座椅加热）→ true
- "头顶那个盖子掀开点"（无历史上下文） → 核心指令："掀开头顶那个盖子"，动作清晰（掀开），实体模糊（头顶那个盖子）→ false
- "外面下雪了给我一个对应氛围吧" → 核心指令："给我对应氛围"，动作模糊（给我氛围），实体模糊（对应氛围）→ false
- "把灯调柔和点儿" → 核心指令："调柔和灯"，动作模糊（调柔和），实体清晰（灯）→ false
- "车里快点暖和起来" → 核心指令："暖和起来"（无明确控制对象），动作模糊（暖和起来），实体模糊（车里环境）→ false

请先补全指代（如有），再提取核心车控指令，最后分析清晰度。

【输出格式】请严格按照以下要求输出：
1. 只能输出以下两个值之一：true 或 false
2. 如果动作和实体都清晰，输出：true
3. 如果动作或实体不清晰，输出：false
4. 不要包含任何其他文字、标点符号、引号、括号等
5. 输出示例：true（正确）或 "true"（错误，不要引号）"""

    client = client or get_openai_client()
    
    # 新模型不支持结构化输出，使用文本输出并手动解析
    response = await allm(
        query,
        vehicle_check_prompt,
        client=client,
        **llm_params,
    )
    
    # 从文本中提取布尔值（prompt已强制要求只输出true或false）
    text = response.output.strip().lower()
    
    # 移除可能的引号、括号等（虽然prompt已要求不要包含，但为了容错还是处理一下）
    text = text.strip('"\'()[]{}').strip()
    
    # 判断是否为true（prompt已强制要求只输出true或false）
    return text == "true"


class IntentClassifier:
    """SGM项目的意图分类器，聚焦复杂意图与定制业务场景。"""

    def __init__(self, *, client: AsyncOpenAI | None = None, **llm_params: Any) -> None:
        self.client = client or get_openai_client()
        # 包含 car_control，通过清晰度检查动态判断是否转为 fuzzy_vehicle_control
        self.intent_categories = [
            car_control,
            ai_content,
            life_service,
            vqa,
            chat,
        ]
        self.custom_category_names = {
            ai_content.name,
            life_service.name,
            vqa.name,
        }
        self.complex_category_names = {
            FUZZY_VEHICLE_CONTROL_LABEL,
            MULTI_INTENT_LABEL,
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
    ) -> ClassificationResult:
        """并行执行 prompt 分类、火山接口调用和 RAG 多意图检索，如果判定为车控则进行清晰度检查。"""
        history_text, history_items = self._prepare_history(history)

        # 四个任务并行执行：LLM 分类、火山接口调用、RAG 多意图检索、清晰度检查
        # 清晰度检查提前启动，如果不是车控则忽略结果，避免等待时间
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
            volcengine_intent(query=query, history=history_items, car_info=car_info)
        )
        rag_task = asyncio.create_task(
            rag_search_multi_intent(query)
        )
        clarity_task = asyncio.create_task(
            check_vehicle_control_clarity(
                query,
                history=history_text,
                client=self.client,
                **self.llm_params,
            )
        )

        # 等待所有任务并行完成
        prompt_result, api_result, rag_result, clarity_result = await asyncio.gather(
            prompt_task, api_task, rag_task, clarity_task, return_exceptions=True
        )
        
        prompt_cls: str | None
        if isinstance(prompt_result, Exception):
            prompt_cls = None
        else:
            prompt_cls = prompt_result

        if isinstance(api_result, Exception):
            api_result = VolcengineIntentResult(
                intent=None,
                question_id=None,
                reject=True,
                debug_info=DebugInfo(),
            )

        rag_search_result: RagSearchResult | None
        if isinstance(rag_result, Exception):
            rag_search_result = None
        else:
            rag_search_result = rag_result

        # 保存 LLM 的原始分类结果（用于调试和分析）
        llm_raw_result = prompt_cls

        # 初始化 vehicle_check
        vehicle_check: bool | None = None

        # RAG 多意图判断：如果相似度 >= 0.9，判定为多意图（优先级最高）
        if rag_search_result and rag_search_result.is_multi_intent:
            prompt_cls = MULTI_INTENT_LABEL
        # 如果 LLM 判定为"闲聊"，清除分类，交给 API 处理
        elif prompt_cls and prompt_cls == chat.name:
            prompt_cls = None
        # 只有当 LLM 判定为"车控"时，才使用清晰度检查结果
        elif prompt_cls and prompt_cls == car_control.name:
            if not isinstance(clarity_result, Exception) and clarity_result is not None:
                vehicle_check = clarity_result
                
                # 根据清晰度检查结果判断是否转为"复杂模糊车控"
                if not vehicle_check:
                    # 动作或实体不清晰，转为"复杂模糊车控"
                    prompt_cls = FUZZY_VEHICLE_CONTROL_LABEL
                else:
                    # 动作和实体都清晰，清除 prompt 分类，交给 API 处理
                    prompt_cls = None
        # 如果不是车控，清晰度检查结果会被忽略（已并行执行但不用）

        # 如果 prompt_cls 是自定义类别或复杂意图，需要覆盖或创建 intent
        if prompt_cls and prompt_cls in self.custom_category_names | self.complex_category_names:
            if not api_result.reject and api_result.intent is not None:
                # API 有返回 intent，直接覆盖 intent_type
                api_result.intent.intent_type = prompt_cls
            else:
                # API 拒识或 intent 为 None，但 LLM 分类为自定义类别，需要创建 intent
                from projects.SGM.common.engine_api import IntentData
                api_result.intent = IntentData(
                    intent_type=prompt_cls,
                    input=query,
                )
                api_result.reject = False

        if not api_result.reject and api_result.intent is not None and not api_result.intent.input:
            api_result.intent.input = query

        return ClassificationResult(
            api_result=api_result,
            prompt_result=prompt_cls,
            llm_raw_result=llm_raw_result,
            vehicle_check=vehicle_check,
            rag_result=rag_search_result,
        )
