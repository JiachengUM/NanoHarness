import time

from rich import print

from projects.mind.mem.volc_api.session import (
    SessionCreate,
    SessionID,
    Message,
    MessageContent,
    SessionMetadata,
    add_session,
    get_session_info,
    get_context,
)
from projects.mind.mem.volc_api.base import CollectionID
from projects.mind.mem.tests.volc_api.common import collection_default, collection_customize

def test_session_default():
    """测试添加会话"""
    now_ts = int(time.time() * 1000)  # 当前时间戳（毫秒）
    test_collection_id = CollectionID(collection_name="test_prompt")
    user_id="dzy_test_session"
    assistant_id = "dzy_test_assistant"
    session_id = "session_music"

    session = SessionCreate(
        collection_name=test_collection_id.collection_name,
        project_name=test_collection_id.project_name,
        resource_id=test_collection_id.resource_id,
        session_id=session_id,
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
            default_user_id=user_id,
            default_user_name="XiaoMing",
            default_assistant_id=assistant_id,
            default_assistant_name="Robot",
            time=now_ts,
        ),
    )

    try:
        session_id = add_session(test_collection_id,session.messages,session_id=session_id,metadata=session.metadata)
        print(f"添加会话成功:")
        print(session_id)
    except Exception as e:
        print(f"添加会话失败:")
        print(e)


    """测试查询会话信息"""
    session = SessionID(
        collection_name=test_collection_id.collection_name,
        session_id=session_id,
    )

    try:
        rsp = get_session_info(session)
        print(f"查询会话信息结果成功 with {session_id}:")
        print(rsp)
    except Exception as e:
        print(f"查询会话信息结果失败 with {session_id}:")
        print(e)

    """测试查询会话上下文"""
    try:
        # 等30秒等待记忆生成
        from tqdm import tqdm
        for i in tqdm(range(30), desc="等待记忆生成"):
            time.sleep(1)

        rsp = get_context(
            collection_id=test_collection_id,
            conversation_id=session_id,
            query="我喜欢什么？",
            event_type=["event_v1"],
            event_search_user_id=user_id,
            event_search_assistant_id=assistant_id,
            profile_type=["interaction_records","work_notice","the_hint_fact_about_user"],
            profile_user_id=user_id,
            profile_assistant_id=assistant_id,
        )
        print(f"查询会话上下文结果成功 with {session_id}:")
        print("*"*80)
        print(rsp.data)
        new_session_id = rsp.data.session_id
        print("*"*80)
    except Exception as e:
        print(f"查询会话上下文结果失败 with {session_id}:")
        print(e)

    # assert new_session_id is not None
    """测试查询会话信息"""
    session = SessionID(
        collection_name=test_collection_id.collection_name,
        session_id=session_id,
    )

    try:
        rsp = get_session_info(session)
        print(f"查询新的会话信息结果成功 with {session_id}:")
        print(rsp)
    except Exception as e:
        print(f"查询新的会话信息结果失败 with {session_id}:")
        print(e)


if __name__ == "__main__":
    
    test_session_default()
