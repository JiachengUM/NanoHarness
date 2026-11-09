from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.mdb_models.user import UserDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.user import (
    UserFilter,
    UserOut, UserCreate,
)
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/users",
    tags=["User Manager"],
)


@router.get("/list", response_model=ApiResponse[list[UserOut]])
async def list_users(filters: UserFilter = Depends()):
    docs = await mdb_api.get_list(model=UserDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, UserOut))


@router.get("/page", response_model=ApiResponse[Page[UserOut]])
async def page_users(
    filters: UserFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=UserDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, UserOut))



@router.post("", response_model=ApiResponse[UserOut])
async def create_user(payload: UserCreate):
    doc = await mdb_api.create(UserDoc, payload)
    return ok(to_out(doc, UserOut), message="创建成功")


@router.put("/{user_id}", response_model=ApiResponse[UserOut])
async def update_user(payload: UserDoc):
    doc = await mdb_api.update(model=UserDoc, data=payload)
    return ok(to_out(doc, UserOut), message="更新成功")


@router.delete("/{user_id}", response_model=ApiResponse)
async def delete_user(user_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=UserDoc, id=user_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
