"""
车辆 Context 轮询工具库。

提供 ContextPoller，支持首次返回完整 JSON，后续只返回 diff 部分 JSON。

用法示例::

    from projects.mind.test_backend.service.context.context import ContextPoller
    from projects.mind.test_backend.service.context.sign import parse_auth_config

    config = parse_auth_config("公参与鉴权.md")
    poller = ContextPoller(config)

    result, log_id = poller.poll()   # 首次 -> 完整 JSON
    result, log_id = poller.poll()   # 后续 -> 仅变化部分 JSON
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from pymongo import ReturnDocument

from projects.mind.advisor.mdb_models.context_log import ContextLogDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.test_backend.config import get_mongodb_config
from projects.mind.test_backend.db.init_beanie import get_motor_client, init_db
from projects.mind.test_backend.service.context.sign import gen_sign, parse_auth_config

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_CONTEXT_SCOPE = [
    "instant_memory",
    "short_memory",
    "long_memory",
    "long_scene_memory",
    "basic_info",
    "vehicle_resource",
    "scene_description",
    "vehicle_common_info",
]

IGNORED_RETRIEVAL_SCOPES: set[str] = {"vehicle_resource"}
CONTEXT_POLL_LOCK_COLLECTION = "service_task_lock"
CONTEXT_POLL_LOCK_ID = "poll_context_loop"

# ---------------------------------------------------------------------------
# 请求构造 & 拉取
# ---------------------------------------------------------------------------


def build_request(config: dict, return_all: bool) -> tuple[str, dict, str]:
    """构造请求 URL、请求头和请求体。"""
    common = config["common_params"]
    auth = config["auth"]

    query_params: dict[str, Any] = {
        "_timestamp": int(time.time()),
        "_nonce": random.randint(0, 65535),
        "channel": auth["channel"],
        "app_id": auth["app_id"],
        "channel_app_id": auth["channel_app_id"],
        "vehicle_id": common["vehicle_id"],
        "vehicle_type": common["vehicle_type"],
        "account_id": common["account_id"],
        "login_doubao_uid": common["login_doubao_uid"],
        "face_id": common.get("face_id", ""),
        "longitude": common.get("longitude", ""),
        "latitude": common.get("latitude", ""),
    }
    querystr = "&".join(f"{k}={v}" for k, v in query_params.items() if v != "")

    body_params: dict[str, Any] = {
        "query": "获取车辆信息",
        "context_scope": DEFAULT_CONTEXT_SCOPE,
    }
    if return_all:
        body_params["with_struct"] = True
        body_params["context_custom_params"] = {
            "vehicle_resource_params": {"filter_mode": "return_all"}
        }

    body = json.dumps(body_params, ensure_ascii=False)
    sign = gen_sign("POST", querystr, auth["sk"], body)

    headers = {
        "X-Signature": f"{auth['ak']}:{sign}",
        "X-Use-PPE": "1",
        "X-Tt-Env": auth["env"],
        "Content-Type": "application/json;charset=utf-8",
    }
    url = f"https://api-vehicle.volcengine.com/aidv/v1/context/query?{querystr}"
    return url, headers, body


def fetch_context(config: dict, return_all: bool = True) -> tuple[dict, str]:
    """请求一次 Context，返回 (data, log_id)。"""
    url, headers, body = build_request(config, return_all=return_all)
    response = requests.post(
        url, headers=headers, data=body.encode("utf-8"), timeout=20
    )
    result = response.json()

    if result.get("errno") != 0:
        raise RuntimeError(
            f"Context API errno={result.get('errno')} msg={result.get('msg')}"
        )

    return result.get("data", {}), response.headers.get("x-tt-logid", "N/A")


# ---------------------------------------------------------------------------
# 数据标准化（用于稳定 diff）
# ---------------------------------------------------------------------------


def _canonicalize_list(items: list) -> Any:
    """将列表按业务主键标准化，避免顺序抖动造成伪变化。"""
    if not items:
        return items

    if not all(isinstance(item, dict) for item in items):
        return [_canonicalize(item) for item in items]

    if all("position" in item for item in items):
        return {
            item["position"]: _canonicalize(
                {k: v for k, v in item.items() if k != "position"}
            )
            for item in sorted(items, key=lambda x: str(x["position"]))
        }

    if all("object" in item for item in items):
        return {
            item["object"]: _canonicalize(
                {k: v for k, v in item.items() if k != "object"}
            )
            for item in sorted(items, key=lambda x: str(x["object"]))
        }

    if all("face_id" in item for item in items):
        return {
            f"{item.get('face_id', '')}:{item.get('position', '')}:{i}": _canonicalize(
                item
            )
            for i, item in enumerate(
                sorted(
                    items,
                    key=lambda x: (
                        str(x.get("face_id", "")),
                        str(x.get("position", "")),
                    ),
                )
            )
        }

    return [_canonicalize(item) for item in items]


def _canonicalize(value: Any) -> Any:
    """递归标准化数据结构，用于变化比较。"""
    if isinstance(value, dict):
        return {k: _canonicalize(v) for k, v in value.items() if k != "old_args"}
    if isinstance(value, list):
        return _canonicalize_list(value)
    return value


def _parse_vehicle_common_info_text(content: str) -> Any:
    """将 vehicle_common_info 的展示文本转成稳定结构。"""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    parsed: dict[str, str] = {}
    for line in lines:
        if not line.startswith("## "):
            continue
        body = line[3:]
        if "：" not in body:
            continue
        position, description = body.split("：", 1)
        parsed[position.strip()] = description.strip()
    return parsed if parsed else content


def normalize_context(data: dict) -> dict:
    """
    将 retrieval 中可解析的 JSON 字符串转为结构化对象，并做 diff 标准化。
    返回的结构固定包含 ``retrieval`` 和 ``structured_retrieval`` 两个顶层键。
    """
    normalized: dict = {
        "retrieval": {},
        "structured_retrieval": _canonicalize(data.get("structured_retrieval", {})),
    }

    for scope, content in data.get("retrieval", {}).items():
        if scope in IGNORED_RETRIEVAL_SCOPES:
            continue
        if scope == "vehicle_common_info" and isinstance(content, str):
            normalized["retrieval"][scope] = _canonicalize(
                _parse_vehicle_common_info_text(content)
            )
            continue
        if isinstance(content, str):
            try:
                normalized["retrieval"][scope] = _canonicalize(json.loads(content))
                continue
            except (json.JSONDecodeError, TypeError):
                pass
        normalized["retrieval"][scope] = _canonicalize(content)

    return normalized


# ---------------------------------------------------------------------------
# Diff 算法
# ---------------------------------------------------------------------------


def get_changes(json1, json2):
    """
    递归比较两个JSON，返回只包含变化部分的JSON
    """
    if not isinstance(json1, dict) or not isinstance(json2, dict):
        return None

    changes = {}

    # 检查所有在json2中的键
    for key in json2:
        if key not in json1:
            # 新增的键
            changes[key] = json2[key]
        else:
            # 键都存在，比较值
            val1 = json1[key]
            val2 = json2[key]

            # 如果都是字典，递归比较
            if isinstance(val1, dict) and isinstance(val2, dict):
                nested_changes = get_changes(val1, val2)
                if nested_changes:  # 只有有变化时才添加
                    changes[key] = nested_changes

            # 如果都是列表，比较整个列表
            elif isinstance(val1, list) and isinstance(val2, list):
                if val1 != val2:
                    changes[key] = val2  # 整个列表变化时直接使用新列表

            # 基本类型的比较
            else:
                if val1 != val2:
                    changes[key] = val2

    return changes


# ---------------------------------------------------------------------------
# 高层封装：ContextPoller
# ---------------------------------------------------------------------------


class ContextPoller:
    """
    车辆 Context 轮询器。

    Args:
        config:     由 :func:`parse_auth_config` 解析的鉴权 & 公参配置。
        return_all: ``True``（默认）使用全量 vehicle_resource，``False`` 使用默认过滤。

    每次调用 :meth:`poll`：
    - **首次**：返回完整标准化 JSON。
    - **后续**：返回仅包含变化字段的 diff JSON；若无变化则返回空字典。
    """

    def __init__(self, return_all: bool = True) -> None:
        _config_file = Path(__file__).parent / "公参与鉴权.md"
        self._config = parse_auth_config(str(_config_file))
        self._return_all = return_all
        self._previous: dict | None = None

    def poll(self) -> tuple[dict, dict, str, str]:
        """
        拉取一次 Context。

        Returns:
            ``(result_json, normalized_json, log_id, log_type)``。

        Raises:
            RuntimeError: 接口返回非零 errno。
        """
        data, log_id = fetch_context(self._config, self._return_all)
        normalized = normalize_context(data)

        if self._previous is None:
            self._previous = normalized
            return normalized, normalized, log_id, "full"

        changed_json = get_changes(self._previous, normalized)

        self._previous = normalized

        return changed_json, normalized, log_id, "diff"

    def reset(self) -> None:
        """清除历史快照，下次 poll 将重新返回完整数据。"""
        self._previous = None


async def _save_context_log(log_id: str, context: dict, log_type: str) -> None:
    if not context:
        return

    doc = ContextLogDoc(log_id=log_id, context=context, log_type=log_type)
    await mdb_api.create(ContextLogDoc, doc)


async def _acquire_poll_lock(
    lock_collection, owner_id: str, lease_seconds: float
) -> bool:
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=lease_seconds)
    doc = await lock_collection.find_one_and_update(
        {
            "_id": CONTEXT_POLL_LOCK_ID,
            "$or": [
                {"owner_id": owner_id},
                {"expires_at": {"$lte": now}},
                {"expires_at": {"$exists": False}},
            ],
        },
        {
            "$set": {
                "owner_id": owner_id,
                "expires_at": expires_at,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return bool(doc and doc.get("owner_id") == owner_id)


async def _release_poll_lock(lock_collection, owner_id: str) -> None:
    now = datetime.utcnow()
    await lock_collection.update_one(
        {"_id": CONTEXT_POLL_LOCK_ID, "owner_id": owner_id},
        {
            "$set": {
                "expires_at": now,
                "updated_at": now,
            }
        },
    )


async def poll_context_loop(interval: float = 10.0) -> None:
    """每隔 interval 秒拉取一次 Context，将完整/diff 数据写入 MongoDB。"""
    poller = ContextPoller()
    mongodb_config = get_mongodb_config()
    lock_collection = get_motor_client(mongodb_config.mongodb_uri)[
        mongodb_config.mongodb_db
    ][CONTEXT_POLL_LOCK_COLLECTION]
    owner_id = f"{socket.gethostname()}:{os.getpid()}"
    lease_seconds = max(interval * 2, 15.0)
    retry_interval = min(interval, max(1.0, lease_seconds / 3))

    index = 0
    is_leader = False
    try:
        while True:
            has_lock = await _acquire_poll_lock(
                lock_collection, owner_id, lease_seconds
            )
            if not has_lock:
                if is_leader:
                    print(f"Context poll leadership lost: owner_id={owner_id}")
                    is_leader = False
                    poller.reset()
                await asyncio.sleep(retry_interval)
                continue

            if not is_leader:
                print(f"Context poll leadership acquired: owner_id={owner_id}")
                is_leader = True
                poller.reset()

            diff_result, full_result, log_id, log_type = poller.poll()

            if diff_result:
                # 每 10 次强制全量一次，方便diff数据merge
                force_full = index % 10 == 0
                result = full_result if force_full else diff_result
                log_type = "full" if force_full else log_type

                print(
                    f"[{index}] log_id={log_id}, log_type={log_type}, keys={list(result.keys()) if result else []}"
                )
                await _save_context_log(log_id, result, log_type)
                index += 1

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        await _release_poll_lock(lock_collection, owner_id)
        raise
    except KeyboardInterrupt:
        await _release_poll_lock(lock_collection, owner_id)
    except Exception:
        await _release_poll_lock(lock_collection, owner_id)
        raise


__all__ = [
    "ContextPoller",
    "fetch_context",
    "normalize_context",
    "parse_auth_config",
    "poll_context_loop",
]

if __name__ == "__main__":
    init_db()
    asyncio.run(poll_context_loop())
