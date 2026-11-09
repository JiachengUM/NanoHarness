from typing import Optional

from pydantic import Field, BaseModel

from projects.mind.advisor.mdb_models.doc_base import TaskDataDocBase
from projects.mind.advisor.task_data import AdviserOutput, AdvisorInput


class Metric(BaseModel):
    """评估指标"""
    name: str = Field(title="名称", description="评估指标名称")
    value: float = Field(title="值", description="评估指标值")
    comment: Optional[str] = Field(default=None, title="评论", description="对评估指标的评论")

class Evaluation(BaseModel):
    """评估信息"""
    score: Optional[float] = Field(default=None, title="分数", description="评估分数")
    comment: Optional[str] = Field(default=None, title="评论", description="评论")
    metrics: Optional[list[Metric]] = Field(default=None, title="评估指标", description="评估指标列表")


class AdvisorRun(BaseModel):
    """advisor输出信息模型"""
    advise_type: Optional[str] = Field(default=None, title="建议类型", description="建议类型,舒适/情感")
    input: Optional[AdvisorInput] = Field(default=None, title="输入", description="advisor的输入信息")
    output: Optional[AdviserOutput] = Field(title="输出", description="advisor的输出信息")
    total_time: Optional[float] = Field(default=None, title="总耗时", description="总耗时")
    manual_evaluation: Optional[Evaluation] = Field(default=None, title="评估指标", description="advisor输出结果的人工评价")


class AdvisorRunDoc(AdvisorRun, TaskDataDocBase):
    class Settings:
        name = "advisor_run"  # MongoDB 集合名称
