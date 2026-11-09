from beanie import PydanticObjectId
from projects.mind.test_backend.service.task.task_auto_run_service import run_task, run_task_by_step
from projects.mind.test_backend.db.init_beanie import init_db
import asyncio

if __name__ == "__main__":
    async def run_a_task():
        await init_db()
        await run_task_by_step(PydanticObjectId("69ea000f799385d1bc6f2603"))
    asyncio.run(run_a_task())
