from typing import Any

from pydantic import BaseModel

from .decorators import (
    ClarifyTaskTool,
)
from .protocol import TaskToolProtocol, TaskToolProtocolGeneral
from .task import TaskTool, TaskAWorker, TaskAStreamWorker, is_task_aworker

from .define import ToolDef, TaskToolImplGeneral

def create_tool[IT: BaseModel, OT, PT, **PS](
    name: str, 
    description: str, 
    args_schema: type[IT], 
    *,
    worker: TaskAWorker[OT] | TaskAStreamWorker[PT, OT, PS],
    timeout: float | None = None,
    with_clarify: bool = False,
    ) -> TaskToolProtocol[
        IT, OT, PT, PS
    ]:
    """
    通用的创建工具的方法。隔离了工具的具体实现，方便内部重构。
    应用层应该尽量使用它，避免直接使用TaskTool, TaskToolWithPlanning等。
    """

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
        # TODO: 下述代码被IDE认为不会执行？似乎是个bug。是可执行的。
        tool = TaskTool[IT, OT, PT, PS](
            name=name,
            description=description,
            args_schema=args_schema,
            stream_worker=worker,
            timeout=timeout,
            )

    if with_clarify:
        # pyright 无法沿 factory 的运行时组合证明 ClarifyTaskTool 的泛型变换。
        return ClarifyTaskTool[IT, OT, PT, PS](tool)  # pyright: ignore[reportArgumentType, reportReturnType]

    # 未开启某些装饰器时，实际 tool 的 OT/PT 是声明返回类型的子集；
    # TaskToolProtocol 的类型参数不协变，pyright 无法证明该赋值安全。
    return tool  # pyright: ignore[reportReturnType]


def create_tools(
    tool_defs: list[ToolDef], 
    workers: dict[str, TaskToolImplGeneral],
    ) -> list[TaskToolProtocolGeneral]:

    return [
        create_tool(
            name=tool.name,
            description=tool.description,
            args_schema=workers[tool.name].args_schema,
            worker=workers[tool.name].worker,
        )
        for tool in tool_defs
    ]


type TaskToolType[IT: BaseModel, OT, PT, **PS] = TaskToolProtocol[IT, OT, PT, PS]

type TaskToolTypeGeneral = TaskToolProtocol[BaseModel, Any, Any, ...]
