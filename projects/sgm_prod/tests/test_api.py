"""
SGM API 手动测试脚本。

直接运行：python projects/sgm_prod/tests/test_api.py

联调时改下面「URL + PAYLOAD」两行，指向 stream 或 processor 即可。
"""
from __future__ import annotations

import sys

import httpx

API_BASE = "http://sgm-complex-dev.extour-inc.com/sgm-complex"

URL_SGM_STREAM = f"{API_BASE}/v1/sgm/stream"
URL_SGM_PROCESSOR = f"{API_BASE}/v1/sgm_processor"

# /v1/sgm/stream — core.AgentDoStreamRequest；勿传 car_info: {}
PAYLOAD_SGM_STREAM: dict = {
    "chat_id": "sgm_test_stream",
    "question_id": "sgm_test_stream_q1",
    "query": "打开车窗",
    "history": [],
    "intent_type": "复杂推理",
}

# /v1/sgm_processor — SGMProcessorRequest；必填 query、request_id
PAYLOAD_SGM_PROCESSOR: dict = {
    "requestId": "374ecd43a9994651a23a28b63f1e2fa5",
    "query": "关闭座椅加热。",
    "latitude": 31.1953,
    "intent_type": "复杂推理",
    "history": [
        {
            "q": "打开空调。",
            "a": "我这就为你检查空调状态。空调已处于开启状态啦，当前车内维持24摄氏度舒适模式。如果需要调整温度、风速或者切换模式，随时跟我说就好~"
        }
    ],
    "car_info": {
        "mainEngine": "sgm-oscar",
        "longitude": 121.5073,
        "latitude": 31.1953,
        "uiAgent": None,
        "vehicleId": "f135c179-2fa3-495a-93a3-40a20baf1b89",
        "userId": ""
    },
    "vehicle_id": "f135c179-2fa3-495a-93a3-40a20baf1b89",
    "question_id": "374ecd43a9994651a23a28b63f1e2fa5",
    "request_id": "374ecd43a9994651a23a28b63f1e2fa5",
    "mem_mode": "real",
    "chat_id": "374ecd43a9994651a23a28b63f1e2fa5",
    "longitude": 121.5073
}

# 改这两行切换接口
URL = URL_SGM_PROCESSOR
PAYLOAD = PAYLOAD_SGM_PROCESSOR


def main() -> None:
    with httpx.stream("POST", URL, json=PAYLOAD, timeout=120) as resp:
        if resp.status_code >= 400:
            # 流式响应必须先 read() 才能读 .text，否则会 ResponseNotRead
            resp.read()
            print(resp.text, file=sys.stderr)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                print(line)


if __name__ == "__main__":
    main()
