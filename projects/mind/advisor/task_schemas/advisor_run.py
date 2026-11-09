from typing import Any, Optional

from pydantic import BaseModel, Field
from projects.mind.advisor.schemas.base import TaskDataOutMixin, CreateMixin
from projects.mind.advisor.task_mdb_models.advisor_run import Metric, AdvisorRun


class AdvisorRunCreate(AdvisorRun, CreateMixin):
    """advisor输出信息 创建"""

    pass


class AdvisorRunOut(AdvisorRun, TaskDataOutMixin):
    """advisor输出信息 输出"""

    pass


class AdvisorRunFilter(BaseModel):
    """用户查询条件"""
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
