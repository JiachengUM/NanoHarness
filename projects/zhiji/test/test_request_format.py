#!/usr/bin/env python3
"""测试所有参数非空时的请求 URL 和 Body 格式"""

import asyncio
import json
import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from projects.zhiji.common.engine_api import (
    volcengine_intent,
    HistoryItem,
    CarInfo,
    _prepare_volcengine_querystr,
)


async def test_request_format():
    """测试所有参数非空时的请求格式"""
    
    # 准备所有参数
    query = "我要导航"
    chat_id = "test-chat-001"
    history = [
        HistoryItem(q="你好！", a="嗯")
    ]
    car_info = CarInfo(
        vehicle_name="Tesla Model Y",
        sound_zone="主驾",
        current_location="北京市朝阳区",
        battery=80,
    )
    vehicle_id = "test-vehicle-001"
    vehicle_name = "Tesla Model Y"
    longitude = 121.5073
    latitude = 31.1953
    function_call_version = "v1.0"
    
    print("=" * 80)
    print("【测试：所有参数非空时的请求格式】")
    print("=" * 80)
    print(f"Query: {query}")
    print(f"Chat ID: {chat_id}")
    print(f"Vehicle ID: {vehicle_id}")
    print(f"Vehicle Name: {vehicle_name}")
    print(f"Longitude: {longitude}")
    print(f"Latitude: {latitude}")
    print(f"Function Call Version: {function_call_version}")
    print(f"History: {[{'q': h.q, 'a': h.a} for h in history]}")
    print(f"Car Info: {car_info.model_dump(exclude_none=True)}")
    print()
    
    # 手动构建请求信息（模拟实际调用）
    from projects.zhiji.common.engine_api import (
        VOLCENGINE_CHANNEL,
        VOLCENGINE_APP_ID,
    )
    import random
    import time
    
    # 构建 query string
    querystr = _prepare_volcengine_querystr(
        chat_id=chat_id,
        vehicle_id=vehicle_id,
        channel=VOLCENGINE_CHANNEL,
        app_id=VOLCENGINE_APP_ID,
    )
    
    # 构建 body（模拟实际逻辑）
    body_dict = {
        "query": query,
        "chat_id": chat_id,
        "history": [{"q": h.q, "a": h.a or ""} for h in history],
        "car_info": car_info.model_dump(exclude_none=True),
        "longitude": longitude,
        "latitude": latitude,
        "vehicle_id": vehicle_id,
        "vehicle_name": vehicle_name,
        "function_call_version": function_call_version,
    }
    
    url = "https://api-vehicle.volcengine.com/dpfm/v1/plugin/do/prepare"
    
    print("=" * 80)
    print("【请求 URL】")
    print("=" * 80)
    print(f"{url}?{querystr}")
    print()
    
    print("=" * 80)
    print("【请求 Body】")
    print("=" * 80)
    print(json.dumps(body_dict, indent=2, ensure_ascii=False))
    print()
    
    # 实际调用验证
    print("=" * 80)
    print("【实际调用验证】")
    print("=" * 80)
    try:
        result = await volcengine_intent(
            query=query,
            history=history,
            chat_id=chat_id,
            car_info=car_info,
            vehicle_id=vehicle_id,
            vehicle_name=vehicle_name,
            longitude=longitude,
            latitude=latitude,
            function_call_version=function_call_version,
        )
        print(f"调用成功: reject={result.reject}")
        if result.intent:
            print(f"Intent Type: {result.intent.intent_type}")
    except Exception as e:
        print(f"调用失败: {type(e).__name__}: {e}")
    finally:
        from projects.zhiji.common.engine_api import close_volcengine_session
        await close_volcengine_session()


if __name__ == "__main__":
    asyncio.run(test_request_format())
