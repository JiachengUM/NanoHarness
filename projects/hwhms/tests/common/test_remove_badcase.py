import json
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent))

from projects.hwhms.datasets import DATASET_ROOT


## 解析datasets里面的json数据，找出badcase
def parse_json_data(json_file_path: str) -> list[dict]:
    with open(json_file_path, 'r', encoding='utf-8') as f:
        json_list = json.load(f)
    return json_list

def remove_badcase(excel_file_path: str, sheet_name: str, json_list: list[dict]) -> list[dict]:
    df = pd.read_excel(excel_file_path, sheet_name=sheet_name)
    for index, row in df.iterrows():
        ## 遍历json_list，找出query和expected_category相同的item
        for item in json_list:
            if row['query'] == item['query']:
                df.drop(index, inplace=True)
    df.to_excel(excel_file_path, sheet_name=sheet_name, index=False)
    return df

if __name__ == "__main__":
    json_list = parse_json_data(DATASET_ROOT / "hwhms_data_cls_老prompt_趣味助手_results.json")
    remove_badcase(DATASET_ROOT / "1018" / "intent_cls_趣味.xlsx", "趣味助手", json_list)