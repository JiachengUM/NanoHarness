from typing import List

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from aicore.agents.experiments.base import AgentDumpPayload
from projects.mind.test_backend.enums.task import TaskRunItemStatus, TaskRunStatus
from projects.mind.test_backend.mdb_models.doc_base import DocBase


class Task(BaseModel):
    """
    测试任务。
    """

    name: str = Field(..., title="测试任务名称")
    description: str | None = Field(default=None, title="测试任务描述")
    dataset_id: PydanticObjectId = Field(..., title="测试数据集ID")
    dataset_item_ids: List[PydanticObjectId] | None = Field(
        default_factory=list,
        title="需测试的CaseId列表",
        description="如果为空，则默认测试数据集中的所有Case",
    )
    config: AgentDumpPayload = Field(..., title="BaseAgent配置")
    metadata: dict | None = Field(
        default=None,
        title="测试任务元信息",
        description="测试任务的其他元信息，格式为键值对",
    )


class ReportTime(BaseModel):
    avg_time: float = Field(..., ge=0, description="平均耗时")
    p50_time: float = Field(..., ge=0, description="50百分位耗时")
    p90_time: float = Field(..., ge=0, description="90百分位耗时")
    p99_time: float = Field(..., ge=0, description="99百分位耗时")


class TaskStatistics(BaseModel):
    rate_accuracy: float = Field(..., description="准确率")
    first_frame_time: ReportTime = Field(..., description="首帧时间")
    total_time: ReportTime = Field(..., description="总耗时")


class TaskProgress(BaseModel):
    total: int = Field(..., ge=0, description="总测试用例数")
    completed: int = Field(..., ge=0, description="已完成测试用例数")
    success: int = Field(..., ge=0, description="成功测试用例数")
    failed: int = Field(..., ge=0, description="失败测试用例数")
    percent: float = Field(..., ge=0, le=100, description="测试完成百分比")


class TaskRun(BaseModel):
    """
    测试任务运行结果。
    """

    task_id: PydanticObjectId = Field(
        ..., title="测试任务ID", description="测试任务的唯一标识符"
    )
    # dataset_id: PydanticObjectId = Field(
    #     ..., title="测试数据集ID", description="测试任务关联的数据集ID"
    # )
    # config: TaskConfig = Field(
    #     ...,
    #     title="测试任务配置",
    #     description="测试任务的配置项，格式为键值对",
    # )
    status: str = Field(default=TaskRunStatus.PENDING, title="测试任务运行状态")
    # statistics: TaskStatistics | None = Field(
    #     default=None,
    #     title="测试任务结果统计",
    #     description="测试任务的结果统计信息，包括准确率、耗时等指标",
    # )
    progress: TaskProgress | None = Field(default=None, description="测试任务运行进度")
    metadata: dict | None = Field(
        default=None,
        title="测试任务运行元信息",
        description="测试任务运行的其他元信息，格式为键值对",
    )


class EvaluationMetricItem(BaseModel):
    name: str = Field(..., description="评估指标名称")
    value: float = Field(..., description="评估指标数值")
    comment: str | None = Field(
        default=None,
        description="评估指标评论，评估人员对该指标的评语和建议",
    )


class Evaluation(BaseModel):
    score: float | None = Field(default=None, description="评估得分")
    is_pass: bool | None = Field(default=None, description="是否通过评估")
    comment: str | None = Field(
        default=None,
        description="评估评论，评估人员对测试用例的评估意见和建议",
    )
    metrics: list[EvaluationMetricItem] | None = Field(
        default=None,
        description="评估指标列表，包含各个评估指标的名称、数值和评论",
    )


class TaskRunItem(BaseModel):
    """
    测试任务运行的单条测试用例结果。
    """

    task_run_id: PydanticObjectId = Field(..., title="测试任务运行ID")
    dataset_item_id: PydanticObjectId = Field(..., title="测试数据集项ID")
    # answer: RunResult | Any | None = Field(
    #     default=None, title="测试任务回答结果"
    # )
    # answer_list: List[RunResult | Any] = Field(
    #     default_factory=list, title="测试任务回答列表"
    # )
    # llm_evaluation: Evaluation | None = Field(
    #     default=None, title="测试任务评估结果"
    # )
    # human_evaluation: Evaluation | None = Field(
    #     default=None, title="人工评估结果"
    # )
    status: str = Field(default=TaskRunItemStatus.PENDING, title="测试用例执行状态")
    metadata: dict | None = Field(
        default=None,
        title="测试用例运行元信息",
        description="测试用例运行的其他元信息，格式为键值对",
    )


class TaskRunItemMessage(BaseModel):
    """
    测试任务中每个测试用例运行过程中的对话消息记录。
    """

    task_run_item_id: PydanticObjectId = Field(..., description="测试任务运行项ID")
    session_id: str = Field(
        ..., description="会话session_id, 每个session_id对应一次完整会话"
    )
    # turns: int = Field(..., description="消息轮次，从1开始")
    role: str = Field(..., description="消息角色，例如user、assistant等")
    content: str | None = Field(default=None, description="消息内容")
    traces: List[dict | str] | None = Field(  # TODO: 改成trace
        default=None,
        description="消息追踪信息，记录该消息在测试用例运行过程中的相关信息，例如输入输出、调用链等",
    )
    metadata: dict | None = Field(
        default=None,
        description="消息元信息，记录该消息的额外信息",
    )


class TaskRunItemEval(BaseModel):
    task_run_item_id: PydanticObjectId = Field(..., title="测试任务运行项ID")
    llm_evaluation: Evaluation | None = Field(default=None, title="测试任务评估结果")
    human_evaluation: Evaluation | None = Field(default=None, title="人工评估结果")


class TaskDoc(DocBase, Task):
    """测试任务的MongoDB文档模型"""

    class Settings:
        name = "task"  # MongoDB 集合名称


class TaskRunDoc(DocBase, TaskRun):
    """测试任务运行结果的MongoDB文档模型"""

    class Settings:  # type: ignore
        name = "task_run"  # MongoDB 集合名称


class TaskRunItemDoc(TaskRunItem, DocBase):
    """测试任务运行结果的MongoDB文档模型"""

    class Settings:
        name = "task_run_item"  # MongoDB 集合名称


class TaskRunItemMessageDoc(TaskRunItemMessage, DocBase):
    """测试任务运行消息记录的MongoDB文档模型"""

    class Settings:
        name = "task_run_item_message"  # MongoDB 集合名称


class TaskRunItemEvalDoc(TaskRunItemEval, DocBase):
    """测试任务运行评估结果的MongoDB文档模型"""

    class Settings:
        name = "task_run_item_eval"  # MongoDB 集合名称
