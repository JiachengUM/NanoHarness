import asyncio
import json
from pathlib import Path
import sys
import time
from typing import Optional
import uuid
import pandas as pd

from openpyxl import load_workbook
import requests
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from projects.hwhms.api import INTENT_TYPE_TO_DOMAIN, History
from projects.hwhms.car_a.run_test import parse_multi_round_data
from projects.hwhms.common import volcengine_api
from projects.hwhms.datasets import DATASET_ROOT, Sample

hw_must_pass_file_path = DATASET_ROOT / "1022" / "hwhms_must_pass_datasets.xlsx"

def load_query_from_excel_multi_rounds(file_path: str):
    """
    解析excel内容，提取query和讯飞的语义
    """
    queries: list[tuple(str, list[History], str)] = []
    try:
        ## 解析excel
        wb = load_workbook(file_path)
        sheets = pd.read_excel(file_path, sheet_name=None)

        for sheet_name, df in sheets.items():
            # 获取当前 Sheet
            ws = wb[sheet_name]

            # 遍历每一行
            for index, row in df.iterrows():

                # 解析多轮对话数据
                query, intent, history = parse_multi_round_data(row)
                ## 组装数据  循环history的内容，将q和a组装成一句话
                history_list = []
                for h in history:
                    history_list.append({"q": h['q'], "a": h['a']})
                queries.append((query, history_list, intent))
                continue
                               

    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 不存在")
    except PermissionError:
        print(f"权限错误: 无法访问文件或目录，请检查权限设置")
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")

    return queries

async def test_volcengine_intent(query: str, history: Optional[list[volcengine_api.HistoryItem]] = None):
    result = await volcengine_api.volcengine_intent(query, history)
    print(result)
    return result  # 返回结果

async def test_hwhms_api(query: str, history: Optional[list[History]] = None):
    url = "http://127.0.0.1:18992/v1/exturing/chat/intent/chat/completions"
    headers = {
        "Authorization": "Bearer lNTZIiZXf_-uwfTE1z2oQM5RekCl94GuiHFTb3ntnK5XAguc-SWrB6hQBUHybggHFYko-iPDAGexPgPdexINizhEQGBGyDeBlOOcFxZQvTEI52tfBeUfJhkV-ADH57QlLrjJxtSV8VUsVIC1hFSB61vOF4rNEDi2kwoc6I",
        "Content-Type": "application/json"
    }
    payload = {"messages": {"query": query, "history": history, "chat_id": str(uuid.uuid4()), "question_id": str(uuid.uuid4()), "car_type": "CAR_A"}}
    response = requests.post(url, headers=headers, json=payload)
    print(response.text)
    return response.json()


async def main():
    """主函数：批量测试意图分类"""
    dataset_path = Path(".") / "projects" / "hwhms" / "datasets"    
    filepath = dataset_path / "1018" / "hwhms_multi_rounds.xlsx"
    samples: list[tuple(str, list[History], str)] = load_query_from_excel_multi_rounds(filepath)
    correct = 0

    correct_samples = []
    wrong_samples = []
    
    for sample in samples:
        
        # 直接 await，不需要 asyncio.run()
        expected = sample[2]
        result = await test_hwhms_api(sample[0], sample[1])
        
        # {'id': 'cmpl-7568b7b061d84deabcd0d655', 'object': 'text_completion', 'created': 1761622179, 'choices': [{'rewritten_query': '查询鄂W车牌号的归属地', 'intent': {'domain': 'CAR_TIPS_DOMAIN', 'query': '鄂 W 是哪里的车牌号呀'}, 'reject': False}]}
        # 解析，获取domain
        domain = result['choices'][0]['intent']['domain']
        print(f"domain: {domain}, expected: {expected}")

        if domain == INTENT_TYPE_TO_DOMAIN.get(expected):
            correct_samples.append({"query": sample[0], "history": sample[1], "actual": domain})
            correct += 1
        else:
            wrong_samples.append({"query": sample[0], "history": sample[1], "actual": domain})
        print(f"正确数量: {correct}")
        ## 休眠1秒防止请求频率过高
        await asyncio.sleep(1)  # 使用异步 sleep
    
    print(f"正确率: {correct / len(samples)}")
    # 将correct_samples和wrong_samples写入一个json文件
    with open(DATASET_ROOT / "1028" / "correct_samples.json", "w", encoding='utf-8') as f:
        json.dump(correct_samples, f, ensure_ascii=False, indent=4)
    with open(DATASET_ROOT / "1028" / "wrong_samples.json", "w", encoding='utf-8') as f:
        json.dump(wrong_samples, f, ensure_ascii=False, indent=4)
    


if __name__ == "__main__":
    """
    验证火山api对用车助手case的意图分类准确率
    """
    asyncio.run(main())
    