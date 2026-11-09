"""
简单/复杂意图仲裁接口手动测试脚本。

先启动服务：
python projects/sgm_prod/api.py

再运行：
python projects/sgm_prod/tests/test_classification.py
"""
from __future__ import annotations

import uuid

import httpx

API_BASE = "http://localhost:8007"
URL = f"{API_BASE}/v1/simple_complex_arbitration"


CASES: list[dict] = [
    {
        "name": "",
        "project": "baic",
        "query": "窗户打开一半",
        "history": [{'q': '导航去迪士尼先去麦当劳再去嘉定北', 'a': '路线规划已打开'}, {'q': '导航去迪士尼先去先去嘉定北地铁站接老婆再去找一个可以把车开进去取餐的麦当劳', 'a': '[em6:-14][se40][te48]抱歉，暂不支持此功能'}, {'q': '导航去人民广场', 'a': '为您找到以下结果，请说第几个'}, {'q': '导航去迪士尼先去嘉定北地铁站接老婆再去', 'a': '好的，我来规划路线。'}],
    },
    {
        "name": "",
        "project": "baic",
        "query": "把座椅加热关了，太热了",
        "history": [{'q': '导航去迪士尼先去麦当劳再去嘉定北', 'a': '路线规划已打开'}],
    },
    # {   
    #     "project": "Volvo",
    #     "name": "",
    #     "query": "播放周杰伦的歌",
    #     "history": [],
    # },
    # {
    #     "name": "结合历史的简单追问",
    #     "query": "先导航到上海圆圆的湖",
    #     "chat_id": "1234",
    #     "question_id": "1234",
    #     "history": [
    #         {
    #             "q": "今天天气怎么样",
    #             "a": "天气晴朗"
    #         }
    #     ],
    # },
    # {
    #     "name": "复杂规划",
    #     "query": "帮我规划一个周末两天上海到杭州的亲子自驾游行程，要避开拥堵并安排充电和餐厅",
    #     "history": [],
    # },
]


def build_payload(case: dict) -> dict:
    request_id = uuid.uuid4().hex
    payload = {
        "query": case["query"],
        "chat_id": case.get("chat_id", f"classification_test_{request_id[:8]}"),
        "question_id": case.get("question_id", request_id),
        "history": case.get("history", []),
    }
    if "project" in case:
        payload["project"] = case["project"]
    return payload


def main() -> None:
    with httpx.Client(timeout=120) as client:
        for idx, case in enumerate(CASES, start=1):
            payload = build_payload(case)
            resp = client.post(URL, json=payload)

            print(f"[CASE {idx}] {case['name']}")
            if case.get("project"):
                print(f"  project: {case['project']}")
            print(f"  query: {case['query']}")
            print(f"  status_code: {resp.status_code}")
            try:
                print(f"  response: {resp.json()}")
            except ValueError:
                print(f"  response: {resp.text}")


if __name__ == "__main__":
    main()
