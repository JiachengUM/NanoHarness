import asyncio

from beanie import PydanticObjectId

from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.complex_reasoning.task_mdb_models.dataset import (
    ComplexReasoningDatasetDoc,
)
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.repositories import mdb_service


async def get_dataset_list():
    """查询数据集列表"""
    return await mdb_service.get_list(ComplexReasoningDatasetDoc)


async def get_case_list(dataset_id: PydanticObjectId | None):
    """根据数据集ID查询测试用例列表"""
    return await mdb_service.get_list(
        ComplexReasoningCaseDoc, query={"dataset_id": dataset_id}
    )


async def get_case_by_id(id: PydanticObjectId | None):
    """根据ID查询测试用例"""
    if not id:
        return None
    return await mdb_service.get_by_id(ComplexReasoningCaseDoc, id)


async def main():
    # 初始化数据库
    await init_db()

    dataset_list = await get_dataset_list()
    print(f"\n✅ 查询数据集列表: {dataset_list}")

    case_list = await get_case_list(PydanticObjectId("69e6f0dac2e54eff80362782"))
    print(f"\n✅ 查询测试用例列表: {case_list}")

    case = await get_case_by_id(PydanticObjectId("69e6f13fc2e54eff80362783"))
    print(f"\n✅ 查询测试用例详情: {case}")


if __name__ == "__main__":
    """
    可执行命令:
    python -m projects.mind.test_backend.test.complex_reasoning.test_dataset
    """
    asyncio.run(main())
