from typing import Any, Type

from beanie import Document, PydanticObjectId
from pydantic import BaseModel
from pymongo.results import DeleteResult


async def create[D: Document](model: Type[D], data: BaseModel, /) -> D:
    """创建"""
    payload = data.model_dump()
    doc = model(**payload)
    return await doc.insert()


async def delete_by_id[D: Document](model: Type[D], id: PydanticObjectId) -> DeleteResult | None:
    """物理删除"""
    doc = await model.get(id)
    if not doc:
        return None
    result = await doc.delete()
    return result


async def update[D: Document](model: Type[D], data: BaseModel) -> D | None:
    """更新"""
    doc_id = data.id
    doc = await model.get(doc_id)
    if not doc:
        return None
    payload = data.model_dump(exclude={"_id", "id"})
    for k, v in payload.items():
        setattr(doc, k, v)
    await doc.save()
    return doc


async def get_list[D: Document](
        model: Type[D],
        query: dict[str, Any] | None = None,
        sort: str | None = None) -> list[D]:
    """列表"""
    query = query or {}
    cursor = model.find(query)
    if sort:
        cursor = cursor.sort(sort)
    return await cursor.to_list()

