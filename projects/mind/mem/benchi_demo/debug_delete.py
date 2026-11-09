"""
查看指定 user_id 的画像记忆，并可选择执行删除。
"""
import json
import requests

BASE_URL = "http://101.126.11.190/nanoai-mem-test"
USER_ID = "bebfaa1f00ca4a08bfd9be58a6a884cb"  # 要查看/删除的用户 ID

PROFILE_MEMORY_TYPES = [
    "profile_v1",
    "profile_device_v1",
    "profile_location_v1",
    "profile_music_v1",
    "steward_note_book",
]

def list_profile_memories() -> None:
    """请求 /memory/retrieve，只查画像类型，打印该 user_id 下所有 profile 记忆。"""
    resp = requests.post(
        f"{BASE_URL}/memory/retrieve",
        json={
            "collection_name": "SGM",
            "limit": 5000,
            "filter": {
                "memory_type": PROFILE_MEMORY_TYPES,
                "user_id": USER_ID,
            },
        },
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200:
        print("检索失败:", data)
        return
    code = data.get("code", -1)
    if code != 0:
        print(f"检索失败 code={code}, message={data.get('message', '')}")
        return
    result = data.get("data", {})
    result_list = result.get("result_list", [])
    count = result.get("count", 0)
    print(f"========== user_id={USER_ID} 的画像记忆，共 {count} 条 ==========\n")
    for i, item in enumerate(result_list, 1):
        print(f"--- [{i}] id={item.get('id')} memory_type={item.get('memory_type')} ---")
        print(json.dumps(item.get("memory_info") or {}, ensure_ascii=False, indent=2))
        print()
    if not result_list:
        print("(无画像记忆)")


def delete_memories() -> None:
    """按 user_id 删除该用户在记忆库中的全部事件与画像。"""
    body: dict = {"user_id": USER_ID}
    resp = requests.post(f"{BASE_URL}/memory/delete", json=body, timeout=30)
    print("删除结果:", resp.json())


if __name__ == "__main__":
    list_profile_memories()
    # delete_memories()
