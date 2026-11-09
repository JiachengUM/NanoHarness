import asyncio
from typing import Any

import httpx


DATASETS = {
    # "复杂推理-天气": "69cde88bf25e1cce1203c712",
    "复杂推理-音乐搜索": "69cde80e1b5870295a1e908b",
    # "复杂推理-联网搜索": "69cde817a858d60f7c9d169f",
    # "复杂推理-媒体控制": "69cde82290fd629f068a3df3",
    # "AICAR-复杂推理-车控-全量-V2": "69cde7ae4507d412f84823f1",
    # "别克NDLB EV复杂推理最终需求边界数据集——闲聊+记忆消费类":"69d4eb2298c22545a0f873eb",
    # "别克NDLB EV复杂推理最终需求边界数据集——记忆生产类":"69d4eb2cc1f0fc06e8ae1b78",
    # "别克NDLB EV复杂推理最终需求边界数据集——媒体类":"69d4eb15ddaddb36b0593d1d",
    # "别克NDLB EV复杂推理最终需求边界数据集——导航类":"69d4e041ddaddb36b0593d01",
}

BASE_URL = "https://ai-mind-web-dev.extour-inc.com/api/complex_reasoning_case/page"


async def fetch_dataset(
    client: httpx.AsyncClient,
    name: str,
    dataset_id: str,
    page: int = 1,
    page_size: int = 1000,
) -> dict[str, Any]:
    params = {
        "page": page,
        "page_size": page_size,
        "dataset_id": dataset_id,
    }
    resp = await client.get(BASE_URL, params=params)
    resp.raise_for_status()
    return {"name": name, "dataset_id": dataset_id, "data": resp.json()}


async def fetch_all_datasets(
    page: int = 1,
    page_size: int = 1000,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [
            fetch_dataset(client, name, dataset_id, page, page_size)
            for name, dataset_id in DATASETS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    output = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"Error: {result}")
            continue
        output[result["name"]] = result["data"]

    return output


async def fetch_all():
    output = dict()
    results = await fetch_all_datasets()
    for name, df in results.items():
        output.setdefault(name, [])
        for row in df["data"]["items"]:
            # 只取一个对话
            conversation = row['user_query_lists'][0]
            queries = "，".join([line["content"] for line in conversation])
            output[name].append({"query": queries})
    return output


if __name__ == "__main__":
    asyncio.run(fetch_all())
