from typing import Any

from pydantic import BaseModel

from aicore.runtime.task import TaskManager
from aicore.tools.decorators import ClarifyTaskTool
from aicore.tools.protocol import TaskToolProtocol
from aicore.tools.task import TaskTool, TaskAWorker, TaskAStreamWorker, is_task_aworker
from aicore.v2.tools.async_task import Asyncable, AsyncableTaskTool


def create_tool[IT: BaseModel, OT, PT, **PS](
    name: str,
    description: str,
    args_schema: type[IT],
    *,
    worker: TaskAWorker[OT] | TaskAStreamWorker[PT, OT, PS],
    timeout: float | None = None,
    asyncable: Asyncable = "async",
    with_clarify: bool = False,
    task_manager: TaskManager | None = None,
) -> TaskToolProtocol[IT, OT, PT, PS]:
    """创建工具并根据 asyncable 选择同步、异步或模型动态执行模式。"""

    assert issubclass(args_schema, BaseModel), "args_schema必须是BaseModel的子类"

    if is_task_aworker(worker):
        tool = TaskTool[IT, OT, PT, PS](
            name=name,
            description=description,
            args_schema=args_schema,
            worker=worker,
            timeout=timeout,
        )
    else:
        tool = TaskTool[IT, OT, PT, PS](
            name=name,
            description=description,
            args_schema=args_schema,
            stream_worker=worker,
            timeout=timeout,
        )

    tool = AsyncableTaskTool[IT, OT, PT, PS](
        tool,
        asyncable=asyncable,
        task_manager=task_manager,
    )

    if with_clarify:
        return ClarifyTaskTool[IT, OT, PT, PS](tool)  # pyright: ignore[reportArgumentType, reportReturnType]

    return tool  # pyright: ignore[reportReturnType]


type TaskToolType[IT: BaseModel, OT, PT, **PS] = TaskToolProtocol[IT, OT, PT, PS]
type TaskToolTypeGeneral = TaskToolProtocol[BaseModel, Any, Any, ...]
