from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.repositories import mdb_api
from projects.mind.intent.task_mdb_models.intent_dataset import IntentDatasetDoc
from projects.mind.intent.task_schemas.intent_dataset import *
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/intent_dataset",
    tags=["Intent Dataset Manager"],
)


@router.get("/list", response_model=ApiResponse[list[IntentDatasetMetaOut]])
async def list_intent_dataset(filters: IntentDatasetMetaFilter = Depends()):
    docs = await mdb_api.get_list(model=IntentDatasetDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, IntentDatasetMetaOut))


@router.get("/page", response_model=ApiResponse[Page[IntentDatasetMetaOut]])
async def page_intent_dataset(
        filters: IntentDatasetMetaFilter = Depends(),
        page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=IntentDatasetDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, IntentDatasetMetaOut))


@router.post("", response_model=ApiResponse[IntentDatasetMetaOut])
async def create_intent_dataset(payload: IntentDatasetMetaCreate):
    doc = await mdb_api.create(IntentDatasetDoc, payload)
    return ok(to_out(doc, IntentDatasetMetaOut), message="创建成功")


@router.put("/{intent_dataset_id}", response_model=ApiResponse[IntentDatasetMetaOut])
async def update_intent_dataset(intent_dataset_id: PydanticObjectId, payload: IntentDatasetDoc):
    doc = await mdb_api.update(model=IntentDatasetDoc, data=payload)
    return ok(to_out(doc, IntentDatasetMetaOut), message="更新成功")


@router.delete("/{intent_dataset_id}", response_model=ApiResponse)
async def delete_intent_dataset(intent_dataset_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=IntentDatasetDoc, id=intent_dataset_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
