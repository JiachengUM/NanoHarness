import asyncio
from rich import print

from projects.mind.intent.ydl import IntentClassifier
from projects.mind.intent.task_data.message import Message
from nanoai.utils.async_utils import amap
from nanoai.utils.nl_repr import nl_repr
from projects.mind.intent.alg.volc_intent import close_volcengine_session

# 测试用例：无历史
test_cases_basic = [
    # 车控类
    ("打开空调", "车控"),
    ("把温度调到25度", "车控"),
    ("关闭车窗", "车控"),
    ("打开天窗", "车控"),
    ("座椅加热打开", "车控"),
    
    # 一方服务类
    ("播放剑来", "一方服务"),
    ("我想听郭德纲的相声", "一方服务"),
    ("播放米小圈上学记", "一方服务"),
    ("来点好听的相声", "一方服务"),
    ("播放我订阅的公众号今天的更新", "一方服务"),
    
    # 捷停车类
    ("帮我缴停车费", "捷停车"),
    ("缴一下万达广场的停车费", "捷停车"),
    ("车停了两个小时多少钱", "捷停车"),
    
    # VQA类
    ("我今天看起来精神吗", "VQA"),
    ("我旁边那个人戴帽子了吗", "VQA"),
    ("我和副驾谁更帅", "VQA"),
    ("车后排现在有几个人", "VQA"),
    
    # 聊天类（兜底）
    ("你好", "聊天"),
    ("早上好", "聊天"),
    ("随便聊聊", "聊天"),
    ("谢谢", "聊天"),
]

# 测试用例：有历史
test_cases_with_history = [
    # 指代补全 - 车控
    (
        "帮我打开前排的",
        [
            Message(role="user", content="帮我打开座椅加热"), 
            Message(role="assistant", content="好的，已为您打开座椅加热")
        ],
        "车控"
    ),
    (
        "把后排的也打开",
        [
            Message(role="user", content="打开前排座椅加热"), 
            Message(role="assistant", content="好的"),
            Message(role="user", content="温度调高一点"), 
            Message(role="assistant", content="已调高")
        ],
        "车控"
    ),
    (
        "关掉它",
        [
            Message(role="user", content="打开空调"), 
            Message(role="assistant", content="空调已打开")
        ],
        "车控"
    ),
    
    # 无指代词 - 应忽略历史
    (
        "帮我搜搜上海比较好吃的小笼包的餐厅吧",
        [
            Message(role="user", content="你接受到车门打开了，你就要把信号发给我"), 
            Message(role="assistant", content="好的，我明白了")
        ],
        "聊天"
    ),
    (
        "播放剑来",
        [
            Message(role="user", content="打开空调"), 
            Message(role="assistant", content="空调已打开")
        ],
        "一方服务"
    ),
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
        
        result = await classifier.run(query, messages=messages)
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
    # 测试带历史对话的分类（指代补全）
    await run_tests(classifier, test_cases_with_history)
    await close_volcengine_session()

def main():
    """运行所有测试"""
    asyncio.run(test_intent_classifier())
    return

if __name__ == "__main__":
    main()