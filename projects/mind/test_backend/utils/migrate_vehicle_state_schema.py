from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from typing import Any

from projects.mind.test_backend.config import get_mongodb_config
from projects.mind.test_backend.db.init_beanie import get_motor_client

"""
车辆状态文档结构在早期版本中存在不一致问题，部分字段在不同文档中可能是单个对象或对象数组。
此脚本用于扫描 vehicle_state 集合中的文档，规范化这些字段为统一的数组格式，并可选择性地将更改应用回数据库。
最新数据结构来源：advisor最新数据结构
使用方法：
1. 进行干运行（不修改数据库）：
   python migrate_vehicle_state_schema.py --limit 100
   这将扫描前100个文档并报告需要更改的数量，但不会修改数据库。
2. 应用更改：
   python migrate_vehicle_state_schema.py --apply
   这将扫描所有文档并将需要更改的文档更新到数据库中。
3. 结合使用限制和应用更改：
   python migrate_vehicle_state_schema.py --apply --limit 100
   这将扫描前100个文档并将需要更改的文档更新到数据库中。
"""

ARRAY_FIELD_MAP: dict[str, list[str]] = {
    "system_control": ["passenger_info"],
    "vehicle_control": [
        "tire_info",
        "air_condition",
        "defrost_defog",
        "interior_temperature",
        "seat_position",
        "seat_ventilation",
        "seat_heating",
        "seat_massage",
        "window_status",
        "door_status",
        "fragrance_system",
    ],
}


def normalize_array_field(value: Any) -> tuple[Any, bool]:
    if value is None or isinstance(value, str):
        return value, False
    if isinstance(value, list):
        return value, False
    if isinstance(value, dict):
        return [value], True
    return value, False


def normalize_vehicle_state(vehicle_state: Any) -> tuple[Any, bool]:
    if not isinstance(vehicle_state, dict):
        return vehicle_state, False

    changed = False
    normalized_vehicle_state = dict(vehicle_state)

    for section_key, field_keys in ARRAY_FIELD_MAP.items():
        section = normalized_vehicle_state.get(section_key)
        if not isinstance(section, dict):
            continue

        normalized_section = dict(section)
        section_changed = False
        for field_key in field_keys:
            normalized_value, value_changed = normalize_array_field(
                normalized_section.get(field_key)
            )
            if value_changed:
                normalized_section[field_key] = normalized_value
                section_changed = True

        if section_changed:
            normalized_vehicle_state[section_key] = normalized_section
            changed = True

    return normalized_vehicle_state, changed


async def migrate_vehicle_state_collection(
    collection, apply_changes: bool, limit: int | None = None
) -> tuple[int, int]:
    cursor = collection.find({}, {"_id": 1, "entity": 1})
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)

    scanned = 0
    changed = 0

    async for doc in cursor:
        scanned += 1
        entity = doc.get("entity")
        normalized_entity, is_changed = normalize_vehicle_state(entity)
        if not is_changed:
            continue

        changed += 1
        if apply_changes:
            await collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "entity": normalized_entity,
                        "updated_time": datetime.now(),
                    }
                },
            )

    return scanned, changed


async def migrate_advisor_input_collection(
    collection, apply_changes: bool, limit: int | None = None
) -> tuple[int, int]:
    cursor = collection.find({}, {"_id": 1, "context": 1})
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)

    scanned = 0
    changed = 0

    async for doc in cursor:
        scanned += 1
        context = doc.get("context")
        if not isinstance(context, dict):
            continue

        vehicle_state = context.get("vehicle_state")
        normalized_vehicle_state, is_changed = normalize_vehicle_state(vehicle_state)
        if not is_changed:
            continue

        changed += 1
        if apply_changes:
            normalized_context = dict(context)
            normalized_context["vehicle_state"] = normalized_vehicle_state
            await collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "context": normalized_context,
                        "updated_time": datetime.now(),
                    }
                },
            )

    return scanned, changed


async def migrate_advisor_run_collection(
    collection, apply_changes: bool, limit: int | None = None
) -> tuple[int, int]:
    cursor = collection.find({}, {"_id": 1, "input": 1})
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)

    scanned = 0
    changed = 0

    async for doc in cursor:
        scanned += 1
        input_ = doc.get("input")
        if not isinstance(input_, dict):
            continue

        context = input_.get("context")
        if not isinstance(context, dict):
            continue

        vehicle_state = context.get("vehicle_state")
        normalized_vehicle_state, is_changed = normalize_vehicle_state(vehicle_state)
        if not is_changed:
            continue

        changed += 1
        if apply_changes:
            normalized_context = dict(context)
            normalized_context["vehicle_state"] = normalized_vehicle_state
            normalized_input = dict(input_)
            normalized_input["context"] = normalized_context
            await collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "input": normalized_input,
                        "updated_time": datetime.now(),
                    }
                },
            )

    return scanned, changed


async def migrate(apply_changes: bool, limit: int | None = None) -> None:
    mongodb_config = get_mongodb_config()
    client = get_motor_client(mongodb_config.mongodb_uri)
    db = client[mongodb_config.mongodb_db]

    vehicle_state_scanned, vehicle_state_changed = (
        await migrate_vehicle_state_collection(
            db["vehicle_state"], apply_changes=apply_changes, limit=limit
        )
    )
    advisor_input_scanned, advisor_input_changed = (
        await migrate_advisor_input_collection(
            db["advisor_input"], apply_changes=apply_changes, limit=limit
        )
    )
    advisor_run_scanned, advisor_run_changed = await migrate_advisor_run_collection(
        db["advisor_run"], apply_changes=apply_changes, limit=limit
    )

    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(
        f"[{mode}] vehicle_state migration: scanned={vehicle_state_scanned}, changed={vehicle_state_changed}"
    )
    print(
        f"[{mode}] advisor_input migration: scanned={advisor_input_scanned}, changed={advisor_input_changed}"
    )
    print(
        f"[{mode}] advisor_run migration: scanned={advisor_run_scanned}, changed={advisor_run_changed}"
    )
    print(
        f"[{mode}] migration summary: scanned={vehicle_state_scanned + advisor_input_scanned + advisor_run_scanned}, changed={vehicle_state_changed + advisor_input_changed + advisor_run_changed}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate vehicle_state documents to latest schema."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to MongoDB. Default is dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of documents to scan.",
    )
    args = parser.parse_args()

    asyncio.run(migrate(apply_changes=args.apply, limit=args.limit))

# python -m projects.mind.test_backend.utils.migrate_vehicle_state_schema
# python -m projects.mind.test_backend.utils.migrate_vehicle_state_schema --apply
