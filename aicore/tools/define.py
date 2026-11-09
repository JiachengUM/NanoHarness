from typing import Any

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskAWorker, TaskAStreamWorker

__all__ = [
    "ToolDef",
    "TaskToolImpl",
    "TaskToolImplGeneral",
]


class ToolDef(BaseModel):
    """非常简单，仅仅是一个helper class"""
    name: str = Field(description="工具的唯一标识")
    description: str = Field(description="工具的描述")


class TaskToolImpl[IT: BaseModel, OT, PT](BaseModel):
    """任务工具的实现。注意它仅支持runtime.task，并非通用的工具实现。"""
    args_schema: type[IT] = Field(description="工具的参数模型")
    worker: TaskAWorker[OT] | TaskAStreamWorker[PT, OT, ...] = Field(description="工具的执行器")


# 用于简化类型注释。注意它并非真实的class，不能用来创建对象。
type TaskToolImplGeneral = TaskToolImpl[BaseModel, Any, Any]