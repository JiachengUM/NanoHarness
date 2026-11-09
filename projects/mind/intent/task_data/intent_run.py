from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from projects.mind.intent.task_data import *


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


class IntentRun(BaseModel):
    result_id: Optional[PydanticObjectId] = Field(default=None, title="结果ID", description="任务运行后的结果集ID")
    param: Optional[IntentClsParam] = Field(default=None, title="意图分类算法参数", description="意图分类算法参数")
    input: Optional[IntentClsInput] = Field(default=None, title="意图分类输入", description="意图分类输入")
    output: Optional[IntentClsOutput] = Field(default=None, title="意图分类输出", description="意图分类输出")
    trajectory: Optional[IntentClsRunTrajectory] = Field(default=None, title="意图分类运行过程", description="意图分类运行过程")
    total_time: Optional[float] = Field(default=None, title="总耗时", description="总耗时")
    manual_evaluation: Optional[Evaluation] = Field(default=None, title="评估指标", description="意图分类输出结果的人工评价")