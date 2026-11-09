import warnings
from typing import Callable, AsyncGenerator, Any, Never

from pydantic import BaseModel, Field

from aicore.tools import BaseTool

from aicore.core.types import SafeResult
from aicore.events.task import TaskProgress, TaskSuccess, StreamWorkerFactory

ErrorHandler = Callable[[Exception], str]

@warnings.deprecated("已废弃。已合并进入TaskTool。")
class StreamTaskTool[IT: BaseModel, OT, PT](BaseTool):
    """基于BaseTool, 封装了关于一个async stream task的功能，和aicore框架配合，提供下述功能:
    - 强类型: 输入输出类型定义(IT, OT)和校验。 注意OutputT不必是BaseModel。
    - asyncio运行时支持: 自带generator function worker, 在asyncio框架下异步流式地执行task。中间输出的过程数据类型为PT。
    注意: StreamTaskTool被调用的方式已经和BaseTool完全不同了。继承BaseTool仅仅是使用其其它能力。
    """

    # BaseTool中的属性
    name: str = Field(..., description="任务名称")
    description: str = Field(..., description="任务描述")
    args_schema: type[IT] = Field(..., description="任务输入的schema")  # type: ignore

    # 新属性
    stream_worker: Callable[..., AsyncGenerator[TaskProgress[PT] | TaskSuccess[OT], None]] = Field(default=..., description="任务的实现", exclude=True, repr=False)  

    timeout: float | None = Field(default=None, description="任务超时时间，单位秒")
    """TODO: 超时控制的实现晚些再加"""

    on_error: ErrorHandler | None = Field(default=None, exclude=True, repr=False)
    """TODO: 错误处理的实现晚些再加"""

    # TODO: 增加model_validate: gen_factory is generator function

    def _run(self, *args: Any, **kwargs: Any) -> Never:
        raise NotImplementedError("stream task tool不支持直接同步调用")

    async def _arun(self, *args: Any, **kwargs: Any) -> Never:
        raise NotImplementedError("stream task tool不支持直接异步调用，必须流式调用")

    def stream_worker_factory(self, *args: Any, **kwargs: Any) -> StreamWorkerFactory[PT, SafeResult[OT]]:
        """返回一个异步生成器factory, 用于异步执行任务"""

        async def wrapper() -> AsyncGenerator[TaskProgress[PT] | TaskSuccess[SafeResult[OT]], None]:
            """异步执行流式任务的核心方法"""
            # TODO: 在这里增加整体和每个步骤的超时控制
            async for event in self.stream_worker(*args, **kwargs):
                match event:
                    case TaskProgress():
                        yield event

                    case TaskSuccess():
                        # 将原始的OT包成SafeResult
                        yield TaskSuccess(result=SafeResult(data=event.result))
        
        return wrapper
