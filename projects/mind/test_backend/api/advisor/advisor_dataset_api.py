from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.task_mdb_models.advisor_dataset import AdvisorDatasetDoc
from projects.mind.advisor.task_schemas.advisor_dataset import AdvisorDatasetMetaOut, AdvisorDatasetMetaFilter, \
    AdvisorDatasetMetaCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/advisor_dataset",
    tags=["Advisor Dataset Manager"],
)


@router.get("/list", response_model=ApiResponse[list[AdvisorDatasetMetaOut]])
async def list_advisor_dataset(filters: AdvisorDatasetMetaFilter = Depends()):
    docs = await mdb_api.get_list(model=AdvisorDatasetDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, AdvisorDatasetMetaOut))


@router.get("/page", response_model=ApiResponse[Page[AdvisorDatasetMetaOut]])
async def page_advisor_dataset(
    filters: AdvisorDatasetMetaFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=AdvisorDatasetDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, AdvisorDatasetMetaOut))


@router.post("", response_model=ApiResponse[AdvisorDatasetMetaOut])
async def create_advisor_dataset(payload: AdvisorDatasetMetaCreate):
    doc = await mdb_api.create(AdvisorDatasetDoc, payload)
    return ok(to_out(doc, AdvisorDatasetMetaOut), message="创建成功")


@router.put("/{advisor_dataset_id}", response_model=ApiResponse[AdvisorDatasetMetaOut])
async def update_advisor_dataset(advisor_dataset_id: PydanticObjectId, payload: AdvisorDatasetDoc):
    doc = await mdb_api.update(model=AdvisorDatasetDoc, data=payload)
    return ok(to_out(doc, AdvisorDatasetMetaOut), message="更新成功")


@router.delete("/{advisor_dataset_id}", response_model=ApiResponse)
async def delete_advisor_dataset(advisor_dataset_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=AdvisorDatasetDoc, id=advisor_dataset_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
