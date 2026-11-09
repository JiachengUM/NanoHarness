from projects.mind.intent.task_data.message import Message

from nanoai.utils.nl_repr import nl_repr

def test_message():
    user_message = Message(role="user", content="你好")
    print(nl_repr(user_message))

    assistant_message = Message(role="assistant", content="你好。我是你的助手。有什么可以帮你的。")
    print(nl_repr([user_message, assistant_message], use_numbering=False))


if __name__ == "__main__":
    test_message()
