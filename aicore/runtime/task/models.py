from __future__ import annotations

from typing import Any, Literal
from enum import StrEnum

from pydantic import BaseModel, Field, ConfigDict
import uuid
from datetime import datetime

__all__ = [
    "TaskDef",
    "TaskStatus",
    "TaskRunBase",
    "TaskProjection",
    "TaskApplyResult",
    "TaskCancelOutcome",
    "TaskRun",
]

# --- 1. 任务定义 (TaskDef) ---

class TaskDef(BaseModel):
    """
    任务定义：描述一种任务类型的元数据。
    它是不可变的（Frozen），作为系统的\u201c常量\u201d存在。
    """
    model_config = ConfigDict(frozen=True)

    # 唯一标识符，例如 "nav_route_planning", "music_search"
    id: str = Field(..., description="任务的唯一标识符")
    
    # 人类可读的名称
    name: str = Field(..., description="任务显示名称")
    
    # 详细描述
    description: str | None = Field(default=None, description="任务描述")
    
    # 分类，前端可根据此字段决定显示什么图标
    category: str = Field(default="system", description="任务分类")
    
    # 是否允许用户手动取消
    cancellable: bool = Field(default=True, description="是否允许用户取消")

    meta_data: dict[str, Any] = Field(default_factory=dict, description="任务元数据")


# --- 2. 任务运行实例 (TaskRun) ---

class TaskStatus(StrEnum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRunBase(BaseModel):
    """任务运行态和控制面投影共享的基础字段。宽松类型，覆盖 TaskRun 的所有需求。"""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="任务实例ID")
    tool_name: str | None = Field(default=None, description="工具名")
    arguments: dict[str, Any] | str | None = Field(default=None, description="任务启动参数")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")


class TaskProjection(TaskRunBase):
    """面向控制面引用解析的任务投影。字段收紧为非空。"""

    task_id: str = Field(..., description="任务实例ID") # type: ignore
    tool_name: str = Field(..., description="工具名") # type: ignore
    arguments: dict[str, Any] = Field(default_factory=dict, description="任务启动参数") # type: ignore

    @classmethod
    def from_run(cls, run: TaskRun) -> TaskProjection:
        return cls(
            task_id=run.task_id,
            tool_name=run.tool_name or run.task_def_id or run.task_id,
            arguments=run.arguments if isinstance(run.arguments, dict) else {},
            status=run.status,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )


class TaskApplyResult(BaseModel):
    """任务事实事件应用结果。"""

    applied: bool
    current_status: TaskStatus
    reason: str | None = None


class TaskCancelOutcome(BaseModel):
    """任务取消请求结果。"""

    status: Literal["accepted", "already_terminal", "not_found", "failed"]
    task_id: str
    terminal_status: TaskStatus | None = None
    reason: str | None = None


class TaskRun(TaskRunBase):
    """
    任务运行实例：描述一个具体任务的生命周期状态。
    它是可变的，由 TaskManager 维护。
    """
    
    # --- 基础信息 ---

    task_def_id: str | None = Field(default=None, description="关联的任务定义ID")
    """
    为了方便，暂时允许None。
    TODO: 有必要要求必须定义么? 对于完全动态生成的任务似乎不需要？想不清楚
    """
    
    # --- 生命周期时间 ---

    completed_at: datetime | None = Field(default=None, description="完成/终止时间")

    # --- 核心状态 ---

    # 进度百分比：0-100。 -1 表示"忙碌/不确定进度"
    progress: int = Field(default=-1, ge=-1, le=100, description="进度百分比")

    # --- 数据载荷 ---

    result: Any | None = Field(default=None, description="任务执行结果")

    # 错误信息, 给人看的
    error: str | None = Field(default=None, description="错误信息")

    # 错误代码, 给机器看的，方便判断错误类型
    error_code: str | None = Field(default=None, description="错误代码")

    # --- 调试与追溯 ---

    # 是否由 TaskStartEvent 兜底创建，等待真实 TaskCreatedEvent 补全元数据
    created_from_start_fallback: bool = Field(
        default=False,
        description="是否由启动事件兜底创建",
    )

    # 轨迹日志：记录关键的中间步骤或流式文本片段
    trace: list[str] = Field(default_factory=list, description="执行轨迹/日志")

    # 原始元数据：启动任务时传入的自定义参数（如：source="voice"）
    metadata: dict[str, Any] = Field(default_factory=dict, description="任务元数据")

    # --- 辅助方法 ---

    def mark_running(self, timestamp: datetime):
        """标记任务运行中"""
        self.status = TaskStatus.RUNNING
        self.updated_at = timestamp

    def mark_success(self, result: Any, timestamp: datetime | None = None):
        """标记任务成功"""
        now = timestamp or datetime.now()
        self.status = TaskStatus.SUCCESS
        self.result = result
        self.progress = 100
        self.completed_at = now
        self.updated_at = now

    def mark_failure(self, error_msg: str, error_code: str = "UNKNOWN", timestamp: datetime | None = None):
        """标记任务失败"""
        now = timestamp or datetime.now()
        self.status = TaskStatus.FAILED
        self.error = error_msg
        self.error_code = error_code
        self.progress = -1
        self.completed_at = now
        self.updated_at = now

    def mark_cancelled(self, timestamp: datetime | None = None):
        """标记任务取消"""
        now = timestamp or datetime.now()
        self.status = TaskStatus.CANCELLED
        self.progress = 0
        self.completed_at = now
        self.updated_at = now

    def update_progress(self, log: str | None = None, percent: int | None = None):
        """更新进度"""
        # 如果提供了 percent 则更新，否则保持原值（或者你可以选择设为 -1）
        if percent is not None:
            self.progress = percent
        self.updated_at = datetime.now()
        if log:
            self.trace.append(log)
