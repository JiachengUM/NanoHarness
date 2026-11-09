import pytest
import asyncio

from nanoai.chat.worker import ChatWorker
    

@pytest.mark.parametrize("stream", [True, False])
def test_worker_basic(stream: bool):
    task = "请回答用户的问题"   
    worker = ChatWorker(task)

    user_messages = ["你好，你是谁？", "啊啊啊", "再见"]
    
    if stream:
        for user_message in user_messages:
            print(f"user: {user_message}")
            print(f"assistant(stream):", end="", flush=True)
            with worker.execute_stream(user_message, delta=True) as result_stream:
                for chunk in result_stream:
                    print(chunk, end="")
                
                res = result_stream.output
            print(f"\nstatus: {worker.status_full}")
    else:
        for user_message in user_messages:
            print(f"user: {user_message}")
            res = worker.execute(user_message)
            print(f"assistant: {res}")
            print(f"status: {worker.status_full}")

    print(worker.details())

    state_dict = worker.save_state()

    # re-instantiate
    worker_new = ChatWorker(task)
    worker_new.load_state(state_dict)

    if stream:
        assert worker_new._result_stream is not None
        assert len(worker_new._result_stream.messages) == 7
        assert worker_new._result_stream.messages[0]["role"] == "system"
        assert worker_new._result_stream.messages[1]["role"] == "user"
        assert worker_new._result_stream.messages[2]["role"] == "assistant"
        assert worker_new._result_stream.messages[3]["role"] == "user"
        assert worker_new._result_stream.messages[4]["role"] == "assistant"
        assert worker_new._result_stream.messages[5]["role"] == "user"
    else:
        assert worker_new._result is not None
        assert len(worker_new._result.messages) == 7
        assert worker_new._result.messages[0]["role"] == "system"
        assert worker_new._result.messages[1]["role"] == "user"
        assert worker_new._result.messages[2]["role"] == "assistant"
        assert worker_new._result.messages[3]["role"] == "user"
        assert worker_new._result.messages[4]["role"] == "assistant"
        assert worker_new._result.messages[5]["role"] == "user"


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.asyncio
async def test_worker_async(stream: bool):
    """异步版本的test_worker_basic，使用aexecute和aexecute_stream"""
    task = "请回答用户的问题"   
    worker = ChatWorker(task)

    user_messages = ["你好，你是谁？", "啊啊啊", "再见"]
    
    if stream:
        for user_message in user_messages:
            print(f"user: {user_message}")
            print(f"assistant(async stream):", end="", flush=True)
            async with worker.aexecute_stream(user_message, delta=True) as result_stream:
                async for chunk in result_stream:
                    print(chunk, end="")
                
                res = result_stream.output
            print(f"\nstatus: {worker.status_full}")
    else:
        for user_message in user_messages:
            print(f"user: {user_message}")
            res = await worker.aexecute(user_message)
            print(f"assistant: {res}")
            print(f"status: {worker.status_full}")

    print(worker.details())

    state_dict = worker.save_state()

    # re-instantiate
    worker_new = ChatWorker(task)
    worker_new.load_state(state_dict)

    if stream:
        assert worker_new._result_stream_async is not None
        assert len(worker_new._result_stream_async.messages) == 7
        assert worker_new._result_stream_async.messages[0]["role"] == "system"
        assert worker_new._result_stream_async.messages[1]["role"] == "user"
        assert worker_new._result_stream_async.messages[2]["role"] == "assistant"
        assert worker_new._result_stream_async.messages[3]["role"] == "user"
        assert worker_new._result_stream_async.messages[4]["role"] == "assistant"
        assert worker_new._result_stream_async.messages[5]["role"] == "user"
    else:
        assert worker_new._result is not None
        assert len(worker_new._result.messages) == 7
        assert worker_new._result.messages[0]["role"] == "system"
        assert worker_new._result.messages[1]["role"] == "user"
        assert worker_new._result.messages[2]["role"] == "assistant"
        assert worker_new._result.messages[3]["role"] == "user"
        assert worker_new._result.messages[4]["role"] == "assistant"
        assert worker_new._result.messages[5]["role"] == "user"


def test_worker_update_user():
    task = "请回答用户的问题"
    worker = ChatWorker[str](task)

    # user_message = "你好。你知道我的名字么?"
    user_message = "你好。你对于我了解多少?"

    # 此时模型并不知道用户是谁
    print(f"user: {user_message}")
    res = worker.execute(user_message)
    print(f"assistant: {res}")
    print(f"status: {worker.status_full}")

    user = "小明，男，20岁，学生，喜欢编程"
    worker.update_user(user)
    assert worker._user == user

    # 此时模型知道用户是谁了
    print(f"user: {user_message}")
    res = worker.execute(user_message)
    print(f"assistant: {res}")
    print(f"status: {worker.status_full}")

    print(f"sys prompt: {worker._sys_prompt}")
    assert worker._result is not None
    assert worker._result.messages[0]["role"] == "system"
    assert worker._result.messages[0]["content"] == worker._sys_prompt
    

RUN_PYTEST = False

if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main(["-vs", __file__])
    else:
        # asyncio.run(test_worker_async(stream=True))
        # asyncio.run(test_worker_async(stream=False))
        
        # test_worker_basic(stream=True)
        # test_worker_basic(stream=False)
        test_worker_update_user()
