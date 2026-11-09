import asyncio
from collections import defaultdict
from pathlib import Path
import sys
from typing import override
import pandas as pd
sys.path.append(str(Path(__file__).parent.parent.parent.parent))


from projects.hwhms.common.domain.fun_assistant import chat_cat
from projects.hwhms.common.domain.search_assistant import encyclopedia_cat, long_tail_tricks_cat, news_cat
from projects.hwhms.common.domain.travel_assistant import travel_cat


from projects.hwhms.common.domain.car_assistant import vehicle_cat, vehicle_other_cat, vehicle_system_cat
from projects.hwhms.common.domain.traditional import call_cat, car_control_cat, car_home_cat, media_cat, navigation_cat, other_cat, schedule_cat, system_setting_cat, vehicle_status_cat

from nanoai.model.config import ModelName
from projects.hwhms.datasets import Sample
from projects.hwhms.car_a.core import IntentClassifier, ClsResult, intent_cls, is_entertainment_poi_query, map_category_to_domain
from projects.hwhms.car_a.run_test import  evaluate_classifier_new

SHEET_NAMES = ['典型说法', "泛化类型1", "泛化类型2", "泛化类型3", "泛化类型4"] 

def load_query_from_excel(file_path: str, sheet_names: list[str]) -> list[Sample]:
    samples: list[Sample] = []

    sheets = pd.read_excel(file_path, sheet_name=None)

    for sheet_name, df in sheets.items():
        if sheet_name not in sheet_names:
            continue

        # 获取当前 Sheet
        for index, row in df.iterrows():
            samples.append(Sample(query=row.iloc[0], expected=row.iloc[1]))

    return samples

def compare_and_validate():
    classifier = IntentClassifier()
    classifier_new = IntentClassifier()

    # step 1: 读取想要测试的数据，通常不是完整的测试集，而是“想要对比的部分，这个实验的改动可能影响的部分”。
    dataset_path = Path(".") / "projects" / "hwhms" / "datasets"    
    filepath = dataset_path / "release" / "单轮意图分类_传统垂域_4900.xlsx"
    samples: list[Sample] = load_query_from_excel(filepath, SHEET_NAMES)
    run_list = [classifier]
    evaluate_classifier_new(run_list, samples, label="traditional", output_structure=False)

if __name__ == "__main__":
    # 新的config模块不再需要switch_model，模型配置在core.py中直接设置
    compare_and_validate()
