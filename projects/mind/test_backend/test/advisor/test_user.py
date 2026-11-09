import asyncio

from projects.mind.advisor.schemas.user import UserCreate
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.advisor.domain_data.user import UserBase, PersonBasicInfo
from projects.mind.advisor.mdb_models.user import UserDoc
from projects.mind.advisor.repositories import mdb_api


async def create_user():
    """
    创建用户画像
    """
    user = UserCreate(
        entity=UserBase(
            basic_info=PersonBasicInfo(name="Neo", age=30, gender="男"),
            profile=["喜欢读书，特别是科幻类作品", "爱听流行、民谣、摇滚类音乐", "喜欢旅游，特别是自驾游"],
        ),
        brief='读书听歌向往自由',
        creator='system'
    )

    created_user = await mdb_api.create(UserDoc, user)
    print(f"\n✅ 用户画像创建成功: {created_user}")
    return created_user


async def update_user(user):
    user.entity.basic_info.name = "Tom"  # 修改字段值
    updated_user = await mdb_api.update(UserDoc, user)
    print(f"\n✅ 用户画像更新成功，updated_user: {updated_user}")
    return updated_user


async def get_user_list():
    users = await mdb_api.get_list(UserDoc)
    print(f"\n✅ 查询用户画像列表: {users}")


async def delete_user(user_id):
    deleted = await mdb_api.delete_by_id(UserDoc, user_id)
    print(f"\n✅ 用户画像删除成功，deleted：{deleted}")


async def main():
    # 初始化数据库
    await init_db()
    user_doc = await create_user()
    await update_user(user_doc)
    await get_user_list()
    await delete_user(user_doc.id)


if __name__ == "__main__":
    """
    可执行命令:
    python -m projects.mind.test_backend.test.advisor.test_user
    """
    asyncio.run(main())
