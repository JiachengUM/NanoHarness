from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.complex_reasoning.task_mdb_models.dataset import (
    ComplexReasoningDatasetDoc,
)
from projects.mind.test_backend.mdb_models.task import TaskRunItemDoc
from projects.mind.complex_reasoning.task_schemas.case import ComplexReasoningCaseCreate
from projects.mind.complex_reasoning.task_schemas.dataset import *
from projects.mind.complex_reasoning.task_schemas.dataset import (
    ComplexReasoningDatasetMetaCopy,
)
from projects.mind.complex_reasoning.task_schemas.dataset import DatasetBuildParams
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/complex_reasoning_dataset",
    tags=["Complex Reasoning Dataset Manager"],
)


@router.get("/list", response_model=ApiResponse[list[ComplexReasoningDatasetMetaOut]])
async def list_complex_reasoning_dataset(
    filters: ComplexReasoningDatasetMetaFilter = Depends(),
):
    docs = await mdb_service.get_list(
        model=ComplexReasoningDatasetDoc,
        query=filters.get_filters(),
        sort="-updated_time",
    )
    return ok(to_out_list(docs, ComplexReasoningDatasetMetaOut))


@router.get("/page", response_model=ApiResponse[Page[ComplexReasoningDatasetMetaOut]])
async def page_complex_reasoning_dataset(
    filters: ComplexReasoningDatasetMetaFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=ComplexReasoningDatasetDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time",
    )

    for doc in page_docs.items:
        case_count = await mdb_service.get_count(
            model=ComplexReasoningCaseDoc, query={"dataset_id": doc.id}
        )
        doc.item_count = case_count

    return ok(to_out_page(page_docs, ComplexReasoningDatasetMetaOut))


@router.post("", response_model=ApiResponse[ComplexReasoningDatasetMetaOut])
async def create_complex_reasoning_dataset(payload: ComplexReasoningDatasetMetaCreate):
    doc = await mdb_service.create(ComplexReasoningDatasetDoc, payload)
    return ok(to_out(doc, ComplexReasoningDatasetMetaOut), message="创建成功")


@router.put(
    "/{complex_reasoning_dataset_id}",
    response_model=ApiResponse[ComplexReasoningDatasetMetaOut],
)
async def update_complex_reasoning_dataset(
    complex_reasoning_dataset_id: PydanticObjectId, payload: ComplexReasoningDatasetDoc
):
    doc = await mdb_service.update(
        model=ComplexReasoningDatasetDoc,
        doc_id=complex_reasoning_dataset_id,
        data=payload,
    )
    return ok(to_out(doc, ComplexReasoningDatasetMetaOut), message="更新成功")


@router.delete("/{complex_reasoning_dataset_id}", response_model=ApiResponse)
async def delete_complex_reasoning_dataset(
    complex_reasoning_dataset_id: PydanticObjectId,
):
    result = await mdb_service.delete_by_id(
        model=ComplexReasoningDatasetDoc, id=complex_reasoning_dataset_id
    )

    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")

    # 删除 dataset 同时删除所有关联dataset_item
    await mdb_service.delete_by_query(
        model=ComplexReasoningCaseDoc,
        query={"dataset_id": complex_reasoning_dataset_id},
    )

    return ok(message="删除成功")


@router.post("/copy", response_model=ApiResponse[ComplexReasoningDatasetMetaOut])
async def copy_complex_reasoning_dataset(payload: ComplexReasoningDatasetMetaCopy):
    # 查询原数据集
    original_dataset = await mdb_service.get_by_id(
        model=ComplexReasoningDatasetDoc, doc_id=payload.dataset_id
    )
    if not original_dataset:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到原数据集")

    # 创建新数据集
    new_dataset_data = original_dataset.model_dump(
        exclude={"id", "created_time", "updated_time"}
    )
    new_dataset_data["name"] = f"{original_dataset.name}_copy"

    new_dataset_doc = await mdb_service.create(
        model=ComplexReasoningDatasetDoc,
        data=ComplexReasoningDatasetMetaCreate(**new_dataset_data),
    )

    # 复制关联的 dataset_item
    query: dict = {"dataset_id": payload.dataset_id}
    if payload.dataset_item_ids:
        query["_id"] = {"$in": payload.dataset_item_ids}

    original_items = await mdb_service.get_list(
        model=ComplexReasoningCaseDoc, query=query
    )

    for item in original_items:
        new_item_data = item.model_dump(exclude={"id", "created_time", "updated_time"})
        new_item_data["dataset_id"] = new_dataset_doc.id
        await mdb_service.create(
            model=ComplexReasoningCaseDoc,
            data=ComplexReasoningCaseCreate(**new_item_data),
        )

    return ok(
        to_out(new_dataset_doc, ComplexReasoningDatasetMetaOut), message="复制成功"
    )


@router.post("/build", response_model=ApiResponse[ComplexReasoningDatasetMetaOut])
async def build_complex_reasoning_dataset(payload: DatasetBuildParams):
    # 1. 根据入参判断是新建数据集还是向现有数据集插入数据
    dataset_doc: ComplexReasoningDatasetDoc | None = None
    if payload.dataset_id:
        dataset_doc = await mdb_service.get_by_id(
            model=ComplexReasoningDatasetDoc, doc_id=payload.dataset_id
        )
        if not dataset_doc:
            return fail(code=ErrorCode.NOT_FOUND, message="未查询到数据集")
    elif payload.dataset:
        dataset_doc = await mdb_service.create(
            ComplexReasoningDatasetDoc, payload.dataset
        )
    else:
        return fail(
            code=ErrorCode.PARAM_INVALID, message="必须提供 dataset_id 或 dataset"
        )

    # 2. task_run_item_ids 查出 task_run_items，获取对应的 dataset_item_id
    extra_dataset_item_ids: list[PydanticObjectId] = []
    if payload.task_run_item_ids:
        task_run_items = await mdb_service.get_list(
            model=TaskRunItemDoc,
            query={"_id": {"$in": payload.task_run_item_ids}},
        )
        extra_dataset_item_ids = [item.dataset_item_id for item in task_run_items]

    # 合并 dataset_item_ids
    all_dataset_item_ids = list(
        set((payload.dataset_item_ids or []) + extra_dataset_item_ids)
    )

    # 3. 从 dataset_item_ids 查出数据集数据，合并到 dataset_items
    dataset_items_from_ids: list[ComplexReasoningCaseCreate] = []
    if all_dataset_item_ids:
        existing_cases = await mdb_service.get_list(
            model=ComplexReasoningCaseDoc,
            query={"_id": {"$in": all_dataset_item_ids}},
        )
        for case_doc in existing_cases:
            case_data = case_doc.model_dump(
                exclude={"id", "created_time", "updated_time", "dataset_id"}
            )
            dataset_items_from_ids.append(ComplexReasoningCaseCreate(**case_data))

    # 合并所有 dataset_items（去重：按 case_id 去重，优先保留 payload.dataset_items 中的）
    all_items: list[ComplexReasoningCaseCreate] = []
    seen_case_ids: set[str] = set()

    for item in payload.dataset_items or []:
        if item.case_id not in seen_case_ids:
            all_items.append(item)
            seen_case_ids.add(item.case_id)

    for item in dataset_items_from_ids:
        if item.case_id not in seen_case_ids:
            all_items.append(item)
            seen_case_ids.add(item.case_id)

    # 4. 设置 dataset_id 并创建 dataset_items
    for item in all_items:
        item.dataset_id = dataset_doc.id
        await mdb_service.create(model=ComplexReasoningCaseDoc, data=item)

    # 返回数据集信息
    return ok(
        to_out(dataset_doc, ComplexReasoningDatasetMetaOut), message="数据集构建成功"
    )


__all__ = ["router"]
