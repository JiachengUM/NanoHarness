#!/usr/bin/env python3
"""测试 IntentClassifier 分类结果"""

from __future__ import annotations

import asyncio
import pytest

from projects.SGM.core import IntentClassifier
from projects.SGM.common.engine_api import close_volcengine_session, HistoryItem
from projects.SGM.common.rag import close_rag_session

@pytest.mark.asyncio
async def test_with_history():
    """测试带历史对话的分类"""
    # 问题案例：餐厅推荐查询，历史对话中有车控干扰信息
    query = "找一下上海次，上海市最好吃的小笼包"
    
    history = [
        HistoryItem(q="导航一下上海市的小笼包。", a=None),
        HistoryItem(q="你接受到车门打开了，你就要把，你把车门打开信号发给我就行了，然后其他信号你触发了就发货。", a=None),
        HistoryItem(q="找一下上面最好吃的小笼包。", a="1. 地名：杭州小笼包(沧源二村店) ID：7141724717479626789\n2. 地名：桂满陇·蟹粉小笼包(环球港店) ID：6903268970506225677\n3. 地名：满口香小笼包(海鹏路店) ID：6623286409916581892\n4. 地名：仙云居小笼包(东兰路分店) ID：6875385270603237391\n5. 地名：仙云居小笼包(星苑小区店) ID：6918113688293476355\n6. 地名：满口香小笼包(新德西路店) ID：6983287165576808485\n7. 地名：仙云居小笼包(工农二村店) ID：6752235664449832971\n8. 地名：仙云居小笼包(杨浦区商业委员会供销经济园区松花江路分部店) ID：6753887934690166795\n9. 地名：仙云居小笼包(莘谭路店) ID：6998720058780289031\n为您推荐上海市的以下小笼包。"),
    ]
    
    print(f"\n{'='*70}")
    print(f"【测试用例：带历史对话的分类】")
    print(f"{'='*70}")
    print(f"\n查询: {query}")
    print(f"\n历史对话:")
    for i, item in enumerate(history, 1):
        print(f"  {i}. 用户: {item.q}")
        if item.a:
            print(f"     助手: {item.a[:80]}..." if len(item.a) > 80 else f"     助手: {item.a}")
        else:
            print(f"     助手: (无回复)")
    
    classifier = IntentClassifier()
    result = await classifier.run(query, history=history)
    
    return result


async def test_without_history():
    """测试不带历史对话的分类"""
    query = "陪我聊聊天"
    
    print(f"\n{'='*70}")
    print(f"【测试用例：不带历史对话的分类】")
    print(f"{'='*70}")
    print(f"\n查询: {query}")
    
    classifier = IntentClassifier()
    result = await classifier.run(query)
    
    return result


def print_result(result, test_name: str = ""):
    """打印分类结果"""
    print(f"\n{'='*70}")
    if test_name:
        print(f"【{test_name} - 分类结果】")
    else:
        print(f"【分类结果】")
    print(f"{'='*70}")
    
    # LLM Prompt 分类
    print("\n【LLM Prompt 分类】")
    if result.llm_raw_result:
        print(f"  LLM原始分类: {result.llm_raw_result}")
    
    if result.prompt_result:
        if result.prompt_result != result.llm_raw_result:
            print(f"  最终分类: {result.prompt_result} (已调整)")
        else:
            print(f"  最终分类: {result.prompt_result}")
    else:
        print(f"  最终分类: None (已清除，交给API处理)")
    
    # RAG 多意图检索
    print("\n【RAG 多意图检索】")
    if result.rag_result:
        print(f"  相似度: {result.rag_result.max_similarity:.4f}")
        print(f"  是否多意图: {'是' if result.rag_result.is_multi_intent else '否'}")
    else:
        print(f"  状态: 失败或未执行")
    
    # 车控清晰度
    if result.vehicle_check is not None:
        print("\n【车控清晰度检查】")
        print(f"  是否清晰: {'是' if result.vehicle_check else '否'}")
    
    # 火山引擎 API
    print("\n【火山引擎 API】")
    print(f"  拒识: {'是' if result.api_result.reject else '否'}")
    if not result.api_result.reject and result.api_result.intent:
        print(f"  领域: {result.api_result.intent.domain}")
        print(f"  意图类型: {result.api_result.intent.intent_type}")
    
    # 最终结果（关键信息）
    print("\n【最终结果 - 关键信息】")
    intent = result.api_result.intent
    print(f"  intent_type: {intent.intent_type if intent else 'None'}")
    print(f"  byte_intent_type: {result.api_result.byte_intent_type if result.api_result.byte_intent_type else 'None'}")
    print(f"  origin_intent_type (字节API原始): {intent.origin_intent_type if intent else 'None'}")
    
    # 判断是否为复杂意图
    from projects.SGM.domain.complex import FUZZY_VEHICLE_CONTROL_LABEL, MULTI_INTENT_LABEL
    COMPLEX_CATEGORY_NAMES = {FUZZY_VEHICLE_CONTROL_LABEL, MULTI_INTENT_LABEL}
    is_complex = (
        result.prompt_result in COMPLEX_CATEGORY_NAMES
        if result.prompt_result
        else False
    )
    print(f"  是否复杂意图: {'是' if is_complex else '否'}")
    
    # 分析结果
    print("\n【结果分析】")
    if intent and intent.intent_type == "一方服务":
        print("  被分类为'一方服务'，这可能是误分类")
        print("  预期：应该分类为'闲聊'或由API处理餐厅推荐")
    elif intent and intent.intent_type:
        print(f"  ✓ 分类为: {intent.intent_type}")
    else:
        print("  ✓ 交给API处理")


async def main():
    import sys
    
    # 如果命令行参数包含 "history"，测试带历史对话的情况
    if len(sys.argv) > 1 and "history" in sys.argv[1].lower():
        result = await test_with_history()
        print_result(result, "带历史对话")
    else:
        result = await test_without_history()
        print_result(result, "不带历史对话")
    
    print(f"\n{'='*70}\n")
    
    # 清理资源：关闭所有 HTTP 会话
    await close_volcengine_session()
    await close_rag_session()


if __name__ == "__main__":
    asyncio.run(main())
