from __future__ import annotations

import asyncio
import uuid

import httpx
from rich import print

from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport
from aicore.utils.volc_client.volc_api import VolcApiClient


async def test_create_collection() -> None:
    """
    用 VolcApiClient 创建记忆库，并查询详情。
    测试风格对齐 projects/mind/mem/tests/volc_api/test_collection.py。
    """
    collection_name = f"volc_client_test_{uuid.uuid4().hex[:8]}"

    create_payload = {
        "CollectionName": collection_name,
        "ProjectName": "default",
        "CollectionType": "ultimate",
        "CollectionModelType": "text",
        "Description": "created by aicore.utils.volc_client.test_volc_api",
        "CpuQuota": 1,
        "BuiltinEventTypes": ["sys_event_v1"],
        "BuiltinProfileTypes": ["sys_profile_v1"],
        "CustomEventTypeSchemas": [],
        "CustomProfileTypeSchemas": [],
        "Tags": [],
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as raw:
        client = VolcApiClient(HttpClient(HttpxTransport(raw)))

        try:
            create_rsp = await client.post("/api/memory/collection/create", create_payload)
            print(f"创建记忆库成功 with {collection_name}")
            print(create_rsp)
        except Exception as e:
            print(f"创建记忆库失败 with {collection_name}")
            print(e)
            return

        resource_id = ""
        if isinstance(create_rsp.data, dict):
            resource_id = str(create_rsp.data.get("ResourceId", "") or "")

        if not resource_id:
            print("创建返回中没有 ResourceId，跳过详情查询。")
            return

        info_payload = {"ResourceId": resource_id}
        try:
            info_rsp = await client.post("/api/memory/collection/info", info_payload)
            print(f"查询记忆库详细信息成功 with ResourceId={resource_id}")
            print(info_rsp)
        except Exception as e:
            print(f"查询记忆库详细信息失败 with ResourceId={resource_id}")
            print(e)


if __name__ == "__main__":
    asyncio.run(test_create_collection())
