from __future__ import annotations

import json
from io import BytesIO

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from projects.mind.complex_reasoning.task_mdb_models.case import (
    ComplexReasoningCaseDoc,
)
from projects.mind.advisor.repositories import mdb_api
from projects.mind.complex_reasoning.task_schemas.case import (
    ComplexReasoningCaseOut,
    ComplexReasoningCaseFilter,
    ComplexReasoningCaseCreate,
)
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.file_import import (
    import_file_to_db,
    parse_json_field,
    parse_str_field,
    split_by_comma,
)
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/complex_reasoning_case",
    tags=["Complex Reasoning Input Manager"],
)


@router.get("/list", response_model=ApiResponse[list[ComplexReasoningCaseOut]])
async def list_input(filters: ComplexReasoningCaseFilter = Depends()):
    docs = await mdb_api.get_list(
        model=ComplexReasoningCaseDoc,
        query=filters.get_filters(),
        sort="-updated_time",
    )
    return ok(to_out_list(docs, ComplexReasoningCaseOut))


@router.get("/page", response_model=ApiResponse[Page[ComplexReasoningCaseOut]])
async def page_input(
    filters: ComplexReasoningCaseFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=ComplexReasoningCaseDoc,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time",
    )
    return ok(to_out_page(page_docs, ComplexReasoningCaseOut))

@router.post("", response_model=ApiResponse[ComplexReasoningCaseOut])
async def create_input(payload: ComplexReasoningCaseCreate):
    doc = await mdb_api.create(ComplexReasoningCaseDoc, payload)
    return ok(to_out(doc, ComplexReasoningCaseOut), message="创建成功")


@router.put(
    "/{complex_reasoning_case_id}",
    response_model=ApiResponse[ComplexReasoningCaseOut],
)
async def update_input(payload: ComplexReasoningCaseDoc):
    doc = await mdb_api.update(model=ComplexReasoningCaseDoc, data=payload)
    return ok(to_out(doc, ComplexReasoningCaseOut), message="更新成功")


@router.delete("/{complex_reasoning_case_id}", response_model=ApiResponse)
async def delete_input(complex_reasoning_case_id: PydanticObjectId):
    result = await mdb_api.delete_by_id(
        model=ComplexReasoningCaseDoc, id=complex_reasoning_case_id
    )
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


@router.post("/import", response_model=ApiResponse)
async def import_input(
    file: UploadFile = Form(...),
    dataset_id: str = Form(...),
):
    fmt = file.filename.split(".")[-1].lower()
    base_data = {"dataset_id": dataset_id}

    def _transform_record(record: dict) -> dict:
        if "case_id" in record:
            record["case_id"] = parse_str_field(record["case_id"])
        if "context_config" in record:
            record["context_config"] = parse_json_field(record["context_config"]) or {}
        if "user_query_lists" in record:
            record["user_query_lists"] = parse_json_field(record["user_query_lists"]) or []
        if "code_assertion" in record:
            record["code_assertion"] = parse_json_field(record["code_assertion"])
        if "nl_assertion" in record:
            record["nl_assertion"] = parse_json_field(record["nl_assertion"])
        if "expected_script" in record:
            record["expected_script"] = parse_str_field(record["expected_script"])
        if "tags" in record:
            record["tags"] = split_by_comma(record["tags"])
        return record

    try:
        inserted_count = await import_file_to_db(
            file,
            ComplexReasoningCaseDoc,
            fmt,
            base_data,
            record_transform=_transform_record,
        )
    except ValueError as e:
        return fail(code=ErrorCode.PARAM_INVALID, message=str(e))
    return ok(message=f"成功导入 {inserted_count} 条记录")


@router.get("/export", response_class=StreamingResponse)
async def export_input(
    filters: ComplexReasoningCaseFilter = Depends(),
) -> StreamingResponse:
    docs = await mdb_api.get_list(
        model=ComplexReasoningCaseDoc,
        query=filters.get_filters(),
        sort="-updated_time",
    )
    records = [json.loads(doc.model_dump_json(by_alias=True)) for doc in docs]
    content = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        content=BytesIO(content),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=complex_reasoning_cases.json"
        },
    )


@router.get("/export_excel", response_class=StreamingResponse)
async def export_input_excel(
    filters: ComplexReasoningCaseFilter = Depends(),
) -> StreamingResponse:
    docs = await mdb_api.get_list(
        model=ComplexReasoningCaseDoc,
        query=filters.get_filters(),
        sort="-updated_time",
    )
    records = [json.loads(doc.model_dump_json(by_alias=True)) for doc in docs]

    headers = [
        "case_id",
        "case_description",
        "context_config",
        "max_round",
        "user_query_lists",
        "expected_script",
        "nl_assertion",
        "code_assertion",
        "tags",
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "cases"
    sheet.append(headers)

    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="ADD8E6", end_color="ADD8E6", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_idx in range(1, len(headers) + 1):
        cell = sheet.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    col_widths = {
        "case_id": 12,
        "case_description": 30,
        "context_config": 30,
        "max_round": 12,
        "user_query_lists": 40,
        "expected_script": 60,
        "nl_assertion": 60,
        "code_assertion": 20,
        "tags": 20,
    }
    for col_idx, header in enumerate(headers, start=1):
        col_letter = sheet.cell(row=1, column=col_idx).column_letter
        sheet.column_dimensions[col_letter].width = col_widths.get(header, 20)

    cell_alignment = Alignment(wrap_text=True, vertical="top")
    for record in records:
        row = []
        for key in headers:
            value = record.get(key, "")
            if isinstance(value, (dict, list)):
                if key in ("tags") and isinstance(value, list):
                    row.append("，".join(str(v) for v in value))
                else:
                    row.append(json.dumps(value, ensure_ascii=False))
            else:
                row.append(value if value is not None else "")
        sheet.append(row)
        row_idx = sheet.max_row
        for col_idx in range(1, len(headers) + 1):
            sheet.cell(row=row_idx, column=col_idx).alignment = cell_alignment

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=complex_reasoning_cases.xlsx"
        },
    )

@router.get(
    "/{complex_reasoning_case_id}", response_model=ApiResponse[ComplexReasoningCaseOut]
)
async def get_input_by_id(complex_reasoning_case_id: PydanticObjectId):
    doc = await mdb_service.get_by_id(
        ComplexReasoningCaseDoc, complex_reasoning_case_id
    )
    if not doc:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(to_out(doc, ComplexReasoningCaseOut))


__all__ = ["router"]
