import asyncio
import time
from functools import partial
from typing import Callable, Awaitable, Iterable, Any

from pydantic import BaseModel, Field

from nanoai.model.llm import allm_output
from nanoai.utils.async_utils import amap, drepeat_and_pick
from nanoai.utils.nl_repr import nl_repr
from projects.hwhms.car_a.core import (
    IntentClassifier,
    ClsResult,
    PoiClsResult,
)
from projects.hwhms.common.client import get_openai_client

# (用户query, 类别)
queries: list[tuple[str, str]] = [
    # 车控类别 (5个示例)
    ("打开空调", "车控"),
    ("设置空调温度为26度", "车控"), 
    ("暂停音乐", "车控"),
    ("切换到收音机频道", "车控"),
    ("关闭车窗", "车控"),
    
    # 用车知识类别 (5个示例)
    ("什么是雨刷器", "用车知识"),
    ("多久换一次雨刮条", "用车知识"),
    ("空气悬架是什么意思", "用车知识"),
    ("雨刷器怎么使用", "用车知识"),
    ("如何正确使用安全带", "用车知识"),
    
    # 新闻搜索类别 (5个示例)
    ("昨天股市怎么样", "新闻搜索"),
    ("最近有什么热点", "新闻搜索"),
    ("今天有什么重要新闻", "新闻搜索"),
    ("油价又涨了吗", "新闻搜索"),
    ("最新的科技新闻有哪些", "新闻搜索"),
    
    # 其它类别 (5个示例)
    ("你好", "其它"),
    ("今天天气怎么样", "其它"),
    ("帮我算一下1+1等于几", "其它"),
    ("推荐一部好看的电影", "其它"),
    ("今天几号了", "其它"),
]


def test_intent_cls_basic():
    classifier = IntentClassifier()

    time_start = time.time()
    res = asyncio.run(classifier.run("打开空调", output_structure=True))
    time_end = time.time()
    print(res)
    print(f"时间: {time_end - time_start}秒")

def test_intent_cls_batch(output_structure: bool):
    classifier = IntentClassifier()    
    res, stats = asyncio.run(amap(partial(classifier.run, output_structure=output_structure), [query for query, _ in queries], progress=True))
    
    correct_count = 0
    for i, (query, category) in enumerate(queries):
        print(f"预期: {category}, 结果: {nl_repr(res[i])}")

        if isinstance(res[i], Exception):
            correct = 0
            continue

        if isinstance(res[i], ClsResult):
            correct = res[i].category == category
        else:
            correct = res[i] == category

        correct_count += correct

    stats.print()

    print(f"正确率: {correct_count / len(queries)}({correct_count}/{len(queries)})")


poi_queries: list[tuple[str, str]] = [
    # 导航类别 (10个示例)
    ("导航去天坛公园", "导航"),
    ("去北京西站", "导航"),
    ("规划一下去天津的路线", "导航"),
    ("带我去最近的加油站", "导航"),
    ("导航到国贸附近的星巴克", "导航"),
    ("怎么去首都机场", "导航"),
    ("去三里屯怎么走", "导航"),
    ("导航到北京大学", "导航"),
    ("去王府井步行街", "导航"),
    ("帮我导航到朝阳大悦城", "导航"),
    
    # 地点发现类别 (10个示例)
    ("推荐几个过生日的地方", "地点发现"),
    ("附近有没有适合团建的场所？", "地点发现"),
    ("中关村附近有啥好吃的", "地点发现"),
    ("我想出去玩", "地点发现"),
    ("附近有什么好玩的", "地点发现"),
    ("推荐一些适合情侣的餐厅", "地点发现"),
    ("我想找个安静的地方看书", "地点发现"),
    ("附近有什么购物中心", "地点发现"),
    ("推荐几个适合拍照的地方", "地点发现"),
    ("我想找个地方放松一下", "地点发现"),
    
    # 其它类别 (10个示例)
    ("我想了解一下北京的历史", "其它"),
    ("帮我查一下明天的会议安排", "其它"),
    ("推荐一些学习编程的方法", "其它"),
    ("我想找个工作", "其它"),
    ("帮我规划一下今天的行程", "其它"),
    ("我想了解一下投资理财", "其它"),
    ("推荐一些健身的方法", "其它"),
    ("我想学习一门新技能", "其它"),
    ("帮我分析一下这个数据", "其它"),
    ("我想了解一下人工智能", "其它"),
]


def test_poi_intent_cls_batch(output_structure: bool):
    classifier = IntentClassifier()

    f = partial(classifier.poi_cls, output_structure=output_structure)

    # 执行1次，会失败大概15个
    res, stats = asyncio.run(amap(f, [query for query, _ in poi_queries], progress=True))

    # 执行2次，失败次数会减少到10个左右
    # res, stats = asyncio.run(amap(repeat(n_repeat=2)(f), [query for query, _ in poi_queries], progress=True))

    correct_count = 0
    for i, (query, category) in enumerate(poi_queries):
        if isinstance(res[i], Exception):
            correct = 0
            #print(f"({i})query: {query}，预期: {category}, 结果: 错误")
            print(f"({i})query: {query}，预期: {category}, 结果: {nl_repr(res[i])}")
            continue

        if isinstance(res[i], PoiClsResult):
            correct = res[i].category == category
        else:
            correct = res[i] == category

        correct_count += correct

        print(f"({i})预期: {category}, 结果: {nl_repr(res[i])}")
        if not correct:
            print(f"结果错误, query: {query}")

    stats.print()

    print(f"正确率: {correct_count / len(poi_queries):.2f}({correct_count}/{len(poi_queries)})")


async def extract_poi(query: str) -> str:
    class PoiData(BaseModel):
        location: str = Field(..., title="地点", description="地点。")

    use_doubao = True

    if False: 
        client = get_openai_client()
        llm_params = get_llm_params()
    else:
        client = None
        llm_params = {}

    res = await allm_output(
        query,
        "请提取出用户提到的地点。如果没有则返回None。",
        output_type=PoiData,
        client=client,
        **llm_params,
    )

    return res.output.location


def test_poi_extraction():

    try:
        res = asyncio.run(extract_poi(poi_queries[26][0]))
        print(f"结果: {res}")
    except Exception as e:
        print(f"错误: {e}")


    # 比较执行1次和多次

    # 执行1次，会失败4,5个左右
    res, stats = asyncio.run(amap(extract_poi, [query for query, _ in poi_queries], progress=True))
    print(nl_repr(res))
    stats.print()

    # 执行多次，失败次数会减少
    res, stats = asyncio.run(amap(drepeat_and_pick(n_repeat=2)(extract_poi), [query for query, _ in poi_queries], progress=True))
    print(nl_repr(res))

    stats.print()


async def find_unstable[T](
    func: Callable[[Any], Awaitable[T]],
    params: Iterable[Any],
) -> list[tuple[int, T, T]]:
    """
    挑选出多次执行结果不稳定的情况。
    """
    
    results0, stats0 = await amap(func, params, max_concurrent=100, progress=True)

    results1, stats1 = await amap(func, params, max_concurrent=100, progress=True)

    # 找到results0和results1不同的元素的索引
    diff = [(i, results0[i], results1[i]) for i, (r0, r1) in enumerate(zip(results0, results1)) if r0 != r1 and not isinstance(r0, Exception) and not isinstance(r1, Exception)]
    
    return diff


def test_find_unstable():
    classifier = IntentClassifier()
    f = partial(classifier.poi_cls, output_structure=False)
    # f = extract_poi
    
    diff = asyncio.run(find_unstable(f, [query for query, _ in poi_queries]))

    print("不稳定的样本：")
    for i, r0, r1 in diff:
        print(f"query: {poi_queries[i][0]}, 结果0: {nl_repr(r0)}, 结果1: {nl_repr(r1)}")


if __name__ == "__main__":
    test_intent_cls_basic()
    # test_intent_cls_batch(False)
    # test_poi_intent_cls_batch(True)
    # test_poi_extraction()
    # test_find_unstable()
