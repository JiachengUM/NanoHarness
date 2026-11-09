from typing import Final

import pytest
from openai import APITimeoutError

from nanoai.model.config import ModelName
from nanoai.model.llm import llm, llm_stream, llm_output_by_schema, llm_output_by_tool
from nanoai.utils._concepts import PersonBasicInfo, Character


# 测试各个系列的最新的模型。它们都支持结构化输出，function call, response API
models_to_test: Final[list[ModelName]] = [
        ModelName.DOUBAO_SEED_1_8_PREVIEW,
        #ModelName.DOUBAO_SEED_1_6_251015,
        #ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        #ModelName.DOUBAO_SEED_1_6_THINKING_250715,
        #ModelName.DOUBAO_SEED_1_6_VISION_250815,
    ]


@pytest.mark.parametrize("model", models_to_test)
def test_basic(model: ModelName) -> None:
    print(f"\n\n测试基本功能llm and llm_stream, 模型: {model}")
    query = "三加四是多少"

    print(f"Query: {query}")
    res = llm(query, model=model)
    print("结果:")
    print("\n".join(res.details()))

    # 测试流式输出
    print("流式输出结果:", end="", flush=True)
    delta = True
    stream_res = llm_stream(query, delta=delta, model=model)
    for chunk in stream_res:
        print(chunk, end="", flush=True)
    print(f"\n流式输出最终结果: {stream_res.output}")


@pytest.mark.parametrize("model", models_to_test)
@pytest.mark.parametrize("model", models_to_test)
def test_conversation(model: ModelName) -> None:
    print(f"\n\n测试多轮对话llm_stream, 模型: {model}")
    """测试多轮对话，使用queries列表中的查询依次处理"""
    # queries = ["讲个笑话", "解释一下刚才的笑话", "再讲一个不同类型的笑话"] # 太慢了
    queries = ["你是谁?", "再见"]
    
    messages = []
    for query in queries:
        print(f"\n用户: {query}")
        
        stream_result = llm_stream(query, messages or "你是一个有用的助手", model=model)
        print("助手: ", end="", flush=True)
        for chunk in stream_result:
            print(chunk, end="", flush=True)
        
        messages = stream_result.messages


QUERIES_STRUCTURE = [
    ("哈利波特和他的朋友们。使用中文"),
    ("生成5个不同职业的人物"),
    ("创建一个医生和一个护士"),
]


@pytest.mark.parametrize("model", models_to_test)
@pytest.mark.parametrize("model", models_to_test)
def test_output_by_schema(model: ModelName) -> None:
    '''
    测试多次，旧版不支持 json_schema 的模型会失败，其它均成功。
    '''
    print(f"\n\n测试结构化输出llm_output_by_schema, 模型: {model}")
    query = "请随机创建一个人物基本信息"
    try:
        res = llm_output_by_schema(query, output_type=PersonBasicInfo, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")

    query = "请随机创建一个角色"
    try:
        res = llm_output_by_schema(query, output_type=Character, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")


@pytest.mark.parametrize("model", models_to_test)
@pytest.mark.parametrize("model", models_to_test)
def test_output_by_tool(model: ModelName) -> None:
    '''
    DOUBAO_SEED_1_6_THINKING_250715成功。
    DOUBAO_SEED_1_6_VISION_250815不报错，但返回无意义的空值。
    其它都失败。
    '''
    print(f"\n\n测试结构化输出llm_output_by_tool, 模型: {model}")
    query = "请创建一个人物基本信息。随机的填写属性值。"
    try:
        res = llm_output_by_tool(query, output_type=PersonBasicInfo, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")

    query = "请生成孙悟空角色。"
    try:
        res = llm_output_by_tool(query, output_type=Character, model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")

    # 测试list[T]的输出，对于qwen模型会死机
    query = "生成若干程序员角色。"
    try:
        res = llm_output_by_tool(query, output_type=list[PersonBasicInfo], model=model)
        print(f"结果: {res.output}")
    except Exception as e:
        print(f"错误: {e}")


@pytest.mark.parametrize("model", models_to_test)
@pytest.mark.parametrize("model", models_to_test)
def test_llm_timeout(model: ModelName) -> None:
    print(f"\n\n测试llm超时功能, 模型: {model}")
    query = "请详细解释一下量子计算的基本原理，包括量子比特、量子叠加态、量子纠缠等概念，并举例说明其在密码学、药物发现等领域的应用前景。"
    
    print(f"Query: {query}")
    print("设置超时时间为0.1秒（非常短）...")
    
    try:
        res = llm(query, timeout=0.1, model=model)
        print("结果:")
        print("\n".join(res.details()))
    except APITimeoutError as e:
        print(f"超时异常: {type(e).__name__}: {e}")
        print("✅ 超时功能正常工作")


# ============= 主函数 =============
RUN_PYTEST: Final = False


def main() -> None:
    for model in models_to_test:
        test_basic(model)

    for model in models_to_test:
        test_conversation(model)

    for model in models_to_test:
        test_output_by_schema(model)

    #for model in models_to_test:
    #    # doubao 1.8 preview 会死掉
    #    test_output_by_tool(model)

    for model in models_to_test:
        test_llm_timeout(model)


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        # test_output_by_tool()
        main()
