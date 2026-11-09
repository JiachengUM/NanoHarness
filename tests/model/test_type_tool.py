from typing import Final, Literal

import pytest
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam
from pydantic import TypeAdapter

from nanoai.model.config import create_client_model, ModelName
from nanoai.model._type_tool import GeneralTypeTool, ModeLikeTypeTool, _BaseTypeTool
from nanoai.model.llm import _compose_messages as compose_messages
from nanoai.utils._concepts import Character, CharacterDict, PersonBasicInfo

types = [
    bool,
    int,
    Literal["red", "blue", "green"],
    Literal["a", "b", "c", 0],
    PersonBasicInfo,
    CharacterDict,
    tuple[int, str, bool, PersonBasicInfo],
    int | str,
    list[Character],
    dict[str, int | PersonBasicInfo],
]


def test_type_adapter() -> None:
    for t in types:
        print(f"\ntype: {t}")
        ta = TypeAdapter(t)
        print(f"type adapter: {ta}")
        print(f"type adapter json schema: {ta.json_schema()}")


type_tools = [
    GeneralTypeTool(bool),
    GeneralTypeTool(int),
    GeneralTypeTool(Literal["a", "b", "c", "d"]),
    GeneralTypeTool(tuple[int, int]),
    ModeLikeTypeTool(Character),
    # ModeLikeTypeTool(CharacterData),
    # ModeLikeTypeTool(CharacterDict),
    GeneralTypeTool(list[Character]),
    # GeneralTypeTool(list[CharacterData]),
    # GeneralTypeTool(list[CharacterDict]),
]


@pytest.mark.parametrize("type_tool", type_tools)
def test_type_tools(type_tool: _BaseTypeTool) -> None:
    print(f"type of the tool:\n {type_tool._type}")
    print(f"tool param:\n {type_tool.tool_param}")


def _llm_type_tool[
    T
](
    client: OpenAI,
    model: str,
    *,
    messages: list[ChatCompletionMessageParam],
    type_tool: _BaseTypeTool[T],
    **kwargs,
) -> (T | str):

    response_origin = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=[type_tool.tool_param],
        tool_choice="auto",
        **kwargs,
    )
    response: ChatCompletionMessage = response_origin.choices[0].message

    if not response.tool_calls:
        return f"没有工具调用，返回内容：{response.content}"

    if len(response.tool_calls) == 0:
        return f"调用的工具数量为0，返回内容：{response.content}"

    if len(response.tool_calls) > 1:
        raise RuntimeError(f"调用的工具数量{len(response.tool_calls)} > 1")

    return type_tool.execute(response.tool_calls[0])


QUERIES_INT = [
    ("张三，李四，王五", 3),
    ("跑步，游泳", 2),
    ("苹果、香蕉、橙子、葡萄、西瓜", 5),
    ("中国、美国、日本、英国、法国、德国", 6),
    ("红色，蓝色，绿色", 3),
    ("数学、语文、英语、物理、化学、生物", 6),
    ("唱歌、跳舞、画画、书法", 4),
    ("猫，狗，鸟", 3),
    ("北京，上海，广州，深圳，杭州", 5),
    ("星期一，星期三，星期五", 3),
    # 更复杂的句子，包含多种名词
    ("我昨天在公园里看到一只猫和两只狗在追逐一只鸟。", 5),
    ("小明带着书包和水杯去学校上课，路上遇到了老师和同学。", 6),
    ("中国的北京、上海和广州是重要的经济中心。", 4),
    ("我喜欢吃苹果、香蕉和西瓜这三种水果，但不喜欢蔬菜。", 5),
    ("在这次会议上，代表们讨论了经济、文化和教育三个重要议题。", 5),
    # 不包含名词或名词极少的句子
    ("", 0),
    ("嗯，啊，哦，呵呵。", 0),
    ("快点！马上！现在！", 0),
    ("真的吗？不会吧！太好了！", 0),
    ("然而，虽然，但是，因为，所以。", 0),
]


@pytest.mark.parametrize("query, expected", QUERIES_INT)
def test_llm_type_tool_int(query: str, expected: int) -> None:
    client, model = create_client_model(ModelName.DOUBAO_SEED_1_6_FLASH_250615)

    res = _llm_type_tool(
        client,
        model,
        messages=compose_messages(query, "提取用户输入中的名词数量"),
        type_tool=GeneralTypeTool(int),
    )
    print(f"输入: {query}, 结果: {res}, expected: {expected}")


QUERIES_BOOL = [
    # 简单的是非判断
    ("地球是圆的吗？", True),
    ("太阳从西边升起吗？", False),
    ("水在常温下是液体吗？", True),
    ("鸟会飞吗？", True),
    ("鱼会飞吗？", False),
    # 数学判断题
    ("2+2=4吗？", True),
    ("1+1=3吗？", False),
    ("π大于3吗？", True),
    ("负数乘以负数等于正数吗？", True),
    # 常识判断题
    ("人类需要呼吸氧气吗？", True),
    ("植物可以进行光合作用吗？", True),
    ("石头会生长吗？", False),
    ("水可以燃烧吗？", False),
    # 语言判断题
    ("'你好'是中文吗？", True),
    ("'Hello'是中文吗？", False),
    ("'こんにちは'是日语吗？", True),
    ("'안녕하세요'是韩语吗？", True),
    # 复杂的是非判断
    ("如果一个人既会游泳又会跑步，那么他至少会一项运动吗？", True),
    ("如果今天是星期一，那么明天是星期二吗？", True),
    ("如果下雨了，那么地面一定会湿吗？", True),
    ("如果一个人不吃不喝，他能永远活下去吗？", False),
    # 模糊判断
    ("大多数鸟都会飞吗？", True),
    ("所有哺乳动物都生活在陆地上吗？", False),
    ("大多数植物都需要阳光吗？", True),
    ("所有金属都会导电吗？", True),
]


@pytest.mark.parametrize("query, expected", QUERIES_BOOL)
def test_llm_type_tool_bool(query: str, expected: bool) -> None:
    client, model = create_client_model(ModelName.DOUBAO_SEED_1_6_FLASH_250615)

    res = _llm_type_tool(
        client,
        model,
        messages=compose_messages(query, "判断以下陈述是否正确，回答是或否"),
        type_tool=GeneralTypeTool(bool),
    )
    print(f"输入: {query}, 结果: {res}, expected: {expected}")


def test_llm_type_tool_complex() -> None:
    client, model = create_client_model(ModelName.DOUBAO_SEED_1_6_FLASH_250615)

    sys_prompt = "根据用户的输入生成人物信息。"

    user_prompt = "哈利波特"
    res = _llm_type_tool(
        client,
        model,
        messages=compose_messages(user_prompt, sys_prompt),
        type_tool=ModeLikeTypeTool(Character),
    )
    print(f"输入: {user_prompt}, 结果: {res}")

    user_prompt = "若干程序员"
    res = _llm_type_tool(
        client,
        model,
        messages=compose_messages(user_prompt, sys_prompt),
        type_tool=GeneralTypeTool(list[Character]),
    )
    print(f"输入: {user_prompt}, 结果: {res}")


RUN_PYTEST: Final = False


def main() -> None:
    test_type_adapter()
    for type_tool in type_tools:
        test_type_tools(type_tool)

    # Test the first test case
    test_llm_type_tool_int(QUERIES_INT[0][0], QUERIES_INT[0][1])
    test_llm_type_tool_bool(QUERIES_BOOL[0][0], QUERIES_BOOL[0][1])

    for query, expected in QUERIES_INT:
        test_llm_type_tool_int(query, expected)
    for query, expected in QUERIES_BOOL:
        test_llm_type_tool_bool(query, expected)

    test_llm_type_tool_complex()


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        main()
