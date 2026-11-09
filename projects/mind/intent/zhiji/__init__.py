from __future__ import annotations

import asyncio
from typing import Any
from pydantic import BaseModel, Field

from projects.mind.intent.alg.core import (
    ModelName,
    ClsResult, 
    IntentClsPrompt, 
    Message, 
    IntentClassifierLLM,
)
from projects.mind.intent.alg.volc_intent import (
    IntentData,
    DebugInfo,
    volcengine_intent,
    VolcengineIntentResult,
)
from projects.mind.intent.zhiji.intent_data.category import (
    chat,
    complex_navigation,
)


__all__ = [
    "IntentClassifier",
]

class ClassificationResult(BaseModel):
    llm_raw_result: ClsResult = Field(..., description="LLM原始分类结果（类别名称+原因）")
    volc_api_result: VolcengineIntentResult = Field(..., description="火山接口原始结果")
    final_intent: str | None = Field(default=None, description="最终使用的分类结果：None（聊天或异常时）或'复杂导航")

# 模型配置
DEFAULT_LLM_PARAMS: dict[str, Any] = {
    "stream": False,
    "temperature": 0.01,
    # "top_p": 0.8,
    # "max_tokens": 256,
    "extra_body": {
        "thinking": {
            "type": "disabled",  # 关闭内部思考显示
        }
    },
}


class IntentClassifier(IntentClassifierLLM):
    """智己项目的意图分类器，支持2分类：聊天、复杂导航。"""

    def __init__(
        self, 
        *, 
        model: ModelName = ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        llm_params: dict[str, Any] | None = DEFAULT_LLM_PARAMS
    ) -> None:
                
        # 定义2个意图类别
        intent_categories = [
            chat,
            complex_navigation,
        ]
        
        # 构建分类提示（支持历史对话）
        prompt = IntentClsPrompt(
            categories=intent_categories,
            expert_role="复杂导航意图分类专家",
            output_hint=(
                "【核心原则】当前为车载场景,尤其注意历史对话仅用于对当前查询的指代补全，不要被历史对话中的其他信息干扰。\n"
                f"只能输出以下类别名称之一：{'、'.join(sorted(cat.name for cat in intent_categories))}\n"
            )
        )
        super().__init__(
            prompt,
            model=model,
            llm_params=llm_params
        )
        
    async def _run_llm_cls(
        self, 
        query: str, 
        messages: list[Message] | None = None
    ) -> ClsResult:
        """内部方法：只执行 LLM 分类"""
        res = await self._run_cls(query, messages)
        return res[0]
    
    async def _run_api(
        self,
        query: str,
        messages: list[Message] | None = None,
        **kwargs: Any,
    ) -> VolcengineIntentResult:
        """内部方法：只执行火山接口调用"""

        # 可能还有更多的参数，如car_info, longitude, latitude, vehicle_id, vehicle_name, function_call_version等
        # TODO：等待volc_intent 改好，重新写。
        return await volcengine_intent(query=query, history=messages, **kwargs)
    

    async def run(
        self,
        query: str,
        messages: list[Message] | None = None,
        **kwargs: Any,
    ) -> ClassificationResult:
        """执行意图分类，返回分类结果。
        
        Args:
            query: 用户输入的查询文本
            messages: 可选的历史对话列表，用于指代补全
            **kwargs: 其他可选参数，用于火山接口调用
            
        Returns:
            ClassificationResult: 最终包含火山接口原始结果、LLM原始分类结果和最终使用的分类结果的分类结果
        """
        
        # 两个任务并行执行
        llm_task = asyncio.create_task(
            self._run_llm_cls(query, messages)
        )
        api_task = asyncio.create_task(
            self._run_api(query, messages)
        )
        
        # 等待并合并结果
        llm_result, api_result = await asyncio.gather(
            llm_task, api_task, return_exceptions=True
        )
        # 方便和火山api结果做处理
        llm_cls: str | None = None
        # 如果LLM分类出错，则最终分类为None
        if isinstance(llm_result, Exception):
            llm_cls = None
            # 分类时出错，需创建个ClsResult对象，用于后续处理
            llm_raw_result = ClsResult(category="", reason="分类时出错！")
        else:
            # 类型断言：llm_result 此时一定是 ClsResult
            assert isinstance(llm_result, ClsResult)
            llm_cls = llm_result.category

            # 保存 LLM 的原始分类结果（用于调试和分析）
            llm_raw_result = llm_result

        # 类型断言：确保 api_result 是 VolcengineIntentResult
        if isinstance(api_result, Exception):
            # 出错情况：返回拒识结果
            api_result = VolcengineIntentResult(
                intent=None,
                question_id=None,
                reject=True,
                debug_info=DebugInfo(),
                byte_intent_type=None,
            )

        # 类型断言：此时 api_result 一定是 VolcengineIntentResult
        assert isinstance(api_result, VolcengineIntentResult)

        # 如果 LLM 判定为"闲聊"或llm_cls为None，清除分类，交给 API 处理
        if not llm_cls or llm_cls == chat.name:
            llm_cls = None
        # 如果LLM判定为`复杂导航`（且llm_cls不为None）
        else:
            # api 有结果且不为拒识，直接覆盖 intent_type
            if not api_result.reject and api_result.intent is not None:
                api_result.intent.intent_type = llm_cls
            else:
                # API 拒识或 intent 为 None，但 LLM 分类为复杂导航，需要创建 intent
                api_result.intent = IntentData(
                    message=None,
                    domain=None,
                    intent_type=llm_cls,
                    input=query,
                    slot_data=None,
                    origin_intent_type=None,
                    next_process=None,
                )
                api_result.reject = False

        if not api_result.reject and api_result.intent is not None and not api_result.intent.input:
            api_result.intent.input = query                
        
        return ClassificationResult(
            volc_api_result=api_result,
            llm_raw_result=llm_raw_result,
            final_intent=llm_cls,
        )