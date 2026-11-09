from __future__ import annotations

import asyncio

import pytest


from nanoai.chat.define import RolePlayScenario, ROLE_PLAY_TASKS
from nanoai.chat.worker import ChatWorker
from nanoai.chat.simulation import (
    gen_chat,
    agen_chat,
    gen_chat_with_nl,
    agen_chat_with_nl,
    MockedChatUser,
    SimulatedChatUser,
)

from examples.edu import (
    Course,
    CourseType,
    Student,
    StudentInfo,
    Teacher,
)


def test_mocked_chat_user_basic():
    """测试MockedChatUser的基本功能"""
    inputs = ["Hello", "How are you?", "Goodbye"]
    user = MockedChatUser(inputs)
    
    # 测试name属性
    assert user.name == "mocked用户"
    
    # 测试execute方法按顺序返回输入
    assert user.execute("any input") == "Hello"
    assert user.execute("any input") == "How are you?"
    assert user.execute("any input") == "Goodbye"
    
    # 测试循环功能（超出列表长度后重新开始）
    assert user.execute("any input") == "Hello"


@pytest.mark.skip(reason="太慢了。手动测试即可")
@pytest.mark.parametrize("simulated,use_async", [(True, False), (False, False), (True, True), (False, True)])
def test_teacher(simulated: bool, use_async: bool):
    chinese_course = Course(tp=CourseType.CHINESE, grade=1)

    if simulated:
        teacher = Teacher(chinese_course)
        student = SimulatedChatUser(
            "小学三年级女生，性格害羞，说话有点紧张。",
            topic="如何提高表达能力",
        )
    else:
        student_info = StudentInfo(name="小明", gender="男", age=10, grade=1)
        teacher = Teacher(chinese_course, user=student_info)
        student = Student(student_info)

    print(f"teacher: {teacher._sys_prompt}")
    print(f"student: {student._sys_prompt}")

    # 根据 use_async 参数选择同步或异步版本
    if use_async:
        asyncio.run(agen_chat(teacher, student, max_rounds=3))
    else:
        gen_chat(teacher, student, max_rounds=3)


@pytest.mark.skip(reason="太慢了。手动测试即可")
@pytest.mark.parametrize("use_async", [True, False])
def test_role_play_and_mocked_user(use_async: bool):
    role = RolePlayScenario.Huafei
    task = ROLE_PLAY_TASKS[role]
    
    user_messages = [
        "你好，华妃姐姐",    # 此处并没有做自我介绍，可以测试asssistant是否会有幻觉
        "我乃齐天大圣, 我师傅在哪儿",  # 测试幻觉
        #"我是甄嬛, 想请教在后宫的生存之道",
        "谢谢姐姐的指点, 再见",
    ]
    assistant: ChatWorker = ChatWorker(task)
    if use_async:
        asyncio.run(agen_chat(assistant, user_messages, max_rounds=3))
    else:
        gen_chat(assistant, user_messages, max_rounds=3)


@pytest.mark.skip(reason="太慢了。手动测试即可")
@pytest.mark.parametrize("use_async", [True, False])
def test_gen_chat_with_nl(use_async: bool):
    print(f"test_gen_chat_with_nl, use_async: {use_async}")

    task = "你是一个友好的数学老师，擅长用简单易懂的方式解释数学概念"
    user_info = "一个对数学感到困惑的小学生，希望得到耐心的指导"
    topic = "如何理解负数"
    
    if use_async:
        # 测试异步版本
        assistant, user, conversation = asyncio.run(agen_chat_with_nl(
            task=task,
            user_info=user_info,
            topic=topic,
            max_rounds=2,
            verbose=True,
        ))
    else:
        # 测试同步版本
        assistant, user, conversation = gen_chat_with_nl(
            task=task,
            user_info=user_info,
            topic=topic,
            max_rounds=2,
            verbose=True,
        )

    print(f"\noutput conversation: \n{conversation.format()}")
    

RUN_PYTEST = False

def main():
    # test_teacher(simulated=True, use_async=True)

    test_teacher(simulated=False, use_async=True)
    # test_teacher(simulated=False, use_async=False)
    
    # 测试gen_chat_with_nl函数
    # test_gen_chat_with_nl(use_async=False)
    # test_gen_chat_with_nl(use_async=True)

if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main(["-vs", __file__])
    else:
        main()
