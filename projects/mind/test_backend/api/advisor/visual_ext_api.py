from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends
from projects.mind.advisor.mdb_models.visual_ext import VisualExtDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.visual_ext import VisualExtFilter, VisualExtOut, VisualExtCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/visual_ext",
    tags=["Visual Exterior Manager"],
)


@router.get("/list", response_model=ApiResponse[list[VisualExtOut]])
async def list_visual_ext(filters: VisualExtFilter = Depends()):
    docs = await mdb_api.get_list(model=VisualExtDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, VisualExtOut))


@router.get("/page", response_model=ApiResponse[Page[VisualExtOut]])
async def page_visual_ext(
    filters: VisualExtFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=VisualExtDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, VisualExtOut))


@router.post("", response_model=ApiResponse[VisualExtOut])
async def create_visual_ext(payload: VisualExtCreate):
    doc = await mdb_api.create(VisualExtDoc, payload)
    return ok(to_out(doc, VisualExtOut), message="创建成功")


@router.put("/{visual_ext_id}", response_model=ApiResponse[VisualExtOut])
async def update_visual_ext(payload: VisualExtDoc):
    doc = await mdb_api.update(model=VisualExtDoc, data=payload)
    return ok(to_out(doc, VisualExtOut), message="更新成功")


@router.delete("/{visual_ext_id}", response_model=ApiResponse)
async def delete_visual_ext(visual_ext_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=VisualExtDoc, id=visual_ext_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
