#!/usr/bin/env python3
"""测试火山引擎 API 的返回值和配置"""

import asyncio
from rich import print

from projects.mind.intent.alg.volc_intent import (
    volcengine_intent,
    Message,
    CarInfo,
    close_volcengine_session
)


async def test_volcengine_api():
    """测试火山引擎 API"""
    
    # 测试用例：我要导航
    query = "我要导航"
    chat_id = "test-chat-001"
    vehicle_id = "test-vehicle-001"
    history = [
        Message(role="user", content="你好！"),
        Message(role="assistant", content="嗯")
    ]
    car_info = CarInfo(vehicle_name="Tesla Model Y")

    result = await volcengine_intent(
        query=query,
        history=history,
        chat_id=chat_id,
        vehicle_id=vehicle_id,
        car_info=car_info,
    )
    await close_volcengine_session()
    print("【API 返回结果】: ", result)
    
        
def main():
    asyncio.run(test_volcengine_api())
    return

if __name__ == "__main__":
    main()
