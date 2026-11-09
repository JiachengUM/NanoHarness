import io
import json

import httpx
from fastapi import UploadFile

from projects.mind.complex_reasoning.task_data.dataset import (
    ComplexReasoningDatasetMeta,
)
from projects.mind.complex_reasoning.task_data.input import ComplexReasoningCase
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.complex_reasoning.task_mdb_models.dataset import (
    ComplexReasoningDatasetDoc,
)
from projects.mind.intent.repositories import mdb_api
from projects.mind.intent.task_data.message import Message
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.utils.file_import import import_file_to_db

API_BASE = "http://ai-eval-dev.extour-inc.com/api/v1"
API_URL = f"{API_BASE}/dataset-item/list"
_LOGIN_URL = f"{API_BASE}/auth/login"
_LOGIN_USERNAME = "exturing_admin"
_LOGIN_PASSWORD = "REDACTED"


def _get_auth_header() -> dict[str, str]:
    """通过登录接口获取 Bearer Token，返回 Authorization 请求头。"""
    resp = httpx.post(
        _LOGIN_URL,
        json={"username": _LOGIN_USERNAME, "password": _LOGIN_PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 200:
        raise RuntimeError(f"登录失败: {body.get('message')}")
    token = body["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _fetch_dataset(dataset_id: str, auth_header: dict[str, str]) -> dict:
    """通过 detail 接口获取数据集信息。"""
    resp = httpx.get(
        f"{API_BASE}/dataset/detail/{dataset_id}",
        headers=auth_header,
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    print(f"数据集信息: {body}")
    if body.get("code") != 200:
        raise RuntimeError(f"获取数据集信息失败: {body.get('message')}")
    return body["data"]


def _fetch_dataset_items(dataset_id: str, auth_header: dict[str, str]) -> list[dict]:
    """向接口请求数据集明细，返回 data 列表。"""
    resp = httpx.post(
        API_URL,
        json={"dataset_id": dataset_id, "is_first": False},
        headers=auth_header,
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 200:
        raise RuntimeError(f"接口返回错误: {body.get('message')}")
    return body["data"]


def _build_tree(items: list[dict]) -> list[dict]:
    """将平铺列表按 parent_id 组装成树，返回根节点列表。"""
    id_map: dict[str, dict] = {item["id"]: {**item, "children": []} for item in items}
    roots: list[dict] = []
    for item in items:
        pid = item.get("parent_id")
        if pid is None:
            roots.append(id_map[item["id"]])
        elif pid in id_map:
            id_map[pid]["children"].append(id_map[item["id"]])
    return roots


def _collect_paths(node: dict, current: list[dict]) -> list[list[dict]]:
    """DFS 收集从当前节点到所有叶子节点的路径（每条路径为一次多轮会话）。"""
    current = current + [node]
    if not node["children"]:
        return [current]
    paths: list[list[dict]] = []
    for child in node["children"]:
        paths.extend(_collect_paths(child, current))
    return paths


def _roots_to_cases(roots: list[dict]) -> list[dict]:
    """将树的根节点列表转换为 ComplexReasoningCase 的字典列表。"""
    cases: list[dict] = []
    for index, root in enumerate(roots):
        paths = _collect_paths(root, [])
        user_query_lists = [
            [Message(role="user", content=node["question"]) for node in path]
            for path in paths
        ]

        expected_attrs: dict = root.get("expected_result_attrs") or {}

        case = ComplexReasoningCase(
            case_id=f"Case_{index + 1}",
            context_config={},
            # context_config=root.get("custom_attrs") or {},
            user_query_lists=user_query_lists,
            expected_script=expected_attrs.get("answer", "") or "",
            tags=[],
        )
        cases.append(case.model_dump())
    return cases


async def dataset_create(dataset_id: str) -> int:
    """从远端接口拉取数据集明细，转换为 ComplexReasoningCase 并写入数据库。

    Args:
        dataset_id: 要创建的数据集 ID。

    Returns:
        成功插入的记录数。
    """
    await init_db()  # 初始化数据库连接
    auth_header = _get_auth_header()

    # 1. 获取数据集信息，取 name
    dataset = _fetch_dataset(dataset_id, auth_header)
    dataset_name = dataset["name"]

    # 2. 在 MongoDB 中创建新的数据集记录
    payload = ComplexReasoningDatasetMeta(name=dataset_name)
    doc = await mdb_api.create(ComplexReasoningDatasetDoc, payload)

    # 3. 拉取数据集明细，转换并写入，关联到新建的 dataset
    items = _fetch_dataset_items(dataset_id, auth_header)
    print("item length:", len(items))
    roots = _build_tree(items)
    cases = _roots_to_cases(roots)

    content = json.dumps(cases, ensure_ascii=False).encode("utf-8")
    file = UploadFile(filename="data.json", file=io.BytesIO(content))

    return await import_file_to_db(
        file, ComplexReasoningCaseDoc, "json", base_data={"dataset_id": str(doc.id)}
    )


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="从远端接口创建数据集")
    parser.add_argument(
        "--dataset_id", type=str, required=True, help="要创建的数据集 ID"
    )
    args = parser.parse_args()

    inserted_count = asyncio.run(dataset_create(args.dataset_id))
    print(f"成功插入 {inserted_count} 条记录")

# python -m projects.mind.test_backend.scripts.dataset_create --dataset_id 69c662280b5c2ffb7b617377
