"""
来自https://www.volcengine.com/docs/84313/1946661?lang=zh
看起来比较干净，实际上有各种问题，没有必要使用，自己包http API即可：
- VikingMem本质上就是client。多余的概念。
- get_collection没有必要是class method，就是普通function。带client参数即可。
- vikingdb的实现质量，代码细节一言难尽。
"""

import os
import time
from vikingdb.memory import VikingMem
from vikingdb import APIKey

API_KEY = os.getenv("MEMORY_API_KEY", "your_key")

client = VikingMem(
    host = "api-knowledgebase.mlp.cn-beijing.volces.com",
    region = "cn-beijing",
    auth= APIKey(api_key=API_KEY),
    scheme = "http",
)

collection = client.get_collection(
    collection_name="my_first_memory_collection",  # 替换为你的记忆库名称
    project_name="default"
)

def add_session():    
    now_ts = int(time.time() * 1000)
    result = collection.add_session(
        session_id="session_001",
        messages=[
            {
                "role": "user",
                "content": "今天天气怎么样？"
            },
            {
                "role": "assistant",
                "content": "今天天气晴朗，气温22度，非常适合外出。"
            }
        ],
        metadata = {
            "default_user_id": "user_01",
            "default_user_name": "XiaoMing",
            "default_assistant_id": "assistant_01",
            "default_assistant_name": "Robot",
            "time": now_ts,
        }
    ) 
    return result

if __name__ == "__main__":
    print("Viking Memory Add Session Messages Example")
    add_session()