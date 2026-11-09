"""执行任务的worker的接口。跟task event, task def, task run等都解耦"""

from typing import Callable, Awaitable, AsyncGenerator, Any, TypeIs
import types
import inspect

from pydantic import BaseModel

__all__ = [
    "TaskAWorker",
    "is_task_aworker",
    "TaskProgress",
    "TaskSuccess",
    "TaskAStreamWorker",
    "TaskAStreamWorkerGeneral",
    "is_task_astreamworker"
]

# task的普通的async worker
# TODO: 这里可以加入parameter spec type variable
# 普通的task worker不应该返回TaskSuccess。它只是为了区分TaskProgress的，只用于TaskAstreamWorker。
type TaskAWorker[R] = Callable[..., Awaitable[R]]


# 为了解耦，worker不应该直接输出events\task中的TaskEvent，而是输出下面的对象。然后在外部的async for中解析它们，生成对应的Event
class TaskProgress[P](BaseModel):
    progress: P

class TaskSuccess[R](BaseModel):
    result: R


# task的async stream worker
type TaskAStreamWorker[P, R, **PS] = Callable[PS, AsyncGenerator[TaskProgress[P] | TaskSuccess[R], None]]

# 语义上，就是允许任意类型，不需要特定类型参数的情况下使用。
type TaskAStreamWorkerGeneral = TaskAStreamWorker[Any, Any, ...]

def _get_target_for_inspect(obj: Any):
    call_attr = getattr(obj, '__call__', None)
    if call_attr is None:
        return obj
    
    # 如果是类实例的 __call__ (bound method)
    if isinstance(call_attr, types.MethodType):
        return call_attr
    
    # 如果是普通函数的 __call__ (method-wrapper) 或其他情况，检查对象本身
    return obj


def is_task_aworker[R](obj: Any) -> TypeIs[TaskAWorker[R]]:
    target = _get_target_for_inspect(obj)
    return inspect.iscoroutinefunction(target)


def is_task_astreamworker[P, R, **PS](obj: Any) -> TypeIs[TaskAStreamWorker[P, R, PS]]:
    target = _get_target_for_inspect(obj)
    return inspect.isasyncgenfunction(target)