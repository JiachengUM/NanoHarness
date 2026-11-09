from typing import Any

from collections.abc import Awaitable, AsyncGenerator

import asyncio

from aicore.core.types import SafeResult


class TaskAsyncRunner:
    """
    任务运行器，结合了asyncio.as_completed和gather的长处: 按照任务完成的顺序流式返回结果，并保证最终结果的顺序和添加任务的顺序相同。
    假设task返回的是SafeResult, 无需做异常处理。
    """

    def __init__(self):
        self._finished = False  # 状态，确保add_task和results调用时的状态正确。

        # 内部缓存的task和results，确保results的顺序和add_task的顺序相同。
        self._results: list[SafeResult[Any] | None] = []
        self._tasks: list[Awaitable[SafeResult[Any]]] = []

    def add_task(self, coro: Awaitable[SafeResult[Any]]) -> None:
        """
        添加一个异步任务到运行器

        参数:
            coro: 可等待对象，通常是TaskTool.create_task返回的Task

        注意：
        1. 这里传入的coro一定是TaskTool.create_task返回的
        2. 类型注释使用Awaitable而不是Coroutine，后者更啰嗦且过度限制
        """

        if self._finished:
            raise RuntimeError("Runner 已经执行完毕，不能再次添加任务")

        index = len(self._results)
        self._results.append(None)

        # 闭包wrapper确保index一直有效，返回的结果位置正确
        async def wrapper():
            # 等待任务完成并获取结果
            result = await coro
            # 将结果存储到对应位置，保证顺序正确
            self._results[index] = result
            return result

        # 创建并添加新的任务
        task = asyncio.create_task(wrapper())
        self._tasks.append(task)

    async def run(self) -> AsyncGenerator[SafeResult[Any], None]:
        """运行所有任务并按照完成顺序流式返回结果

        1. 使用 asyncio.as_completed 获取已完成的任务
        2. 使用 yield 关键字实现异步生成器，逐个返回结果
        3. 任务全部完成后设置 finished 状态
        """
        assert self._tasks, "Runner 为空，不能运行"
        assert not self._finished, "Runner 已经执行完毕，不能再次运行"

        # asyncio.as_completed 会按照任务完成的顺序返回可等待对象
        for coro in asyncio.as_completed(self._tasks):
            # 等待任务完成并获取结果
            result = await coro
            # 流式返回结果
            yield result

        self._finished = True

    @property
    def results(self) -> list[SafeResult[Any]]:
        """获取所有任务的结果，确保顺序与添加任务的顺序一致

        注意：必须在 run() 执行结束后才能调用此属性
        """
        if not self._finished:
            raise RuntimeError("必须等 run() 执行结束后才能获取 results")

        # self._results的类型包括None，需要被忽略
        return self._results  # type: ignore
