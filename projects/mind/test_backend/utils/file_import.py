from __future__ import annotations

import io
import json
import re
from typing import Any, Callable, Literal, Type, TypeVar

from beanie import Document
from fastapi import UploadFile
from openpyxl import load_workbook
from pydantic import ValidationError

DocT = TypeVar("DocT", bound=Document)

FileFormat = Literal["json", "jsonl", "xlsx", "xls"]


def _parse_records(content: bytes, fmt: FileFormat) -> list[dict[str, Any]]:
    if fmt == "jsonl":
        records = []
        for line in io.BytesIO(content):
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    if fmt == "json":
        data = json.loads(content)
        return data if isinstance(data, list) else [data]

    if fmt in ("xlsx", "xls"):
        return _parse_excel_records(content)

    return []


def _parse_excel_records(content: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(filename=io.BytesIO(content), data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(cell) if cell is not None else "" for cell in rows[0]]
    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        if all(cell is None or cell == "" for cell in row):
            continue
        record: dict[str, Any] = {}
        for header, cell in zip(headers, row):
            if header:
                record[header] = cell
        records.append(record)
    return records

def parse_str_field(value: Any, default = "") -> str | None:
    if value is None or value == "":
        return default
    return str(value)

def parse_float_field(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None
    
def parse_int_field(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
    
def split_by_comma(value: list | str | None) -> list[str]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    parts = re.split(r"[，,]", value)
    return [p.strip() for p in parts if p.strip()]


def parse_json_field(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


async def import_file_to_db(
    file: UploadFile,
    doc_cls: Type[DocT],
    fmt: FileFormat,
    base_data: dict[str, Any] | None = None,
    record_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> int:
    """将 HTTP 上传的文件批量导入到 MongoDB。
    Args:
        file: HTTP 上传的文件对象。
        doc_cls: Beanie Document 类，用于验证和插入数据。
        fmt: 文件格式，支持 "json"、"jsonl"、"xlsx"、"xls"。
        base_data: 可选的基础数据字典，将被合并到每条记录中。
        record_transform: 可选的记录转换函数，在验证前对每条记录进行后处理。

    Returns:
        成功插入的记录数。
    """
    content = await file.read()
    records = _parse_records(content, fmt)
    if base_data:
        for record in records:
            record.update(base_data)
    if record_transform:
        records = [record_transform(r) for r in records]
    for record in records:
        record.pop("id", None)
        record.pop("_id", None)
    try:
        docs = [doc_cls.model_validate(r) for r in records]
    except ValidationError as e:
        raise ValueError(f"数据校验失败: {e}") from e
    inserted = await doc_cls.insert_many(docs)
    return len(inserted.inserted_ids)
