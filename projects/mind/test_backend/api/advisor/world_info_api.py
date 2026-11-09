from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends
from projects.mind.advisor.mdb_models.world_info import WorldInfoDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.world_info import WorldInfoFilter, WorldInfoOut, WorldInfoCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/world_info",
    tags=["World Info Manager"],
)


@router.get("/list", response_model=ApiResponse[list[WorldInfoOut]])
async def list_world_info(filters: WorldInfoFilter = Depends()):
    docs = await mdb_api.get_list(model=WorldInfoDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, WorldInfoOut))


@router.get("/page", response_model=ApiResponse[Page[WorldInfoOut]])
async def page_world_info(
    filters: WorldInfoFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=WorldInfoDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, WorldInfoOut))


@router.post("", response_model=ApiResponse[WorldInfoOut])
async def create_world_info(payload: WorldInfoCreate):
    doc = await mdb_api.create(WorldInfoDoc, payload)
    return ok(to_out(doc, WorldInfoOut), message="创建成功")


@router.put("/{world_info_id}", response_model=ApiResponse[WorldInfoOut])
async def update_world_info(world_info_id: PydanticObjectId, payload: WorldInfoDoc):
    doc = await mdb_api.update(model=WorldInfoDoc, data=payload)
    return ok(to_out(doc, WorldInfoOut), message="更新成功")


@router.delete("/{world_info_id}", response_model=ApiResponse)
async def delete_world_info(world_info_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=WorldInfoDoc, id=world_info_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
