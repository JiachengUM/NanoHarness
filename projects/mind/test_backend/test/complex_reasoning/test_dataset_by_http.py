import asyncio

import httpx

BASE_URL = "https://ai-mind-web-dev.extour-inc.com"


async def get(url: str, params: dict = {}):
    """通用的 GET 请求方法"""
    url = f"{BASE_URL}{url}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        return body["data"]


async def get_dataset_items_by_dataset_id(dataset_id: str) -> list[dict]:
    """根据数据集ID通过 HTTP 接口查询数据集 case 列表"""
    url = f"/api/complex_reasoning_case/list"
    params = {"dataset_id": dataset_id}
    return await get(url, params)


async def get_dataset_item_by_id(id: str) -> dict:
    """根据数据集项ID通过 HTTP 接口查询数据集 case 详情"""
    url = f"/api/complex_reasoning_case/{id}"
    return await get(url)


async def main():
    items = await get_dataset_items_by_dataset_id("69e6f0dac2e54eff80362782")
    print(f"\n✅ 共获取 {len(items)} 条 case")


    dataset_item = await get_dataset_item_by_id("69e6f13fc2e54eff80362783")
    print(f"\n✅ 获取到 case 详情: {dataset_item}")


if __name__ == "__main__":
    asyncio.run(main())
