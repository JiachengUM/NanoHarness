from __future__ import annotations
import asyncio
from typing import Any

from nanoai.model.llm import allm
from nanoai.utils.nl_repr import nl_repr
from projects.mind.intent.alg.core import (
    ClsResult,
    IntentClassifierLLM,
    IntentClsPrompt,
    Message,
    ModelName,
)
from projects.mind.intent.alg.volc_intent import (
    DebugInfo,
    IntentData,
    VolcengineIntentResult,
    volcengine_intent,
)
from projects.mind.intent.ydl.category import (
    ai_content,
    category_vehicle_control,
    chat,
    life_service,
    vqa,
)

__all__ = [
    "IntentClassifier",
]


# 模型配置
DEFAULT_LLM_PARAMS: dict[str, Any] = {
    "stream": False,
    "temperature": 0.3,
    "top_p": 0.7,
    "max_tokens": 512,
    "extra_body": {
        "thinking": {
            "type": "disabled",
        }
    },
}
# 复杂模糊车控标签常量，用于代码逻辑判断，不参与 LLM 分类
FUZZY_VEHICLE_CONTROL_LABEL = "复杂模糊车控"

MULTI_INTENT_LABEL = "多意图"


class IntentClassifier(IntentClassifierLLM):
    """YDL 项目的意图分类器，支持5分类：车控、一方服务、捷停车、VQA、聊天。"""

    def __init__(
        self,
        *,
        model: ModelName = ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        llm_params: dict[str, Any] | None = DEFAULT_LLM_PARAMS
    ) -> None:
        # 定义5个意图类别
        self.categories = [
            category_vehicle_control,
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
        # 构建分类提示（支持历史对话）
        prompt = IntentClsPrompt(
            categories=self.categories,
            expert_role="车联网意图分类专家",
            output_hint=(
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
                "处理：当前query没有指代词，忽略历史对话中的车控信息，直接分类为'聊天'（让API处理餐厅推荐）\n\n"
                f"【输出格式】请严格按照以下要求输出：\n"
                f"1. 只能输出以下类别名称之一：{', '.join(cat.name for cat in self.categories)}\n"
                f"2. 不要包含任何其他文字、标点符号、引号、括号等\n"
                f"3. 输出示例：车控（正确）或 \"车控\"（错误，不要引号）"
            )
        )

        super().__init__(
            prompt,
            model=model,
            llm_params=llm_params
        )


    async def _check_vehicle_control_clarity(
        self,
        query: str,
        *,
        history: list[str] | None = None
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

        # 新模型不支持结构化输出，使用文本输出并手动解析
        response = await allm(
            query,
            vehicle_check_prompt,
            **self.llm_params,
        )

        # 从文本中提取布尔值（prompt已强制要求只输出true或false）
        text = response.output.strip().lower()

        # 移除可能的引号、括号等（虽然prompt已要求不要包含，但为了容错还是处理一下）
        text = text.strip('"\'()[]{}').strip()

        # 判断是否为true（prompt已强制要求只输出true或false）
        return text == "true"

    async def run(
        self,
        query: str,
        car_info: dict[str, Any] | None = None,
        messages: list[Message] | None = None,
    ) -> ClsResult:
        """执行意图分类，返回分类结果。

        Args:
            query: 用户输入的查询文本
            history: 可选的历史对话列表，用于指代补全

        Returns:
            ClsResult: 包含类别名称和判断原因的分类结果
        """
        # 准备历史对话文本
        history_text: list[str] = []
        if messages:
            history_text = [nl_repr(item) for item in messages]

        prompt_task = asyncio.create_task(
            super()._run_cls(query, messages)
        )
        api_task = asyncio.create_task(
            volcengine_intent(query=query, history=messages, car_info=car_info)
        )
        clarity_task = asyncio.create_task(
            self._check_vehicle_control_clarity(
                query,
                history=history_text,
            )
        )
        # 等待所有任务并行完成
        prompt_result, api_result, clarity_result = await asyncio.gather(
            prompt_task, api_task, clarity_task, return_exceptions=True
        )

        prompt_cls: ClsResult | None
        if isinstance(prompt_result, Exception):
            prompt_cls = None
        else:
            assert isinstance(prompt_result, tuple)
            assert isinstance(prompt_result[0], ClsResult)
            prompt_cls = prompt_result[0]

        if isinstance(api_result, Exception):
            api_result = VolcengineIntentResult(
                intent=None,
                question_id=None,
                reject=True,
                debug_info=DebugInfo(),
                byte_intent_type=None
            )
        assert isinstance(api_result, VolcengineIntentResult)

        # 初始化 vehicle_check
        vehicle_check: bool | None = None

        # 如果 LLM 判定为"闲聊"，清除分类，交给 API 处理
        if prompt_cls and prompt_cls.category == chat.name:
            # prompt_cls设置为None，那么api结果就原原本本不会改变。火山api的结果就是最终结果
            prompt_cls = None

        # 只有当 LLM 判定为"车控"时，才使用清晰度检查结果
        if prompt_cls and prompt_cls.category == category_vehicle_control.name:
            if not isinstance(clarity_result, Exception) and clarity_result is not None:
                assert isinstance(clarity_result, bool)
                vehicle_check = clarity_result

                # 根据清晰度检查结果判断是否转为"复杂模糊车控"
                if not vehicle_check:
                    # 动作或实体不清晰，转为"复杂模糊车控"
                    prompt_cls.category = FUZZY_VEHICLE_CONTROL_LABEL
                else:
                    # 动作和实体都清晰，交给 API 处理
                    if not api_result.reject and api_result.intent is not None:
                    # API 有返回 intent，直接覆盖 intent_type
                        api_result.intent.intent_type = prompt_cls.category
                    else:
                        # API 拒识或 intent 为 None，但 LLM 分类为自定义类别，需要创建 intent
                        api_result.intent = IntentData(
                            intent_type=prompt_cls.category,
                            input=query,
                        )
                        api_result.reject = False
        # 如果不是车控，清晰度检查结果会被忽略（已并行执行但不用）

        # 如果 prompt_cls 是自定义类别或复杂意图，需要覆盖或创建 intent
        if prompt_cls and prompt_cls.category in self.custom_category_names | self.complex_category_names:
            if not api_result.reject and api_result.intent is not None:
                # API 有返回 intent，直接覆盖 intent_type
                api_result.intent.intent_type = prompt_cls.category
            else:
                # API 拒识或 intent 为 None，但 LLM 分类为自定义类别，需要创建 intent
                api_result.intent = IntentData(
                    intent_type=prompt_cls.category,
                    input=query,
                )
                api_result.reject = False

        if not api_result.reject and api_result.intent is not None and not api_result.intent.input:
            api_result.intent.input = query
        assert api_result is not None
        assert api_result.intent is not None
        assert api_result.intent.intent_type is not None
        assert not isinstance(prompt_result, Exception)
        return ClsResult(
            category=api_result.intent.intent_type,
            reason=prompt_result[0].reason,
        )
