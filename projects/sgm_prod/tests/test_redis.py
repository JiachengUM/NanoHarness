"""
读取 SGM 写入 Redis 的 agent 状态（与 session.AgentManager 使用同一套环境变量）。

用法（在仓库根目录，且 PYTHONPATH=. 或已配置 .vscode）：

  python projects/sgm_prod/tests/test_redis.py              # 列出 sgm:agent:* 的 key
  python projects/sgm_prod/tests/test_redis.py <chat_id>    # 打印该会话的 JSON

依赖 projects/sgm_prod/.env 中的 SGM_REDIS_*（至少 SGM_REDIS_HOST）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import redis
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _client() -> redis.Redis:
    host = os.environ.get("SGM_REDIS_HOST")
    if not host:
        print("未设置 SGM_REDIS_HOST，请检查 projects/sgm_prod/.env", file=sys.stderr)
        sys.exit(1)
    return redis.Redis(
        host=host,
        port=int(os.environ.get("SGM_REDIS_PORT", "6379")),
        db=int(os.environ.get("SGM_REDIS_DB", "0")),
        password=os.environ.get("SGM_REDIS_PASSWORD") or None,
        decode_responses=True,
        socket_connect_timeout=10,
    )


def _print_json(raw: str) -> None:
    obj = json.loads(raw)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> None:
    prefix = os.environ.get("SGM_AGENT_REDIS_PREFIX", "sgm:agent")
    r = _client()
    if not r.ping():
        print("Redis PING 失败", file=sys.stderr)
        sys.exit(1)
    print("Redis PING: OK")

    chat_id = sys.argv[1] if len(sys.argv) > 1 else None
    pattern = f"{prefix}:*"

    if chat_id:
        key = f"{prefix}:{chat_id}"
        raw = r.get(key)
        if raw is None:
            print(f"无数据: {key}")
            sys.exit(0)
        if not isinstance(raw, str):
            print(f"值类型异常: {type(raw)}", file=sys.stderr)
            sys.exit(1)
        print(f"key: {key}\n")
        _print_json(raw)
        return

    # redis 存根将 keys 标成 ResponseT，运行时 sync 客户端返回 list[str]
    keys = sorted(list(r.keys(pattern)))  # type: ignore[arg-type]
    print(f"匹配 {pattern!r} 的 key: {len(keys)} 个")
    for k in keys:
        print(f"  {k}")
    if keys:
        print(f"\n查看某条: python {Path(__file__).name} <chat_id>")


if __name__ == "__main__":
    main()
