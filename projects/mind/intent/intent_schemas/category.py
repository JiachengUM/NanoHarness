from typing import Any, Optional
from pydantic import BaseModel, Field
from projects.mind.intent.intent_data.category import IntentCategory
from projects.mind.intent.intent_schemas.base import CreateMixin, OutMixin


class CategoryCreate(IntentCategory, CreateMixin):
    """intent category输入信息创建"""

    group: str | None = Field(default=None, title="分组", description="分组名称")


class CategoryOut(IntentCategory, OutMixin):
    """intent category输入信息"""

    group: str | None = Field(default=None, title="分组", description="分组名称")


class CategoryFilter(BaseModel):
    """查询条件"""

    name: Optional[str] = None
    creator: Optional[str] = None
    group: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.name:
            filters["name"] = {"$regex": self.name, "$options": "i"}
        if self.group:
            filters["group"] = {"$regex": self.group, "$options": "i"}
        return filters
