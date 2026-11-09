#!/usr/bin/env python3
"""
测试新的意图识别API接口
"""
import asyncio
import time
from pathlib import Path
import sys

# 将项目根目录添加到Python路径
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from projects.SGM.common.engine_api import volcengine_intent, HistoryItem, close_volcengine_session

async def test_intent_recognition():
    """测试意图识别功能"""
    print("=== 测试意图识别功能 ===")
    
    # 测试用例1：正常意图识别
    print("\n1. 测试正常意图识别:")
    query1 = "如果小朋友睡着了，把空调调低一点"
    start_time = time.time()
    result1 = await volcengine_intent(query1)
    elapsed_time = time.time() - start_time
    print(f"查询: {query1}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result1.reject}")
    if not result1.reject and result1.intent:
        print(f"领域: {result1.intent.domain}")
        print(f"意图类型: {result1.intent.intent_type}")
        print(f"原始意图类型: {result1.intent.origin_intent_type}")
        print(f"输入: {result1.intent.input}")
        print(f"消息: {result1.intent.message}")
        print(f"下一步处理: {result1.intent.next_process}")
    print(f"问题ID: {result1.question_id}")
    
    # 测试用例2：可能被拒识的查询
    print("\n2. 测试可能被拒识的查询:")
    query2 = "随便说点什么"
    start_time = time.time()
    result2 = await volcengine_intent(query2)
    elapsed_time = time.time() - start_time
    print(f"查询: {query2}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result2.reject}")
    if not result2.reject and result2.intent:
        print(f"领域: {result2.intent.domain}")
        print(f"意图类型: {result2.intent.intent_type}")
        print(f"输入: {result2.intent.input}")
    print(f"问题ID: {result2.question_id}")
    
    # 测试用例3：车辆控制相关
    print("\n3. 测试车辆控制相关:")
    query3 = "打开空调"
    start_time = time.time()
    result3 = await volcengine_intent(query3)
    elapsed_time = time.time() - start_time
    print(f"查询: {query3}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result3.reject}")
    if not result3.reject and result3.intent:
        print(f"领域: {result3.intent.domain}")
        print(f"意图类型: {result3.intent.intent_type}")
        print(f"输入: {result3.intent.input}")
        print(f"槽位数据: {result3.intent.slot_data}")
    print(f"问题ID: {result3.question_id}")
    
    # 测试用例4：连续对话测试（同一chat_id，不传history）
    print("\n4. 测试连续对话（同一chat_id，不传history）:")
    chat_id = "test_chat_001"
    
    # 第一句话
    print(f"\n第一句话:")
    query4_1 = "帮我打开座椅加热"
    start_time = time.time()
    result4_1 = await volcengine_intent(query4_1, chat_id=chat_id)
    elapsed_time = time.time() - start_time
    print(f"查询: {query4_1}")
    print(f"chat_id: {chat_id}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result4_1.reject}")
    if not result4_1.reject and result4_1.intent:
        print(f"领域: {result4_1.intent.domain}")
        print(f"意图类型: {result4_1.intent.intent_type}")
        print(f"输入: {result4_1.intent.input}")
        print(f"槽位数据: {result4_1.intent.slot_data}")
    print(f"问题ID: {result4_1.question_id}")
    
    # 第二句话（使用同一个chat_id，API应该能基于chat_id维护上下文）
    print(f"\n第二句话（基于chat_id上下文）:")
    query4_2 = "打开前排的"
    start_time = time.time()
    result4_2 = await volcengine_intent(query4_2, chat_id=chat_id)
    elapsed_time = time.time() - start_time
    print(f"查询: {query4_2}")
    print(f"chat_id: {chat_id}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result4_2.reject}")
    if not result4_2.reject and result4_2.intent:
        print(f"领域: {result4_2.intent.domain}")
        print(f"意图类型: {result4_2.intent.intent_type}")
        print(f"输入: {result4_2.intent.input}")
        print(f"槽位数据: {result4_2.intent.slot_data}")
        
        # 验证意图类型
        if result4_2.intent.intent_type == "vehicle_control":
            print("✓ 第二句话成功识别为 vehicle_control")
        else:
            print(f"✗ 第二句话的意图类型是 {result4_2.intent.intent_type}，不是 vehicle_control")
    else:
        print("✗ 第二句话被拒识或没有识别到意图")
    print(f"问题ID: {result4_2.question_id}")
    
    # 测试用例5：连续对话测试（使用history参数，对比效果）
    print("\n" + "="*60)
    print("5. 测试连续对话（使用history参数，对比效果）:")
    chat_id_with_history = "test_chat_002"
    
    # 第一句话
    print(f"\n第一句话:")
    query5_1 = "今天天气怎么样"
    start_time = time.time()
    result5_1 = await volcengine_intent(query5_1, chat_id=chat_id_with_history)
    elapsed_time = time.time() - start_time
    print(f"查询: {query5_1}")
    print(f"chat_id: {chat_id_with_history}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result5_1.reject}")
    if not result5_1.reject and result5_1.intent:
        print(f"领域: {result5_1.intent.domain}")
        print(f"意图类型: {result5_1.intent.intent_type}")
        print(f"输入: {result5_1.intent.input}")
        print(f"槽位数据: {result5_1.intent.slot_data}")
    print(f"问题ID: {result5_1.question_id}")
    
    # 构建历史记录（使用第一句的实际结果来构建更真实的history）
    history = [
        HistoryItem(
            q=query5_1,
            a="今天天气很好"  # 模拟的回答
        )
    ]
    
    # 第二句话（使用history参数，显式传递上下文）
    print(f"\n第二句话（使用history参数）:")
    query5_2 = "那上海呢"
    start_time = time.time()
    result5_2 = await volcengine_intent(query5_2, chat_id=chat_id_with_history, history=history)
    elapsed_time = time.time() - start_time
    print(f"查询: {query5_2}")
    print(f"chat_id: {chat_id_with_history}")
    print(f"history: {[{'q': h.q, 'a': h.a} for h in history]}")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result5_2.reject}")
    if not result5_2.reject and result5_2.intent:
        print(f"领域: {result5_2.intent.domain}")
        print(f"意图类型: {result5_2.intent.intent_type}")
        print(f"输入: {result5_2.intent.input}")
        print(f"槽位数据: {result5_2.intent.slot_data}")
        
        # 验证意图类型
        if result5_2.intent.intent_type == "vehicle_control":
            print("✓ 第二句话成功识别为 vehicle_control")
        else:
            print(f"✗ 第二句话的意图类型是 {result5_2.intent.intent_type}，不是 vehicle_control")
    else:
        print("✗ 第二句话被拒识或没有识别到意图")
    print(f"问题ID: {result5_2.question_id}")
    
    # 对比总结
    print("\n" + "="*60)
    print("对比总结:")
    print(f"测试用例4（仅chat_id）:")
    print(f"  - 第二句话意图类型: {result4_2.intent.intent_type if result4_2.intent else 'N/A'}")
    print(f"  - 是否识别为vehicle_control: {'是' if result4_2.intent and result4_2.intent.intent_type == 'vehicle_control' else '否'}")
    print(f"\n测试用例5（chat_id + history）:")
    print(f"  - 第二句话意图类型: {result5_2.intent.intent_type if result5_2.intent else 'N/A'}")
    print(f"  - 是否识别为vehicle_control: {'是' if result5_2.intent and result5_2.intent.intent_type == 'vehicle_control' else '否'}")
    
    # 测试用例6：测试额外参数（vehicle_id, vehicle_name, longitude, latitude）
    print("\n" + "="*60)
    print("6. 测试额外参数（vehicle_id, vehicle_name, longitude, latitude）:")
    query6 = "帮我导航到天安门"
    start_time = time.time()
    result6 = await volcengine_intent(
        query6,
        chat_id="test_chat_003",
        vehicle_id="test_vehicle_001",
        vehicle_name="Model X",
        longitude=116.3974,
        latitude=39.9093
    )
    elapsed_time = time.time() - start_time
    print(f"查询: {query6}")
    print(f"参数: vehicle_id=test_vehicle_001, vehicle_name=Model X, longitude=116.3974, latitude=39.9093")
    print(f"耗时: {elapsed_time:.2f}秒")
    print(f"是否拒识: {result6.reject}")
    if not result6.reject and result6.intent:
        print(f"领域: {result6.intent.domain}")
        print(f"意图类型: {result6.intent.intent_type}")
        print(f"输入: {result6.intent.input}")
    print(f"问题ID: {result6.question_id}")
    
    # 清理资源：关闭所有 HTTP 会话
    await close_volcengine_session()


if __name__ == "__main__":
    asyncio.run(test_intent_recognition())
