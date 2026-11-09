from __future__ import annotations

from typing import Any, Type, Iterable, TypeVar

from beanie import Document
from pydantic import BaseModel

from projects.mind.test_backend.schemas.paginate import Page

# ----------------------------- 文档 -> 输出模型 -----------------------------


_OutT = TypeVar("_OutT", bound=BaseModel)
_DocT = TypeVar("_DocT", bound=Document)


def to_out(doc: Document | dict[str, Any] | None, out_cls: Type[_OutT]) -> _OutT | None:
    """统一的 Document -> OutModel 转换。

    支持：beanie Document / dict。
    可扩展：未来可加入通用钩子、性能统计、字段白名单过滤等。
    """
    if doc is None:
        return None
    return out_cls.model_validate(doc, from_attributes=True)


def to_out_list(docs: Iterable[_DocT], out_cls: Type[_OutT]) -> list[_OutT]:
    return [out_cls.model_validate(d, from_attributes=True) for d in docs]


def to_out_page(docs: Page[_DocT], out_cls: Type[_OutT]) -> Page[_OutT]:
    return Page(
        items=to_out_list(docs.items, out_cls),
        total=docs.total,
        page=docs.page,
        page_size=docs.page_size,
    )


__all__ = [
    "to_out",
    "to_out_list",
    "to_out_page",
]
