from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.complex_reasoning.task_data.complex_reasoning_run import ComplexReasoningRun
from projects.mind.intent.intent_schemas.base import OutMixin, CreateMixin


class ComplexReasoningRunCreate(ComplexReasoningRun, CreateMixin):
    """complex reasoning输入信息创建"""
    pass


class ComplexReasoningRunOut(ComplexReasoningRun, OutMixin):
    """complex reasoning输出信息"""

    pass


class ComplexReasoningRunFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        filters = self.model_dump(exclude_none=True)
        return filters
