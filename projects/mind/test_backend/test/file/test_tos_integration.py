"""真实 TOS 集成测试：验证上传和下载功能是否正常。

直接运行：
    .venv/Scripts/python.exe projects/mind/test_backend/test/file/test_tos_integration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from projects.mind.test_backend.config import get_tos_config
from projects.mind.test_backend.utils.huoshan_tos import TosClient


def main() -> None:
    cfg = get_tos_config()
    print(f"[config] bucket={cfg.bucket_name}")
    print(f"[config] endpoint={cfg.endpoint}")
    print(f"[config] region={cfg.region}")
    print(f"[config] base_path={cfg.base_path}")
    print()

    client = TosClient(cfg)

    test_key = client.build_object_key("integration_test", "hello_tos.txt")
    test_content = b"Hello, Volcengine TOS! This is an integration test.\n"

    # === 1. 上传 ===
    print(f"[upload] object_key={test_key}")
    try:
        key = client.upload_bytes(test_key, test_content, content_type="text/plain")
        print(f"[upload] success, key={key}")
    except Exception as exc:
        print(f"[upload] FAILED: {exc}")
        return 1
    print()

    # === 2. 下载 ===
    print(f"[download] object_key={test_key}")
    try:
        data = client.download_bytes(test_key)
        print(f"[download] success, size={len(data)} bytes")
        print(f"[download] content: {data.decode('utf-8').strip()}")
        if data == test_content:
            print("[download] content matches! OK")
        else:
            print("[download] content mismatch! FAIL")
            return 1
    except Exception as exc:
        print(f"[download] FAILED: {exc}")
        return 1
    print()

    # === 3. 预签名 URL ===
    print(f"[presigned_url] object_key={test_key}")
    try:
        url = client.presigned_get_url(test_key, expires_sec=300)
        print(f"[presigned_url] success: {url}")
    except Exception as exc:
        print(f"[presigned_url] FAILED: {exc}")
        return 1
    print()

    print("=== ALL TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
