#!/usr/bin/env python3
"""测试火山引擎 API 的返回值和配置"""

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
    close_volcengine_session
)



async def test_volcengine_api():
    """测试火山引擎 API"""
    
    # 测试用例：我要导航
    query = "我要导航"
    chat_id = "test-chat-001"
    history = [
        HistoryItem(q="你好！", a="嗯")
    ]
    car_info = CarInfo(vehicle_name="Tesla Model Y")

    result = await volcengine_intent(
        query=query,
        history=history,
        chat_id=chat_id,
        car_info=car_info,
    )
    await close_volcengine_session()
    print("=" * 80)
    print("【API 返回结果】: ", result)
    print("=" * 80)
    
        

def main():
    asyncio.run(test_volcengine_api())
    return

if __name__ == "__main__":
    main()

