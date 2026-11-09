import asyncio
from rich import print

from projects.mind.complex_reasoning.tools.PoiSearch import poi_search

async def test_poi_search():
    query = "找一下徐家汇附近的餐厅"
    #query = "今天几个北京的朋友过来了，帮我找个适合吃川菜的餐厅"
    result = await poi_search(query)
    print(result)


if __name__ == "__main__":
    asyncio.run(test_poi_search())
