from __future__ import annotations

import time

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.intent.task_data import api_alg
from projects.mind.intent.task_mdb_models.intent_run import IntentRunDoc
from projects.mind.intent.repositories import mdb_api
from projects.mind.intent.task_schemas.intent_run import IntentRunOut, IntentRunFilter, IntentRunCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/intent_run",
    tags=["Intent Run Manager"],
)


@router.get("/list", response_model=ApiResponse[list[IntentRunOut]])
async def list_intent_run(filters: IntentRunFilter = Depends()):
    docs = await mdb_api.get_list(model=IntentRunDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, IntentRunOut))


@router.get("/page", response_model=ApiResponse[Page[IntentRunOut]])
async def page_intent_run(
        filters: IntentRunFilter = Depends(),
        page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=IntentRunDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, IntentRunOut))


@router.put("/{intent_run_id}", response_model=ApiResponse[IntentRunOut])
async def update_intent_run(payload: IntentRunDoc):
    doc = await mdb_api.update(model=IntentRunDoc, data=payload)
    return ok(to_out(doc, IntentRunOut), message="更新成功")


@router.delete("/{intent_run_id}", response_model=ApiResponse)
async def delete_intent_run(intent_run_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=IntentRunDoc, id=intent_run_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


@router.post("/intent", response_model=ApiResponse[IntentRunOut])
async def create_intent_run(payload: IntentRunCreate):
    """Intent category run api，记录输入、参数、输出、过程等数据"""
    start_time = time.time()
    output, trajectory = await api_alg.api_intent_cls(input=payload.input, param=payload.param)
    end_time = time.time()
    total_time = round(end_time - start_time, 2)
    payload.total_time = total_time
    payload.output = output
    payload.trajectory = trajectory
    doc = await mdb_api.create(IntentRunDoc, payload)
    return ok(to_out(doc, IntentRunDoc), message="创建成功")


__all__ = ["router"]
