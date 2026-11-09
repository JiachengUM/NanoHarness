from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from projects.sgm_prod.classification.llm import llm_fallback

# 读取我们刚改的 Volvo 提示词
VOLVO_PROMPT_FILE = Path(__file__).parent.parent / "classification" / "assets" / "Volvo" / "llm_classfication" / "prompt.py"
namespace = {}
exec(open(VOLVO_PROMPT_FILE, encoding="utf-8").read(), namespace)
VOLVO_PROMPT = namespace["SYSTEM_PROMPT"]

CASES: list[dict] = [
    {
        "name": "百科查询-介绍人物",
        "query": "介绍一下周杰伦",
        "expect": "simple",
    },
    {
        "name": "音乐播放",
        "query": "播放周杰伦的歌",
        "expect": "simple",
    },
    {
        "name": "导航到具体地点",
        "query": "先导航到上海圆圆的湖",
        "expect": "complex",
    },
    {
        "name": "复杂规划",
        "query": "帮我规划一个周末两天上海到杭州的亲子自驾游行程，要避开拥堵并安排充电和餐厅",
        "expect": "complex",
    },
    # 额外加几个截图中的场景测试
    {
        "name": "实时资讯",
        "query": "介绍一下周杰伦",
        "expect": "simple",
    },
    {
        "name": "天气查询",
        "query": "今天上海嘉定区的天气怎么样？",
        "expect": "simple",
    },
    {
        "name": "百科常识",
        "query": "一杯美式咖啡有多少卡路里？",
        "expect": "simple",
    },
    {
        "name": "车型参数查询",
        "query": "2026款沃尔沃XC60的百公里油耗是多少？",
        "expect": "simple",
    },
    {
        "name": "影视资讯",
        "query": "最近上映的热门电影有哪些？",
        "expect": "simple",
    },
    {
        "name": "生活服务",
        "query": "附近的星巴克门店几点开门？",
        "expect": "simple",
    },
    {
        "name": "健康建议",
        "query": "感冒期间适合吃什么食物？",
        "expect": "simple",
    },
    {
        "name": "概念/术语解释",
        "query": "什么是插电混动汽车？",
        "expect": "simple",
    },
    {
        "name": "闲聊/轻娱乐",
        "query": "讲一个适合开车听的冷笑话",
        "expect": "simple",
    },
    {
        "name": "音乐内容推荐",
        "query": "推荐几首适合开车听的歌",
        "expect": "simple",
    },
    {
        "name": "模糊音乐-封面反查",
        "query": "呃有我记得有个专辑它的封面是一个黄色的香蕉我想听这里面的一个主打歌曲",
        "expect": "complex",
    },
    {
        "name": "模糊音乐-关系反查",
        "query": "我想听周杰伦前女友的歌",
        "expect": "complex",
    },
]


def test_volvo_prompt_latest_failure_boundaries() -> None:
    assert "体感或情绪前缀" in VOLVO_PROMPT
    assert "未提出车控动作" in VOLVO_PROMPT
    assert "仍按单一媒体请求判 simple" in VOLVO_PROMPT
    assert "我有点热播放我常听的歌" in VOLVO_PROMPT
    assert "我有点热，播放我常听的歌" in VOLVO_PROMPT
    assert "单一媒体播放请求前有体感或情绪前缀时" not in VOLVO_PROMPT
    assert "一定是复杂" not in VOLVO_PROMPT
    assert "播放周杰伦演唱会的开场曲" in VOLVO_PROMPT
    assert "我要听周杰伦世界末日，现场版" in VOLVO_PROMPT
    assert "打开车窗和空调" in VOLVO_PROMPT
    assert "我的玻璃水怎么加" in VOLVO_PROMPT
    assert "最后一个" in VOLVO_PROMPT
    assert "添加服务区为途经点" in VOLVO_PROMPT
    assert "到下个途经点有多远" in VOLVO_PROMPT
    assert "我要给你洗澡了" in VOLVO_PROMPT


async def _run_case(case: dict) -> tuple[bool, str]:
    """返回 (是否匹配, 结果)"""
    result = await llm_fallback(
        case["query"],
        history=[],
        prompt=VOLVO_PROMPT,
    )
    is_match = result == case["expect"]
    return is_match, result

async def main() -> None:
    print("=== 使用 Volvo 提示词测试 ===")
    print(f"\n提示词：\n{VOLVO_PROMPT[:200]}...\n")
    results = []
    
    for idx, case in enumerate(CASES, 1):
        is_match, result = await _run_case(case)
        results.append(is_match)
        
        status = "[PASS]" if is_match else "[FAIL]"
        print(f"{idx}. {status} {case['name']}")
        print(f"   Query: {case['query']}")
        print(f"   预期: {case['expect']}，实际: {result}")
        
        if idx < len(CASES):
            print()

    correct = sum(results)
    total = len(results)
    print(f"\n=== 总结: {correct}/{total} 符合预期 ===")

if __name__ == "__main__":
    asyncio.run(main())
