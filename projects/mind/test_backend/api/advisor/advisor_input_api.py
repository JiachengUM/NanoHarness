from __future__ import annotations

from typing import List
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.task_mdb_models.advisor_input import AdvisorInputDoc
from projects.mind.advisor.task_schemas.advisor_input import AdvisorInputOut, AdvisorInputFilter, AdvisorInputCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/advisor_input",
    tags=["Advisor Input Manager"],
)


@router.get("/list", response_model=ApiResponse[List[AdvisorInputOut]])
async def list_advisor_input(filters: AdvisorInputFilter = Depends()):
    docs = await mdb_api.get_list(model=AdvisorInputDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, AdvisorInputOut))


@router.get("/page", response_model=ApiResponse[Page[AdvisorInputOut]])
async def page_advisor_input(
    filters: AdvisorInputFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=AdvisorInputDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, AdvisorInputOut))


@router.post("", response_model=ApiResponse[AdvisorInputOut])
async def create_advisor_input(payload: AdvisorInputCreate):
    doc = await mdb_api.create(AdvisorInputDoc, payload)
    return ok(to_out(doc, AdvisorInputOut), message="创建成功")


@router.put("/{advisor_input_id}", response_model=ApiResponse[AdvisorInputOut])
async def update_advisor_input(advisor_input_id: PydanticObjectId, payload: AdvisorInputDoc):
    doc = await mdb_api.update(model=AdvisorInputDoc, data=payload)
    return ok(to_out(doc, AdvisorInputOut), message="更新成功")


@router.delete("/{advisor_input_id}", response_model=ApiResponse)
async def delete_advisor_input(advisor_input_id: PydanticObjectId):
    result= await mdb_api.delete_by_id(model=AdvisorInputDoc, id=advisor_input_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")



__all__ = ["router"]
