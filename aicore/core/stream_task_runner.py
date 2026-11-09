from typing import AsyncGenerator, Any

import asyncio
import uuid

from aicore.events.task import (
    TaskEvent, 
    TaskStartEvent, 
    TaskProgressEvent, 
    TaskSuccessEvent, 
    TaskFailureEvent, 
    TaskCancelledEvent,
)

from aicore.runtime.task.worker import TaskProgress, TaskSuccess, TaskAStreamWorker

from aicore.core.types import SafeResult

class StreamTaskRunner:
    """
    流式任务并发运行器
    :param R: 最终结果的类型 (例如: dict, str, UserObject)
    :param P: 中间流式数据的类型 (例如: str, dict)
    """
    
    def __init__(self):
        self._finished = False  # 状态，确保add_task和results调用时的状态正确。

        # 存储任务工厂和对应的ID
        self._factories: list[tuple[str, TaskAStreamWorker[Any, Any, ...]]] = []
        
        # 存储所有任务的结果，顺序与添加任务的顺序一致
        self._results: list[SafeResult[Any] | None] = []


    def add_task(
        self, 
        factory: TaskAStreamWorker[Any, Any, ...], 
        task_id: str | None = None
        ) -> str:
        """
        添加一个流式任务
        :param factory: 生成器工厂函数 (lambda: my_func())
        :param task_id: 可选的任务ID
        """
        if self._finished:
            raise RuntimeError("Runner 已经执行完毕，不能再次添加任务")

        uid = task_id or str(uuid.uuid4())
        self._factories.append((uid, factory))
        return uid


    async def run(self) -> AsyncGenerator[TaskEvent, None]:
        """
        并发执行所有任务，并 yield 统一的事件流
        """
        assert self._factories, "No tasks added to the runner."
        assert not self._finished, "Runner 已经执行完毕，不能再次运行"

        # 使用 Queue 进行生产者-消费者模式
        queue: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        
        num_tasks = len(self._factories)
        finished_tasks = 0

        async def worker(
            task_id: str, 
            factory: TaskAStreamWorker[Any, Any, ...],
            index: int
        ) -> None:
            nonlocal finished_tasks
            await queue.put(TaskStartEvent(task_id=task_id))

            generator = factory()  # 必须在这里第一次生成generator，不能提前生成
            
            try:
                async for chunk in generator:
                    if isinstance(chunk, TaskProgress):
                        await queue.put(TaskProgressEvent(task_id=task_id, progress=chunk.progress))
                    else:
                        assert isinstance(chunk, TaskSuccess)
                        # TaskSuccess只能被返回一次，确保结果未被设置过
                        assert self._results[index] is None, f"Task {task_id} result already set"
                        self._results[index] = SafeResult(data=chunk.result)
                        await queue.put(TaskSuccessEvent(task_id=task_id, result=chunk.result))

            except asyncio.CancelledError:
                assert self._results[index] is None, f"Task {task_id} result already set"
                self._results[index] = SafeResult(error="Task was cancelled")
                await queue.put(TaskCancelledEvent(task_id=task_id, reason="Task was cancelled"))
            
            except Exception as e:
                assert self._results[index] is None, f"Task {task_id} result already set"
                self._results[index] = SafeResult(error=str(e))
                await queue.put(TaskFailureEvent[str](task_id=task_id, error=str(e)))
            
            finally:
                # 任务彻底结束，更新计数
                finished_tasks += 1
                if finished_tasks == num_tasks:
                    await queue.put(None) # 发送结束信号

        # --- 启动阶段 ---
        self._results = [None] * num_tasks
        bg_tasks: list[asyncio.Task[Any]] = []
        for index, (task_id, factory) in enumerate(self._factories):
            # 创建后台任务
            task: asyncio.Task[Any] = asyncio.create_task(worker(task_id, factory, index))
            bg_tasks.append(task)

        # --- 消费阶段 ---
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break # 收到结束信号
                yield event
        finally:
            # 主动取消所有后台任务
            for task in bg_tasks:
                task.cancel()
            # 等待所有后台任务被清理
            await asyncio.gather(*bg_tasks, return_exceptions=True)

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