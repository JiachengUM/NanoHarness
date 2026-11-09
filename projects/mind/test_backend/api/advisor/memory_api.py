from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends
from projects.mind.advisor.mdb_models.memory import EpisodicMemoryDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.memory import (
    EpisodicMemoryFilter,
    EpisodicMemoryOut, EpisodicMemoryCreate,
)
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/memory",
    tags=["Memory Manager"],
)


@router.get("/list", response_model=ApiResponse[list[EpisodicMemoryOut]])
async def list_memory(filters: EpisodicMemoryFilter = Depends()):
    docs = await mdb_api.get_list(model=EpisodicMemoryDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, EpisodicMemoryOut))


@router.get("/page", response_model=ApiResponse[Page[EpisodicMemoryOut]])
async def page_memory(
        filters: EpisodicMemoryFilter = Depends(),
        page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=EpisodicMemoryDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, EpisodicMemoryOut))


@router.post("", response_model=ApiResponse[EpisodicMemoryOut])
async def create_user(payload: EpisodicMemoryCreate):
    doc = await mdb_api.create(EpisodicMemoryDoc, payload)
    return ok(to_out(doc, EpisodicMemoryOut), message="创建成功")


@router.put("/{memory_id}", response_model=ApiResponse[EpisodicMemoryOut])
async def update_user(memory_id: PydanticObjectId, payload: EpisodicMemoryDoc):
    doc = await mdb_api.update(model=EpisodicMemoryDoc, data=payload)
    return ok(to_out(doc, EpisodicMemoryOut), message="更新成功")


@router.delete("/{memory_id}", response_model=ApiResponse)
async def delete_user(memory_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=EpisodicMemoryDoc, id=memory_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
