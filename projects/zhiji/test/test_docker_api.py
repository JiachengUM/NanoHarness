#!/usr/bin/env python3
"""
SGM Docker 镜像 API 测试脚本（Python 版本）
"""
import requests
import json
from typing import Dict, Any

API_URL = "http://10.0.53.244/zhiji-nanoai-dev/intent"

def print_response(case_name: str, response: requests.Response):
    """格式化打印响应"""
    print(f"\n{'='*50}")
    print(f"【{case_name}】")
    print(f"{'='*50}")
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"响应内容:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # 解析关键字段
        if response.status_code == 200:
            result_data = data.get("data", {})
            if result_data.get("reject"):
                print(f"\n 结果: 被拒识")
            else:
                print(f"\n 结果:")
                print(f"   - 领域: {result_data.get('domain', 'N/A')}")
                print(f"   - 意图类型: {result_data.get('intent_type', 'N/A')}")
                print(f"   - 字节API原始意图类型: {result_data.get('byte_intent_type', 'N/A')}")
                print(f"   - 输入: {result_data.get('input', 'N/A')}")
                print(f"   - 消息: {result_data.get('message', 'N/A')}")
                print(f"   - 复杂意图: {result_data.get('isComplexIntent', False)}")
    except Exception as e:
        print(f"解析响应失败: {e}")
        print(f"原始响应: {response.text}")

def test_case_1():
    """测试用例 1: 基础查询（无历史对话）"""
    payload = {
        "query": "帮我搜搜上海比较好吃的小笼包的餐厅吧，然后给我推荐三个。",
        "chat_id": "123456789",
        "history": [{
		"q": "导航一下上海市的小笼包。",
		"a": None
	}, {
		"q": "你接受到车门打开了，你就要把，你把车门打开信号发给我就行了，然后其他信号你触发了就发货。",
		"a": None
	}, {
		"q": "找一下上面最好吃的小笼包。",
		"a": "1. 地名：杭州小笼包(沧源二村店) ID：7141724717479626789\n2. 地名：桂满陇·蟹粉小笼包(环球港店) ID：6903268970506225677\n3. 地名：满口香小笼包(海鹏路店) ID：6623286409916581892\n4. 地名：仙云居小笼包(东兰路分店) ID：6875385270603237391\n5. 地名：仙云居小笼包(星苑小区店) ID：6918113688293476355\n6. 地名：满口香小笼包(新德西路店) ID：6983287165576808485\n7. 地名：仙云居小笼包(工农二村店) ID：6752235664449832971\n8. 地名：仙云居小笼包(杨浦区商业委员会供销经济园区松花江路分部店) ID：6753887934690166795\n9. 地名：仙云居小笼包(莘谭路店) ID：6998720058780289031\n为您推荐上海市的以下小笼包。"
	}]
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 1: 基础查询（无历史对话）", response)

def test_case_2():
    """测试用例 2: 带历史对话的查询"""
    payload = {
        "query": "播放这三首歌",
        "chat_id": "b11a891b-9d71-4cb5-94a0-f44dd63564cb",
        "vehicle_id": "7b811248-1b44-4f98-9a3f-555685ade4ff",
        "longitude": 121.5073,
        "latitude": 31.1953,
        "history": [
            {
                "q": "周杰伦最火的三首歌是啥",
                "a": "分别是七里香、稻香、晴天，是否需要为您播放其中一首"
            }
        ],
        "car_info": {
            "mainEngine": "main",
            "vehicleId": "7b811248-1b44-4f98-9a3f-555685ade4ff",
            "longitude": 121.5073,
            "latitude": 31.1953
        }
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 2: 带历史对话的查询", response)

def test_case_3():
    """测试用例 3: 带车辆信息的查询"""
    payload = {
        "query": "打开空调",
        "chat_id": "test-chat-003",
        "car_info": {
            "vehicle_name": "测试车型"
        }
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 3: 带车辆信息的查询", response)

def test_case_4():
    """测试用例 4: 复杂意图（复杂模糊车控）"""
    payload = {
        "query": "我想去一个地方吃东西",
        "chat_id": "test-chat-004"
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 4: 复杂意图（复杂模糊车控）", response)

def test_case_5():
    """测试用例 5: 定制业务（旅游规划）"""
    payload = {
        "query": "推荐附近适合带老人吃的川菜馆",
        "chat_id": "test-chat-005"
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 5: 定制业务（旅游规划）", response)

def test_case_6():
    """测试用例 6: 可能被拒识的查询"""
    payload = {
        "query": "你好，陪我聊聊天吧",
        "chat_id": "test-chat-006"
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 6: 可能被拒识的查询", response)

def test_case_7():
    """测试用例 7: 完整参数（所有字段）"""
    payload = {
        "query": "播放《蔡康永的情商课》",
        "chat_id": "test-chat-007",
        "history": [
            {
                "q": "我想听点东西",
                "a": "好的，我可以为您推荐一些内容"
            },
            {
                "q": "有什么推荐的？",
                "a": "可以为您播放音乐、有声书等"
            }
        ],
        "car_info": {
            "vehicle_name": "测试车型A"
        }
    }
    response = requests.post(API_URL, json=payload)
    print_response("测试用例 7: 完整参数（所有字段）", response)

def main():
    """运行所有测试用例"""
    print("="*50)
    print("SGM Docker 镜像 API 测试（Python 版本）")
    print("="*50)
    
    # 检查服务是否可用
    print(f"测试目标: {API_URL}")
    try:
        test_payload = {"query": "测试", "chat_id": "health-check"}
        health_check = requests.post(API_URL, json=test_payload, timeout=10)
        if health_check.status_code == 200:
            print("API 服务可用")
        else:
            print(f"警告: API 返回状态码 {health_check.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"警告: 无法连接到 API 服务 ({e})")
        print(" 继续执行测试用例...")
    
    # 运行测试用例
    test_case_1()
    test_case_2()
    test_case_3()
    test_case_4()
    test_case_5()
    test_case_6()
    test_case_7()
    
    print("\n" + "="*50)
    print("所有测试用例执行完成")
    print("="*50)

if __name__ == "__main__":
    main()

