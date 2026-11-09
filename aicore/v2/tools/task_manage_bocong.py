from typing import Any, Never, List

from aicore.events.task import TaskCancelRequest

from aicore.tools import BaseTool

from pydantic import BaseModel, Field

class SingleTaskCommand(BaseModel):
    task_id: str = Field(description="任务ID")
    task_name: str = Field(description="通用任务名称")
    from_state: str = Field(description="上一次状态")
    to_state: str = Field(description="目标状态")
    # trigger: str = Field(description="触发原因")


class TaskCommand(BaseModel):
    # task_id: str = Field(description="任务ID")

    task_name: str = Field(description="任务名称")

    task_state: str = Field(description="状态变化详细描述（最新状态和目标状态）")

    # from_state: str = Field(description="最新状态描述")

    final_action: str = Field(description="目标动作：增加、取消、暂停、立即返回、继续查询")



class MultiTaskCommand(BaseModel):
    tasks: List[TaskCommand] = Field(description="本次指令中包含的所有任务状态变更")

class POITaskCancelTool(BaseTool):
    name: str = "POI查询取消"

    description: str = "识别到用户说出了取消POI查询时调用"

    args_schema: type[TaskCommand] = Field(default=TaskCommand)

    def _run(self, *args: Any, **kwargs: Any) -> Never:
        # TODO: 可以通过asyncer很简单地就支持同步。
        raise NotImplementedError("不支持同步调用，请使用异步调用")

    async def _arun(self, task_name: str, task_state: str) -> TaskCancelRequest:
        pass

class WeatherTaskCancelTool(BaseTool):
    name: str = "天气查询取消"

    description: str = "识别到用户说出了取消天气查询时调用"

    args_schema: type[TaskCommand] = Field(default=TaskCommand)

    def _run(self, *args: Any, **kwargs: Any) -> Never:
        # TODO: 可以通过asyncer很简单地就支持同步。
        raise NotImplementedError("不支持同步调用，请使用异步调用")

    async def _arun(self, task_name: str, task_state: str) -> TaskCancelRequest:
        pass

class TaskManager(BaseTool):
    name: str = "POI查询与天气查询状态管理"

    description: str = "识别到了用户意图增删改任务时调用"

    args_schema: type[MultiTaskCommand] = Field(default=MultiTaskCommand)

    def _run(self, *args: Any, **kwargs: Any) -> Never:
        # TODO: 可以通过asyncer很简单地就支持同步。
        raise NotImplementedError("不支持同步调用，请使用异步调用")

    async def _arun(self, tasks: MultiTaskCommand) -> TaskCancelRequest:
        pass
