from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends
from projects.mind.advisor.mdb_models.visual_int import VisualIntDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.visual_int import VisualIntFilter, VisualIntOut, VisualIntCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/visual_int",
    tags=["Visual Interior Manager"],
)


@router.get("/list", response_model=ApiResponse[list[VisualIntOut]])
async def list_visual_int(filters: VisualIntFilter = Depends()):
    docs = await mdb_api.get_list(model=VisualIntDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, VisualIntOut))


@router.get("/page", response_model=ApiResponse[Page[VisualIntOut]])
async def page_visual_int(
    filters: VisualIntFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=VisualIntDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, VisualIntOut))


@router.post("", response_model=ApiResponse[VisualIntOut])
async def create_visual_int(payload: VisualIntCreate):
    doc = await mdb_api.create(VisualIntDoc, payload)
    return ok(to_out(doc, VisualIntOut), message="创建成功")


@router.put("/{visual_int_id}", response_model=ApiResponse[VisualIntOut])
async def update_visual_int(payload: VisualIntDoc):
    doc = await mdb_api.update(model=VisualIntDoc, data=payload)
    return ok(to_out(doc, VisualIntOut), message="更新成功")


@router.delete("/{visual_int_id}", response_model=ApiResponse)
async def delete_visual_int(visual_int_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=VisualIntDoc, id=visual_int_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
