from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.intent.intent_mdb_models.category import CategoryDoc
from projects.mind.intent.repositories import mdb_api
from projects.mind.intent.intent_schemas.category import CategoryOut, CategoryFilter, CategoryCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/category",
    tags=["Category Manager"],
)


@router.get("/list", response_model=ApiResponse[list[CategoryOut]])
async def list_category(filters: CategoryFilter = Depends()):
    docs = await mdb_api.get_list(model=CategoryDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, CategoryOut))


@router.get("/page", response_model=ApiResponse[Page[CategoryOut]])
async def page_category(
    filters: CategoryFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=CategoryDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, CategoryOut))



@router.post("", response_model=ApiResponse[CategoryOut])
async def create_category(payload: CategoryCreate):
    doc = await mdb_api.create(CategoryDoc, payload)
    return ok(to_out(doc, CategoryOut), message="创建成功")


@router.put("/{category_id}", response_model=ApiResponse[CategoryOut])
async def update_category(payload: CategoryDoc):
    doc = await mdb_api.update(model=CategoryDoc, data=payload)
    return ok(to_out(doc, CategoryOut), message="更新成功")


@router.delete("/{category_id}", response_model=ApiResponse)
async def delete_category(category_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=CategoryDoc, id=category_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
