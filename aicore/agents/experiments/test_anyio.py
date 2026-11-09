import anyio
from anyio import CancelScope, create_task_group, create_memory_object_stream
from anyio.streams.memory import MemoryObjectReceiveStream

async def endless_loop():
    while True:
        await anyio.sleep(1)
        print("死循环中...")


async def test_endless_loop():
    print("1. 准备进入 Group")
    async with anyio.create_task_group() as tg:
        print("2. 进入 Group，启动死循环")
        tg.start_soon(endless_loop) # 3. 这行代码瞬间执行完毕
        
        print("4. start_soon 返回了，但我还在 async with 块里面！")
        
        # 5. 代码执行到这里，下面是 async with 块的末尾
        # 6. 要离开这个块，程序必须问 TaskGroup：“我可以走了吗？”
        # 7. TaskGroup 会检查：“组里还有没完成的任务吗？”
        # 8. 它发现 endless_loop 还在跑，于是回答：“不行，你得等着。”
        # 9. 程序就被卡在这里，永远等待。

        await anyio.sleep(1)  # 即使增加了一个显式的await，依然是死循环
        
    print("10. 这行代码永远无法打印")


async def process_items(receive_stream: MemoryObjectReceiveStream[str]) -> None:
    async with receive_stream:
        async for item in receive_stream:
            print('received', item)


async def test_stream():
    # The [str] specifies the type of the objects being passed through the
    # memory object stream. This is a bit of trick, as create_memory_object_stream
    # is actually a class masquerading as a function.
    send_stream, receive_stream = create_memory_object_stream[str]()
    async with create_task_group() as tg:
        tg.start_soon(process_items, receive_stream)
        async with send_stream:
            for num in range(10):
                await send_stream.send(f'number {num}')


async def waiter(index: int):
    try:
        # 如果这样处理，print不出来。不知道异常是如何处理的
        await anyio.sleep(index)
        print(f"Waiter {index} succeeded")
        # return

    except anyio.get_cancelled_exc_class():
        print(f"Waiter {index} cancelled")
        raise


async def test_cancel():
    cs: CancelScope | None = None
    async with create_task_group() as tg:
        # Start a couple tasks and wait until they are blocked
        tg.start_soon(waiter, 1)
        tg.start_soon(waiter, 2)
        await anyio.sleep(1.5)

        # Cancel the scope and exit the task group
        cs = tg.cancel_scope
        cs.cancel()

    assert cs is not None
    assert cs.cancelled_caught, "cancelled caught should be true" # 通过 cancelled_caught 判断是否被 canceled

    # Output:
    # Waiter 1 cancelled
    # Waiter 2 cancelled


if __name__ == "__main__":
    #anyio.run(test_endless_loop)
    #anyio.run(test_stream)
    anyio.run(test_cancel)
