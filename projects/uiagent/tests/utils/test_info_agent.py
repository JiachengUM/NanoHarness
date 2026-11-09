import asyncio

from pydantic import BaseModel, Field

from nanoai.chat.simulation import agen_chat

from projects.uiagent.utils.info_agent import (
    InfoAgent, 
    Concept, 
    Attribute, 
    AttributeType,
    TaskStatus,
)


class Person(BaseModel):
    name: str = Field(default="", title="姓名", description="全名。")
    gender: str = Field(default="", title="性别", description="性别，如男、女或其他。")
    age: int = Field(default=0, title="年龄", description="当前年龄。")
    occupation: str = Field(default="", title="职业", description="职业。")


def create_info_agent_basic() -> InfoAgent:  
    return InfoAgent(Person)


def create_info_agent_with_concept() -> InfoAgent:
    person_concept = Concept(
        name="Person",
        definition="一个人的基本信息",
        attributes=[
            Attribute(name="name", type=AttributeType.STRING, title="姓名", description="姓名", is_required=True),
            Attribute(name="age", type=AttributeType.INTEGER, title="年龄", description="年龄", is_required=True, default_value=20),
            Attribute(name="gender", type=AttributeType.STRING, title="性别", description="性别", is_required=True),
            Attribute(name="occupation", type=AttributeType.STRING, title="职业", description="职业", is_required=True),
       ],
    )
    return InfoAgent(person_concept)


user_messages = [
    "你好，我是小明，男，20岁，学生，喜欢编程",  # 正确信息
    "我是小明", # 缺少字段 
    "男，20岁，学生", # 一句一句说
]


def test_info_agent_basic(agent: InfoAgent, user_message: str):
    print("test_info_agent_mocked_user:")

    # print(f"intro: {agent.intro()}")

    print(f"user: {user_message}")
    try:
        res = asyncio.run(agent.aexecute(user_message))
        print(f"assistant: {res}")
        print(f"status: {agent.status_full}")
    except Exception as e:
        print(f"Error: {e}")


def test_info_agent_mocked_user():
    agent = create_info_agent_with_concept()

    messages = [
        "我是小明",
        "我是男的",
        "我20岁",
        "我是学生",
    ]

    try:
        # 必须使用stream=False。
        asyncio.run(agen_chat(agent, messages, stream=False, max_rounds=len(messages)))
    except Exception as e:
        print(f"Error: {e}")


def main():
    #agent = create_info_agent_basic()
    #test_info_agent_basic(agent, user_messages[0])
    #return

    # test with concept
    #test_info_agent_basic(create_info_agent_with_concept(), user_messages[0])
    #test_info_agent_basic(create_info_agent_with_concept(), user_messages[1])
    #return


    test_info_agent_mocked_user()
    return


if __name__ == "__main__":
    main()