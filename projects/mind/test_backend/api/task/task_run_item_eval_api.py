from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter

from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.mdb_models.task import (
    TaskRunItemEval,
    TaskRunItemEvalDoc,
)

from projects.mind.test_backend.schemas.task.task import TaskRunItemEvalOut
from projects.mind.test_backend.utils.schemas import to_out
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/task_run_item/eval",
    tags=["Task Run Item Eval Manager"],
)


@router.get("/get_by_item_id/{item_id}", response_model=ApiResponse[TaskRunItemEvalOut])
async def get_by_item_id(item_id: PydanticObjectId):
    doc = await mdb_service.get_one(
        model=TaskRunItemEvalDoc,
        query={"task_run_item_id": item_id},
    )
    if not doc:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(to_out(doc, TaskRunItemEvalOut))


@router.put("/{id}", response_model=ApiResponse[TaskRunItemEvalOut])
async def update(id: PydanticObjectId, payload: TaskRunItemEval):
    doc = await mdb_service.update(model=TaskRunItemEvalDoc, doc_id=id, data=payload)
    return ok(to_out(doc, TaskRunItemEvalOut), message="更新成功")
