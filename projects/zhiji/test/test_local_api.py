#!/usr/bin/env python3
"""本地 API 测试脚本"""

import requests
import json
import sys

url = "http://localhost:8000/intent"

def test_api(payload, test_name):
    """测试 API 接口"""
    print(f"\n{'='*70}")
    print(f"【{test_name}】")
    print(f"{'='*70}")
    print(f"请求 URL: {url}")
    print(f"请求数据: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n响应结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"\n错误响应:")
            print(f"状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n 连接错误: 无法连接到服务器")
        print(f"   请确保服务已启动: uvicorn projects.zhiji.main:app --host 0.0.0.0 --port 8000")
        return False
    except requests.exceptions.Timeout:
        print(f"\n 请求超时: 服务器响应时间过长")
        return False
    except requests.exceptions.RequestException as e:
        print(f"\n 请求异常: {e}")
        return False
    except Exception as e:
        print(f"\n 未知错误: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    # 测试用例1: 闲聊
    payload1 = {
        "query": "我要导航",
        "chat_id": "test-chat-001",
        "history":[
        {
            "q":"你好！",
            "a":"嗯"
        }],
        "car_info": {
            "vehicle_name": "Tesla Model Y",
        },
        "vehicle_id": "test-vehicle-001"
    }
    test_api(payload1, "测试用例1 - 闲聊")
    
    # 测试用例2: 复杂导航（不带 car_info）
    payload2 = {
        "query": "看看附近最近的海底捞然后导航过去",
        "chat_id": "test-chat-002",
        "vehicle_id": "test-vehicle-001"
    }
    test_api(payload2, "测试用例2 - 复杂导航（不带 car_info）")
    
    # 测试用例3: 带 car_info 的复杂导航
    payload3 = {
        "query": "看看附近最近的海底捞然后导航过去",
        "chat_id": "test-chat-003",
        "car_info": {
            "vehicle_name": "Tesla Model Y",
            "sound_zone": "主驾",
            "current_location": "上海市浦东新区",
            "battery": 80,
            "song": "正在播放的歌名",
            "singer": "歌手名"
        },
        "longitude": 121.5073,
        "latitude": 31.1953,
        "vehicle_id": "test-vehicle-001"
    }
    test_api(payload3, "测试用例3 - 复杂导航（带 car_info）")
    
    # 测试用例4: 带 car_info 的闲聊
    payload4 = {
        "query": "陪我聊聊天",
        "chat_id": "test-chat-004",
        "car_info": {
            "vehicle_name": "Tesla Model Y",
            "sound_zone": "副驾",
            "current_location": "北京市朝阳区"
        },
        "vehicle_id": "test-vehicle-001"
    }
    test_api(payload4, "测试用例4 - 闲聊（带 car_info）")
    
    print(f"\n{'='*70}\n")