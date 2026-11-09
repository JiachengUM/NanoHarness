from typing import Any, Optional
from pydantic import BaseModel, Field

from projects.mind.intent.intent_schemas.base import OutMixin, CreateMixin
from projects.mind.intent.task_data import IntentClsParam


class IntentParamCreate(IntentClsParam, CreateMixin):
    """intent param信息创建"""
    brief: Optional[str] = Field(default=None, title="概要", description="概要")


class IntentParamOut(IntentClsParam, OutMixin):
    """intent param输出信息"""

    brief: Optional[str] = Field(default=None, title="概要", description="概要")


class IntentParamFilter(BaseModel):
    """查询条件"""

    name: Optional[str] = None
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        if self.name:
            filters["name"] = {"$regex": self.name, "$options": "i"}
        return filters
