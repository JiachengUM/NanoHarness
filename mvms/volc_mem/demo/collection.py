"""
Demo: 火山引擎 Memory Collection 管理脚本

Collection（记忆库）是存储和管理所有记忆数据的容器。
在使用 Memory API 之前，需要先创建一个 Collection。

支持的操作：
    - create: 创建新的记忆库
    - update: 更新记忆库配置（如添加自定义事件类型）
    - info: 查询记忆库详细信息
    - list: 列出所有记忆库
    - delete: 删除记忆库
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，以便导入项目模块
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mvms.volc_mem.common.client import internal_request

# 记忆库名称，所有操作都基于此名称
COLLECTION_NAME = "my_first_memory_collection"


def create_collection():
    """
    创建新的记忆库（Collection）
    
    功能说明：
        创建一个新的记忆库，用于存储和管理用户记忆数据。
        记忆库定义了可以存储的事件类型（Event Types）和画像类型（Profile Types）。
    
    参数说明：
        - CollectionName: 记忆库名称，必须唯一
        - Description: 记忆库描述信息
        - BuiltinEventTypes: 内置事件类型列表，如 ["sys_event_v1"] 表示使用系统内置的事件类型
        - BuiltinProfileTypes: 内置画像类型列表，如 ["sys_profile_v1"] 表示使用系统内置的画像类型
    
    使用场景：
        - 首次使用 Memory API 时需要创建记忆库
        - 为不同业务场景创建独立的记忆库
    """
    path = "/api/memory/collection/create"
    payload = {
        "CollectionName": COLLECTION_NAME,
        "Description": "test description",
        "BuiltinEventTypes": ["sys_event_v1"],  # 使用系统内置的事件类型
        "BuiltinProfileTypes": ["sys_profile_v1"],  # 使用系统内置的画像类型
    }
    return internal_request("POST", path, payload)


def update_collection():
    """
    更新记忆库配置
    
    功能说明：
        更新已存在的记忆库配置，可以修改描述信息、添加自定义事件类型（CustomEventTypeSchemas）
        或自定义画像类型（CustomProfileTypeSchemas）。
    
    参数说明：
        - CollectionName: 要更新的记忆库名称
        - Description: 更新后的描述信息
        - CustomEventTypeSchemas: 自定义事件类型列表，定义业务特定的数据结构
            - EventType: 事件类型名称
            - Description: 事件类型描述
            - Properties: 事件属性列表，定义该事件包含哪些字段
                - PropertyName: 属性名称
                - PropertyValueType: 属性值类型（string, int64, float 等）
                - Description: 属性描述
            - Version: Schema 版本号
    
    使用场景：
        - 需要添加业务特定的自定义事件类型
        - 需要修改记忆库描述信息
    """
    path = "/api/memory/collection/update"
    payload = {
        "CollectionName": COLLECTION_NAME,
        "Description": "用于记录和分析学生英语学习过程的记忆库",
        "CustomEventTypeSchemas": [
            {
                "EventType": "english_study",
                "Description": "记录一次英语学习会话中助教与学生的问答及评分",
                "Properties": [
                    {
                        "PropertyName": "knowledge_point_name",
                        "PropertyValueType": "string",
                        "Description": "当前对话涉及的知识点名称",
                    },
                    {
                        "PropertyName": "question",
                        "PropertyValueType": "string",
                        "Description": "助教提出的问题",
                    },
                    {
                        "PropertyName": "answer",
                        "PropertyValueType": "string",
                        "Description": "学生的回答",
                    },
                    {
                        "PropertyName": "rating_score",
                        "PropertyValueType": "int64",
                        "Description": "对学生回答的数值评分",
                    },
                    {
                        "PropertyName": "fluency_score",
                        "PropertyValueType": "int64",
                        "Description": "口语流利度评分 (1-5)",
                    },
                ],
                "Version": "2",
            }
        ],
    }
    return internal_request("POST", path, payload)


def get_collection_info():
    """
    查询记忆库详细信息
    
    功能说明：
        获取指定记忆库的详细配置信息，包括：
        - 记忆库描述
        - 支持的事件类型列表（内置 + 自定义）
        - 支持的画像类型列表（内置 + 自定义）
        - Schema 定义等
    
    参数说明：
        - CollectionName: 要查询的记忆库名称
    
    使用场景：
        - 查看记忆库配置是否正确
        - 确认支持的事件类型和画像类型
        - 调试时查看 Schema 定义
    """
    path = "/api/memory/collection/info"
    payload = {
        "CollectionName": COLLECTION_NAME
    }
    return internal_request("POST", path, payload)


def list_collections():
    """
    列出所有记忆库
    
    功能说明：
        获取指定项目下的所有记忆库列表。
    
    参数说明：
        - project_name: 项目名称，默认为 "default"
    
    使用场景：
        - 查看当前项目下有哪些记忆库
        - 管理多个记忆库时查看列表
    """
    path = "/api/memory/collection/list"
    payload = {
        "project_name": "default"
    }
    return internal_request("POST", path, payload)


def delete_collection():
    """
    删除记忆库
    
    功能说明：
        删除指定的记忆库。注意：删除操作会同时删除该记忆库下的所有数据，
        包括会话、事件、画像等，此操作不可恢复，请谨慎使用。
    
    参数说明：
        - CollectionName: 要删除的记忆库名称
    
    使用场景：
        - 清理测试数据
        - 不再使用的记忆库需要删除
    """
    path = "/api/memory/collection/delete"
    payload = {
        "CollectionName": COLLECTION_NAME
    }
    return internal_request("POST", path, payload)


def main():
    rsp = create_collection()
    # rsp = update_collection()
    # rsp = get_collection_info()
    # rsp = list_collections()
    # rsp = delete_collection()

    try:
        print(json.dumps(rsp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(rsp.status_code, rsp.text)


if __name__ == "__main__":
    main()