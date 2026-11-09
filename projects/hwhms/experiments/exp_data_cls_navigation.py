from pathlib import Path
import sys
from typing import override
import asyncio
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from projects.hwhms.common.constants import CategoryName, Domain
from projects.hwhms.common.domain.car_assistant import vehicle_other_cat
from projects.hwhms.common.domain.traditional import navigation_cat
from projects.hwhms.common.domain.travel_assistant import travel_cat

from nanoai.model.config import ModelName
from projects.hwhms.datasets import Sample
from projects.hwhms.car_a.core import TREVAL_COMMON_PHRASES, IntentClassifier, ClsResult, intent_cls, is_entertainment_poi_query, map_category_to_domain
from projects.hwhms.car_a.run_test import evaluate_classifier_new, load_dataset_from_excel

dataset_path = Path(".") / "projects" / "hwhms" / "datasets"    
filepath = dataset_path / "1018" / "intent_cls.xlsx"

class IntentClassifierNew(IntentClassifier):
    def __init__(self):
        super().__init__()
        
    @override
    async def run(self, query: str, history: list[str] = [], output_structure: bool = False,) -> tuple[str, ClsResult | str]:
        # 统一处理 history 参数：转换为 list[str] 格式
        return await super().run(query, history, output_structure)

SHEET_NAMES = [Domain.TRADITIONAL, Domain.TRAVEL, Domain.SEARCH, Domain.FUN, Domain.VEHICLE]

def compare_and_validate():
    classifier = IntentClassifier()
    classifier_new = IntentClassifierNew()
    samples: list[Sample] = load_dataset_from_excel(filepath, SHEET_NAMES)
    
    run_list = [classifier_new]

    evaluate_classifier_new(run_list, samples, label="导航-出行", output_structure=True)




if __name__ == "__main__":
    # 新的config模块不再需要switch_model，模型配置在core.py中直接设置
    compare_and_validate()
