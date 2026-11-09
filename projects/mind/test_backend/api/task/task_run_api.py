from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from projects.mind.complex_reasoning.task_mdb_models.case import (
    ComplexReasoningCaseDoc,
)
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.mdb_models.task import (
    TaskDoc,
    TaskRun,
    TaskRunDoc,
    TaskRunItemDoc,
    TaskRunItemEvalDoc,
    TaskRunItemMessageDoc,
)
from projects.mind.test_backend.schemas.task.task import TaskRunFilter, TaskRunOut
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import (
    ApiResponse,
    excel_export_ok,
    ok,
    fail,
)
from projects.mind.test_backend.service.task import task_run_export_service
from projects.mind.test_backend.service.task.task_report_service import (
    generate_and_save_task_run_report,
)

router = APIRouter(
    prefix="/task_run",
    tags=["Task Run Manager"],
)


@router.get("/list", response_model=ApiResponse[list[TaskRunOut]])
async def list(filters: TaskRunFilter = Depends()):
    docs = await mdb_service.get_list(
        model=TaskRunDoc,
        query=filters.get_filters(),
        sort="-updated_time",
        exclude_fields=["metadata", "ai_report"],
    )
    return ok(to_out_list(docs, TaskRunOut))


@router.get("/page", response_model=ApiResponse[Page[TaskRunOut]])
async def page(
    filters: TaskRunFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=TaskRunDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time",
        exclude_fields=["metadata"],
    )
    return ok(to_out_page(page_docs, TaskRunOut))


@router.get("/{id}", response_model=ApiResponse[TaskRunOut])
async def get(id: PydanticObjectId):
    doc = await mdb_service.get_by_id(TaskRunDoc, id)
    if not doc:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(to_out(doc, TaskRunOut))


@router.get("/{id}/export", response_class=StreamingResponse)
async def export(id: PydanticObjectId):
    task_run = await mdb_service.get_by_id(TaskRunDoc, id)
    if not task_run:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")

    task = await mdb_service.get_by_id(TaskDoc, task_run.task_id)
    run_items = await mdb_service.get_list(
        model=TaskRunItemDoc,
        query={"task_run_id": id},
        sort="created_time",
    )

    run_item_ids = [item.id for item in run_items if item.id]
    dataset_item_ids = [item.dataset_item_id for item in run_items]

    cases = []
    eval_docs = []
    message_docs = []
    if dataset_item_ids:
        cases = await mdb_service.get_list(
            model=ComplexReasoningCaseDoc,
            query={"_id": {"$in": dataset_item_ids}},
        )
    if run_item_ids:
        eval_docs = await mdb_service.get_list(
            model=TaskRunItemEvalDoc,
            query={"task_run_item_id": {"$in": run_item_ids}},
        )
        message_docs = await mdb_service.get_list(
            model=TaskRunItemMessageDoc,
            query={"task_run_item_id": {"$in": run_item_ids}},
            sort="created_time",
        )

    case_map = {str(doc.id): doc for doc in cases if doc.id}
    eval_map = {str(doc.task_run_item_id): doc for doc in eval_docs}
    message_map: dict[str, list[TaskRunItemMessageDoc]] = {}
    for doc in message_docs:
        message_map.setdefault(str(doc.task_run_item_id), []).append(doc)

    excel_bytes = task_run_export_service.build_task_run_export_workbook(
        task=task,
        task_run=task_run,
        run_items=run_items,
        case_map=case_map,
        eval_map=eval_map,
        message_map=message_map,
    )
    return excel_export_ok(
        excel_bytes,
        filename=task_run_export_service.build_task_run_export_filename(task_run),
    )


@router.post("", response_model=ApiResponse[TaskRunOut])
async def create(payload: TaskRun):
    doc = await mdb_service.create(model=TaskRunDoc, data=payload)
    return ok(to_out(doc, TaskRunOut), message="创建成功")


@router.put("/{id}", response_model=ApiResponse[TaskRunOut])
async def update(id: PydanticObjectId, payload: TaskRun):
    doc = await mdb_service.update(model=TaskRunDoc, doc_id=id, data=payload)
    return ok(to_out(doc, TaskRunOut), message="更新成功")


@router.delete("/{id}", response_model=ApiResponse)
async def delete(id: PydanticObjectId):
    result = await mdb_service.delete_by_id(model=TaskRunDoc, id=id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


@router.post("/{id}/generate_report", response_model=ApiResponse)
async def generate_report(id: PydanticObjectId):
    """
    触发生成AI测试报告（异步后台执行，生成完自动写入 ai_report 字段）
    """
    task_run = await mdb_service.get_by_id(TaskRunDoc, id)
    if not task_run:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")

    import asyncio

    async def _background_generate():
        try:
            await generate_and_save_task_run_report(id)
        except Exception as e:
            print(f"[generate_report] 后台生成报告失败: {e}")
            import traceback

            traceback.print_exc()

    asyncio.create_task(_background_generate())

    return ok(message="报告生成中，请稍后刷新查看")


__all__ = ["router"]
