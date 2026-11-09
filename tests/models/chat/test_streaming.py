from typing import Final

import asyncio

import pytest

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, Ark, AsyncArk

from aicore.models.chat.params import ChatParams

from aicore.models.chat.streaming import (
    stream,
    astream,
)

# 测试各个系列的最新的模型。它们都支持结构化输出，function call, response API
model_names: Final[list[ModelName]] = [
        ModelName.SEED_1_8_251228,            # 最好的
        # ModelName.SEED_1_6_251015,
        #ModelName.DOUBAO_SEED_1_6_251015,
        ModelName.SEED_1_6_FLASH_250828,      # 最快的
        #ModelName.DOUBAO_SEED_1_6_THINKING_250715,
        #ModelName.DOUBAO_SEED_1_6_VISION_250815,
    ]


@pytest.mark.parametrize("model_name", model_names)
def test_stream(model_name: ModelName) -> None:
    print(f"\n======================================================")
    print(f"测试stream, 模型: {model_name}")
    query = "三加四是多少"

    # 整体比invoke快非常多。为什么？
    #params = ChatParams(thinking = {"type": "disabled"})  # 关掉thinking快一点
    params = ChatParams(thinking = {"type": "enabled"}) # 即使打开thinking，也不知道怎么看到reasoning_content。choice_delta中看不到。

    show_reasoning = False
    
    client, model = create_client(model_name, Ark)
    print(f"Query: {query}")
    print("stream 输出结果:", end="", flush=True)
    stream_res = stream(query, show_reasoning=show_reasoning, client=client, model=model, params=params)
    for chunk in stream_res:
        print(chunk, end="", flush=True)

    print(f"\nstream 输出最终结果")
    print(stream_res)

    # 测试序列化
    # print(stream_res.model_dump())

    client_async, model = create_client(model_name, AsyncArk)
    print(f"Query: {query}")
    print("astream 输出结果:", end="", flush=True)

    async def _run_astream():
        stream_res = await astream(query, show_reasoning=show_reasoning, client=client_async, model=model, params=params)
        async for chunk in stream_res:
            print(chunk, end="", flush=True)

        print(f"\nastream 输出最终结果")
        print(stream_res)

    asyncio.run(_run_astream())


@pytest.mark.parametrize("model_name", model_names)
def test_conversation(model_name: ModelName) -> None:
    print(f"\n======================================================")
    print(f"测试多轮对话stream, 模型: {model_name}")
    """测试多轮对话，使用queries列表中的查询依次处理"""
    queries = ["讲个笑话", "解释一下刚才的笑话", "再讲一个不同类型的笑话"] # 吐出首字太慢。因为开了thinking。
    # queries = ["你是谁?", "再见"]

    params = ChatParams(thinking = {"type": "disabled"})  # 关掉thinking快多了
    # params = ChatParams(thinking = {"type": "enabled"})
    show_reasoning = True

    client, model = create_client(model_name, Ark)
    
    messages = []
    for query in queries:
        print(f"\n==========================\n用户: {query}")
        
        stream_res = stream(query, messages or "你是一个幽默的人，讲话简洁", show_reasoning=show_reasoning, client=client, model=model, params=params)
        print("助手: ", end="", flush=True)
        for chunk in stream_res:
            print(chunk, end="", flush=True)

        print(f"\n流式输出最终结果")
        print(stream_res)
        
        messages = stream_res.messages


# ============= 主函数 =============
RUN_PYTEST: Final = False


def main() -> None:
    for model in model_names:
        test_stream(model)
        test_conversation(model)
        break


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        #test_safe_update()
        main()
