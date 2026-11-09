from rich import print

from projects.mind.mem.volc_api import (
    Message,
    create_collection,
    SearchMemory,
    MemoryFilter,
    search_memory,
    add_to_memory,
)

def init_mem_db(db_name: str) -> str:
    """初始化记忆库"""

    try:
        id = create_collection(db_name)
        print(f"记忆库{db_name}创建成功, id={id}")
    except Exception as e:
        print(f"记忆库{db_name}已经存在")
        print(e)

    return db_name


def main():
    """主链路"""
    mem_db_name = init_mem_db("memory_for_benchi")

    user_id = "鹤群"
    session_id = "session_music"

    # 创建对话
    conversation = [
        Message(role="user", content="我最近很喜欢听周杰伦的歌。"),
        Message(role="assistant", content="周杰伦的歌确实很经典，有没有特别喜欢的专辑？"),
        Message(role="user", content="我最喜欢他的《叶惠美》和《七里香》，几乎每天晚上都会听几首。"),
        Message(role="assistant", content="看来你晚上是听歌放松型的呀，有没有其他喜欢的歌手？"),
    ]

    # 生成记忆
    do_add = False
    if do_add:
        add_to_memory(
            conversation,
            collection_name=mem_db_name,
            user_id = user_id,
            session_id = session_id,
        )

    search_request = SearchMemory(
        collection_name=mem_db_name,
        # query="音乐",  # 搜索关键词
        limit=2,  # 最多返回 2 条结果
        filter=MemoryFilter(
            memory_type=["sys_event_v1", "sys_profile_v1"],
            user_id=user_id,  # 只搜索该用户的记忆  
        ),
    )

    try:
        mem_res = search_memory(search_request)
        print(f"记忆检索成功mem_res")
        print(mem_res)
    except Exception as e:
        print(f"记忆检索失败: {e}")


if __name__ == "__main__":
    main()