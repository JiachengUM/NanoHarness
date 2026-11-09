#!/usr/bin/env python3
"""
简单的火山模型测试脚本
"""

import requests
import json

# 火山模型配置
VOLCANO_CONFIG = {
    "api_key": "REDACTED",
    "api_endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "model": "doubao-seed-1-6-flash-250615"
}

def test_openai_client():
    from openai import OpenAI
    
    # 火山引擎API兼容配置
    # 需要使用正确的base_url格式，去掉具体的路径
    base_url = "https://ark.cn-beijing.volces.com/api/v3"
    
    try:
        print(f"使用火山引擎兼容配置...")
        print(f"Base URL: {base_url}")
        print(f"模型: {VOLCANO_CONFIG['model']}")
        
        client = OpenAI(
            base_url=base_url,
            api_key=VOLCANO_CONFIG["api_key"]
        )
        
        response = client.chat.completions.create(
            model=VOLCANO_CONFIG["model"],
            messages=[
                {"role": "user", "content": "你好，请简单介绍一下你自己。"}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        print("✅ OpenAI客户端连接成功！")
        print(f"模型回复: {response.choices[0].message.content}")
        print(f"使用的模型: {response.model}")
        print(f"Token使用情况: {response.usage}")
        
    except Exception as e:
        print(f"❌ OpenAI客户端错误: {e}")
        print("错误类型:", type(e).__name__)
        
        # 尝试备用配置
        try_alternative_config()

def try_alternative_config():
    """尝试备用的OpenAI客户端配置"""
    from openai import OpenAI
    import os
    
    print("\n尝试备用配置...")
    
    # 方法1: 使用环境变量方式
    os.environ['OPENAI_API_KEY'] = VOLCANO_CONFIG["api_key"]
    os.environ['OPENAI_BASE_URL'] = "https://ark.cn-beijing.volces.com/api/v3"
    
    try:
        client = OpenAI()  # 会自动读取环境变量
        
        response = client.chat.completions.create(
            model=VOLCANO_CONFIG["model"],
            messages=[
                {"role": "user", "content": "测试环境变量配置"}
            ],
            max_tokens=50,
            temperature=0.5
        )
        
        print("✅ 环境变量配置成功！")
        print(f"模型回复: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ 环境变量配置也失败: {e}")
        
        # 方法2: 直接指定完整端点
        try_direct_endpoint()

def try_direct_endpoint():
    """尝试直接指定完整端点"""
    from openai import OpenAI
    
    print("\n尝试直接端点配置...")
    
    # 完整的端点URL
    full_endpoint = VOLCANO_CONFIG["api_endpoint"].replace("/chat/completions", "")
    
    try:
        client = OpenAI(
            base_url=full_endpoint,
            api_key=VOLCANO_CONFIG["api_key"],
            timeout=30.0
        )
        
        response = client.chat.completions.create(
            model=VOLCANO_CONFIG["model"],
            messages=[
                {"role": "user", "content": "测试直接端点配置"}
            ],
            max_tokens=50
        )
        
        print("✅ 直接端点配置成功！")
        print(f"模型回复: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ 直接端点配置失败: {e}")
        print("\n建议：")
        print("1. 检查火山引擎API文档中的OpenAI兼容性说明")
        print("2. 确认模型名称是否正确")
        print("3. 确认API密钥是否有效")
        print("4. 使用requests版本作为备选方案")

def test_volcano_model():
    """测试火山模型API"""
    
    # 请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VOLCANO_CONFIG['api_key']}"
    }
    
    # 请求体
    data = {
        "model": VOLCANO_CONFIG["model"],
        "messages": [
            {"role": "user", "content": "你好，请简单介绍一下你自己。"}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    try:
        print("正在测试火山模型...")
        print(f"模型: {VOLCANO_CONFIG['model']}")
        print(f"API端点: {VOLCANO_CONFIG['api_endpoint']}")
        print("-" * 50)
        
        # 发送请求
        response = requests.post(
            VOLCANO_CONFIG["api_endpoint"],
            headers=headers,
            json=data,
            timeout=30
        )
        
        # 检查响应状态
        if response.status_code == 200:
            result = response.json()
            print("✅ 连接成功！")
            print(f"响应状态: {response.status_code}")
            
            # 提取回复内容
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                print(f"模型回复: {content}")
            else:
                print("响应格式异常:", result)
                
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求错误: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")

if __name__ == "__main__":
    print("=== 测试OpenAI客户端版本 ===")
    test_openai_client()
    print("\n=== 测试Requests版本 ===")
    test_volcano_model()