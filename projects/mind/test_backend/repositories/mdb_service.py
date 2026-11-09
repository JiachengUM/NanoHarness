from typing import Any, Type
from beanie import Document, PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING
from pymongo.results import DeleteResult
from projects.mind.test_backend.schemas.paginate import Page


def _build_motor_sort(sort: str | None):
    """把 Beanie 风格的排序字符串（如 '-updated_time'）转换为 Motor 的 sort 参数。"""
    if not sort:
        return None
    field = sort.lstrip("-")
    direction = DESCENDING if sort.startswith("-") else ASCENDING
    return [(field, direction)]


def _with_deleted_filter(query: dict[str, Any] | None) -> dict[str, Any]:
    """合并软删除过滤：只查询未删除（deleted_time 为空/不存在）的数据。

    说明：MongoDB 中 `{deleted_time: null}` 同时匹配字段为 null 和不存在的文档，
    因此对尚未加软删除字段的老数据同样生效。
    """
    q = dict(query or {})
    q.setdefault("deleted_time", None)
    return q


async def get_count[D: Document](
    model: Type[D], query: dict[str, Any] | None = None
) -> int:
    """统计数量"""
    query = _with_deleted_filter(query)
    return await model.find(query).count()


async def get_page[D: Document](
    model: Type[D],
    filters: dict[str, Any] | None = None,
    page: int = 1,
    page_size: int = 10,
    max_page_size: int = 200,
    sort: str | None = None,
    exclude_fields: list[str] | None = None,
) -> Page[D]:
    """分页"""
    page = max(1, page)
    page_size = max(1, min(page_size, max_page_size))
    skip = (page - 1) * page_size

    query = _with_deleted_filter(filters)
    total = await model.find(query).count()

    if total == 0:
        return Page[Any](items=[], total=0, page=page, page_size=page_size)

    if exclude_fields:
        projection = {field: 0 for field in exclude_fields}
        motor_cursor = model.get_pymongo_collection().find(query, projection)
        motor_sort = _build_motor_sort(sort)
        if motor_sort:
            motor_cursor = motor_cursor.sort(motor_sort)
        raw_docs = await motor_cursor.skip(skip).limit(page_size).to_list(None)
        items = [model.model_validate(d) for d in raw_docs]
    else:
        cursor = model.find(query)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(page_size)
        items = await cursor.to_list()

    return Page[Any](items=items, total=total, page=page, page_size=page_size)


async def get_list[D: Document](
    model: Type[D],
    query: dict[str, Any] | None = None,
    sort: str | None = None,
    exclude_fields: list[str] | None = None,
) -> list[D]:
    """列表"""
    query = _with_deleted_filter(query)

    if exclude_fields:
        projection = {field: 0 for field in exclude_fields}
        motor_cursor = model.get_pymongo_collection().find(query, projection)
        motor_sort = _build_motor_sort(sort)
        if motor_sort:
            motor_cursor = motor_cursor.sort(motor_sort)
        raw_docs = await motor_cursor.to_list(None)
        return [model.model_validate(d) for d in raw_docs]

    cursor = model.find(query)
    if sort:
        cursor = cursor.sort(sort)
    return await cursor.to_list()


async def get_one[D: Document](model: Type[D], query: dict[str, Any]) -> D | None:
    """查询单个"""
    return await model.find_one(_with_deleted_filter(query))


async def get_by_id[D: Document](model: Type[D], doc_id: PydanticObjectId) -> D | None:
    """根据ID查询（同样过滤软删除）"""
    return await model.find_one(_with_deleted_filter({"_id": doc_id}))


async def create[D: Document](model: Type[D], data: BaseModel) -> D:
    """创建"""
    payload = data.model_dump()
    doc = model(**payload)
    return await doc.insert()


async def update[D: Document](
    model: Type[D], doc_id: PydanticObjectId, data: BaseModel
) -> D | None:
    """更新"""
    doc = await model.get(doc_id)
    if not doc:
        return None
    payload = data.model_dump(exclude={"_id", "id"})
    for k, v in payload.items():
        setattr(doc, k, v)
    await doc.save()
    return doc


async def delete_by_id[D: Document](
    model: Type[D], id: PydanticObjectId
) -> DeleteResult | None:
    """物理删除"""
    doc = await model.get(id)
    if not doc:
        return None
    result = await doc.delete()
    return result


async def delete_by_query[D: Document](
    model: Type[D], query: dict[str, Any]
) -> DeleteResult | None:
    """根据查询条件物理删除"""
    result = await model.find(query).delete()
    return result
