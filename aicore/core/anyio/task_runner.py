from contextlib import aclosing
from typing import Any, Callable, Awaitable, AsyncGenerator

from anyio import create_task_group, create_memory_object_stream
from anyio.streams.memory import MemoryObjectSendStream

from aicore.core.types import SafeResult


class TaskAsyncRunner:
    """通用异步并发引擎 (类型擦除).

    收 N 个 factory, 调度并发执行, 流式按完成顺序 yield SafeResult, results 按插入顺序.
    factory 抛任何 Exception 会被 catch 并包成 SafeResult.error; CancelledError (BaseException)
    自然透出, 留给 task_group 处理结构化取消.

    类型擦除是有意的: 主要消费方 (TaskToolRunner) 是异构的, 一次 add 多种 OT 不同的 tool,
    没有有意义的统一 T. 调用方在 factory 出口处自己 narrow 类型.

    使用方式:
        runner = TaskAsyncRunner()
        runner.add_task(lambda: my_async_func(x))
        runner.add_task(another_factory)
        async for safe in runner.run():
            ...  # 完成顺序
        for safe in runner.results:
            ...  # 插入顺序
    """

    def __init__(self):
        self._pending: list[Callable[[], Awaitable[Any]]] = []
        self._results: list[SafeResult[Any] | None] = []
        self._finished = False

    def add_task(self, factory: Callable[[], Awaitable[Any]]) -> None:
        """收集一个 factory, 不立即调度. 调度发生在 run() 内.

        factory 是无参可调用对象, 调用后返回一个待 await 的协程. factory 可能抛任何 Exception,
        runner 在 worker 内 catch 后包成 SafeResult(error=str(e)).
        """
        if self._finished:
            raise RuntimeError("Runner 已经执行完毕, 不能再次添加任务")
        self._pending.append(factory)
        self._results.append(None)

    async def run(self) -> AsyncGenerator[SafeResult[Any], None]:
        """并发执行所有 factory, 按完成顺序 yield SafeResult."""
        async with aclosing(self.run_indexed()) as inner:
            async for _, result in inner:
                yield result

    async def run_indexed(self) -> AsyncGenerator[tuple[int, SafeResult[Any]], None]:
        """并发执行所有 factory, 按完成顺序 yield (插入顺序 index, SafeResult)."""
        assert self._pending, "Runner 为空, 不能运行"
        assert not self._finished, "Runner 已经执行完毕, 不能再次运行"

        send_stream, recv_stream = create_memory_object_stream[
            tuple[int, SafeResult[Any]]
        ](max_buffer_size=len(self._pending))

        try:
            async with create_task_group() as tg:
                async with send_stream:
                    for index, factory in enumerate(self._pending):
                        tg.start_soon(
                            self._worker,
                            index,
                            factory,
                            send_stream.clone(),
                        )

                async with recv_stream:
                    async for indexed_result in recv_stream:
                        yield indexed_result

            self._finished = True
        except BaseExceptionGroup as eg:
            # consumer break 时 GeneratorExit 被 task_group 包成 BaseExceptionGroup,
            # 还原成裸 GeneratorExit 才符合 async generator close 协议.
            if len(eg.exceptions) == 1 and isinstance(eg.exceptions[0], GeneratorExit):
                raise eg.exceptions[0]
            raise

    async def _worker(
        self,
        index: int,
        factory: Callable[[], Awaitable[Any]],
        send_clone: MemoryObjectSendStream[tuple[int, SafeResult[Any]]],
    ) -> None:
        async with send_clone:
            try:
                data = await factory()
                result: SafeResult[Any] = SafeResult(data=data)
            except Exception as e:
                result = SafeResult(error=str(e))
            self._results[index] = result
            await send_clone.send((index, result))

    @property
    def results(self) -> list[SafeResult[Any]]:
        """获取所有任务的结果, 顺序与 add_task 插入顺序一致. 必须 run() 结束后才能调用."""
        if not self._finished:
            raise RuntimeError("必须等 run() 执行结束后才能获取 results")
        return self._results  # type: ignore[return-value]
