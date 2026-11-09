#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import sys
import random
import time
import uuid
from typing import Optional

import requests


def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def build_sorted_query(raw_query: str) -> str:
    if not raw_query:
        return ""
    parts = raw_query.split("&")
    parts.sort()
    return "&".join(parts)


def generate_signature(sk: str, method: str, raw_query: str, body: Optional[str]) -> str:
    sorted_query = build_sorted_query(raw_query)
    to_sign = method + "\n" + sorted_query + "\n"
    if body and len(body) > 0:
        to_sign += md5_hex(body) + "\n"
    digest = hmac.new(sk.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()

# http://101.126.11.190/sgm-volc-llm-agent-dev/dpfm/v1/agent/do/stream
HOST = "http://101.126.11.190/sgm-volc-llm-agent-dev"
AK = "biekefd2ac80148034f53f7a46133330ca"
SK = "ssassasUpNAgVQyiGvqPaCfcpHmgWezppUvFOxdiQOCs"
RAW_QUERY_BASE = ""  # 例如: "chat_id=123&limit=84"，没有就留空字符串
BODY = json.dumps({
    "query": "打开车窗",
    "chat_id": "356e0e6f569aa7845bd8ada738c79f5c",
    # "request_id": "078b436e-4dd7-43c4-b339-81234afa3f0c",
    "intent_type": "vehicle_control", # vehicle_control, media, navigation
    "role_id": "default",
    "intent_log_id": "2025040812061117C8C47F18C05DD79F12",
    "history": [],
    "car_info": {
        "vehicle_name": "越野车",
        "sound_zone": "velit consectetur ut nulla",
        "audio_name": "剑梓玥",
        "audio_producer": "nisi",
        "current_location": "sit anim",
        "nav_dest_name": "郦梓萱",
        "nav_dest_address": "云南省 诸乡县 秀洲区 狂中心1942号 11单元",
        "battery": 10,
        "tts_language": "anim eiusmod elit laboris commodo"
    }
}, ensure_ascii=False, separators=(",", ":"))  # 注意需与实际发送完全一致
TIMEOUT = 60
DRY_RUN = False  # 只生成签名并打印 curl，不实际发请求
# None 表示不限制行数；设为正整数可限制打印前 N 行
MAX_LINES = None


def main():
    base = HOST.rstrip("/")
    url = base + "/dpfm/v1/agent/do/stream"
    method = "POST"
    body = BODY

    # 追加必填鉴权参数 _timestamp 与 _nonce（服务端60秒窗口）
    ts = str(int(time.time()))
    # 服务端要求 _nonce 为 [0,65535] 的十进制整数
    nonce = str(random.randint(0, 65535))
    raw_query_parts = []
    if RAW_QUERY_BASE:
        raw_query_parts.append(RAW_QUERY_BASE)
    raw_query_parts.append(f"_timestamp={ts}")
    raw_query_parts.append(f"_nonce={nonce}")
    raw_query = "&".join([p for p in raw_query_parts if p])

    # 不调用 /dpfm/v1/plugin/do/prepare

    signature = generate_signature(SK, method, raw_query, body)
    x_signature = f"{AK}:{signature}"

    headers = {
        "Content-Type": "application/json",
        "X-Signature": x_signature,
    }

    full_url = url if not raw_query else f"{url}?{raw_query}"
    print("Requesting:", full_url)
    print("X-Signature:", x_signature)

    if DRY_RUN:
        print("\n# curl 示例：")
        print(f"curl -X POST \"{full_url}\" \\")
        print("  -H 'Content-Type: application/json' \\")
        print(f"  -H 'X-Signature: {x_signature}' \\")
        print(f"  -d '{body}'")
        return 0

    with requests.post(full_url, data=body.encode("utf-8"), headers=headers, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        # 明确指定 UTF-8，避免 SSE 在无 charset 时被按 ISO-8859-1 解码导致乱码
        r.encoding = "utf-8"
        print("Status:", r.status_code)
        print("--- SSE stream ---")
        count = 0
        for line in r.iter_lines(decode_unicode=True):
            if line:
                print(line)
                count += 1
                if isinstance(MAX_LINES, int) and MAX_LINES > 0 and count >= MAX_LINES:
                    break


if __name__ == "__main__":
    sys.exit(main())