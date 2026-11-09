#!/usr/bin/env python3
"""详细测试 IntentClassifier 性能"""
import asyncio
import time
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from projects.zhiji.core import IntentClassifier, intent_cls, check_vehicle_control_clarity
from projects.zhiji.common.engine_api import volcengine_intent, close_volcengine_session
from projects.zhiji.common.rag import rag_search_multi_intent, close_rag_session
from projects.zhiji.domain.complex import car_control


async def test_performance():
    """详细性能测试"""
    query = "打开头顶上的那个盖子"
    
    print(f"\n{'='*70}")
    print(f"查询: {query}")
    print(f"{'='*70}\n")
    
    classifier = IntentClassifier()
    
    print("【性能分析 - 各任务单独耗时】\n")
    
    # 1. LLM 分类
    print("1. 测试 LLM 分类:")
    llm_start = time.time()
    llm_result = await intent_cls(
        query,
        classifier.intent_categories,
        client=classifier.client,
        **classifier.llm_params,
    )
    llm_time = time.time() - llm_start
    print(f"   耗时: {llm_time:.2f}秒")
    print(f"   分类: {llm_result}\n")
    
    # 2. 火山引擎 API
    print("2. 测试火山引擎 API:")
    api_start = time.time()
    api_result = await volcengine_intent(query=query)
    api_time = time.time() - api_start
    print(f"   耗时: {api_time:.2f}秒")
    print(f"   是否拒识: {api_result.reject}")
    if not api_result.reject and api_result.intent:
        print(f"   意图类型: {api_result.intent.intent_type}\n")
    else:
        print()
    
    # 3. RAG 检索
    print("3. 测试 RAG 检索:")
    rag_start = time.time()
    rag_result = await rag_search_multi_intent(query)
    rag_time = time.time() - rag_start
    print(f"   耗时: {rag_time:.2f}秒")
    print(f"   相似度: {rag_result.max_similarity:.4f}")
    print(f"   是否多意图: {rag_result.is_multi_intent}\n")
    
    # 4. 清晰度检查（如果是车控）
    clarity_time = 0
    if llm_result == car_control.name:  # car_control.name 是 "车控"
        print("4. 测试清晰度检查:")
        clarity_start = time.time()
        clarity_result = await check_vehicle_control_clarity(
            query,
            client=classifier.client,
            **classifier.llm_params,
        )
        clarity_time = time.time() - clarity_start
        print(f"   耗时: {clarity_time:.2f}秒")
        print(f"   是否清晰: {'是' if clarity_result else '否'}\n")
    else:
        print("4. 清晰度检查: 跳过（非车控）\n")
    
    # 5. 完整流程（并行）
    print("5. 测试完整流程（并行执行）:")
    full_start = time.time()
    full_result = await classifier.run(query)
    full_time = time.time() - full_start
    print(f"   耗时: {full_time:.2f}秒\n")
    
    # 性能总结
    print(f"{'='*70}")
    print("【性能总结】")
    print(f"  各任务单独耗时（串行）:")
    print(f"    - LLM分类: {llm_time:.2f}秒")
    print(f"    - 火山引擎API: {api_time:.2f}秒")
    print(f"    - RAG检索: {rag_time:.2f}秒")
    if clarity_time > 0:
        print(f"    - 清晰度检查: {clarity_time:.2f}秒")
        serial_total = llm_time + api_time + rag_time + clarity_time
        parallel_total = max(llm_time, api_time, rag_time, clarity_time)
    else:
        serial_total = llm_time + api_time + rag_time
        parallel_total = max(llm_time, api_time, rag_time)
        print(f"    - 清晰度检查: 未执行")
    
    print(f"\n  串行总耗时: {serial_total:.2f}秒")
    print(f"  并行理论耗时: {parallel_total:.2f}秒（最慢任务）")
    print(f"  实际并行耗时: {full_time:.2f}秒")
    
    if full_time > 0:
        efficiency = (parallel_total / full_time) * 100 if full_time > 0 else 0
        print(f"  并行效率: {efficiency:.1f}%")
    
    print(f"\n  最慢任务: ", end="")
    times = [
        ("LLM分类", llm_time),
        ("火山引擎API", api_time),
        ("RAG检索", rag_time),
    ]
    if clarity_time > 0:
        times.append(("清晰度检查", clarity_time))
    
    max_task = max(times, key=lambda x: x[1])
    print(f"{max_task[0]} ({max_task[1]:.2f}秒)")
    
    print(f"\n{'='*70}\n")
    
    # 清理资源：关闭所有 HTTP 会话
    await close_volcengine_session()
    await close_rag_session()


if __name__ == "__main__":
    asyncio.run(test_performance())

