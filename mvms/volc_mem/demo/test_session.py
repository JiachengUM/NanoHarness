import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mvms.volc_mem.api.session import (
    AddSession,
    SessionInfo,
    Message,
    MessageContent,
    SessionMetadata,
    add_session,
    get_session_info,
)


def test_add_session():
    """测试添加会话"""
    now_ts = int(time.time() * 1000)  # 当前时间戳（毫秒）

    session = AddSession(
        collection_name="memory_test1",
        session_id="session_001",
        messages=[
            Message(
                role="user",
                content=[MessageContent(type="text", text="我最近特别迷上了流行和R&B的音乐，尤其是周杰伦的歌。")],
            ),
            Message(
                role="assistant",
                content=[MessageContent(type="text", text="周杰伦的歌确实很经典，有没有特别喜欢的专辑？")],
            ),
            Message(
                role="user",
                content=[MessageContent(type="text", text="我最喜欢他的《叶惠美》和《七里香》，几乎每天晚上都会听几首。")],
            ),
            Message(
                role="assistant",
                content=[MessageContent(type="text", text="看来你晚上是听歌放松型的呀，有没有其他喜欢的歌手？")],
            ),
            Message(
                role="user",
                content=[MessageContent(type="text", text="Adele我也挺喜欢的，她的《Someone Like You》百听不厌。")],
            ),
        ],
        metadata=SessionMetadata(
            default_user_id="user_01",
            default_user_name="XiaoMing",
            default_assistant_id="assistant_01",
            default_assistant_name="Robot",
            time=now_ts,
        ),
    )

    rsp = add_session(session)
    print(rsp.json())


def test_get_session_info():
    """测试查询会话信息"""
    session = SessionInfo(
        collection_name="memory_test1",
        session_id="session_001"
    )

    rsp = get_session_info(session)
    print(rsp.json())


if __name__ == "__main__":
    # test_add_session()
    test_get_session_info()
