import asyncio
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Type, override
from jinja2 import Template
from numpy import true_divide
from openai import AsyncOpenAI
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from projects.hwhms.car_b.core import IntentClassifierCarB
from projects.hwhms.common.config.config import AppConfig
from projects.hwhms.common.config.nacos_configs import NacosConfigs
from projects.hwhms.common.config.nacos_util import init_nacos
from projects.hwhms.common.domain.fun_assistant import chat_cat

from nanoai.model.llm import allm, allm_output
from nanoai.utils.nl_repr import nl_repr
from projects.hwhms.common.client import get_openai_client

from projects.hwhms.common.category import Category
from projects.hwhms.common.rag import RAG_TRADITIONAL_THRESHOLD, rag_search_must_pass, rag_search_traditional
from projects.hwhms.common.domain.car_assistant import vehicle_cat, vehicle_other_cat, vehicle_system_cat
from projects.hwhms.common.domain.traditional import car_control_cat, car_home_cat, media_cat, navigation_cat, other_cat, schedule_cat, system_setting_cat, vehicle_status_cat

from projects.hwhms.common.domain.search_assistant import encyclopedia_cat, long_tail_tricks_cat, news_cat
from projects.hwhms.common.domain.travel_assistant import travel_cat


from projects.hwhms.common.constants import CategoryName, Domain
from projects.hwhms.common.domain.navigation_treval import poi_navigation_cat, poi_travel_cat
from nanoai.model.config import ModelName
from projects.hwhms.datasets import DATASET_ROOT, Sample
from projects.hwhms.car_a.core import  DecisionPath, IntentClassifier, ClsResult, IntentClsResult, intent_cls, is_entertainment_poi_query, map_category_to_domain
from projects.hwhms.car_a.run_test import evaluate_classifier_new, evaluate_classifier_new_car_b, load_dataset_from_excel

SHEET_NAMES = ['1202_car_a']
# SHEET_NAMES = ["现场问题明细排序"]
hw_must_pass_file_path = DATASET_ROOT / "1203" / "华为问题清单_1202.xlsx"

class IntentClassifierNew(IntentClassifier):
    def __init__(self):
        super().__init__()

    chat_cat.notices = [
        "如果用户请求的是讲故事，讲谐音梗，请归属于多功能助手。"
    ]

        
    @override
    async def run(self, query: str, history: list[str] = [], output_structure: bool = False,) -> tuple[str, ClsResult | str]:
        # 统一处理 history 参数：转换为 list[str] 格式
        return await super().run(query, history, output_structure)


def compare_and_validate():
    classifier = IntentClassifier()

    samples = load_dataset_from_excel(file_path=str(hw_must_pass_file_path), sheet_names=SHEET_NAMES, query_column=5, history_column=6, expected_column=7)

    run_list = [classifier]

    evaluate_classifier_new(run_list, samples, label="must_pass_datasets", output_structure=True)

def compare_and_validate_car_b():
    classifier = IntentClassifierCarB()

    samples = load_dataset_from_excel(file_path=str(hw_must_pass_file_path), sheet_names=SHEET_NAMES, query_column=5, history_column=6, expected_column=7)

    run_list = [classifier]

    evaluate_classifier_new_car_b(run_list, samples, label="must_pass_datasets", output_structure=True)


def json_to_excel():
    """
    解析JSON文件，筛选history为空的条目，将query和expected写入Excel
    """
    json_path = "D:\\workspace\\bak\\nanoai\\projects\\hwhms\\datasets\\1203\\hwhms_data_cls_1021_results_must_pass_datasets.json"
    
    # 读取JSON文件
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 存储筛选后的数据
    filtered_data = []
    
    # 遍历JSON数据
    for item in data:
        if 'list' in item:
            # 处理包含list的结构
            for sub_item in item['list']:
                history = sub_item.get('history')
                # 筛选history为空字符串或null的条目
                if history is None or history == '' or history == "":
                    filtered_data.append({
                        'query': sub_item.get('query', ''),
                        'expected': sub_item.get('expected', '')
                    })
        else:
            # 处理直接的数据结构
            history = item.get('history')
            if history is None or history == '' or history == "":
                filtered_data.append({
                    'query': item.get('query', ''),
                    'expected': item.get('expected', '')
                })
    
    # 创建DataFrame
    df = pd.DataFrame(filtered_data)
    
    # 输出Excel路径
    output_path = Path(json_path).parent / f"{Path(json_path).stem}_filtered.xlsx"
    
    # 写入Excel
    df.to_excel(output_path, index=False, engine='openpyxl')
    
    print(f"✅ 成功处理 {len(filtered_data)} 条数据")
    print(f"📊 输出文件: {output_path}")
    print(f"\n📋 数据预览（前5行）：")
    print(df.head())
    print(f"\n📈 expected分布:")
    print(df['expected'].value_counts())
    
    return df



def convert_badcase_to_excel():
    excel_file_path = DATASET_ROOT / "1203" / "华为问题清单_1202.xlsx"

    sheets = pd.read_excel(excel_file_path, sheet_name=["1202_car_a"])
    filtered_data = []
    for sheet_name, df in sheets.items():
        for index, row in df.iterrows():
            flg = row.iloc[10]
            if flg == 1:
                continue
            query = row.iloc[5]
            history = row.iloc[6]
            if pd.isna(history) or history is None:
                continue
            expected = row.iloc[7]
            ## print(f"query: {query}, history: {history}, expected: {expected}")
            history_list = json.loads(history)
            ## 输出history_list的所有q， - 相隔
            history_str = "-".join([h['q'] for h in history_list])
            
            ## print(f"query: {history_str}-{query}, expected: {expected}")
            filtered_data.append({"query": f"{history_str}-{query}", "expected": expected})

    print(f"filtered_data: {filtered_data}")   
    ## 保存到一个新的excel中
    df = pd.DataFrame(filtered_data)
    df.to_excel(DATASET_ROOT / "1203" / "华为问题清单3.xlsx", index=False)
    print(f"已保存到 {excel_file_path}")
    return df


if __name__ == "__main__":
    # 初始化 Nacos 和 AppConfig (ak sk直接硬编码会被扫描风险，现在统一放到nacos中，下面三行代码主要是读取配置信息)
    init_nacos() 
    asyncio.run(NacosConfigs.init())
    asyncio.run(AppConfig.init())
    ##compare_and_validate()
    ## json_to_excel()
    convert_badcase_to_excel()
