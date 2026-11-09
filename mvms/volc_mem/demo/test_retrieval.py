import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mvms.volc_mem.api.retrieval import (
    SearchMemory,
    MemoryFilter,
    search_memory,
)


def test_search_memory():
    """测试带查询关键词的搜索"""
    request = SearchMemory(
        collection_name="memory_test1",
        query="空调",  # 搜索关键词
        limit=2,  # 最多返回 2 条结果
        filter=MemoryFilter(
            memory_type=["sys_event_v1", "sys_profile_v1"],
            user_id="user_01",  # 只搜索该用户的记忆
        ),
    )

    rsp = search_memory(request)
    print(rsp.json())


if __name__ == "__main__":
    test_search_memory()

