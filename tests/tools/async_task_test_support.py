from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aicore.runtime.task import TaskAStreamWorkerGeneral


@dataclass
class SubmittedTask:
    factory: TaskAStreamWorkerGeneral
    task_id: str
    name: str
    arguments: dict[str, Any]


class FakeTaskManager:
    def __init__(self) -> None:
        self.submitted: list[SubmittedTask] = []

    def submit_task(
        self,
        factory: TaskAStreamWorkerGeneral,
        *,
        name: str,
        arguments: dict[str, Any] | None = None,
        task_id: str | None = None,
        task_def_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        uid = task_id or f"task-{len(self.submitted) + 1:03d}"
        self.submitted.append(
            SubmittedTask(
                factory=factory,
                task_id=uid,
                name=name,
                arguments=arguments or {},
            )
        )
        return uid


class WeatherInput(BaseModel):
    city: str = Field(..., description="查询城市名称")
    time_range: str | None = Field(default="today", description="查询时间范围")
    criteria: list[str] | None = Field(default=None, description="天气查询条件")


class WeatherOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    city: str
    condition: str
    temperature: str


async def weather_worker(
    city: str,
    time_range: str | None = None,
    criteria: list[str] | None = None,
) -> WeatherOutput:
    return WeatherOutput(city=city, condition="晴", temperature="15-25C")
