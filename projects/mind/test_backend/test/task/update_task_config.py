"""
将所有 TaskDoc 中 config.memory.consumer.config.profile_types 的值
复制到 config.memory.consumer.config.system_prompt_profile_types。

由于 profile_types 不在当前 MemoryConsumerConfig schema 中，会被 Pydantic 丢弃，
因此直接操作原始 MongoDB 文档。

可执行命令:
python -m projects.mind.test_backend.test.task.update_task_config
"""

import asyncio

from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.mdb_models.task import TaskDoc


async def update_task_configs() -> None:
    collection = TaskDoc.get_pymongo_collection()
    updated = 0
    skipped = 0

    async for task_dict in collection.find({}):
        task_id = task_dict.get("_id")
        config = task_dict.get("config") or {}
        memory = config.get("memory") or {}
        consumer = memory.get("consumer") or {}
        consumer_config = consumer.get("config") or {}

        profile_types = consumer_config.get("profile_types")
        if profile_types is None:
            skipped += 1
            continue

        await collection.update_one(
            {"_id": task_id},
            {
                "$set": {
                    "config.memory.consumer.config.system_prompt_profile_types": profile_types
                }
            },
        )
        updated += 1
        print(f"  ✅ 已更新 task_id={task_id}  profile_types={profile_types}")

    print(f"\n完成：更新 {updated} 条，跳过 {skipped} 条")


async def main() -> None:
    await init_db()
    await update_task_configs()


if __name__ == "__main__":
    asyncio.run(main())

# python -m projects.mind.test_backend.test.task.update_task_config