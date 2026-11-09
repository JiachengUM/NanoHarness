from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from aicore.runtime.task import TaskManager, TaskProgress, TaskSuccess
from aicore.tools import TaskAStreamWorker
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.tools.factory import create_tool
from projects.sgm_prod.tools.CarControl import (
    CarControlInput,
    CarControlOutput,
    CarControlWorker,
)
from projects.sgm_prod.tools.Media import MediaInput, MediaOutput, MediaWorker
from projects.sgm_prod.tools.Navigation import (
    NavigationInput,
    NavigationOutput,
    NavigationWorker,
)


CarControlWorkerType = Callable[..., Awaitable[CarControlOutput]]
CarControlStreamWorker = TaskAStreamWorker[str, CarControlOutput, ...]
MediaWorkerType = Callable[..., Awaitable[MediaOutput]]
MediaStreamWorker = TaskAStreamWorker[str, MediaOutput, ...]
NavigationWorkerType = Callable[..., Awaitable[NavigationOutput]]
NavigationStreamWorker = TaskAStreamWorker[str, NavigationOutput, ...]


class CarControlV2Worker:
    def __init__(
        self,
        worker: CarControlWorkerType | None = None,
        *,
        chat_id: str | None = None,
    ) -> None:
        if worker is None:
            if chat_id is None:
                raise ValueError("使用默认车控 worker 时必须提供 chat_id")
            worker = CarControlWorker(chat_id)
        self.worker = worker

    async def __call__(self, command: str) -> CarControlOutput:
        return await self.worker(command=command)


class CarControlV2StreamWorker:
    def __init__(self, worker: CarControlWorkerType):
        self.worker = worker

    async def __call__(
        self,
        command: str,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[CarControlOutput], None]:
        yield TaskProgress(progress="开始执行车控")
        yield TaskProgress(progress=f"车控指令: {command}")
        result = await self.worker(command=command)
        yield TaskSuccess(result=result)


class MediaV2Worker:
    def __init__(
        self,
        worker: MediaWorkerType | None = None,
        *,
        chat_id: str | None = None,
    ) -> None:
        if worker is None:
            if chat_id is None:
                raise ValueError("使用默认媒体 worker 时必须提供 chat_id")
            worker = MediaWorker(chat_id)
        self.worker = worker

    async def __call__(self, command: str) -> MediaOutput:
        return await self.worker(command=command)


class MediaV2StreamWorker:
    def __init__(self, worker: MediaWorkerType):
        self.worker = worker

    async def __call__(
        self,
        command: str,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[MediaOutput], None]:
        yield TaskProgress(progress="开始执行媒体控制")
        yield TaskProgress(progress=f"媒体指令: {command}")
        result = await self.worker(command=command)
        yield TaskSuccess(result=result)


class NavigationV2Worker:
    def __init__(
        self,
        worker: NavigationWorkerType | None = None,
        *,
        chat_id: str | None = None,
    ) -> None:
        if worker is None:
            if chat_id is None:
                raise ValueError("使用默认导航 worker 时必须提供 chat_id")
            worker = NavigationWorker(chat_id)
        self.worker = worker

    async def __call__(self, command: str) -> NavigationOutput:
        return await self.worker(command=command)


class NavigationV2StreamWorker:
    def __init__(self, worker: NavigationWorkerType):
        self.worker = worker

    async def __call__(
        self,
        command: str,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[NavigationOutput], None]:
        yield TaskProgress(progress="开始执行导航任务")
        yield TaskProgress(progress=f"导航指令: {command}")
        result = await self.worker(command=command)
        yield TaskSuccess(result=result)


def car_control_v2_tool(
    worker: CarControlWorkerType | CarControlStreamWorker | None = None,
    *,
    chat_id: str | None = None,
    timeout: float | None = None,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    if worker is None:
        worker = CarControlV2StreamWorker(CarControlV2Worker(chat_id=chat_id))

    return create_tool(
        name="car_control",
        description=(
            "执行车载设备控制，包括：空调（温度、风量、模式）、座椅（位置、按摩、加热、通风）、"
            "车窗/天窗/车门、灯光（氛围灯、阅读灯、远近光）等。输入为自然语言车控指令。"
        ),
        args_schema=CarControlInput,
        worker=worker,
        timeout=timeout,
        asyncable="sync",
        task_manager=task_manager,
    )


def media_v2_tool(
    worker: MediaWorkerType | MediaStreamWorker | None = None,
    *,
    chat_id: str | None = None,
    timeout: float | None = None,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    if worker is None:
        worker = MediaV2StreamWorker(MediaV2Worker(chat_id=chat_id))

    return create_tool(
        name="media",
        description="控制车载多媒体，如播放/暂停/切歌、播放指定歌曲或歌单。输入为自然语言控制指令。",
        args_schema=MediaInput,
        worker=worker,
        timeout=timeout,
        asyncable="sync",
        task_manager=task_manager,
    )


def navigation_v2_tool(
    worker: NavigationWorkerType | NavigationStreamWorker | None = None,
    *,
    chat_id: str | None = None,
    timeout: float | None = None,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    if worker is None:
        worker = NavigationV2StreamWorker(NavigationV2Worker(chat_id=chat_id))

    return create_tool(
        name="navigation",
        description="执行导航相关任务，如开始导航、取消导航、添加途经点、调整路线偏好。",
        args_schema=NavigationInput,
        worker=worker,
        timeout=timeout,
        asyncable="sync",
        task_manager=task_manager,
    )


def build_sgm_v2_tools(
    *,
    chat_id: str,
    task_manager: TaskManager,
    timeout: float | None = None,
) -> list[TaskToolProtocolGeneral]:
    return [
        car_control_v2_tool(chat_id=chat_id, timeout=timeout, task_manager=task_manager),
        media_v2_tool(chat_id=chat_id, timeout=timeout, task_manager=task_manager),
        navigation_v2_tool(chat_id=chat_id, timeout=timeout, task_manager=task_manager),
    ]


__all__ = [
    "CarControlStreamWorker",
    "CarControlV2Worker",
    "CarControlV2StreamWorker",
    "CarControlWorkerType",
    "MediaStreamWorker",
    "MediaV2Worker",
    "MediaV2StreamWorker",
    "MediaWorkerType",
    "NavigationStreamWorker",
    "NavigationV2Worker",
    "NavigationV2StreamWorker",
    "NavigationWorkerType",
    "build_sgm_v2_tools",
    "car_control_v2_tool",
    "media_v2_tool",
    "navigation_v2_tool",
]
