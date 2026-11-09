from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """通用分页响应结构。"""

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

    @computed_field
    @property
    def pages(self) -> int:
        if self.page_size == 0:
            return 1
        return (self.total + self.page_size - 1) // self.page_size


class PageQuery(BaseModel):
    """分页查询参数基类。"""

    page: int = Field(default=1, ge=1, description="页码，默认 1")
    page_size: int = Field(
        default=10, ge=1, le=1000, description="每页数量，默认 10，最大 1000"
    )


__all__ = ["Page", "PageQuery"]
