from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from typing import Any

from aicore.runtime.task import TaskManager, TaskProgress, TaskSuccess, is_task_astreamworker
from aicore.tools import TaskAStreamWorker
from aicore.tools.dag.base_classes import PlanExecutionOutput
from aicore.tools.dag.observer import DAGRenderFrame, observe_dag_frames
from aicore.tools.dag.plan_execution_tool import _plan_execution_worker
from aicore.tools.dag.plan_generator import (
    PlanGeneratorInput,
    StructuredPlan,
    _generate_operator_description,
)
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.tools.factory import create_tool


DAGPlanWorker = Callable[..., Awaitable[PlanExecutionOutput]]
DAGPlanStreamWorker = TaskAStreamWorker[DAGRenderFrame, PlanExecutionOutput, ...]


def _failed_frame_from_result(result: PlanExecutionOutput) -> DAGRenderFrame:
    raw_message = result.message or "DAG计划执行失败"
    first_line = raw_message.splitlines()[0] if raw_message else "DAG计划执行失败"
    if first_line.startswith("任务执行失败"):
        message = f"DAG计划生成失败: {first_line}"
    else:
        message = first_line

    return DAGRenderFrame(
        phase="failed",
        message=message,
        progress_percent=100,
        status="failed",
        detail={
            "stage": result.stage,
            "message": raw_message,
        },
    )


class DAGPlanV2StreamWorker:
    def __init__(self, plan_worker: DAGPlanWorker = _plan_execution_worker) -> None:
        self.plan_worker = plan_worker

    async def __call__(
        self,
        structured_plan: StructuredPlan,
    ) -> AsyncGenerator[TaskProgress[DAGRenderFrame] | TaskSuccess[PlanExecutionOutput], None]:
        queue: asyncio.Queue[DAGRenderFrame | None] = asyncio.Queue()
        emitted_failed_frame = False

        async def observer(frame: DAGRenderFrame) -> None:
            nonlocal emitted_failed_frame
            render_frame = DAGRenderFrame.model_validate(frame)
            if render_frame.phase == "failed" or render_frame.status == "failed":
                emitted_failed_frame = True
            await queue.put(render_frame)

        async def run_plan() -> PlanExecutionOutput:
            try:
                with observe_dag_frames(observer):
                    return await self.plan_worker(structured_plan=structured_plan)
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_plan())
        try:
            yield TaskProgress(
                progress=DAGRenderFrame(
                    message="DAG任务已进入后台执行",
                    phase="queued",
                    progress_percent=1,
                )
            )

            while True:
                payload = await queue.get()
                if payload is None:
                    break
                yield TaskProgress(progress=payload)

            result = await task
            if result.success is False and not emitted_failed_frame:
                yield TaskProgress(progress=_failed_frame_from_result(result))
            yield TaskSuccess(result=result)
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


def dag_plan_v2_tool(
    worker: DAGPlanWorker | DAGPlanStreamWorker | None = None,
    *,
    timeout: float | None = 120,
    task_manager: TaskManager,
) -> TaskToolProtocolGeneral:
    stream_worker: DAGPlanStreamWorker
    if worker is None:
        stream_worker = DAGPlanV2StreamWorker()
    elif is_task_astreamworker(worker):
        stream_worker = worker  # pyright: ignore[reportAssignmentType]
    else:
        stream_worker = DAGPlanV2StreamWorker(plan_worker=worker)  # pyright: ignore[reportArgumentType]

    return create_tool(
        name="dag_plan",
        description=f"""
        将用户输入转换成结构化Plan，基于Plan获取任务目标所需的信息；
        Plan生成策略：一步一步将目标分解成最小可执行单元；
        优化Plan时必须输出完整的steps列表；
        DAG执行失败时优化相关节点的算子入参；
        注册算子类型：
        {_generate_operator_description()}
        """,
        args_schema=PlanGeneratorInput,
        worker=stream_worker,
        timeout=timeout,
        asyncable="async",
        with_clarify=False,
        task_manager=task_manager,
    )


__all__ = [
    "DAGPlanStreamWorker",
    "DAGPlanV2StreamWorker",
    "DAGPlanWorker",
    "dag_plan_v2_tool",
]
