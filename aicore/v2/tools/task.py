from typing import Callable, Any, Never, AsyncGenerator

from pydantic import BaseModel, Field, model_validator

from aicore.tools import BaseTool

from aicore.runtime.task import TaskSuccess, TaskProgress, TaskAWorker, TaskAStreamWorker, is_task_aworker, is_task_astreamworker

from aicore.core.types import SafeResult

ErrorHandler = Callable[[Exception], str]

# 和TaskAStreamWorker的区别是输入参数为空[]
type TaskAStreamWorkerWrapped[P, R] = Callable[[], AsyncGenerator[TaskProgress[P] | TaskSuccess[R], None]]

class TaskTool[IT: BaseModel, OT, PT, **PS](BaseTool):
    """基于BaseTool, 封装了关于runtime.task的功能，和整个框架配合执行task，提供下述功能:
    - 强类型: 输入输出类型定义和校验。 注意OutputT不必是BaseModel。
    - 自带coroutine stream worker, 用于异步执行task。
    - 自带异常处理机制，会将worker和stream worker的返回值包装为SafeResult

    TaskTool这个名字语义太强，有很多关于架构的考虑还不清楚，可能需要不停重构。尽量避免直接使用，通过factory间接使用。

    TODO: 是否值得去掉继承BaseTool? 好像意义不大。如果去掉的话，似乎代价也不大，只需要在react中能把tool转换成提示词就行。似乎没有对于BaseTool的其它依赖。
    """

    # BaseTool中的属性
    name: str = Field(..., description="任务名称")
    description: str = Field(..., description="任务描述")
    args_schema: type[IT] = Field(..., description="任务输入的schema") # type: ignore

    # 新属性
    worker: TaskAWorker[OT] | None = Field(default=None, description="任务的实现", exclude=True, repr=False)

    stream_worker: TaskAStreamWorker[PT, OT, PS] | None = Field(default=None, description="任务的流式实现", exclude=True, repr=False)

    # timeout: float | None = Field(default=None, description="任务超时时间，单位秒")

    on_error: ErrorHandler | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def check_data_error(self):

        """校验worker和stream_worker至少有一个不为None"""
        if (self.worker is None) and (self.stream_worker is None):
            raise ValueError("worker和stream_worker必须有一个不为None")

        # 验证worker
        if (self.worker is not None):
            if not is_task_aworker(self.worker):
                raise ValueError("worker必须是TaskAWorker的实例")

        # 验证stream_worker
        if (self.stream_worker is not None):
            if not is_task_astreamworker(self.stream_worker):
                raise ValueError("stream_worker必须是TaskAStreamWorker的实例")

        return self

    def _run(self, *args: Any, **kwargs: Any) -> Never:
        raise NotImplementedError("不支持同步调用，请使用流式调用")

    async def _arun(self, *args: Any, **kwargs: Any) -> SafeResult[OT]:
        """异步执行任务的核心方法
        
        1. 使用 asyncio.wait_for 包装 worker 调用，支持超时设置
        2. 捕获异常并转换为 TaskToolOutput 对象
        3. 返回包含结果或错误信息的 TaskToolOutput
        """
        raise NotImplementedError("不支持异步调用，请使用流式调用")

    def stream_worker_factory(self, *args: PS.args, **kwargs: PS.kwargs) -> TaskAStreamWorkerWrapped[PT, SafeResult[OT]]:
        """
        一个wrapper API，保持和StreamTaskTool的接口一致，用于流式输出任务结果。
        TODO: 目前还无法通过继承或者Protocol表达这个关系。这两种方式都比较麻烦，不太会写。因此，只能隐式地表达。
        """
        
        async def worker_wrapper():
            result = await self._arun(*args, **kwargs)
            yield TaskSuccess[SafeResult[OT]](result=result)

        async def streamworker_wrapper():
            """异步执行流式任务的核心方法"""
            # TODO: 在这里增加整体和每个步骤的超时控制
            assert self.stream_worker is not None, "stream_worker必须存在"

            async for event in self.stream_worker(*args, **kwargs):
                match event:
                    case TaskProgress():
                        yield event

                    case TaskSuccess():
                        # 将原始的OT包成SafeResult
                        yield TaskSuccess(result=SafeResult(data=event.result))

        # 优先用stream_worker，否则用普通worker
        if self.stream_worker is not None:
            return streamworker_wrapper
        else:
            return worker_wrapper
