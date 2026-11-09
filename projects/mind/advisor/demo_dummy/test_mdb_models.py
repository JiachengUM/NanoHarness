import asyncio

from rich import print

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from projects.mind.advisor.mdb_models.user import UserDoc
from projects.mind.advisor.task_mdb_models.advisor_dataset import AdvisorDatasetDoc
from projects.mind.advisor.task_mdb_models.advisor_input import AdvisorInput, AdvisorInputDoc

from projects.mind.advisor.repositories import mdb_api


async def init():
    # 连接 MongoDB（默认本地 27017，数据库名：mydb）
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    await init_beanie(
        database=client.mydb,  # type: ignore
        document_models=[
            UserDoc,
            AdvisorInputDoc,
            AdvisorDatasetDoc,
        ]
    )


async def test_user():

    # C - Create
    user1 = UserDoc(name="wei yichen", age=48)
    await user1.insert()
    print("✅ Created:", user1.id)

    # R - Read (by id)
    fetched = await UserDoc.get(user1.id)
    print("🔍 Fetched by ID:", fetched)

    users = await UserDoc.find().to_list()
    print("🔍 Found all users:", users)

    # R - Find (by field)
    users = await UserDoc.find(UserDoc.name == "wei yichen").to_list()
    print("🔍 Found by name:", users)

    # U - Update
    # user1.age = 45
    # await user1.save()
    # print("✏️ Updated age to:", user1.age)

    # # D - Delete
    # await user1.delete()
    # print("🗑️ Deleted user")

    # # 验证是否删除
    # exists = await UserDoc.get(user1.id)
    # print("🔍 After delete, exists?", exists is None)


async def test_advisor_input():
    # C - Create
    input1 = AdvisorInput(
        event="用户上车了",
        context="空调未开启, 车内气温40度",
    )
    input_doc = await mdb_api.create(AdvisorInputDoc, input1)
    print("✅ Created:", input_doc)


async def main():
    await init()

    # await test_user()
    await test_advisor_input()


if __name__ == "__main__":
    asyncio.run(main())
