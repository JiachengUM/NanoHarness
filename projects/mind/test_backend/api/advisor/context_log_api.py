from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.mdb_models.context_log import ContextLogDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.context_log import (
    ContextLogFilter,
    ContextLogOut,
    ContextLogCreate,
)
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/context-log",
    tags=["Context Log Manager"],
)


@router.get("/list", response_model=ApiResponse[list[ContextLogOut]])
async def list_context_log(filters: ContextLogFilter = Depends()):
    docs = await mdb_api.get_list(
        model=ContextLogDoc, query=filters.get_filters(), sort="-time"
    )
    return ok(to_out_list(docs, ContextLogOut))


@router.get("/page", response_model=ApiResponse[Page[ContextLogOut]])
async def page_context_log(
    filters: ContextLogFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=ContextLogDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-created_time",
    )
    return ok(to_out_page(page_docs, ContextLogOut))


@router.post("", response_model=ApiResponse[ContextLogOut])
async def create_context_log(payload: ContextLogCreate):
    doc = await mdb_api.create(ContextLogDoc, payload)
    return ok(to_out(doc, ContextLogOut), message="创建成功")


@router.put("/{context_log_id}", response_model=ApiResponse[ContextLogOut])
async def update_context_log(payload: ContextLogDoc):
    doc = await mdb_api.update(model=ContextLogDoc, data=payload)
    return ok(to_out(doc, ContextLogOut), message="更新成功")


@router.delete("/{context_log_id}", response_model=ApiResponse)
async def delete_context_log(context_log_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=ContextLogDoc, id=context_log_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
