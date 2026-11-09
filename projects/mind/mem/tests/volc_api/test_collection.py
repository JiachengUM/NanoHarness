from rich import print

from projects.mind.mem.volc_api.collection import (
    CollectionCreate,
    create_collection,

    CollectionManagementCollectionID,
    CollectionUpdate,
    update_collection,
    
    CollectionInfo,
    get_collection_info,
    
    delete_collection,
    
    list_collections,
)

from projects.mind.mem.tests.volc_api.test_event import (
    sys_event_v1,
    event_english_study,
    event_cabin_user_boarding,
    event_cabin_user_leaving,
    event_cabin_navigation_start,
    event_cabin_voice_command,
)

from projects.mind.mem.tests.volc_api.test_profile import (
    sys_profile_v1,
    car_user_profile,
)

from projects.mind.mem.tests.volc_api.common import collection_default, collection_customize

def test_collection_default():
    collection_name = collection_default

    """创建记忆库"""
    c = CollectionCreate(CollectionName=collection_name, Description="test description")

    try:
        res = create_collection(c)
        print(f"创建记忆库成功 with {c}")
        print(res)
    except Exception as e:
        print(f"创建记忆库失败 with {c}")
        print(e)

    """查询记忆库详细信息"""
    try:
        info = get_collection_info(CollectionManagementCollectionID(CollectionName=collection_name))
        print(f"查询记忆库详细信息结果 with {collection_name}:")
        print(info)
    except Exception as e:
        print(f"查询记忆库详细信息失败 with {collection_name}")
        print(e)

    return

    """删除记忆库"""
    try:
        rsp = delete_collection(CollectionID(CollectionName=collection_name))
        print(f"删除记忆库成功 with {collection_name}")
        print(rsp)
    except Exception as e:
        print(f"删除记忆库失败 with {collection_name}")
        print(e)


def test_collection_customize():
    collection_name = collection_customize
    """测试创建记忆库"""
    c = CollectionCreate(
        CollectionName=collection_name,
        Description="test description",
        CustomEventTypeSchemas=[
            event_cabin_user_boarding,
        ],
        CustomProfileTypeSchemas=[
            car_user_profile,
        ],
    )

    try:
        res = create_collection(c)
        print(f"创建记忆库成功 with {c}")
        print(res)
    except Exception as e:
        print(f"创建记忆库失败 with {c}")
        print(e)

    """查询记忆库详细信息"""
    try:
        info = get_collection_info(CollectionManagementCollectionID(CollectionName=collection_name))
        print(f"查询记忆库详细信息结果 with {collection_name}:")
        print(info)
    except Exception as e:
        print(f"查询记忆库详细信息失败 with {collection_name}")
        print(e)

    return
    
    """测试更新记忆库配置"""
    # 创建更新对象，添加自定义事件类型
    update = CollectionUpdate(
        CollectionName=collection_name,
        CustomEventTypeSchemas=[
            event_cabin_user_boarding,
        ],
    )

    rsp = update_collection(update)
    print("更新记忆库结果:")
    print(rsp)

    """测试查询记忆库详细信息"""
    c = CollectionID(CollectionName=collection_name)
    rsp = get_collection_info(c)
    print("查询记忆库详细信息结果:")
    print(rsp)


def test_list_collections():
    """测试列出记忆库"""
    rsp = list_collections()
    print("列出记忆库结果:")
    print(rsp)


if __name__ == "__main__":    
    test_collection_default()

    test_collection_customize()
    
    test_list_collections()