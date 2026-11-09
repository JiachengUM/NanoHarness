import asyncio
import difflib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent))


from projects.hwhms.common.rag import rag_search_must_pass

def similarity_ratio(str1, str2):
    """使用 SequenceMatcher 计算相似度比例"""
    return difflib.SequenceMatcher(None, str1, str2).ratio()

# 示例
# str1 = "打开空调"
# str2 = "打开空调"
# time_start = time.time()
# similarity = similarity_ratio(str1, str2)
# time_end = time.time()
# print(f"时间: {(time_end - time_start) * 1000} 毫秒")
# print(f"相似度: {similarity:.2%}")  # 输出: 相似度: 54.55%

if __name__ == "__main__":
    result = asyncio.run(rag_search_must_pass("打开空调"))
    print(result)
