"""
主要测试llm自定义意图分类器,复杂导航和聊天
"""

import asyncio
from rich import print

from projects.mind.intent.zhiji import IntentClassifier
from projects.mind.intent.task_data.message import Message
from nanoai.utils.async_utils import amap
from nanoai.utils.nl_repr import nl_repr


# 测试用例：无历史
test_cases_basic = [
    # 复杂导航类
    ("看看附近最近的海底捞然后导航过去", "复杂导航"),
    ("附近最近的买花的地方帮我导航过去", "复杂导航"),
    ("我想抽雪茄,徐汇区帮我找一个店", "复杂导航"),
    ("找个附近3公里以内性价比最高的川菜馆,帮我导航过去", "复杂导航"),
    ("看看去虹桥火车站哪个停车场接人方便,马上帮我导航过去", "复杂导航"),
    ("有没有适合4个人的商务一点的粤菜,推荐几个看看再导航过去", "复杂导航"),
    ("有没有适合带小朋友去的公园,树木多一点的", "复杂导航"),
    ("我想出去开车兜兜风,有没有比较好的地方推荐啊", "复杂导航"),
    ("公司附近的酒店,有个朋友要过来,推荐一个500元左右的,导航过去", "复杂导航"),
    ("上海有哪些热门的景点,帮我挑一个然后导航过去", "复杂导航"),
    ("去上次说的那个商场附近找个停车场", "复杂导航"),
    ("导航到之前去过的那个景点附近的餐厅", "复杂导航"),
    
    # 聊天类（兜底）
    ("你好", "聊天"),
    ("早上好", "聊天"),
    ("随便聊聊", "聊天"),
    ("谢谢", "聊天"),
    ("最近怎么样", "聊天"),
    ("在干嘛呢", "聊天"),
    ("我想听音乐", "聊天"),
    ("我想听新闻", "聊天"),
    # 简单导航（明确地点）应该归类为聊天，因为不属于复杂导航
    ("导航到北京西站", "聊天"),
    ("去上海浦东机场", "聊天")
]

# 测试用例：无历史
test_cases_with_history = [
    # 复杂导航类
    (
        "看看附近最近的海底捞然后导航过去",
        [
            Message(role="user", content="外面天气怎么样？"),
            Message(role="assistant", content="外面天气很好，适合出门游玩")
        ],
        "复杂导航"
    ),
    (
        "附近最近的买花的地方帮我导航过去",
        [
            Message(role="user", content="打开空调"),
            Message(role="assistant", content="空调已打开")
        ],
        "复杂导航"
    ),
    (
        "我想抽雪茄,徐汇区帮我找一个店",
        [
            Message(role="user", content="有点冷啊"),
            Message(role="assistant", content="我帮你把空调调高一点")
        ],
        "复杂导航"
    ),
    (
        "找个附近3公里以内性价比最高的川菜馆,帮我导航过去",
        [
            Message(role="user", content="小途，我饿了"),
            Message(role="assistant", content="你想吃什么菜？")
        ],
        "复杂导航"
    ),
    # 聊天类（简单，上下文中有地点）
    (
        "看看去虹桥火车站哪个停车场接人方便,马上帮我导航过去",
        [
            Message(role="user", content="我要去虹桥火车站接人,之前听朋友说A区停车场那边停车很方便，"),
            Message(role="assistant", content="好的。")
        ],
        "聊天"
    ),
]

test_cases_basic_increment = [
    # 复杂导航类（新增场景，需推理/补充信息）
    ("找个能看江景的咖啡馆,离我当前位置不远的,导航过去", "复杂导航"),
    ("推荐一个适合约会的日料店,在静安区的,然后导航过去", "复杂导航"),
    ("我想找个24小时营业的药店,帮我导航过去", "复杂导航"),
    ("周边有没有适合露营的地方,帮我选一个近的导航过去", "复杂导航"),
    ("找个离地铁站近的健身房,月卡500以内的,导航过去", "复杂导航"),
    ("帮我找个宠物友好的公园,带狗狗去玩,导航过去", "复杂导航"),
    ("想找个能停车的网红奶茶店,离我这不超过5公里,导航过去", "复杂导航"),
    ("推荐一个适合商务洽谈的茶馆,在金融区附近,导航过去", "复杂导航"),
    ("我想去游泳，附近有没有合适的游泳馆", "复杂导航"),
    ("找个能看日落的江边步道，开车过去", "复杂导航"),
    ("推荐一个能办生日派对的轰趴馆，在闵行区的，导航过去", "复杂导航"),
    ("找个24小时营业的洗车店，离高速口近的，导航过去", "复杂导航"),
    ("帮我找个可以带宠物的咖啡馆，导航过去", "复杂导航"),
    ("想找个有充电桩的停车场，在中环内的，导航过去", "复杂导航"),
    ("导航到上次聚餐的那家湘菜馆", "复杂导航"),
    ("找个离演唱会场馆近的酒店，导航过去", "复杂导航"),
    ("帮我找个能钓鱼的水库，导航过去", "复杂导航"),
    ("我想爬山，附近有没有难度低的山，导航过去", "复杂导航"),
    ("找个人均80以内、有包厢的江浙菜馆，导航过去", "复杂导航"),
    ("推荐一个适合自习的书店，有充电口的，导航过去", "复杂导航"),
    ("导航到常去的那家便利店", "复杂导航"), 
    
    # 聊天类（新增场景，兜底/简单导航）
    ("导航到上海市人民广场", "聊天"),
    ("帮我打开导航功能", "聊天"),
    ("嗯，好的", "聊天"),
    ("麻烦导航到南京东路步行街", "聊天"),
    ("打开空调", "聊天"),
    ("今天天气不错", "聊天"),
    ("导航去迪士尼乐园", "聊天"),
    ("再见", "聊天"),
    ("帮我导航到公司", "聊天"),  # 公司为默认已知地点，无需额外推理
    ("导航到北京首都机场T2航站楼", "聊天"),
    ("随便逛逛，没什么特别想去的地方", "聊天"),
    ("我不想出门了，谢谢", "聊天"),
    ("天气有点冷了啊这两天", "聊天"),
    ("公司这周要去团建", "聊天"),
    ("导航到上海市黄浦区中山东一路18号外滩十八号", "聊天"),
    ("去北京市海淀区中关村南大街5号北京理工大学", "聊天"),
    ("帮我导航到广州天河区天河路383号太古汇M层", "聊天"),
    ("导航到家里的小区门口", "聊天"),
    ("今天加班好累啊", "聊天"),
    ("帮我设置一个早上7点的闹钟", "聊天"),
    ("我想买点水果，你有什么推荐吗", "聊天"),
    ("导航功能怎么用啊", "聊天"),
    ("随便走走，导航到最近的公交站就行", "聊天"),
]

test_cases_with_history_increment = [
    # 复杂导航类（历史无关键信息，仍需推理）
    (
        "周边有没有适合露营的地方,帮我选一个近的导航过去",
        [
            Message(role="user", content="周末想出去玩"),
            Message(role="assistant", content="想去户外还是室内呀？")
        ],
        "复杂导航"
    ),
    (
        "找个能看江景的咖啡馆,离我当前位置不远的,导航过去",
        [
            Message(role="user", content="我想找个安静的地方办公"),
            Message(role="assistant", content="需要有网络和充电的地方吗？")
        ],
        "复杂导航"
    ),
    (
        "帮我找个宠物友好的公园,带狗狗去玩,导航过去",
        [
            Message(role="user", content="想带我的金毛出门散步"),
            Message(role="assistant", content="需要找有草坪的公园吗？")
        ],
        "复杂导航"
    ),
    (
        "想找个能停车的网红奶茶店,离我这不超过5公里,导航过去",
        [
            Message(role="user", content="我想喝奶茶，开车去买"),
            Message(role="assistant", content="你想喝什么口味的？")
        ],
        "复杂导航"
    ),
    (
        "导航到那个轰趴馆",
        [
            Message(role="user", content="想找个能办派对的轰趴馆"),
            Message(role="assistant", content="好的，正在为您查找")
        ],
        "复杂导航"
    ),
    (
        "帮我导航过去",
        [
            Message(role="user", content="我想找个能钓鱼的地方"),
            Message(role="assistant", content="你想在市区还是郊区找？")
        ],
        "复杂导航"
    ),
    (
        "找个有充电桩的停车场导航过去",
        [
            Message(role="user", content="我开电动车出门"),
            Message(role="assistant", content="需要帮你规划充电路线吗？")
        ],
        "复杂导航"
    ),

    # 聊天类（历史补齐关键信息/兜底场景）
    (
        "导航到那个商场",
        [
            Message(role="user", content="我刚才说的是陆家嘴的正大广场"),
            Message(role="assistant", content="好的，我记住了")
        ],
        "聊天"  # 历史已明确地点，无需推理
    ),
    (
        "帮我导航到公司",
        [
            Message(role="user", content="我的公司在上海市浦东新区张江高科技园区"),
            Message(role="assistant", content="收到，已记录你的公司地址")
        ],
        "聊天"
    ),
    (
        "去机场",
        [
            Message(role="user", content="我要去的是北京首都国际机场T3航站楼"),
            Message(role="assistant", content="好的，我明白你的需求")
        ],
        "聊天"
    ),
    (
        "随便聊聊",
        [
            Message(role="user", content="推荐个附近的餐厅"),
            Message(role="assistant", content="你想吃什么类型的？")
        ],
        "聊天"  # 当前查询无导航意图，兜底为聊天
    ),
    (
        "导航到上次说的那个健身房",
        [
            Message(role="user", content="我上次提的健身房是静安寺地铁站旁的乐刻运动"),
            Message(role="assistant", content="好的，已记下来了")
        ],
        "聊天"
    ),
    (
        "导航到那个湘菜馆",
        [
            Message(role="user", content="我上次聚餐的湘菜馆是上海市徐汇区天钥桥路323号"),
            Message(role="assistant", content="好的，已记录地址")
        ],
        "聊天"
    ),
    (
        "去演唱会场馆附近的酒店",
        [
            Message(role="user", content="我要去的是上海梅赛德斯奔驰文化中心看演唱会"),
            Message(role="assistant", content="明白，你需要找附近的酒店？")
        ],
        "聊天"
    ),
    (
        "导航去吧，我想去爬山",
        [
            Message(role="user", content="我想去的是杭州西湖边的宝石山，难度低适合散步"),
            Message(role="assistant", content="好的，宝石山确实难度低")
        ],
        "聊天"
    ),
    (
        "随便聊聊",
        [
            Message(role="user", content="帮我找个附近的餐厅"),
            Message(role="assistant", content="你想吃什么类型的？")
        ],
        "聊天"
    ),
    (
        "导航到最近的公交站",
        [
            Message(role="user", content="我现在在上海市静安区南京西路1266号"),
            Message(role="assistant", content="好的，你的位置已确认")
        ],
        "聊天"
    )
]



async def run_tests(classifier: IntentClassifier, test_cases: list[tuple[str, list[Message], str]] | list[tuple[str, str]]) -> None:
    """统一的测试函数，处理有历史和无历史两种情况"""
    async def run(params: tuple[str, list[Message], str] | tuple[str, str]) -> bool:
        # 判断参数格式：2元组(无历史) 或 3元组(有历史)
        if len(params) == 2:
            query, expected = params
            messages: list[Message] | None = None
        else:
            query, messages, expected = params
        
        result = await classifier._run_llm_cls(query, messages=messages)
        category = result.category
        status = "✅" if category == expected else "❌"
        
        # 如果有历史且需要显示
        if messages is not None:
            print(f"[green]历史对话:[/green] {nl_repr(messages, use_numbering=False)}")
        
        print(f"{status} query: {query} | 预期: [green]{expected}[/green] | 实际: [blue]{category}[/blue] | 原因: {result.reason}\n")
        return category == expected
    
    res, stats = await amap(run, test_cases, progress=False)
    print(f"\n成功: {sum(1 for r in res if r)}/{len(test_cases)}")
    stats.print()


async def test_intent_classifier():
    """测试意图分类器"""
    classifier = IntentClassifier()
    # 测试基础分类（无历史对话）
    await run_tests(classifier, test_cases_basic)

    # 测试带历史对话的分类
    await run_tests(classifier, test_cases_with_history)
    
    # 增量测试用例
    await run_tests(classifier, test_cases_basic_increment)

    await run_tests(classifier, test_cases_with_history_increment)


def main():
    """运行所有测试"""
    
    asyncio.run(test_intent_classifier())
    return

if __name__ == "__main__":
    main()

