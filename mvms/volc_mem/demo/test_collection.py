import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mvms.volc_mem.api.collection import (
    Collection,
    UpdateCollection,
    EventTypeSchema,
    EventProperty,
    create_collection,
    update_collection,
    CollectionInfo,
    get_collection_info,
    CollectionDelete,
    delete_collection,
    CollectionList,
    list_collections,
)


def test_create_collection():
    """测试创建记忆库"""
    c = Collection(
        CollectionName="memory_test1",
        Description="test description",
        BuiltinEventTypes=["sys_event_v1"],
        BuiltinProfileTypes=["sys_profile_v1"]
    )

    rsp = create_collection(c)
    print("创建记忆库结果:")
    print(rsp.json())


def test_update_collection():
    """测试更新记忆库配置，仿照 demo/collection.py 中的例子"""
    # 创建更新对象，添加自定义事件类型
    update = UpdateCollection(
        CollectionName="memory_test1",
        Description="用于记录和分析学生英语学习过程的记忆库",
        CustomEventTypeSchemas=[
            EventTypeSchema(
                EventType="english_study",
                Description="记录一次英语学习会话中助教与学生的问答及评分",
                Properties=[
                    EventProperty(
                        PropertyName="knowledge_point_name",
                        PropertyValueType="string",
                        Description="当前对话涉及的知识点名称",
                    ),
                    EventProperty(
                        PropertyName="question",
                        PropertyValueType="string",
                        Description="助教提出的问题",
                    ),
                    EventProperty(
                        PropertyName="answer",
                        PropertyValueType="string",
                        Description="学生的回答",
                    ),
                    EventProperty(
                        PropertyName="rating_score",
                        PropertyValueType="int64",
                        Description="对学生回答的数值评分",
                    ),
                    EventProperty(
                        PropertyName="fluency_score",
                        PropertyValueType="int64",
                        Description="口语流利度评分 (1-5)",
                    ),
                ],
                Version="2",
            )
        ],
    )

    rsp = update_collection(update)
    print("更新记忆库结果:")
    print(rsp.json())


def test_get_collection_info():
    """测试查询记忆库详细信息"""
    c = CollectionInfo(CollectionName="memory_test1")
    rsp = get_collection_info(c)
    print("查询记忆库详细信息结果:")
    print(rsp.json())


def test_delete_collection():
    """测试删除记忆库"""
    c = CollectionDelete(CollectionName="memory_test1")
    rsp = delete_collection(c)
    print("删除记忆库结果:")
    print(rsp.json())


def test_list_collections():
    """测试列出记忆库"""
    c = CollectionList()
    rsp = list_collections(c)
    print("列出记忆库结果:")
    print(rsp.json())


if __name__ == "__main__":
    # 先创建记忆库
    test_create_collection()
    # 然后更新记忆库
    # test_update_collection()
    # 然后查询记忆库详细信息
    # test_get_collection_info()
    # 然后删除记忆库
    # test_delete_collection()
    # 然后列出记忆库
    # test_list_collections()