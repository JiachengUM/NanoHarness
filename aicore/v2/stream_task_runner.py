import logging
import uuid
from collections import deque
from dataclasses import dataclass
from typing import AsyncGenerator, Literal, assert_never

import anyio
from anyio.streams.memory import MemoryObjectSendStream
from anyio import CapacityLimiter, CancelScope

from aicore.events.task import (
    TaskEvent,
    TaskStartEvent,
    TaskProgressEvent,
    TaskSuccessEvent,
    TaskFailureEvent,
    TaskCancelledEvent,
)
from aicore.runtime.task import TaskProgress, TaskSuccess, TaskAStreamWorkerGeneral


logger = logging.getLogger(__name__)


_EntryState = Literal["pending", "scheduled", "running", "draining"]


@dataclass
class _TaskEntry:
    task_id: str
    factory: TaskAStreamWorkerGeneral
    cancel_scope: CancelScope
    # draining: business success was published, while the generator is still
    # being consumed to EOF in the same task for tail/finally cleanup.
    state: _EntryState


class DynamicStreamTaskRunner:
    """
    基于 AnyIO 的纯异步流式任务运行器
    """

    def __init__(self, max_concurrency: int = 10):
        # 输出流 (Output Stream) - 用于 yield 事件
        self._event_output_send, self._event_output_recv = anyio.create_memory_object_stream[TaskEvent](100)

        # 并发限流器
        self._limiter = CapacityLimiter(max_concurrency)

        # 调度器唤醒信号。add_task() 是同步函数，只负责写 registry 并唤醒 run()。
        self._task_available = anyio.Event()

        self._entries: dict[str, _TaskEntry] = {}
        self._pending_order: deque[str] = deque()

    def add_task(
        self,
        factory: TaskAStreamWorkerGeneral,
        task_id: str | None = None
    ) -> str:
        """
        添加任务。同步写入 execution registry，submit 返回后任务即可被 cancel。
        """
        uid = task_id or str(uuid.uuid4())

        if uid in self._entries:
            raise AssertionError(f"Task ID {uid} already in use")

        self._entries[uid] = _TaskEntry(
            task_id=uid,
            factory=factory,
            cancel_scope=CancelScope(),
            state="pending",
        )
        self._pending_order.append(uid)
        self._task_available.set()

        return uid

    def cancel_task(self, task_id: str) -> bool:
        """Cancel active work; return false once its business terminal is fixed."""
        entry = self._entries.get(task_id)
        if entry is None or entry.state == "draining":
            return False
        entry.cancel_scope.cancel()
        return True

    async def _next_pending_entry(self) -> _TaskEntry:
        while True:
            while self._pending_order:
                task_id = self._pending_order.popleft()
                entry = self._entries.get(task_id)
                if entry is not None and entry.state == "pending":
                    return entry

            # anyio.Event cannot be cleared. Replacing it after the queue is drained
            # gives the next synchronous add_task() a fresh signal to set.
            self._task_available = anyio.Event()
            await self._task_available.wait()

    async def _emit_pending_cancelled(self, entry: _TaskEntry) -> None:
        await self._event_output_send.send(
            TaskCancelledEvent(task_id=entry.task_id, reason="Task was cancelled")
        )
        self._entries.pop(entry.task_id, None)

    async def _worker(
        self,
        entry: _TaskEntry,
        event_send: MemoryObjectSendStream[TaskEvent]
    ) -> None:
        """
        实际执行任务的 Worker
        """
        cancelled_exc = anyio.get_cancelled_exc_class()
        success_published = False

        async with event_send:
            try:
                # Keep the cancel scope outside the limiter so a scheduled task can be
                # cancelled while it is still waiting for a concurrency slot.
                with entry.cancel_scope:
                    async with self._limiter:
                        entry.state = "running"
                        await event_send.send(TaskStartEvent(task_id=entry.task_id))

                        generator = entry.factory()

                        async for event in generator:
                            # Cancellation wins over a worker that catches the
                            # injected cancellation and keeps yielding events.
                            if entry.cancel_scope.cancel_called:
                                logger.warning(
                                    "Ignoring task event after cancellation: task_id=%s event=%s",
                                    entry.task_id,
                                    type(event).__name__,
                                )
                                continue

                            match event:
                                case TaskProgress():
                                    if success_published:
                                        logger.warning(
                                            "Ignoring TaskProgress after TaskSuccess: task_id=%s",
                                            entry.task_id,
                                        )
                                        continue
                                    await event_send.send(TaskProgressEvent(task_id=entry.task_id, progress=event.progress))

                                case TaskSuccess():
                                    if success_published:
                                        logger.warning(
                                            "Ignoring duplicate TaskSuccess: task_id=%s",
                                            entry.task_id,
                                        )
                                        continue

                                    # This is the task's business terminal point.
                                    # Keep the registry entry until EOF so the
                                    # generator still owns its cleanup, but make
                                    # subsequent cancel requests no-ops.
                                    success_published = True
                                    entry.state = "draining"
                                    await event_send.send(TaskSuccessEvent(task_id=entry.task_id, result=event.result))

                                case _:
                                    assert_never(event)

                # scope.cancel() 后，CancelledError 在 with scope 内的 await 点被注入，
                # scope 自己捕获并吞掉，正常退出到这里。此时需要手动 emit TaskCancelledEvent。
                if entry.cancel_scope.cancel_called:
                    await event_send.send(TaskCancelledEvent(task_id=entry.task_id, reason="Task was cancelled"))
                elif not success_published:
                    await event_send.send(
                        TaskFailureEvent(
                            task_id=entry.task_id,
                            error="Task completed without TaskSuccess",
                        )
                    )

            except cancelled_exc:
                # 外部取消（如父级 task group 被取消），非 scope.cancel() 引起
                if not success_published:
                    await event_send.send(TaskCancelledEvent(task_id=entry.task_id, reason="Task was cancelled"))

            except Exception as exc:
                if success_published:
                    logger.warning(
                        "Task cleanup failed after TaskSuccess: task_id=%s",
                        entry.task_id,
                        exc_info=exc,
                    )
                elif entry.cancel_scope.cancel_called:
                    await event_send.send(
                        TaskCancelledEvent(
                            task_id=entry.task_id,
                            reason="Task was cancelled",
                        )
                    )
                else:
                    await event_send.send(TaskFailureEvent(task_id=entry.task_id, error=str(exc)))

            finally:
                self._entries.pop(entry.task_id, None)

    async def run(self) -> None:
        """
        调度协程：监听 registry 中的 pending task，控制并发执行
        """
        async with anyio.create_task_group() as tg:
            while True:
                entry = await self._next_pending_entry()

                if entry.cancel_scope.cancel_called:
                    await self._emit_pending_cancelled(entry)
                    continue

                entry.state = "scheduled"
                tg.start_soon(self._worker, entry, self._event_output_send.clone())


    async def astream(self) -> AsyncGenerator[TaskEvent, None]:
        """
        消费输出事件流
        """
        async with self._event_output_recv:
            async for event in self._event_output_recv:
                yield event
