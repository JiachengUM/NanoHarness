from typing import Any, Optional
from pydantic import BaseModel, Field

from projects.mind.intent.intent_schemas.base import OutMixin, CreateMixin
from projects.mind.intent.task_data import IntentClsParam, IntentClsInput
from projects.mind.intent.task_data.intent_run import IntentRun



class IntentRunCreate(IntentRun, CreateMixin):
    """intent category输入信息创建"""
    pass


class IntentRunOut(IntentRun, OutMixin):
    """intent category输入信息"""

    pass


class IntentRunFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        return filters
