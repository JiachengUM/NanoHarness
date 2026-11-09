import uuid
from typing import Any, AsyncGenerator, assert_never

from anyio import CancelScope, create_memory_object_stream, create_task_group
from anyio.streams.memory import MemoryObjectSendStream

from aicore.core.types import SafeResult
from aicore.events.task import (
    TaskCancelledEvent,
    TaskEvent,
    TaskFailureEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.runtime.task import (
    TaskAStreamWorkerGeneral,
    TaskProgress,
    TaskSuccess,
)

__all__ = [
    "StreamTaskRunner",
    "TaskAStreamWorkerGeneral",
    "TaskProgress",
    "TaskSuccess",
    "TaskEvent",
    "TaskStartEvent",
    "TaskProgressEvent",
    "TaskSuccessEvent",
    "TaskFailureEvent",
    "TaskCancelledEvent",
]


class StreamTaskRunner:
    """AnyIO 版流式任务并发运行器.

    收 N 个 async-generator factory, 并发执行后产出一条合并的 TaskEvent 流:
    Start -> Progress* -> Success/Failure/Cancelled.

    results 按 add_task 插入顺序保存每个任务的最终 SafeResult.

    取消语义:
    - cancel_task() 是 runner-local 业务取消, 会产出 TaskCancelledEvent 并写入 results.
    - 父级 TaskGroup/消费者关闭导致的结构化取消不在这里吞掉; 交给 AnyIO 传播和清理.
    """

    def __init__(self):
        self._finished = False
        self._factories: list[tuple[str, TaskAStreamWorkerGeneral]] = []
        self._results: list[SafeResult[Any] | None] = []
        self._active_scopes: dict[str, CancelScope] = {}

    def add_task(
        self,
        factory: TaskAStreamWorkerGeneral,
        task_id: str | None = None,
    ) -> str:
        """添加一个流式任务, 返回任务 ID."""
        if self._finished:
            raise RuntimeError("Runner 已经执行完毕, 不能再次添加任务")

        uid = task_id or str(uuid.uuid4())
        if any(existing_id == uid for existing_id, _ in self._factories):
            raise RuntimeError(f"Task ID {uid} already exists")

        self._factories.append((uid, factory))
        self._results.append(None)
        return uid

    def cancel_task(self, task_id: str) -> None:
        """请求取消一个正在运行的任务."""
        try:
            scope = self._active_scopes[task_id]
        except KeyError as e:
            raise RuntimeError(f"Task ID {task_id} is not running") from e

        scope.cancel()

    async def run(self) -> AsyncGenerator[TaskEvent, None]:
        """并发执行所有任务, yield 合并后的任务事件流."""
        assert self._factories, "Runner 为空, 不能运行"
        assert not self._finished, "Runner 已经执行完毕, 不能再次运行"

        send_stream, recv_stream = create_memory_object_stream[TaskEvent](
            max_buffer_size=max(1, len(self._factories))
        )

        try:
            async with create_task_group() as tg:
                async with send_stream:
                    for index, (task_id, factory) in enumerate(self._factories):
                        tg.start_soon(
                            self._worker,
                            index,
                            task_id,
                            factory,
                            send_stream.clone(),
                        )

                async with recv_stream:
                    async for event in recv_stream:
                        yield event

            self._finished = True
        except BaseExceptionGroup as eg:
            if len(eg.exceptions) == 1 and isinstance(eg.exceptions[0], GeneratorExit):
                raise eg.exceptions[0]
            raise

    async def _worker(
        self,
        index: int,
        task_id: str,
        factory: TaskAStreamWorkerGeneral,
        send_clone: MemoryObjectSendStream[TaskEvent],
    ) -> None:
        async with send_clone:
            await send_clone.send(TaskStartEvent(task_id=task_id))

            scope = CancelScope()
            self._active_scopes[task_id] = scope

            try:
                with scope:
                    generator = factory()
                    async for chunk in generator:
                        match chunk:
                            case TaskProgress():
                                await send_clone.send(
                                    TaskProgressEvent(
                                        task_id=task_id,
                                        progress=chunk.progress,
                                    )
                                )

                            case TaskSuccess():
                                self._set_result_once(
                                    index,
                                    task_id,
                                    SafeResult(data=chunk.result),
                                )
                                await send_clone.send(
                                    TaskSuccessEvent(
                                        task_id=task_id,
                                        result=chunk.result,
                                    )
                                )

                            case _:
                                assert_never(chunk)

                if scope.cancelled_caught:
                    self._set_result_once(
                        index,
                        task_id,
                        SafeResult(error="Task was cancelled"),
                    )
                    await send_clone.send(
                        TaskCancelledEvent(
                            task_id=task_id,
                            reason="Task was cancelled",
                        )
                    )
                elif self._results[index] is None:
                    error = "Task completed without TaskSuccess"
                    self._set_result_once(
                        index,
                        task_id,
                        SafeResult(error=error),
                    )
                    await send_clone.send(
                        TaskFailureEvent[str](
                            task_id=task_id,
                            error=error,
                        )
                    )

            except Exception as e:
                if self._results[index] is not None:
                    raise

                self._set_result_once(
                    index,
                    task_id,
                    SafeResult(error=str(e)),
                )
                await send_clone.send(
                    TaskFailureEvent[str](
                        task_id=task_id,
                        error=str(e),
                    )
                )
            finally:
                self._active_scopes.pop(task_id, None)

    def _set_result_once(
        self,
        index: int,
        task_id: str,
        result: SafeResult[Any],
    ) -> None:
        assert self._results[index] is None, f"Task {task_id} result already set"
        self._results[index] = result

    @property
    def results(self) -> list[SafeResult[Any]]:
        """获取所有任务的结果, 顺序与 add_task 插入顺序一致."""
        if not self._finished:
            raise RuntimeError("必须等 run() 执行结束后才能获取 results")
        return self._results  # type: ignore[return-value]
