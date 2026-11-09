from typing import Any, Callable, Protocol, runtime_checkable

from pydantic import BaseModel

from aicore.runtime.task import TaskAStreamWorker, TaskAWorker


ErrorHandler = Callable[[Exception], str]

# 和 TaskAStreamWorker 的区别是输入参数为空 []。
type TaskAStreamWorkerWrapped[P, R] = TaskAStreamWorker[P, R, []]


@runtime_checkable
class ToolProtocol[IT: BaseModel](Protocol):
    @property
    def name(self) -> str:
        """任务名称"""
        ...

    @property
    def description(self) -> str:
        """任务描述"""
        ...

    @property
    def args_schema(self) -> type[IT]:
        """任务输入的 schema"""
        ...


@runtime_checkable
class TaskToolProtocol[IT: BaseModel, OT, PT, **PS](ToolProtocol[IT], Protocol):
    @property
    def timeout(self) -> float | None:
        """任务超时时间，单位秒"""
        ...

    @property
    def on_error(self) -> ErrorHandler | None:
        """任务异常处理器"""
        ...

    def simple_worker(self, *args: PS.args, **kwargs: PS.kwargs) -> TaskAWorker[OT]:
        ...

    def stream_worker_factory(
        self, *args: PS.args, **kwargs: PS.kwargs
    ) -> TaskAStreamWorkerWrapped[PT, OT]:
        ...


type TaskToolProtocolGeneral = TaskToolProtocol[BaseModel, Any, Any, ...]


def validate_tool_arguments[IT: BaseModel](
    tool: ToolProtocol[IT], arguments: dict[str, object]
) -> IT:
    """校验并规范化工具参数；参数不合法时 throw ValidationError。"""
    # TODO: 应该包装为内部 Error, 而不是暴露 pydantic.ValidationError
    return tool.args_schema.model_validate(arguments)
