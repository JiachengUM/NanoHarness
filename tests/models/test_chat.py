from typing import Final

import asyncio

import pytest

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, Ark, AsyncArk
from aicore.models.chat import (
    ChatParams, 
    invoke, 
    ainvoke,
    invoke_output_by_schema, 
    ainvoke_output_by_schema,
    stream,
    astream,
)

from aicore.utils._concepts.person import PersonBasicInfo

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
def test_invoke(model_name: ModelName) -> None:
    print(f"\n======================================================")
    print(f"测试invoke和ainvoke, 模型: {model_name}")
    query = "三加四是多少"

    params = ChatParams(thinking = {"type": "disabled"})  # 关掉thinking快一点

    client, model = create_client(model_name, Ark)
    print(f"Query: {query}")
    res = invoke(query, client=client, model=model, params=params)
    print("结果 with invoke:")
    print(res)

    client_async, model = create_client(model_name, AsyncArk)
    res = asyncio.run(ainvoke(query, client=client_async, model=model, params=params))
    print("结果 with ainvoke:")
    print(res)


@pytest.mark.parametrize("model_name", model_names)
def test_params(model_name: ModelName) -> None:
    print(f"\n======================================================")
    print(f"测试invoke with params, 模型: {model_name}")

    params = ChatParams(
        temperature=1.0,
        thinking = {"type": "disabled"},
    )

    query = "讲个冷笑话"

    # 下面两组运行的时间差别很大
    print(f"Query: {query} with params {params}")
    client, model = create_client(model_name, Ark)
    res = invoke(query, client=client, model=model, params=params)
    print("结果 with invoke:")
    print(res)
    
    print(f"Query: {query}")
    res = invoke(query, client=client, model=model)
    print("结果 with invoke:")
    print(res)


QUERIES_STRUCTURE = [
    ("哈利波特和他的朋友们。使用中文"),
    ("生成5个不同职业的人物"),
    ("创建一个医生和一个护士"),
]

@pytest.mark.parametrize("model_name", model_names)
def test_output_by_schema(model_name: ModelName) -> None:
    '''
    某些旧版模型失败：json_schema` is not supported by this model
    其它均成功。
    '''
    print(f"\n======================================================")
    print(f"测试invoke_output_by_schema, 模型: {model_name}")

    # params = ChatParams(thinking = {"type": "enabled"})  # 打开thinking很慢，但是从reasoning_content中能看出非常多内容，对于如何更好的结构化输出有帮助
    params = ChatParams(thinking = {"type": "disabled"})  # 关掉thinking快多了
    query = "请随机创建一个人物基本信息"

    client, model = create_client(model_name, Ark)
    print(f"Query: {query}")
    try:
        res = invoke_output_by_schema(query, output_type=PersonBasicInfo, client=client, model=model, params=params)
        print("结果 with invoke_output_by_schema:")
        print(res)
    except Exception as e:
        print(f"错误: {e}")


    client_async, model = create_client(model_name, AsyncArk)
    print(f"Query: {query}")
    try:
        res = asyncio.run(ainvoke_output_by_schema(query, output_type=PersonBasicInfo, client=client_async, model=model, params=params))
        print("结果 with ainvoke_output_by_schema:")
        print(res)
    except Exception as e:
        print(f"错误: {e}")


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
        test_invoke(model)
        test_params(model)
        test_output_by_schema(model)
        test_stream(model)
        test_conversation(model)


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        #test_safe_update()
        main()
