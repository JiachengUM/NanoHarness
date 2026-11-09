import asyncio

import pytest

from projects.mind.intent.intent_mdb_models.category import CategoryDoc
from projects.mind.intent.intent_schemas.category import CategoryCreate
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.intent.repositories import mdb_api


async def test_init_db():
    await init_db()
    print("\n✅ 数据库连接初始化完成")


@pytest.mark.asyncio
async def test_create_category():
    """创建意图分类"""
    # await test_init_db() # 执行单元测试可以先初始化数据库
    category = CategoryCreate(name="闲聊", definition="用户提出的问题无法归类到其他类别，作为兜底分类。",
                              example=["问候语,如: 你好, 你好呀, 早上好, 晚上好",
                                       "寒暄对话,如: 随便聊聊, 最近怎么样, 在干嘛呢"],
                              example_neg=None,
                              notice=None,
                              creator="xuwenze")

    created_category = await mdb_api.create(CategoryDoc, category)
    print(f"\n✅ 意图分类创建成功，类名称: {type(created_category).__name__}")
    print(f"\n✅ 意图分类创建成功: {created_category}")

    return created_category

async def update_category(category):
    """更新意图分类"""
    category.name = "百科"
    updated_category = await mdb_api.update(CategoryDoc, category)
    print(f"\n✅ 意图分类更新成功: {updated_category}")
    return updated_category

@pytest.mark.asyncio
async def test_get_category_list():
    """获取意图分类列表"""
    # await test_init_db() # 执行单元测试可以先初始化数据库
    category_list = await mdb_api.get_list(CategoryDoc)
    print(f"\n✅ 意图分类列表: {category_list}")

async def delete_category(category_id):
    """删除意图分类"""
    deleted = await mdb_api.delete_by_id(CategoryDoc, category_id)
    print(f"\n✅ 删除结果，deleted：{deleted}")


async def main():
    await test_init_db() # 初始化数据库
    category_doc = await test_create_category() # 创建意图分类
    await update_category(category_doc) # 更新意图分类
    await test_get_category_list() # 获取意图分类列表
    await delete_category(category_doc.id) # 删除意图分类


if __name__ == "__main__":
    """
    可执行命令:
    python -m projects.mind.test_backend.test.intent.test_category
    """

    asyncio.run(main())
