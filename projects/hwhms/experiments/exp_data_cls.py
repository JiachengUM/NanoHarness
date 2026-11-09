import asyncio
from collections import defaultdict
from pathlib import Path
import sys
from typing import override
import pandas as pd
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from nanoai.model.config import ModelName
from projects.hwhms.datasets import Sample
from projects.hwhms.car_a.core import IntentClassifier, ClsResult, intent_cls, is_entertainment_poi_query
from projects.hwhms.car_a.run_test import evaluate_classifier_new

class IntentClassifierNew(IntentClassifier):
    def __init__(self):
        super().__init__()
    @override
    async def run(self, query: str, history: list[str] = [], output_structure: bool = False,) -> tuple[str, ClsResult | str]:
        return await super().run(query, history, output_structure)

SHEET_NAMES = ['传统垂域', '出行助手', "搜索助手", "趣味助手", "用车助手"]

def load_query_from_excel(file_path: str, sheet_names: list[str]) -> list[Sample]:
    samples: list[Sample] = []

    sheets = pd.read_excel(file_path, sheet_name=None)

    for sheet_name, df in sheets.items():
        if sheet_name not in sheet_names:
            print("sheet_name invalid", sheet_name)
            continue

        # 获取当前 Sheet
        for index, row in df.iterrows():
            samples.append(Sample(query=row.iloc[0], expected=row.iloc[2]))

    return samples

def compare_and_validate():
    classifier = IntentClassifier()
    classifier_new = IntentClassifierNew()

    # step 1: 读取想要测试的数据，通常不是完整的测试集，而是“想要对比的部分，这个实验的改动可能影响的部分”。
    dataset_path = Path(".") / "projects" / "hwhms" / "datasets"    
    filepath = dataset_path / "1018" / "intent_cls.xlsx"
    samples: list[Sample] = load_query_from_excel(filepath, SHEET_NAMES)

    run_list = [classifier, classifier_new]

    evaluate_classifier_new(run_list, samples, label="", output_structure=True)




if __name__ == "__main__":
    # 新的config模块不再需要switch_model，模型配置在core.py中直接设置
    compare_and_validate()
