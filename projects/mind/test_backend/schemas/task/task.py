from typing import Any, List

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from projects.mind.test_backend.mdb_models.task import (
    Task,
    TaskRun,
    TaskRunItem,
    TaskRunItemEval,
    TaskRunItemEvalDoc,
    TaskRunItemMessageDoc,
)
from projects.mind.test_backend.schemas.base import OutMixin
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc


class TaskFilter(BaseModel):
    """测试任务过滤条件"""

    name: str | None = None
    dataset_id: PydanticObjectId | None = None
    creator: str | None = None

    def get_filters(self) -> dict[str, Any]:
        filters = {}
        if self.name:
            filters["name"] = {"$regex": self.name, "$options": "i"}
        if self.dataset_id:
            filters["dataset_id"] = self.dataset_id
        if self.creator:
            filters["creator"] = self.creator

        return filters


class TaskOut(OutMixin, Task):
    """测试任务输出模型"""


class TaskRunRequest(BaseModel):
    """启动任务的可选入参。"""

    email: str | None = Field(default=None, description="飞书通知用户邮箱")
    phone: str | None = Field(default=None, description="飞书通知用户手机号")


class TaskRunFilter(BaseModel):
    """测试任务运行过滤条件"""

    task_id: PydanticObjectId | None = None
    status: str | None = None

    def get_filters(self) -> dict[str, Any]:
        filters = {}
        if self.task_id:
            filters["task_id"] = self.task_id
        if self.status:
            filters["status"] = self.status

        return filters


class TaskRunOut(OutMixin, TaskRun):
    """测试任务运行输出模型"""


class TaskRunItemFilter(BaseModel):
    """测试任务运行项过滤条件"""

    task_run_id: PydanticObjectId | None = None
    status: str | None = None
    llm_evaluation_is_pass: str | None = None
    human_evaluation_is_pass: int | None = None
    tag: str | None = None

    def get_filters(self) -> dict[str, Any]:
        filters = {}
        if self.task_run_id:
            filters["task_run_id"] = self.task_run_id
        if self.status:
            filters["status"] = self.status

        return filters

    async def resolve_filters(self) -> dict[str, Any]:
        """同步过滤条件 + 跨集合过滤（tag/eval）。"""
        filters = self.get_filters()

        eval_query: dict[str, Any] = {}
        if self.llm_evaluation_is_pass is not None:
            eval_query["llm_evaluation.is_pass"] = self.llm_evaluation_is_pass == "true"
        if self.human_evaluation_is_pass is not None:
            eval_query["human_evaluation.is_pass"] = bool(self.human_evaluation_is_pass)

        if eval_query:
            matched_item_ids = (
                await TaskRunItemEvalDoc.get_pymongo_collection().distinct(
                    "task_run_item_id", eval_query
                )
            )
            filters["_id"] = {"$in": matched_item_ids}

        if self.tag:
            matched_ids = (
                await ComplexReasoningCaseDoc.get_pymongo_collection().distinct(
                    "_id", {"tags": {"$regex": self.tag, "$options": "i"}}
                )
            )
            filters["dataset_item_id"] = {"$in": matched_ids}
        return filters


class TaskRunItemOut(OutMixin, TaskRunItem):
    """测试任务运行项输出模型"""

    eval: TaskRunItemEvalDoc | None = None
    messages: List[TaskRunItemMessageDoc] | None = None

class TaskRunItemEvalOut(OutMixin, TaskRunItemEval):
    """测试任务运行项评测输出模型"""
