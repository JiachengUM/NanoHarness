import time
from enum import Enum
import asyncio

import pytest

from nanoai.model.config import ModelName, create_client, AsyncOpenAI
from nanoai.utils.nl_repr import nl_repr

from projects.uiagent.utils.common_task import intent_classify


task_and_inputs = [
    ("帮助用户订餐", ["我要订一个汉堡", "今天天气怎么样", "再见"]),
    (None, ["你是谁", "@%&@AGF#$%^&*()", "再见"]),
]


@pytest.mark.asyncio
async def test_intent_classify(task, user_inputs: list[str], output_type: type[str] | None):
    """测试相关意图的分类"""
    print(f"\n测试意图分类 for task: {task}")

    client, model = create_client(ModelName.DOUBAO_SEED_1_6_FLASH_250828, AsyncOpenAI)

    history = [
        {
            "role": "user", "content": "你好"
        },
        {
            "role": "assistant", "content": "你好，有什么可以帮你的吗？"
        },
    ]

    for input in user_inputs:
        try:
            time_start = time.time()
            result = await intent_classify(
                input,
                task=task,
                history=history,
                output_type=output_type,
                client = client,
                model = model
            )
            time_end = time.time()
            print(f"输入: {input}")
            print(f"分类时间: {time_end - time_start:.2f}秒, 分类结果: {nl_repr(result)}")
        except Exception as e:
            print(f"意图分类错误: {e} for input: {input}")


class ToneCategory(Enum):
    CASUAL_CHAT = ("日常闲聊", "日常闲聊，没有特别的目的。")
    QUESTION = ("提问", "提问，有明确的目的。")
    REQUEST = ("请求", "请求，有明确的目的。")
    OTHER = ("其它", "其它，不属于上述类别。")


tone_messages = [
    # CASUAL_CHAT (日常闲聊) - 2个例子
    "你好",
    "最近过得怎么样",
    # QUESTION (提问) - 2个例子
    "今天天气怎么样",
    "这个功能怎么使用？",
    # REQUEST (请求) - 2个例子
    "帮我查询一下航班",
    "请帮我订一张电影票",
    # OTHER (其它) - 2个例子
    "再见",
    "谢谢你的帮助",
]


@pytest.mark.asyncio
async def test_intent_classify_customized_categories(output_type: type[str] | None):
    """测试自定义意图类别"""
    print(f"\n测试意图分类 for ToneCategory")

    client, model = create_client(ModelName.DOUBAO_SEED_1_6_FLASH_250828, AsyncOpenAI)

    for input in tone_messages:
        try:
            time_start = time.time()
            result = await intent_classify(
                input,
                [tone.value for tone in ToneCategory],
                output_type=output_type,
                client=client,
                model=model
            )
            time_end = time.time()
            print(f"输入: {input}")
            print(f"分类时间: {time_end - time_start:.2f}秒, 分类结果: {nl_repr(result)}")
        except Exception as e:
            print(f"意图分类错误: {e} for input: {input}")


def main():
    
    # 结构化输出比str输出慢一倍不止，about 5 sec vs. 2 sec
    output_type = str

    asyncio.run(test_intent_classify(*task_and_inputs[0], output_type=output_type))
    
    asyncio.run(test_intent_classify(*task_and_inputs[1], output_type=output_type))

    asyncio.run(test_intent_classify_customized_categories(output_type=output_type))

if __name__ == "__main__":
    main()