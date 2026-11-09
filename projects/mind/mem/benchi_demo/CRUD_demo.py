import time

from rich import print

from projects.mind.mem.volc_api import (
    Message,
    create_collection,
    CollectionCreate,
    add_session,
    SessionCreate,
    SessionMetadata,
    SearchMemory,
    MemoryFilter,
    search_memory,
    msg_to_volc_format,
)
from projects.mind.mem.volc_api.collection import (
    CollectionUpdate,
    CollectionID,
    get_collection_info,
    update_collection,
)
from projects.mind.mem.volc_api.profile import ProfileTypeSchema
from projects.mind.mem.benchi_demo.location_profile_v1 import location_profile_v1_dict

#创建记忆库需要等待3-5分钟
def init_mem_db_with_location_profile(db_name: str) -> str:
    """初始化记忆库，包含 location_profile_v1 自定义画像类型"""
    
    # 将 location_profile_v1 字典转换为 ProfileTypeSchema 对象
    # 需要过滤掉 Role 字段，因为 ProfileTypeSchema 不接受该字段
    location_profile_dict = {k: v for k, v in location_profile_v1_dict.items() if k != "Role"}
    location_profile = ProfileTypeSchema.model_validate(location_profile_dict)
    
    try:
        id = create_collection(
            CollectionCreate(
                CollectionName=db_name,
                CustomProfileTypeSchemas=[location_profile],
            )
        )
        print(f"记忆库{db_name}创建成功（包含 location_profile_v1）, id={id}")
    except Exception as e:
        print(f"记忆库{db_name}已经存在，尝试更新添加 location_profile_v1")
        # 如果已存在，尝试更新添加 location_profile_v1
        try:
            update_mem_db_with_location_profile(db_name)
        except Exception as update_error:
            print(f"更新记忆库失败: {update_error}")
    
    return db_name


def update_mem_db_with_location_profile(db_name: str) -> None:
    """更新已有记忆库，添加 location_profile_v1 自定义画像类型"""
    
    # 将 location_profile_v1 字典转换为 ProfileTypeSchema 对象
    location_profile_dict = {k: v for k, v in location_profile_v1_dict.items() if k != "Role"}
    location_profile = ProfileTypeSchema.model_validate(location_profile_dict)
    
    # 获取现有配置
    try:
        existing_info = get_collection_info(CollectionID(CollectionName=db_name))
        llm_config = existing_info.PipelineConfig.LlmExtractConfig
        
        # 从现有配置中提取自定义画像类型
        existing_custom_profiles: list[ProfileTypeSchema] = []
        if llm_config.CustomProfileTypeSchemas:
            existing_custom_profiles = llm_config.CustomProfileTypeSchemas
        
        # 检查是否已经包含 location_profile_v1
        profile_names = [p.ProfileType for p in existing_custom_profiles]
        if 'location_profile_v1' in profile_names:
            print(f"记忆库{db_name}已包含 location_profile_v1，无需更新")
            return
        
        # 合并现有的和新的画像类型
        all_profiles = existing_custom_profiles + [location_profile]
        
        # 更新记忆库（需要带上全部配置）
        update_collection(
            CollectionUpdate(
                CollectionName=db_name,
                CustomProfileTypeSchemas=all_profiles,
                BuiltinEventTypes=llm_config.BuiltinEventTypes if hasattr(llm_config, 'BuiltinEventTypes') else ["sys_event_v1"],
                BuiltinProfileTypes=llm_config.BuiltinProfileTypes if hasattr(llm_config, 'BuiltinProfileTypes') else ["sys_profile_v1"],
                CustomEventTypeSchemas=llm_config.CustomEventTypeSchemas if hasattr(llm_config, 'CustomEventTypeSchemas') else [],
            )
        )
        print(f"记忆库{db_name}更新成功，已添加 location_profile_v1")
    except Exception as e:
        # 如果获取或更新失败，打印错误信息
        print(f"更新记忆库失败: {e}")
        print("提示：更新记忆库需要带上全部配置，如果记忆库已有其他自定义配置，可能需要手动合并")
        raise


def add_to_memory(
    conversation: list[Message],
    /,
    *,
    collection_name: str,
    user_id: str,
    default_assistant_id: str = "小途助手",
    session_id: str | None = None,
    ) -> None:
    """将对话添加到记忆库"""

    msgs = msg_to_volc_format(conversation)
    add_session(
        session=SessionCreate(
            collection_name=collection_name,
            session_id=session_id,
            # metadata = SessionMetadata(),
            messages=msgs,
            metadata=SessionMetadata(
                default_user_id=user_id,
                default_assistant_id=default_assistant_id,
                time=int(time.time() * 1000),
            )
        ),
    )


def main():
    """主链路"""
    mem_db_name = init_mem_db_with_location_profile("memory_for_benchi")

    user_id = "嘉骋"
    session_id = "session_location"

    # 创建对话
    conversation = [
        Message(role="user", content="记一下我做瑜伽的地方在闵行区顾戴路2468号"),
        Message(role="assistant", content="已帮你记录瑜伽馆地址：闵行区顾戴路2468号。下次需要导航过去可以随时告诉我哦～或者现在要帮你导航过去吗？"),
        Message(role="user", content="不用，导航到我爸妈家"),
        Message(role="assistant", content="好的，为你导航到爸妈家。不过我还不知道叔叔阿姨家的具体地址，麻烦告诉我一下详细地址（比如XX市XX区XX路XX号），我马上帮你规划路线～"),
        Message(role="user", content="万达广场3号楼"),
        Message(role="assistant", content="以下是多个结果，请问是第几个？1. 万达广场 3 号楼 上海市宝山区共和新路 4995 号宝山万达广场 3 号楼（共康路地铁站附近，楼下为招商银行） 2. 万达广场公寓 3 号楼 上海市松江区广富林路 658 弄 215 号万达广场 3 号楼 3. 万达广场江桥店 3 号写字楼 上海市嘉定区江桥镇金沙江西路 1069 号（金运路地铁站 1 号口步行 230 米，鹤旋路与华江公路交叉口西北侧） 4. 万达广场 3 号楼 (南门) 上海市松江区广富林路 658 弄 215 号万达广场 3 号楼南门"),
        Message(role="user", content="就第一个"),
        Message(role="assistant", content="好的，为你导航到宝山万达广场 3号楼"),
        Message(role="user", content="你帮我记一下我爸妈的地址吧"),
        Message(role="assistant", content="好的，已经帮你记下来了。"),
        Message(role="user", content="记一下我外婆家的地址在今天花园8号楼")
    ]

    # 生成记忆
    do_add = True
    if do_add:
        add_to_memory(
            conversation,
            collection_name=mem_db_name,
            user_id = user_id,
            session_id = session_id,
        )

    # 更新记忆，需要等待大约5秒
    session_id_update = "session_location_update"
    conversation_update = [
        Message(role="user", content="导航到爸妈家"),
        Message(role="assistant", content="好的，为你导航到宝山万达广场3号楼"),
        Message(role="user", content="不对不对，爸妈搬家了搬到田林养老了，住气象苑"),
        Message(role="assistant", content="好的，为你导航到徐汇区气象苑"),
    ]
    do_update = False
    if do_update:
        add_to_memory(
            conversation_update,
            collection_name=mem_db_name,
            user_id = user_id,
            session_id = session_id_update,
        )

    # 删除记忆，需要等待大约5秒
    session_id_delete = "session_location_delete"
    conversation_delete = [
        Message(role="user", content="最近没兴趣做瑜伽了，别存着我做瑜伽的地址了，我的卡都到期了"),
        Message(role="assistant", content="明白了，已经帮你从记忆中移除瑜伽相关的地址信息，如果你以后需要再添加，随时告诉我哦"),
    ]
    do_delete = False
    if do_delete:
        add_to_memory(
            conversation_delete,
            collection_name=mem_db_name,
            user_id = user_id,
            session_id = session_id_delete,
        )

    # 搜索记忆
    search_request = SearchMemory(
        collection_name=mem_db_name,
        # query="音乐",  # 搜索关键词
        limit=2,  # 最多返回 2 条结果
        filter=MemoryFilter(
            memory_type=["location_profile_v1"],
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

