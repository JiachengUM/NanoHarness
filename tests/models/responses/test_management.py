from typing import Final

import asyncio

import pytest

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.credentials import create_client, Ark, AsyncArk

from aicore.models.responses.management import (
    retrieve,
    delete,
    adelete,
    list_items,
    alist_items,
    alist_all_items
)

from aicore.models.responses import (
    ResponseParams,
    FunctionToolParam,
    invoke,
    ainvoke,
    Response,
)


model_names: Final[list[ModelName]] = [
        # ModelName.SEED_1_8_251228,            # 最好的，没开启缓存服务
        ModelName.SEED_1_8_251228,
        # ModelName.SEED_1_6_251015,
        # ModelName.SEED_1_6_FLASH_250828,      # 最快的
    ]


weather_tool = FunctionToolParam(
    type="function",
    name="get_weather",
    description="根据城市名称查询该城市当日天气（含温度、天气状况）",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "城市名称，如北京、上海（仅支持国内地级市）"
            }
        },
        "required": ["location"]
    }
)


weather_tool = FunctionToolParam(
    type="function",
    name="get_weather",
    description="根据城市名称查询该城市当日天气（含温度、天气状况）",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "城市名称，如北京、上海（仅支持国内地级市）"
            }
        },
        "required": ["location"]
    }
)


def test_retrieve(model_name: ModelName) -> None:
    """
    测试通过id获取Response。
    单轮情况下，与invoke获取的内容一致。只涉及当前轮的一些内容，如 usage， content， 不涉及用户query。
    """
    print("\n======================================================")
    print(f"测试retrieve, 模型: {model_name}")
    query = "讲一个笑话"
    params = ResponseParams(thinking = {"type": "disabled"})  # 关掉thinking
    # params = ResponseParams(thinking = {"type": "enabled"})  # 打开thinking


    client, model = create_client(model_name, Ark)
    first_response = invoke(query, client=client, model=model, params=params)
    print(f"第一轮模型返回的Response:\n{first_response}")
    print(f"第一轮response.id: {first_response.id}")

    res = retrieve(first_response.id, client=client)
    print(f"第一轮通过API返回的Response:\n{res}")   
    print("\n\n")

    # 第二轮，传入第一轮id
    query = "这个笑话的笑点在哪？"
    second_response = invoke(query, first_response, client=client, model=model, params=params)
    print(f"第二轮模型返回的Response:\n{second_response}")
    print(f"第二轮response.id: {second_response.id}")

    res = retrieve(second_response.id, client=client)
    print(f"第二轮通过API返回的Response:\n{res}")

    # 错误情形，id不存在
    print("*"*80)
    print("错误情形，id不存在,抛异常")
    try:
        res = retrieve("123455", client=client)
    except Exception as e:
        print(f"【报错表示正确！】: {e}")


def test_delete(model_name: ModelName) -> None:
    """
    测试通过id获取Response。
    单轮情况下，与invoke获取的内容一致。只涉及当前轮的一些内容，如 usage， content， 不涉及用户query。
    """
    print("\n======================================================")
    print(f"测试delete, 模型: {model_name}")
    query = "讲一个笑话"
    params = ResponseParams(thinking = {"type": "disabled"})  # 关掉thinking
    # params = ResponseParams(thinking = {"type": "enabled"})  # 打开thinking


    client, model = create_client(model_name, Ark)
    first_response = invoke(query, client=client, model=model, params=params)
    print(f"第一轮模型返回的Response:\n{first_response}")
    print(f"第一轮response.id: {first_response.id}")
    res = delete(first_response.id, client=client)

    print(f"通过API删除的Response:\n{res}")
    try:
        res = retrieve(first_response.id, client=client)
        print(f"通过API返回的Response:\n{res}")
        assert False, "删除后应该无法获取"
    except Exception as e:
        print(f"【报错表示正确！】: {e}")

    # 错误情形，id不存在
    print("*"*80)
    print("错误情形，id不存在,抛出异常")
    try:
        res = delete("123455", client=client)
    except Exception as e:
        print(f"【报错表示正确！】: {e}")


@pytest.mark.parametrize("model_name", model_names)
def test_list_items(model_name: ModelName) -> None:
    print("\n======================================================")
    print(f"测试list_items, 模型: {model_name}")
    client, model = create_client(model_name, Ark)
    # 模拟生成
    query_list = ["讲一个冷笑话，不要太长", "这个笑话的笑点在哪？", "推荐两首音乐"]
    params = ResponseParams(thinking = {"type": "disabled"}) 
    response_list: list[Response] = []
    for query in query_list:
        if response_list == []:
            res = invoke(query, client=client, model=model, params=params)
        else:
            res = invoke(query, response_list[-1], client=client, model=model, params=params)
        response_list.append(res)
    print(f"response_list: {response_list}")
    context = list_items(response_list[-1].id, client=client)

    print(f"响应上下文:\n{context}")
    print(f"响应上下文长度: {len(context.data)}")


@pytest.mark.parametrize("model_name", model_names)
def test_alist_items(model_name: ModelName) -> None:
    print("\n======================================================")
    print(f"测试alist_items, 模型: {model_name}")
    async def _run() -> None:
        client, model = create_client(model_name, AsyncArk)
        # 模拟生成
        query_list = ["讲一个冷笑话，不要太长", "这个笑话的笑点在哪？"]
        params = ResponseParams(thinking = {"type": "enabled"}) 
        response_list: list[Response] = []
        for query in query_list:
            if response_list == []:
                res = await ainvoke(query, client=client, model=model, params=params)
            else:
                res = await ainvoke(query, response_list[-1], client=client, model=model, params=params)
            response_list.append(res)
        print(f"response_list: {response_list}")
        context = await alist_items(response_list[-1].id, client=client)

        print(f"响应上下文:\n{context}")
        print(f"响应上下文长度: {len(context.data)}")
        print(f"转为Message列表: \n{context.for_messages(context)}")

    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_alist_all_items(model_name: ModelName) -> None:
    """获取所有响应上下文（自动分页直到没有更多）"""
    print("\n======================================================")
    print(f"测试alist_all_items, 模型: {model_name}")
    async def _run() -> None:
            client, model = create_client(model_name, AsyncArk)
            # 模拟生成
            query_list = ["你是一个复读机你要重复我的话！了解规则了，回复OK，后续开始游戏！", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
            params = ResponseParams(thinking = {"type": "disabled"}) 
            response_list: list[Response] = []
            for query in query_list:
                if response_list == []:
                    res = await ainvoke(query, client=client, model=model, params=params)
                else:
                    res = await ainvoke(query, response_list[-1], client=client, model=model, params=params)
                response_list.append(res)
            print(f"response_list: {response_list}")
            context = await alist_items(response_list[-1].id, client=client,limit=3)
            print("验证：这里limit=3，所返回的上下文是：上下文历史中的前三条，而不是该response_id的最新三条")
            print("如 ：limit = 3， 历史有10条，正序0-9，传入id为9，则召回的是0、1、2，而不是8、9、10")
            print(f"alist_items响应上下文:\n{context}")
            print(f"alist_items响应上下文长度: {len(context.data)}")
            print(f"alist_items转为Message列表: \n{context.for_messages(context)}")
            print("*"*80, "\n")
            # 一次性列出所有
            items = await alist_all_items(response_list[-1].id, client=client)
            print("alist_all_items响应上下文:")
            for index, item in enumerate(items):
                print(f"index: {index} | item: {item}")
            print(f"alist_all_items响应上下文长度: {len(items)}")
            
    asyncio.run(_run())


@pytest.mark.parametrize("model_name", model_names)
def test_ainvoke_truncate(model_name: ModelName) -> None:
    """删除中间状态的response。
    利用 delete 接口实现 Responses API 的窗口截断的功能，使得程序可以在 response 粒度上管理历史记忆，便于后续进行更复杂的对话。"""
    async def _run() -> None:
        print("\n======================================================")
        print(f"测试 ainvoke, 模型: {model_name}")

        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"})

        query = "讲个谐音梗笑话"
        print(f"Query: {query}")
        res1 = await ainvoke(query, client=client, model=model, params=params)

        query = "讲个有哲理的笑话"
        print(f"Query: {query}")
        res2 = await ainvoke(
            query,
            res1,
            client=client,
            model=model,
            params=params,
        )
        query = "讲个冷笑话"
        print(f"Query: {query}")
        res3 = await ainvoke(
            query,
            res2,
            client=client,
            model=model,
            params=params,
        )

        # 开始删除会话,
        print("开始删除第二个会话")
        result = await adelete(res2.id, client=client)
        if result:
            print(f"删除Response {res2.id} 成功")

        # 用第三个会话的id的上下文。
        query = "刚刚讲了几个笑话？都是什么主题的？"
        res4 = await ainvoke(
            query,
            res3,
            client=client,
            model=model,
            params=params,
        )
        # print(f"第四轮模型返回的Response:\n{res4}"
        print(res4.raw_text)

    asyncio.run(_run())

# ============= 主函数 =============
RUN_PYTEST: Final = False


def main() -> None:
    for model in model_names:
        # # 通过id 获取Response
        test_retrieve(model)

        # # 通过id 删除Response
        test_delete(model)
        
        # # 通过id召回上下文
        test_list_items(model)
        test_alist_items(model)

        # # 上下文截断
        test_ainvoke_truncate(model)

        # 获取所有响应上下文
        test_alist_all_items(model)

        break  # 只跑第一个模型；要跑全部模型可删掉本行


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        #test_safe_update()
        main()
