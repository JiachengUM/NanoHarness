from pydantic import BaseModel, Field

from aicore.runtime.task import TaskAWorker, TaskSuccess

from ..protocol import ErrorHandler, TaskAStreamWorkerWrapped, TaskToolProtocol


def extend_model_with_goal_generation(cls: type[BaseModel]) -> type[BaseModel]:
    """在任意表达用户意图的数据类上增加任务生成 meta 字段。"""

    assert issubclass(cls, BaseModel), "cls 必须是 BaseModel 的子类"

    class Extended(cls):
        description: str = Field(
            default=...,
            title="对于用户目标的总结描述",
            description="对于用户目标的总结描述。如果不够清楚，需要在 clarify 字段中给出需要澄清的问题。",
        )

        clarify: str | None = Field(
            default=None,
            title="需要向用户澄清的问题",
            description="为了明确用户的目标，需要向用户反问或澄清的问题。如果用户的描述足够清晰，不需要澄清。为空即可。",
        )

        __name__ = f"{cls.__name__}WithClarify"

    return Extended


def clarify_response(clarify: str) -> str:
    """返回给模型看的澄清响应。"""
    return f"用户意图不清晰，无法执行任务。不要再调用我这个工具了。需要向用户提问：{clarify}"


class ClarifyTaskTool[IT: BaseModel, OT, PT, **PS]:
    """TaskTool 的对象装饰器: 增加 clarify schema 与执行前分支。"""

    def __init__(self, inner_tool: TaskToolProtocol[IT, OT, PT, PS]):
        self.inner_tool = inner_tool
        self.args_schema = extend_model_with_goal_generation(inner_tool.args_schema)

    @property
    def name(self) -> str:
        return self.inner_tool.name

    @property
    def description(self) -> str:
        return self.inner_tool.description

    @property
    def timeout(self) -> float | None:
        return self.inner_tool.timeout

    @property
    def on_error(self) -> ErrorHandler | None:
        return self.inner_tool.on_error

    def simple_worker(
        self,
        description: str | None = None,
        clarify: str | None = None,
        *args: PS.args,
        **kwargs: PS.kwargs,
    ) -> TaskAWorker[OT | str]:
        """有澄清问题则短路返回，否则转发给被装饰的工具。"""

        async def wrapper() -> OT | str:
            if clarify:
                return clarify_response(clarify)

            return await self.inner_tool.simple_worker(*args, **kwargs)()

        return wrapper

    def stream_worker_factory(
        self,
        description: str | None = None,
        clarify: str | None = None,
        *args: PS.args,
        **kwargs: PS.kwargs,
    ) -> TaskAStreamWorkerWrapped[PT, OT | str]:
        """stream 路径同样支持澄清短路。"""

        async def wrapper():
            if clarify:
                yield TaskSuccess(result=clarify_response(clarify))
                return

            async for event in self.inner_tool.stream_worker_factory(*args, **kwargs)():
                yield event

        return wrapper # pyright: ignore[reportReturnType]


__all__ = [
    "ClarifyTaskTool",
    "clarify_response",
    "extend_model_with_goal_generation",
]
