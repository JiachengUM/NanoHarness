import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent))

from projects.hwhms.car_b.core import IntentClassifierCarB

queries: list[str] = [
    "今天有什么热点新闻",
    "今天天气怎么样",
    "帮我算一下1+1等于几",
    "推荐一部好看的电影",
    "今天几号了",
    "你好",
    "今天天气怎么样",
    "帮我算一下1+1等于几",
    "推荐一部好看的电影",
    "今天几号了",
    "喜马拉雅怎么用",
    "喜马拉雅怎么用",
    "我想出去玩",
    "我想去北京玩",
    "我想去上海玩",
    "多久换一次雨刮条",
    "空气悬架是什么意思",
    "雨刷器怎么使用",
    "如何正确使用安全带",
    "什么是雨刷器",
    "关闭车窗",
    "切换到收音机频道",
    "暂停音乐",
    "设置空调温度为26度",
]


def test_intent_cls_basic(output_structure: bool):
    classifier = IntentClassifierCarB()

    time_start = time.time()
    for query in queries:
        res = asyncio.run(classifier.run(query, output_structure=output_structure))
        time_end = time.time()
        print(res)
        print(f"时间: {time_end - time_start}秒")
        print(f"query: {query}")

if __name__ == "__main__":
    test_intent_cls_basic(output_structure=False)