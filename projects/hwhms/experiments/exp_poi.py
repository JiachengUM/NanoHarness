import asyncio
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from nanoai.model.config import ModelName
from projects.hwhms.car_a.core import is_entertainment_poi_query

def get_poi_data():
    poi_data = ["搜索附近的动物园","搜索附近的餐厅","搜索附近的酒店","搜索附近的景点","搜索附近的医院","搜索附近的学校","搜索附近的工商银行","搜索附近的公园", "导航到附近的国购广场"]
    ## poi_data = ["搜索附近的医院","搜索附近的医院","搜索附近的医院","搜索附近的医院","搜索附近的医院","搜索附近的医院","搜索附近的医院","搜索附近的医院", "搜索附近的医院"]
    return poi_data

if __name__ == "__main__":
    # 新的config模块不再需要switch_model，模型配置在core.py中直接设置
    poi_data = get_poi_data()
    for query in poi_data:
        res = asyncio.run(is_entertainment_poi_query(query))
        print(f"最终结果: query: {query}, res: {res}")
