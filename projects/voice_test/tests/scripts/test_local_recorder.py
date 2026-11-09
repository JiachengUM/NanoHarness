#!/usr/bin/env python3
"""本地记录服务最小交互测试：health → 回车 start → 回车 stop。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PORT = os.environ.get("PORT", "8765")
BASE = f"http://127.0.0.1:{PORT}"
CASE_ID = "test_case"


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read().decode())


def _post(path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def run_local_recorder_smoke_test(case_id: str = CASE_ID, batch_id: str = "") -> None:
    print(f"[1/3] GET /health  ({BASE})")
    health = _get("/health")
    print(json.dumps(health, ensure_ascii=False, indent=2))

    if not health.get("ready"):
        issues = health.get("issues") or []
        print(f"\nFAIL: 本地记录未就绪，不进入 start 流程")
        if issues:
            print("问题：" + " · ".join(issues))
        print("请先解决上述问题，再重新运行本测试。")
        return

    input("\n设备就绪，回车 → 开始本地记录 …")
    print("[2/3] POST /start")
    print(
        json.dumps(
            _post("/start", {"case_id": case_id, "batch_id": batch_id}),
            ensure_ascii=False,
            indent=2,
        )
    )

    input("\n回车 → 结束本地记录 …")
    print("[3/3] POST /stop")
    print(json.dumps(_post("/stop", {"case_id": case_id}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        run_local_recorder_smoke_test()
    except urllib.error.URLError as exc:
        print(f"连不上本地记录服务，请先启动: python local_recorder.py\n{exc}")
