import asyncio

from rich import print

from nanoai.model.config import ModelName, create_client, AsyncOpenAI
from nanoai.utils.async_utils import amap

from projects.mind.intent.alg.core import (
    Message,
    IntentClsPrompt, 
    _intent_cls, 
    IntentClassifierLLM
)

from projects.mind.intent.tests.intent_data.test_category import (
   category_chat, 
   category_vehicle_control, 
   category_vehicle_other,
)

def create_prompt():
    
    categories = ["闲聊", "座舱内的车辆控制", "其它不属于上述类别的"]

    #categories = [category_chat, category_vehicle_control, category_vehicle_other]

    return IntentClsPrompt(categories=categories)


def test_intent_cls_prompt():
    '''用于看提示词'''
    prompt = create_prompt()

    print(prompt.render())


def test_intent_cls():
    '''用于看提示词的效果'''

    prompt = create_prompt()

    client, model = create_client(
        ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        client_class = AsyncOpenAI,
        )
    
    queries = [
        # 闲聊的
        "你好",
        #"在干嘛呢",

        # 车控的
        "空调提到25度",
        #"车窗打开",

        # 其它
        "帮我查一下最新的股市数据"
    ]

    for query in queries:
        result = asyncio.run(
            _intent_cls(
            prompt,
            query, 
            model=model, 
            client=client))
        
        print(f"\nquery: {query}")
        print(f"意图: {result[0]}")
        print(f"原始查询: {result[1][0]}")
        print(f"系统提示: {result[1][1]}")


inputs = [
    # "车控"
    (
        "关掉它", 
        [
        Message(role="user", content="打开空调"),
        Message(role="assistant", content="空调已打开")
        ]
    ),
    # "聊天"
    (
        "今天有点热啊",
        [
            Message(role="user", content="你接受到车门打开了，你就要把信号发给我"),
            Message(role="assistant", content="好的，我明白了")
        ],
    ),
    # 其它
    (
        "帮我查一下最新的股市数据",
        [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！有什么我可以帮助你的吗？")
        ],
    ),
]


def test_intent_classifer():
    classifier = IntentClassifierLLM(
        ["闲聊", "座舱内的车辆控制", "其它不属于上述类别的"],
        model = ModelName.DOUBAO_SEED_1_6_FLASH_250828,
    )
    # 是否并发执行
    concurrent = False

    if not concurrent:
        for query, messages in inputs:
            result = classifier.run(query, messages)
            print("\n")
            print(result)
        return

    # 并发执行
    async def run(params):
        query, messages = params
        return await classifier._run_cls(query, messages)
    
    # 将inputs转换为参数列表（只传递必要的参数）
    params_list = [(query, messages) for query, messages in inputs]
    
    res, stats = asyncio.run(amap(run, params_list, progress=True))
    print(res)
    stats.print()


def main():
    # test_intent_cls_prompt()
    # test_intent_cls()
    test_intent_classifer()


if __name__ == "__main__":
    main()