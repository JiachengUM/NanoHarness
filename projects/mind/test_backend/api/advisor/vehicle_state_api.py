from __future__ import annotations
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends
from projects.mind.advisor.mdb_models.vehicle_state import VehicleStateDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.schemas.vehicle_state import VehicleStateFilter, VehicleStateOut, VehicleStateCreate
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/vehicle_state",
    tags=["Vehicle State Manager"],
)


@router.get("/list", response_model=ApiResponse[list[VehicleStateOut]])
async def list_vehicle_state(filters: VehicleStateFilter = Depends()):
    docs = await mdb_api.get_list(model=VehicleStateDoc, query=filters.get_filters(), sort="-updated_time")
    return ok(to_out_list(docs, VehicleStateOut))


@router.get("/page", response_model=ApiResponse[Page[VehicleStateOut]])
async def page_vehicle_state(
    filters: VehicleStateFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=VehicleStateDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time"
    )
    return ok(to_out_page(page_docs, VehicleStateOut))


@router.post("", response_model=ApiResponse[VehicleStateOut])
async def create_vehicle_state(payload: VehicleStateCreate):
    doc = await mdb_api.create(VehicleStateDoc, payload)
    return ok(to_out(doc, VehicleStateOut), message="创建成功")


@router.put("/{vehicle_state_id}", response_model=ApiResponse[VehicleStateOut])
async def update_vehicle_state(vehicle_state_id: PydanticObjectId, payload: VehicleStateDoc):
    doc = await mdb_api.update(model=VehicleStateDoc, data=payload)
    return ok(to_out(doc, VehicleStateOut), message="更新成功")


@router.delete("/{vehicle_state_id}", response_model=ApiResponse)
async def delete_vehicle_state(vehicle_state_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(model=VehicleStateDoc, id=vehicle_state_id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


__all__ = ["router"]
