from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.intent.task_mdb_models.intent_input import IntentInputDoc
from projects.mind.intent.repositories import mdb_api
from projects.mind.intent.task_schemas.intent_input import IntentInputOut, IntentInputFilter, IntentInputCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/intent_input",
    tags=["Intent Input Manager"],
)


@router.get("/list", response_model=ApiResponse[list[IntentInputOut]])
async def list_input(filters: IntentInputFilter = Depends()):
    docs = await mdb_api.get_list(model=IntentInputDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, IntentInputOut))


@router.get("/page", response_model=ApiResponse[Page[IntentInputOut]])
async def page_input(
    filters: IntentInputFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=IntentInputDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, IntentInputOut))



@router.post("", response_model=ApiResponse[IntentInputOut])
async def create_input(payload: IntentInputCreate):
    doc = await mdb_api.create(IntentInputDoc, payload)
    return ok(to_out(doc, IntentInputOut), message="创建成功")


@router.put("/{intent_input_id}", response_model=ApiResponse[IntentInputOut])
async def update_input(payload: IntentInputDoc):
    doc = await mdb_api.update(model=IntentInputDoc, data=payload)
    return ok(to_out(doc, IntentInputOut), message="更新成功")


@router.delete("/{intent_input_id}", response_model=ApiResponse)
async def delete_input(intent_input_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=IntentInputDoc, id=intent_input_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
