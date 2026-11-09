from typing import Any

import warnings

from pydantic import BaseModel, Field

from aicore.core.types import SafeResult
from aicore.tools.task import TaskTool, TaskAWorker, TaskAStreamWorker

class StructuredGoal(BaseModel):
    """结构化描述的目标"""
    description: str = Field(default=..., title="对于用户目标的总结描述", description="对于用户目标的总结描述")
    
    clarify: str | None = Field(default=None, title="需要向用户澄清的问题", description="为了明确用户的目标，需要向用户反问或澄清的问题。如果用户的描述足够清晰，不需要澄清。为空即可。")

    criteria: list[str] | None = Field(default=None, title="用户目标完成的标准列表", description="用户目标完成的标准列表")
    

async def goal_plan_worker(
    description: str,
    clarify: str | None = None,
    criteria: list[str] | None = None,
) -> StructuredGoal:
    """什么也不用干"""

    return StructuredGoal(description=description, criteria=criteria, clarify=clarify)


def goal_plan_tool() -> TaskTool[StructuredGoal, StructuredGoal, None, ...]:
    """
    这个tool只负责任务的创建，不负责执行。
    """
    
    return TaskTool[StructuredGoal, StructuredGoal, None, ...](
        name="用户目标总结和生成的工具。",
        description="""当用户表达了比较复杂的意图和目标，难以直接回答或者调用其它工具直接完成用户意图，请调用该工具对于用户目标和完成标准进行总结确认。
如需要向用户反问或者澄清其意图和目标的细节，也调用该工具生成需要澄清的问题。
注意，只有当缺乏关键细节，或者用户表达过于模糊时，才需要反问和澄清。尽量避免澄清，而是直接开始完成用户的任务。
""",
        args_schema=StructuredGoal,
        worker=goal_plan_worker,
    )


@warnings.deprecated("已废弃。use ClarifyTaskTool instead")
class TaskToolWithPlanning[G: StructuredGoal, R, P, **PS](TaskTool[G, R | str, P, PS]):
    """
    这个tool负责创建structured goal并执行。如果用户输入不足以创建structured goal，则返回"需要澄清的问题"。
    """

    # 注意worker的返回值类型被窄化到了R, 而TaskTool是R | str
    worker: TaskAWorker[R] | None = Field(default=None, description="任务的实现", exclude=True, repr=False)  # type: ignore

    stream_worker: TaskAStreamWorker[P, SafeResult[R | str]] | None = Field(default=None, description="任务的流式实现", exclude=True, repr=False) # type: ignore

    async def _arun(
        self,
        description: str,
        clarify: str | None = None, 
        criteria: list[str] | None = None,
        *args: Any, 
        **kwargs: Any) -> SafeResult[R | str]:
        """
        所有goal共享的通用字段: description, clarify, criteria
        TODO: criteria是否能写成list[str]的通用形式存疑，也许需要在每个具体的goal task中定制
        *args, **kwargs: 具体的goal task的参数
        """
        
        if clarify:
            # 直接返回f"需要向用户澄清的问题：{clarify}"居然可能不work，模型会傻傻地继续调该工具。参见 test_react.py中的测试case。
            # 改成下面这样终于好了。
            return SafeResult(data=f"用户意图不清晰，无法执行任务。不要再调用我这个工具了。需要向用户提问：{clarify}")

        # TODO: 这里显式地写criteria很脏
        return await super()._arun(criteria=criteria, *args, **kwargs)
