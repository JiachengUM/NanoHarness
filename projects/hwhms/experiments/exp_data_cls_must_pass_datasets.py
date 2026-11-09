import asyncio
from collections import defaultdict
from pathlib import Path
import sys
from typing import Type, override
from jinja2 import Template
from openai import AsyncOpenAI
import pandas as pd
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

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
from projects.hwhms.car_a.run_test import evaluate_classifier_new, load_dataset_from_excel_hwhms_must_pass

SHEET_NAMES = ['传统垂域', '出行助手', '搜索助手', '趣味助手', '用车助手']
# SHEET_NAMES = ["现场问题明细排序"]
hw_must_pass_file_path = DATASET_ROOT / "1022" / "hwhms_must_pass_datasets.xlsx"



def compare_and_validate():
    classifier = IntentClassifier()

    samples = load_dataset_from_excel_hwhms_must_pass(str(hw_must_pass_file_path), SHEET_NAMES)

    run_list = [classifier]

    evaluate_classifier_new(run_list, samples, label="must_pass_datasets", output_structure=False)


async def poi_cls():
    data = []
    classifier = IntentClassifier()
    query = "我想去欢乐谷"
    output = await classifier.poi_cls(
        query=query,
        output_structure=True
    )
    print(output)

    output2 = await classifier.run(
        query=query,
        output_structure=True
    )
    print("---")
    print(output2)



if __name__ == "__main__":
    # 新的config模块不再需要switch_model，模型配置在core.py中直接设置
    compare_and_validate()
    ## asyncio.run(poi_cls())
