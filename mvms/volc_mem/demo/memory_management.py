"""
Demo: 火山引擎 Memory Profile 管理脚本

Profile（用户画像）是系统对用户的长期记忆，包括用户的基本信息、偏好、习惯等。
Profile 会基于会话数据自动生成，也可以手动创建和更新。

支持的操作：
    - add profile: 手动添加用户画像
    - update profile: 更新已存在的用户画像
    - delete profile: 删除单个用户画像
    - batch delete profile: 批量删除用户画像
    - trigger profile update: 触发系统重新计算用户画像
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


def add_profile():
    """
    添加用户画像
    
    功能说明：
        手动创建一个新的用户画像。如果该用户已存在相同类型的画像，会返回错误。
        建议先检查是否存在，或使用 update_profile() 进行更新。
    
    参数说明：
        - collection_name: 记忆库名称
        - profile_type: 画像类型，如 "sys_profile_v1"（系统内置）或自定义类型
        - memory_info: 画像内容，格式取决于 profile_type 的 schema
            - 对于 sys_profile_v1，只支持 "user_profile" 字段（字符串类型）
        - user_id: 用户ID，标识该画像属于哪个用户
        - assistant_id: 助手ID，当启用助手隔离时必填，用于区分不同助手的记忆
    
    使用场景：
        - 手动初始化用户画像
        - 从外部系统导入用户信息
        - 补充系统自动生成画像中缺失的信息
    
    注意事项：
        - 如果启用助手隔离，必须提供 assistant_id
        - 相同的 (user_id, assistant_id, profile_type) 组合只能有一个画像
    """
    path = "/api/memory/profile/add"
    payload = {
        "collection_name": COLLECTION_NAME,
        "profile_type": "sys_profile_v1",  # 使用系统内置的画像类型
        "memory_info": {
            # sys_profile_v1 只支持 user_profile 字段，所有信息都放在这个字符串中
            "user_profile": "### 基础信息:性别 男/年龄 28/家乡 广州/职业 产品经理"
        },
        "user_id": "user_02",
        "assistant_id": "assistant_02",  # 启用 assistant 隔离时必填
    }
    return internal_request("POST", path, payload)


def update_profile():
    """
    更新指定 profile_id 的画像内容
    
    功能说明：
        更新已存在的用户画像内容。需要提供 profile_id（可通过查询或添加时获得）。
    
    参数说明：
        - collection_name: 记忆库名称
        - profile_id: 画像ID，唯一标识一个画像
        - memory_info: 更新后的画像内容，格式需符合对应 profile_type 的 schema
    
    使用场景：
        - 用户信息发生变化，需要更新画像
        - 补充或修正画像内容
        - 定期维护用户画像
    
    注意事项：
        - 必须提供正确的 profile_id
        - memory_info 格式必须符合 schema 定义
        - 更新会覆盖原有内容，不是合并
    """
    path = "/api/memory/profile/update"
    payload = {
        "collection_name": COLLECTION_NAME,
        "profile_id": "6954fc30e370fc4461bd29dd",  # 替换为实际 profile_id
        "memory_info": {
            "user_profile": "### 基础信息:性别 男/年龄 28/家乡 广州/职业 产品经理\n### 兴趣偏好:马拉松、跑步、健身"
        },
    }
    return internal_request("POST", path, payload)


def delete_profile():
    """
    删除单个用户画像
    
    功能说明：
        根据 profile_id 删除指定的用户画像。
    
    参数说明：
        - collection_name: 记忆库名称
        - profile_id: 要删除的画像ID
    
    使用场景：
        - 用户画像数据错误，需要删除后重新创建
        - 清理测试数据
        - 用户注销账号时删除相关画像
    
    注意事项：
        - 删除操作不可恢复
        - 删除后如需重新创建，使用 add_profile()
    """
    path = "/api/memory/profile/delete"
    payload = {
        "collection_name": COLLECTION_NAME,
        "profile_id": "6954fc30e370fc4461bd29dd",  # 替换为需要删除的画像 ID
    }
    return internal_request("POST", path, payload)


def batch_delete_profile():
    """
    按条件批量删除用户画像
    
    功能说明：
        根据过滤条件批量删除匹配的用户画像。支持按 user_id、profile_type 等条件过滤。
    
    参数说明：
        - collection_name: 记忆库名称
        - filter: 过滤条件
            - user_id: 用户ID列表，匹配这些用户的画像
            - profile_type: 画像类型列表，匹配这些类型的画像
            - 可以组合多个条件，满足任一条件即匹配
    
    使用场景：
        - 批量清理测试数据
        - 删除特定类型的所有画像
        - 清理特定用户的画像
    
    注意事项：
        - 批量删除操作不可恢复
    """
    path = "/api/memory/profile/batch_delete"
    payload = {
        "collection_name": COLLECTION_NAME,
        "filter": {
            "user_id": ["user_02"],  # 匹配这些用户ID
            "profile_type": ["sys_profile_v1"],  # 匹配这些画像类型
        },
    }
    return internal_request("POST", path, payload)


def trigger_profile_update():
    """
    触发指定 profile_type 的重算 / 更新
    
    功能说明：
        触发系统后台重新计算指定类型的所有用户画像。这是一个异步操作，
        系统会基于最新的会话数据重新分析并更新画像。
    
    参数说明：
        - collection_name: 记忆库名称
        - project_name: 项目名称，默认为 "default"
        - update_profile_type: 需要重算的画像类型列表
    
    使用场景：
        1. Schema 更新：修改了 collection 的 schema，需要重新计算所有画像以填充新字段
        2. 算法升级：画像计算算法更新，需要用新算法重新分析历史数据
        3. 数据修复：修复了会话数据后，需要基于修复后的数据重新生成画像
    """
    path = "/api/memory/profile/trigger_update"
    payload = {
        "collection_name": COLLECTION_NAME,
        "project_name": "default",
        "update_profile_type": [
            "profile_v1",  # 重算这些类型的画像
            "social network",
        ],
    }
    return internal_request("POST", path, payload)


def main():
    # ===== 选择要执行的操作 =====
    rsp = add_profile()
    # rsp = update_profile()
    # rsp = delete_profile()
    # rsp = batch_delete_profile()
    # rsp = trigger_profile_update()

    try:
        print(json.dumps(rsp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(rsp.status_code, rsp.text)


if __name__ == "__main__":
    main()
