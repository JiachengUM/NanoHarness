"""
Demo: 搜索火山引擎记忆库

功能：
    - 根据关键词搜索记忆
    - 支持 user_id / memory_type 过滤
    - 支持结果数量限制
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from mvms.volc_mem.common.client import internal_request

COLLECTION_NAME = "my_first_memory_collection"


def main():
    """
    搜索记忆库中的记忆数据
    
    功能说明：
        根据关键词在记忆库中搜索相关的记忆，支持多种过滤条件。
        搜索结果包括匹配的会话、事件、画像等记忆数据。
    
    参数说明：
        - collection_name: 记忆库名称
        - query: 搜索关键词，系统会基于语义相似度匹配
        - limit: 返回结果的最大数量
        - filter: 过滤条件（可选）
            - user_id: 用户ID，只搜索该用户的记忆
            - memory_type: 记忆类型列表，如 ["sys_event_v1", "sys_profile_v1"]
                - sys_event_v1: 系统事件类型
                - sys_profile_v1: 系统画像类型
                - 也可以使用自定义类型
    
    返回：
        Response 对象，包含匹配的记忆列表，每个记忆包含：
        - memory_id: 记忆ID
        - memory_type: 记忆类型
        - content: 记忆内容
        - score: 相似度分数
        - metadata: 元数据（如 user_id, time 等）
    
    使用场景：
        - 对话时检索相关记忆，提供上下文
        - 查找用户的历史偏好和习惯
        - 分析用户行为模式
        - 调试时查看存储的记忆内容
    """
    path = "/api/memory/search"
    
    payload = {
        "collection_name": COLLECTION_NAME,
        "query": "空调",  # 搜索关键词
        "limit": 2,  # 最多返回 2 条结果
        "filter": {
            "user_id": "user_01",  # 只搜索该用户的记忆
            "memory_type": ["sys_event_v1"],  # 只搜索事件类型的记忆
        },
    }

    rsp = internal_request("POST", path, payload)

    try:
        print(json.dumps(rsp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(rsp.text)


if __name__ == "__main__":
    main()