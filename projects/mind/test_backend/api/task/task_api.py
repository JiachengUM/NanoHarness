from __future__ import annotations

import asyncio

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Depends

from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.mdb_models.auth import FeishuUserDoc
from projects.mind.test_backend.mdb_models.task import Task, TaskDoc
from projects.mind.test_backend.schemas.task.task import (
    TaskFilter,
    TaskOut,
    TaskRunRequest,
)
from projects.mind.test_backend.service.task.feishu_notify_service import (
    FeishuNotifyRecipient,
)
from projects.mind.test_backend.service.auth.feishu_auth_service import (
    get_optional_current_feishu_user,
)
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/task",
    tags=["Task Manager"],
)


def _get_task_auto_run_service():
    from projects.mind.test_backend.service.task import task_auto_run_service

    return task_auto_run_service


@router.get("/list", response_model=ApiResponse[list[TaskOut]])
async def list(filters: TaskFilter = Depends()):
    docs = await mdb_service.get_list(
        model=TaskDoc, query=filters.get_filters(), sort="-updated_time"
    )
    return ok(to_out_list(docs, TaskOut))


@router.get("/page", response_model=ApiResponse[Page[TaskOut]])
async def page(
    filters: TaskFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=TaskDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time",
    )
    return ok(to_out_page(page_docs, TaskOut))


@router.post("", response_model=ApiResponse[TaskOut])
async def create(payload: Task):
    doc = await mdb_service.create(model=TaskDoc, data=payload)
    return ok(to_out(doc, TaskOut), message="创建成功")


@router.put("/{id}", response_model=ApiResponse[TaskOut])
async def update(id: PydanticObjectId, payload: Task):
    doc = await mdb_service.update(model=TaskDoc, doc_id=id, data=payload)
    return ok(to_out(doc, TaskOut), message="更新成功")


@router.delete("/{id}", response_model=ApiResponse)
async def delete(id: PydanticObjectId):
    result = await mdb_service.delete_by_id(model=TaskDoc, id=id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


@router.post("/run/{task_id}", response_model=ApiResponse)
async def run_task(
    task_id: PydanticObjectId,
    payload: TaskRunRequest | None = Body(default=None),
    current_user: FeishuUserDoc | None = Depends(get_optional_current_feishu_user),
):
    notify_recipient = None
    if payload and (payload.email or payload.phone):
        notify_recipient = FeishuNotifyRecipient(
            email=payload.email,
            mobile=payload.phone,
        )
    elif current_user:
        notify_recipient = FeishuNotifyRecipient(
            receive_id=current_user.open_id,
            receive_id_type="open_id",
        )
    task_auto_run_service = _get_task_auto_run_service()
    asyncio.create_task(
        task_auto_run_service.run_task_by_step(
            task_id,
            notify_recipient=notify_recipient,
        )
    )

    return ok(message="任务开始运行")


__all__ = ["router"]

# python -m projects.mind.test_backend.api.task.task_api
