from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import assert_never, Any
import inspect
import logging
import uuid

import anyio

from aicore.events.task import (
    TaskCreatedEvent,
    TaskEvent,
    TaskStartEvent,
    TaskProgressEvent,
    TaskSuccessEvent,
    TaskFailureEvent,
    TaskCancelledEvent,
)

from .models import TaskRun, TaskStatus, TaskDef, TaskProjection, TaskApplyResult, TaskCancelOutcome
from .worker import TaskAStreamWorkerGeneral, TaskProgress

from aicore.utils.nl_repr import nl_repr_safe


__all__ = [
    "TaskManager",
]

logger = logging.getLogger(__name__)

ExternalTaskCancel = Callable[[], Awaitable[Any] | Any]
_EXTERNAL_REPLACED_REASON = "Superseded by newer external task"


class TaskManager:
    """
    负责任务的生命周期管理与状态路由。

    对外提供同步/异步接口（submit/cancel/run/astream），内部管理底层 Runner。
    通过监听 Runner 的生命周期事件来维护内部任务状态表（Projection）。

    并发与原子性保障 (Event Loop 约束):
    ----------------------------------
    `submit_task` 和 `cancel_task` 故意设计为**非 async 的同步函数**。
    在当前单事件循环（Single Event Loop）的协作式调度下，无 `await` 的代码段不会被
    其它协程（Coroutine）抢占执行。因此，可以安全地将 Manager 存储与 Runner 注册表的
    变更视为单线程内的**原子操作**。
    
    注意：此约束仅适用于同事件循环内的 Agent Runner、Async Task Tool 和 Cancel Tool。

    状态滞后与取消策略 (Cancel Intent):
    ----------------------------------
    由于 Runner 事件上报存在异步延迟，取消操作以 Manager 的状态表为准：
    1. 调用 `cancel_task` 时，先在Manager记录“取消意图”（Cancel Intent）。
    2. 对底层 `runner.cancel_task` 的调用属于“尽力而为”（Best-effort）。
       如果 runner 明确返回 False，说明业务终态已经固定但事件尚未完成投影，
       Manager 会撤销取消意图并返回 already_terminal。
    3. 其余情况下，若随后收到该任务延迟到达的 Success/Failure 事件，Manager 会将其设置
       为 `TaskCancelledEvent` 再记录和发布。
    4. 任务的 Start 和 Progress 事件仍按原样正常应用与发布。
    """

    def __init__(
        self,
        *,
        runner: Any | None = None,
        max_concurrency: int = 10,
        event_buffer_size: int | float = 1000,
    ):
        self._store: dict[str, TaskRun] = {}
        self._definitions: dict[str, TaskDef] = {}
        self._cancel_requested_task_ids: set[str] = set()
        self._external_cancel_suppressed_task_ids: set[str] = set()
        self._submission_metadata: ContextVar[dict[str, Any] | None] = ContextVar(
            f"task_submission_metadata_{id(self)}",
            default=None,
        )
        self._runner = runner if runner is not None else self._create_default_runner(max_concurrency)
        self._event_output_send, self._event_output_recv = anyio.create_memory_object_stream[TaskEvent](
            event_buffer_size
        )

    def __class_getitem__(cls, item: Any):
        return cls

    # --- 1. 注册与定义 ---

    def register_def(self, def_: TaskDef):
        """注册一个任务定义"""
        self._definitions[def_.id] = def_

    def get_def(self, task_def_id: str) -> TaskDef | None:
        raise NotImplementedError("TaskManager CRUD API is reserved but not implemented yet")

    def list_defs(self) -> list[TaskDef]:
        raise NotImplementedError("TaskManager CRUD API is reserved but not implemented yet")

    def unregister_def(self, task_def_id: str) -> TaskDef | None:
        raise NotImplementedError("TaskManager CRUD API is reserved but not implemented yet")

    # --- 2. 控制面 ---

    @contextmanager
    def submission_context(self, metadata: dict[str, Any]):
        current = self._submission_metadata.get() or {}
        token = self._submission_metadata.set({**current, **metadata})
        try:
            yield
        finally:
            self._submission_metadata.reset(token)

    def submit_task(
        self,
        factory: TaskAStreamWorkerGeneral,
        *,
        name: str,
        arguments: dict[str, Any] | None = None,
        task_id: str | None = None,
        task_def_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """同步提交任务，并发布 TaskCreatedEvent。"""
        uid = task_id or str(uuid.uuid4())
        task_arguments = arguments or {}
        created = TaskCreatedEvent(task_id=uid, name=name, arguments=task_arguments)

        result = self.apply_created(created)
        if not result.applied:
            raise AssertionError(result.reason or "任务创建事件被拒绝")

        run = self._store[uid]
        if task_def_id is not None:
            run.task_def_id = task_def_id
        merged_metadata = {
            **(self._submission_metadata.get() or {}),
            **(metadata or {}),
        }
        if merged_metadata:
            run.metadata = merged_metadata

        try:
            self._runner.add_task(factory=factory, task_id=uid)
        except Exception:
            self._store.pop(uid, None)
            raise

        self._emit_nowait(created)
        return uid

    def submit_external_task(
        self,
        *,
        name: str,
        arguments: dict[str, Any] | None = None,
        cancel: ExternalTaskCancel,
        task_id: str | None = None,
        task_def_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        cancel_timeout: float = 5.0,
        replace_existing: bool = False,
    ) -> str:
        """
        注册一个由外部系统执行的长期任务。

        这类任务本身不由 runner 执行业务逻辑；runner 只维持一个 active
        projection，使取消工具可以定位它。取消发生时，在 shielded cleanup
        中尽力调用外部 cancel callback。

        replace_existing=True 时，同名 active external task 会被标记为 cancelled
        并向 client 发布事件，但不会调用旧任务的外部 cancel callback，避免旧任务
        cleanup 影响刚启动的新外部任务。
        """
        uid = task_id or str(uuid.uuid4())

        if replace_existing:
            self._replace_active_external_tasks(
                name=name,
                replacement_task_id=uid,
            )

        async def external_worker():
            try:
                yield TaskProgress(progress="External task is active")
                # 当前决策：外部任务暂不建模自然完成信号，只通过 cancel best-effort 结束。
                # 影响：如果播放结束/导航到达但没有状态回调，任务会继续出现在 active
                # context 中，可能造成后续取消匹配到陈旧任务；后续可接入车机状态回调
                # 或 complete_external_task(task_id) 来补齐自然完成路径。
                await anyio.sleep_forever()
            finally:
                if uid in self._external_cancel_suppressed_task_ids:
                    self._external_cancel_suppressed_task_ids.discard(uid)
                    return

                with anyio.move_on_after(cancel_timeout, shield=True) as cancel_scope:
                    try:
                        result = cancel()
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        logger.exception("External task cancel callback failed")

                if cancel_scope.cancelled_caught:
                    logger.warning("External task cancel callback timed out")

        external_metadata = {"external": True}
        if metadata is not None:
            external_metadata.update(metadata)

        return self.submit_task(
            factory=external_worker,
            name=name,
            arguments=arguments,
            task_id=uid,
            task_def_id=task_def_id,
            metadata=external_metadata,
        )

    def cancel_task(self, task_id: str) -> TaskCancelOutcome:
        """同步取消任务。终态判断由 manager 负责，执行取消由内部 runner 负责。"""
        run = self.get_task(task_id)
        if run is None:
            return TaskCancelOutcome(
                status="not_found",
                task_id=task_id,
                reason=f"Task ID {task_id} not found",
            )

        if run.status in self._TERMINAL_STATUSES:
            return TaskCancelOutcome(
                status="already_terminal",
                task_id=task_id,
                terminal_status=run.status,
            )

        self._cancel_requested_task_ids.add(task_id)
        cancel_accepted = self._runner.cancel_task(task_id)
        if cancel_accepted is False:
            # DynamicStreamTaskRunner uses False when its first business
            # terminal is already fixed (including the internal draining
            # phase) but the manager has not projected the queued event yet.
            # Do not let this late cancel intent rewrite that terminal.
            self._cancel_requested_task_ids.discard(task_id)
            return TaskCancelOutcome(
                status="already_terminal",
                task_id=task_id,
            )
        return TaskCancelOutcome(
            status="accepted",
            task_id=task_id,
        )

    def cancel_tasks(self, task_ids: list[str]) -> list[TaskCancelOutcome]:
        raise NotImplementedError("TaskManager CRUD API is reserved but not implemented yet")

    def list_tasks(self, *, statuses: set[TaskStatus] | None = None) -> list[TaskRun]:
        raise NotImplementedError("TaskManager CRUD API is reserved but not implemented yet")

    def delete_task(self, task_id: str, *, allow_active: bool = False) -> bool:
        raise NotImplementedError("TaskManager CRUD API is reserved but not implemented yet")

    async def run(self) -> None:
        """启动内部 runner，并消费其生命周期事件。"""
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._runner.run)
            tg.start_soon(self._consume_runner_events)

    async def astream(self) -> AsyncGenerator[TaskEvent, None]:
        """消费 manager 规约后的对外任务事件流。"""
        async with self._event_output_recv:
            async for event in self._event_output_recv:
                yield event

    async def _consume_runner_events(self) -> None:
        async for event in self._runner.astream():
            if isinstance(event, TaskCancelledEvent):
                self._external_cancel_suppressed_task_ids.discard(event.task_id)

            event = self._normalize_event_with_cancel_intent(event)
            result = self.apply_event(event)
            if result.applied:
                await self._event_output_send.send(event)

    def _replace_active_external_tasks(
        self,
        *,
        name: str,
        replacement_task_id: str,
    ) -> None:
        for run in list(self._store.values()):
            if run.task_id == replacement_task_id:
                continue
            if run.status not in self._ACTIVE_STATUSES:
                continue
            if run.tool_name != name:
                continue
            if run.metadata.get("external") is not True:
                continue

            self._external_cancel_suppressed_task_ids.add(run.task_id)
            event = TaskCancelledEvent(
                task_id=run.task_id,
                reason=_EXTERNAL_REPLACED_REASON,
            )
            result = self.apply_event(event)
            if result.applied:
                self._emit_nowait(event)
            self._runner.cancel_task(run.task_id)

    def _normalize_event_with_cancel_intent(self, event: TaskEvent) -> TaskEvent:
        if event.task_id not in self._cancel_requested_task_ids:
            return event

        match event:
            case TaskSuccessEvent() | TaskFailureEvent():
                self._cancel_requested_task_ids.discard(event.task_id)
                return TaskCancelledEvent(
                    task_id=event.task_id,
                    reason="Task was cancelled",
                    timestamp=event.timestamp,
                )
            case TaskCancelledEvent():
                self._cancel_requested_task_ids.discard(event.task_id)
                return event
            case _:
                return event

    # --- 3. 核心：事件投影 ---

    _ACTIVE_STATUSES = {TaskStatus.PENDING, TaskStatus.RUNNING}
    _TERMINAL_STATUSES = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}

    def apply_created(self, event: TaskCreatedEvent) -> TaskApplyResult:
        """
        应用任务创建事件。
        TaskCreatedEvent 来自 agent-out，早于 runner 的 TaskStartEvent。
        """
        run = self._store.get(event.task_id)

        if run is None:
            run = TaskRun(
                task_id=event.task_id,
                task_def_id=event.name,
                tool_name=event.name,
                arguments=event.arguments,
                status=TaskStatus.PENDING,
                created_at=event.timestamp,
                updated_at=event.timestamp,
            )
            self._store[event.task_id] = run
            return self._applied(run)

        if run.created_from_start_fallback and run.status not in self._TERMINAL_STATUSES:
            run.task_def_id = event.name
            run.tool_name = event.name
            run.arguments = event.arguments
            run.created_from_start_fallback = False
            run.updated_at = event.timestamp
            return self._applied(run)

        return self._rejected(run.status, "任务创建事件重复")

    def apply_event(self, event: TaskEvent) -> TaskApplyResult:
        """接收任务运行事实事件，并更新内部投影。"""
        match event:
            case TaskCreatedEvent():
                return self.apply_created(event)
            case TaskStartEvent():
                return self._apply_start(event)
            case TaskProgressEvent():
                return self._apply_progress(event)
            case TaskSuccessEvent():
                return self._apply_terminal(event)
            case TaskFailureEvent():
                return self._apply_terminal(event)
            case TaskCancelledEvent():
                return self._apply_terminal(event)
            case _:
                assert_never(event)

    _MISSING_TASK_REASON = "任务不存在"

    def handle_event(self, event: TaskEvent):
        """
        兼容旧调用方的事件入口。
        对终态后的 late event 静默忽略；对真正异常的拒绝抛 AssertionError。
        """
        result = self.apply_event(event)
        if not result.applied:
            is_late_event = result.current_status in self._TERMINAL_STATUSES and result.reason != self._MISSING_TASK_REASON
            if not is_late_event:
                raise AssertionError(result.reason or "任务事件被拒绝")

    # --- 投影实现 ---

    def _apply_start(self, event: TaskStartEvent) -> TaskApplyResult:
        run = self._store.get(event.task_id)

        if run is None:
            # 兜底：TaskStartEvent 先于 TaskCreatedEvent 到达（或后者缺失）。
            # 此时缺少 name/arguments 等元数据，只能用 task_id 填充 placeholder。
            # 见 AgentRunner._process_agent_out_event 中的 TODO：根本解法是让 runner
            # 事件流自身携带完整元数据，而非依赖 agent-out 管道的交叉注入。
            run = TaskRun(
                task_id=event.task_id,
                task_def_id=event.task_id,
                tool_name=event.task_id,
                arguments={},
                status=TaskStatus.PENDING,
                created_at=event.timestamp,
                updated_at=event.timestamp,
                created_from_start_fallback=True,
            )
            self._store[event.task_id] = run

        if run.status in self._TERMINAL_STATUSES:
            return self._rejected(run.status, f"任务不能启动: {run.status}")

        if run.status == TaskStatus.RUNNING:
            return self._rejected(run.status, "任务已存在")

        run.mark_running(timestamp=event.timestamp)
        return self._applied(run)

    def _apply_progress(self, event: TaskProgressEvent[Any]) -> TaskApplyResult:
        run = self._store.get(event.task_id)
        if run is None:
            return self._rejected(TaskStatus.FAILED, "任务不存在")

        if run.status in self._TERMINAL_STATUSES:
            return self._rejected(run.status, f"任务不能更新进度: {run.status}")

        run.trace.append(nl_repr_safe(event.progress))
        run.updated_at = event.timestamp
        return self._applied(run)

    def _apply_terminal(
        self, event: TaskSuccessEvent[Any] | TaskFailureEvent[Any] | TaskCancelledEvent
    ) -> TaskApplyResult:
        run = self._store.get(event.task_id)
        if run is None:
            return self._rejected(TaskStatus.FAILED, "任务不存在")

        if run.status in self._TERMINAL_STATUSES:
            return self._rejected(run.status, f"任务已结束: {run.status}")

        match event:
            case TaskSuccessEvent():
                run.mark_success(result=event.result, timestamp=event.timestamp)
            case TaskFailureEvent():
                run.mark_failure(error_msg=nl_repr_safe(event.error), timestamp=event.timestamp)
            case TaskCancelledEvent():
                run.mark_cancelled(timestamp=event.timestamp)

        return self._applied(run)

    def _applied(self, run: TaskRun) -> TaskApplyResult:
        return TaskApplyResult(applied=True, current_status=run.status)

    def _rejected(self, current_status: TaskStatus, reason: str) -> TaskApplyResult:
        return TaskApplyResult(applied=False, current_status=current_status, reason=reason)

    def _emit_nowait(self, event: TaskEvent) -> None:
        try:
            self._event_output_send.send_nowait(event)
        except anyio.WouldBlock as exc:
            raise RuntimeError("TaskManager event buffer is full") from exc
        except (anyio.BrokenResourceError, anyio.ClosedResourceError) as exc:
            raise RuntimeError("TaskManager event stream is closed") from exc

    def _create_default_runner(self, max_concurrency: int):
        from aicore.v2.stream_task_runner import DynamicStreamTaskRunner

        return DynamicStreamTaskRunner(max_concurrency=max_concurrency)

    # --- 4. 只读查询 ---

    def get_task(self, task_id: str) -> TaskRun | None:
        return self._store.get(task_id, None)

    def get_active_tasks(self) -> list[TaskRun]:
        return [
            run for run in self._store.values()
            if run.status in self._ACTIVE_STATUSES
        ]

    def get_projection(self, task_id: str) -> TaskProjection | None:
        run = self._store.get(task_id)
        if run is None:
            return None
        return self._to_projection(run)

    def get_active_task_projections(self) -> list[TaskProjection]:
        return [
            self._to_projection(run)
            for run in self._store.values()
            if run.status in self._ACTIVE_STATUSES
        ]

    def _to_projection(self, run: TaskRun) -> TaskProjection:
        return TaskProjection.from_run(run)
