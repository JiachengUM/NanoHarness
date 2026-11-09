from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.repositories import mdb_api
from projects.mind.intent.task_mdb_models.intent_param import IntentParamDoc
from projects.mind.intent.task_schemas.intent_param import *
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/intent_param",
    tags=["Intent Param Manager"],
)


@router.get("/list", response_model=ApiResponse[list[IntentParamOut]])
async def list_intent_param(filters: IntentParamFilter = Depends()):
    docs = await mdb_api.get_list(model=IntentParamDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, IntentParamOut))


@router.get("/page", response_model=ApiResponse[Page[IntentParamOut]])
async def page_intent_param(
        filters: IntentParamFilter = Depends(),
        page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=IntentParamDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, IntentParamOut))


@router.post("", response_model=ApiResponse[IntentParamOut])
async def create_intent_param(payload: IntentParamCreate):
    doc = await mdb_api.create(IntentParamDoc, payload)
    return ok(to_out(doc, IntentParamOut), message="创建成功")


@router.put("/{intent_param_id}", response_model=ApiResponse[IntentParamOut])
async def update_intent_param(intent_param_id: PydanticObjectId, payload: IntentParamDoc):
    doc = await mdb_api.update(model=IntentParamDoc, data=payload)
    return ok(to_out(doc, IntentParamOut), message="更新成功")


@router.delete("/{intent_param_id}", response_model=ApiResponse)
async def delete_intent_param(intent_param_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=IntentParamDoc, id=intent_param_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
