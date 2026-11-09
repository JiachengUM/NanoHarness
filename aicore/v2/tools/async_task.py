import uuid
from functools import cache
from typing import Any, Callable, ClassVar, Literal, cast

from pydantic import BaseModel, Field, create_model

from aicore.runtime.task import TaskAWorker, TaskManager, TaskSuccess
from aicore.tools.protocol import ErrorHandler, TaskAStreamWorkerWrapped, TaskToolProtocol
from aicore.utils.nl_repr import nl_repr

TaskIdFactory = Callable[[], str]
type Asyncable = Literal["sync", "async", "dynamic"]


_WITH_ASYNC_FIELD_DESCRIPTION = (
    "是否异步执行，对于耗时较长的任务，可以选择异步执行，不阻塞用户持续提问"
)
_ASYNC_REASON_FIELD_DESCRIPTION = (
    "选择同步或异步执行的简短原因，说明用户要求、预计耗时或结果依赖"
)


@cache
def _get_dynamic_args_schema[IT: BaseModel](
    schema: type[IT],
) -> type[IT]:
    reserved_fields = {"with_async", "reason"} & schema.model_fields.keys()
    if reserved_fields:
        fields = "、".join(sorted(reserved_fields))
        raise ValueError(
            f"{schema.__name__} 已定义 {fields}，不能由 AsyncableTaskTool 重复注入"
        )

    extended = create_model(
        f"{schema.__name__}WithAsyncMode",
        __base__=schema,
        with_async=(
            bool,
            Field(
                default=False,
                description=_WITH_ASYNC_FIELD_DESCRIPTION,
            ),
        ),
        reason=(
            str,
            Field(
                ...,
                min_length=1,
                description=_ASYNC_REASON_FIELD_DESCRIPTION,
            ),
        ),
    )
    return cast(type[IT], extended)


class AsyncTaskReceipt(BaseModel):
    """异步任务已创建的占位回执。"""

    DEFAULT_ASYNC_PLACEHOLDER: ClassVar[str] = (
        "[占位回执] 【任务名:{tool_name},id:{task_id}】真实结果尚未到达，工具仍在异步执行中，"
        "请简短告知用户正在查询，不要重复调用工具。"
    )

    task_id: str
    tool_name: str

    def __nl_repr__(self, **_: Any) -> str:
        return self.DEFAULT_ASYNC_PLACEHOLDER.format(
            tool_name=self.tool_name,
            task_id=self.task_id,
        )


class AsyncTaskResultBackfill(BaseModel):
    """异步任务完成后的真实结果回灌。"""

    DEFAULT_BACKFILL_TEMPLATE: ClassVar[str] = (
        "[工具结果回灌] task_id={task_id} tool={tool_name}\n{result}"
    )

    task_id: str
    tool_name: str
    result: Any

    def __nl_repr__(self, **_: Any) -> str:
        return self.DEFAULT_BACKFILL_TEMPLATE.format(
            task_id=self.task_id,
            tool_name=self.tool_name,
            result=nl_repr(self.result),
        )


class AsyncableTaskTool[IT: BaseModel, OT, PT, **PS]:
    """根据 asyncable 以同步、异步或模型动态方式执行 TaskTool。"""

    def __init__(
        self,
        inner_tool: TaskToolProtocol[IT, OT, PT, PS],
        *,
        asyncable: Asyncable = "async",
        task_id_factory: TaskIdFactory | None = None,
        task_manager: TaskManager | None = None,
    ) -> None:
        if asyncable not in ("sync", "async", "dynamic"):
            raise ValueError(f"不支持的 asyncable 模式：{asyncable}")
        if asyncable in ("async", "dynamic") and task_manager is None:
            raise ValueError(f"asyncable={asyncable} requires task_manager")

        self.inner_tool = inner_tool
        self.asyncable = asyncable
        self.task_id_factory = task_id_factory or (lambda: str(uuid.uuid4()))
        self.task_manager = task_manager
        self._args_schema = (
            _get_dynamic_args_schema(inner_tool.args_schema)
            if asyncable == "dynamic"
            else inner_tool.args_schema
        )

    @property
    def name(self) -> str:
        return self.inner_tool.name

    @property
    def description(self) -> str:
        return self.inner_tool.description

    @property
    def args_schema(self) -> type[IT]:
        return self._args_schema

    @property
    def timeout(self) -> float | None:
        return self.inner_tool.timeout

    @property
    def on_error(self) -> ErrorHandler | None:
        return self.inner_tool.on_error

    def _split_execution_arguments(
        self,
        kwargs: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        inner_kwargs = dict(kwargs)
        if self.asyncable == "sync":
            return False, inner_kwargs
        if self.asyncable == "async":
            return True, inner_kwargs

        with_async = inner_kwargs.pop("with_async", False)
        inner_kwargs.pop("reason", None)
        if not isinstance(with_async, bool):
            raise TypeError("with_async 必须是 bool")
        return with_async, inner_kwargs

    def simple_worker(
        self, *args: PS.args, **kwargs: PS.kwargs
    ) -> TaskAWorker[OT | AsyncTaskReceipt]:
        if args:
            raise TypeError("AsyncableTaskTool 只支持 keyword arguments")

        with_async, inner_kwargs = self._split_execution_arguments(dict(kwargs))
        if not with_async:
            return self.inner_tool.simple_worker(  # pyright: ignore[reportCallIssue, reportReturnType]
                **inner_kwargs
            )

        async def wrapper() -> AsyncTaskReceipt:
            task_id = self.task_id_factory()

            async def backfill_wrapper():
                inner_worker = self.inner_tool.simple_worker(  # pyright: ignore[reportCallIssue]
                    **inner_kwargs
                )
                result = await inner_worker()
                backfill = AsyncTaskResultBackfill(
                    task_id=task_id,
                    tool_name=self.name,
                    result=result,
                )
                yield TaskSuccess(result=backfill)

            task_manager = self.task_manager
            assert task_manager is not None
            task_manager.submit_task(
                factory=backfill_wrapper,
                task_id=task_id,
                name=self.name,
                arguments=inner_kwargs,
            )
            return AsyncTaskReceipt(task_id=task_id, tool_name=self.name)

        return wrapper

    def stream_worker_factory(
        self, *args: PS.args, **kwargs: PS.kwargs
    ) -> TaskAStreamWorkerWrapped[PT, OT | AsyncTaskReceipt]:
        if args:
            raise TypeError("AsyncableTaskTool 只支持 keyword arguments")

        with_async, inner_kwargs = self._split_execution_arguments(dict(kwargs))
        if not with_async:
            return self.inner_tool.stream_worker_factory(  # pyright: ignore[reportCallIssue, reportReturnType]
                **inner_kwargs
            )

        async def wrapper():
            task_id = self.task_id_factory()

            async def backfill_stream_wrapper():
                inner_factory: TaskAStreamWorkerWrapped[
                    PT, OT
                ] = self.inner_tool.stream_worker_factory(  # pyright: ignore[reportCallIssue]
                    **inner_kwargs
                )
                async for event in inner_factory():
                    match event:
                        case TaskSuccess(result=result):
                            backfill = AsyncTaskResultBackfill(
                                task_id=task_id,
                                tool_name=self.name,
                                result=result,
                            )
                            yield TaskSuccess(result=backfill)
                        case _:
                            yield event

            task_manager = self.task_manager
            assert task_manager is not None
            task_manager.submit_task(
                factory=backfill_stream_wrapper,
                task_id=task_id,
                name=self.name,
                arguments=inner_kwargs,
            )
            receipt = AsyncTaskReceipt(task_id=task_id, tool_name=self.name)
            yield TaskSuccess(result=receipt)

        return wrapper  # pyright: ignore[reportReturnType]


__all__ = [
    "Asyncable",
    "AsyncableTaskTool",
    "AsyncTaskReceipt",
    "AsyncTaskResultBackfill",
]
