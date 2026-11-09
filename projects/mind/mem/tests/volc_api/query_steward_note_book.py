"""查询指定用户的 steward_note_book 画像记忆并打印到终端。

- collection_name: test_prompt
- user_id:         dzy_train_jarvis
- profile_type:    steward_note_book
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把仓库根目录加入 sys.path，让脚本在任何 cwd 下都能直接 `python xxx.py` 运行
_REPO_ROOT = Path(__file__).resolve().parents[5]  # volc_api/tests/mem/mind/projects/nanoai
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rich import print

from projects.mind.mem.volc_api.base import CollectionID
from projects.mind.mem.volc_api.profile import search_profile_memory


def main() -> None:
    collection_id = CollectionID(collection_name="test_prompt")
    user_id = "dzy_train_jarvis"
    profile_type = "steward_note_book"

    result = search_profile_memory(
        collection_id=collection_id,
        profile_type=profile_type,
        user_id=user_id,
        limit=100,
    )

    data = result.data
    print(f"共找到 {data.count} 条记忆")
    print("=" * 80)

    for idx, item in enumerate(data.result_list, start=1):
        print(f"[{idx}/{data.count}] memory_type={item.memory_type}")
        print(f"    id={item.id}")
        print(f"    user_id={item.user_id}")
        print(f"    assistant_id={item.assistant_id}")
        print(f"    time={item.time}")
        print(f"    memory_info:")
        for key, value in (item.memory_info or {}).items():
            print(f"        {key}: {value}")
        print("-" * 80)


if __name__ == "__main__":
    main()
