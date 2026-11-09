from __future__ import annotations

from typing import List
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.services import advisor_run_service
from projects.mind.advisor.task_mdb_models.advisor_run import AdvisorRunDoc
from projects.mind.advisor.task_schemas.advisor_input import AdvisorInputCreate
from projects.mind.advisor.task_schemas.advisor_run import AdvisorRunOut, AdvisorRunFilter, AdvisorRunCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/advisor_run",
    tags=["Advisor Run Manager"],
)


@router.get("/list", response_model=ApiResponse[List[AdvisorRunOut]])
async def list_advisor_run(filters: AdvisorRunFilter = Depends()):
    docs = await mdb_api.get_list(model=AdvisorRunDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, AdvisorRunOut))


@router.get("/page", response_model=ApiResponse[Page[AdvisorRunOut]])
async def page_advisor_run(
    filters: AdvisorRunFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=AdvisorRunDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, AdvisorRunOut))


@router.post("", response_model=ApiResponse[AdvisorRunOut])
async def create_advisor_run(payload: AdvisorRunCreate):
    doc = await mdb_api.create(AdvisorRunDoc, payload)
    return ok(to_out(doc, AdvisorRunOut), message="创建成功")


@router.put("/{advisor_run_id}", response_model=ApiResponse[AdvisorRunOut])
async def update_advisor_run(payload: AdvisorRunDoc):
    doc = await mdb_api.update(model=AdvisorRunDoc, data=payload)
    return ok(to_out(doc, AdvisorRunOut), message="更新成功")


@router.delete("/{advisor_run_id}", response_model=ApiResponse)
async def delete_advisor_run(advisor_run_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=AdvisorRunDoc, id=advisor_run_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


@router.post("/advise/{advise_type}", response_model=ApiResponse[AdvisorRunOut])
async def create_advisor_run(advise_type: str, payload: AdvisorInputCreate):
    doc = await advisor_run_service.advisor_run(advise_type, payload)
    return ok(to_out(doc, AdvisorRunOut), message="创建成功")



__all__ = ["router"]
