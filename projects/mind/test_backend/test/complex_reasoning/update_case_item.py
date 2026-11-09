"""
将 dataset_ids 对应的所有 ComplexReasoningCaseDoc 中
context_config.car_state 字段重命名为 car_info。

可执行命令:
python -m projects.mind.test_backend.test.complex_reasoning.update_case_item
"""

import asyncio

from beanie import PydanticObjectId

from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.advisor.repositories import mdb_api

# ✏️ 修改这里，填入需要处理的 dataset_id 列表
DATASET_IDS: list[str] = [
    "69b924d73dea8e7ef5bc8ac5",
]


async def update_case_items(dataset_ids: list[str]) -> None:
    updated = 0
    skipped = 0

    for dataset_id_str in dataset_ids:
        dataset_id = PydanticObjectId(dataset_id_str)
        cases = await mdb_api.get_list(
            ComplexReasoningCaseDoc, query={"dataset_id": dataset_id}
        )
        print(f"dataset_id={dataset_id_str}  找到 {len(cases)} 条记录")

        for case in cases:
            if not isinstance(case.context_config, dict):
                skipped += 1
                continue
            if "car_state" not in case.context_config:
                skipped += 1
                continue

            case.context_config["car_info"] = case.context_config.pop("car_state")
            await mdb_api.update(ComplexReasoningCaseDoc, case)
            updated += 1
            print(f"  ✅ 已更新 case_id={case.case_id}")

    print(f"\n完成：更新 {updated} 条，跳过 {skipped} 条")


async def main() -> None:
    await init_db()
    await update_case_items(DATASET_IDS)


if __name__ == "__main__":
    asyncio.run(main())
