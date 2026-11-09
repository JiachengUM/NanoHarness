"""
Demo: 火山引擎 Memory Session API

Session（会话）是用户与助手之间的对话记录。系统会基于会话数据自动提取和生成记忆。

支持的操作：
    - add session: 添加会话记录到记忆库
    - get session info: 查询会话的详细信息
"""

import json
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mvms.volc_mem.common.client import internal_request

COLLECTION_NAME = "my_first_memory_collection"
SESSION_ID = "session_001"  # 会话ID，用于标识不同的对话会话


def add_session():
    """
    添加会话记录到记忆库
    
    功能说明：
        将用户与助手之间的多轮对话记录添加到记忆库。
        系统会自动分析会话内容，提取关键信息并生成记忆（如用户偏好、习惯等）。
    
    参数说明：
        - collection_name: 记忆库名称
        - session_id: 会话ID，用于标识不同的对话会话（若使用相同的 session_id，会覆盖该对话之前生成的事件版本，并从画像中撤回之前生成的事件！！！）
        - messages: 对话消息列表，按时间顺序排列
            - role: 角色，可选 "user"（用户）或 "assistant"（助手）
            - content: 消息内容
        - metadata: 元数据信息
            - default_user_id: 默认用户ID，如果消息中没有指定，使用此值
            - default_user_name: 默认用户名
            - default_assistant_id: 默认助手ID
            - default_assistant_name: 默认助手名称
            - time: 时间戳（毫秒）
    
    使用场景：
        - 记录用户与助手的对话历史
        - 批量导入历史对话数据
        - 实时同步对话记录到记忆库
    """
    path = "/api/memory/session/add"

    now_ts = int(time.time() * 1000)  # 当前时间戳（毫秒）

    payload = {
        "collection_name": COLLECTION_NAME,
        "session_id": SESSION_ID,
        # "messages": [
        #     # 对话消息列表，按时间顺序排列
        #     {"role": "user", "content": "我一般冬天开空调都会调到28度，不然太冷了"},
        #     {"role": "assistant", "content": "好的，那冬天我帮你记住空调偏好是28度。"},
        #     {"role": "user", "content": "夏天的话我更喜欢24度，凉快一点"},
        #     {"role": "assistant", "content": "明白了，夏天空调偏好是24度。"},
        #     {"role": "user", "content": "以后我只说开空调的时候，就按这个来吧"},
        #     {"role": "assistant", "content": "好的，以后在你没有特别说明时，我会按你的空调偏好自动调节。"},
        #     {"role": "user", "content": "现在帮我把空调打开"},
        #     {"role": "assistant", "content": "好的，正在帮你打开空调。"}
        # ],
        "messages": [
            {"role": "user", "content": "我最近特别迷上了流行和R&B的音乐，尤其是周杰伦的歌。"},
            {"role": "assistant", "content": "周杰伦的歌确实很经典，有没有特别喜欢的专辑？"},
            {"role": "user", "content": "我最喜欢他的《叶惠美》和《七里香》，几乎每天晚上都会听几首。"},
            {"role": "assistant", "content": "看来你晚上是听歌放松型的呀，有没有其他喜欢的歌手？"},
            {"role": "user", "content": "Adele我也挺喜欢的，她的《Someone Like You》百听不厌。"}
        ],
        # "messages": [
        #     {"role": "user", "content": "记一下我做瑜伽的地方在万达广场1号楼"},
        #     {"role": "assistant", "content": "好的，已经帮你记下来了。"},
        #     {"role": "user", "content": "记一下我爸妈家在万达广场3号楼"},
        #     {"role": "assistant", "content": "明白了，爸妈家的地址我也记住了。"},
        #     {"role": "user", "content": "我要去做瑜伽"},
        #     {"role": "assistant", "content": "好的，我可以帮你导航。"}
        #],
        "metadata": {
            "default_user_id": "user_01",  # 默认用户ID
            "default_user_name": "XiaoMing",  # 默认用户名
            "default_assistant_id": "assistant_01",  # 默认助手ID
            "default_assistant_name": "Robot",  # 默认助手名称
            "time": now_ts,  # 会话时间戳
        },
    }

    resp = internal_request("POST", path, payload)
    return resp


def get_session_info():
    """
    查询会话的详细信息
    
    功能说明：
        获取指定会话的详细信息，包括会话中的所有消息、元数据等。
    
    参数说明：
        - collection_name: 记忆库名称
        - session_id: 要查询的会话ID
    
    使用场景：
        - 查看历史对话记录
    """
    path = "/api/memory/session/info"

    payload = {
        "collection_name": COLLECTION_NAME,
        "session_id": SESSION_ID,  # 要查询的会话ID
    }

    resp = internal_request("POST", path, payload)
    return resp


def main():
    # resp = add_session()
    resp = get_session_info()

    try:
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(resp.status_code, resp.text)


if __name__ == "__main__":
    main()
