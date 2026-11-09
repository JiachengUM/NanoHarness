from examples.edu import create_teachers
from nanoai.chat.manager import ChatManager
from nanoai.chat.simulation import gen_chat

# def test_manager_stream():
#     teachers = create_teachers()

#     chat_manager = ChatManager(teachers)

#     user = [
#         "请问你是谁?",
#         "我可以问哪些问题?",
#         "20除以4等于多少?",
#         '请解释"守株待兔"这个成语的意思',
#         "再见",
#     ]

#     run_chat_cli(chat_manager, user, stream=True)


def test_manager_serialization():
    teachers = create_teachers()

    chat_manager = ChatManager(teachers)

    user = [
        "请问你是谁?",
        "我可以问哪些问题?",
        "20除以4等于多少?",
        '请解释"守株待兔"这个成语的意思',
        "How do you say '你好' in English?",
        "再见",
    ]

    gen_chat(chat_manager, user, stream=False)

    state = chat_manager.save_state()
    print(state)
    chat_manager = ChatManager(teachers)
    chat_manager.load_state(state)
    print(chat_manager._messages)
    assert len(chat_manager._messages) == len(user)


@pytest.mark.skip(reason="太慢了。手动测试即可")
def test_teacher_manager():
    teachers = create_teachers()
    chat_manager = ChatManager(teachers)

    user = [
        "请问你是谁?",
        "我可以问哪些问题?",
        "20除以4等于多少?",
        '请解释"守株待兔"这个成语的意思',
        "How do you say '你好' in English?",
        "四大发明是哪四个?",
        "中国有多少个省份?",
        "请解释量子物理。",
        "哈哈哈",
        "再见",
    ]

    gen_chat(chat_manager, user, stream=False)


def main():
    # test_manager_stream()
    test_manager_serialization()


if __name__ == "__main__":
    main()
