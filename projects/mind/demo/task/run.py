from enum import StrEnum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import time

class TaskResult(BaseModel):
    status: str
    content: str | None = None
    error: str | None = None


class TaskStatus(StrEnum):
    """任务状态枚举"""
    PENDING = "pending"  # 待处理
    IN_PROGRESS = "in_progress"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消

class TaskRun(BaseModel):
    """任务执行模型"""
    # 关联字段
    task_id: str  # 关联的任务ID
    
    # 执行状态
    status: TaskStatus = TaskStatus.PENDING  # 任务状态
    
    # 时间戳
    created_at: float = Field(default_factory=time.time)  # 创建时间
    updated_at: float = Field(default_factory=time.time)  # 更新时间
    completed_at: Optional[float] = None  # 完成时间
    
    # 结果字段
    result: Optional[str] = None  # 任务结果
    error: Optional[str] = None  # 错误信息
    
    # 进度信息
    progress: float = 0.0  # 任务进度 (0.0-1.0)
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True  # 使用枚举值而不是枚举对象
    
    def update_status(self, status: TaskStatus):
        """更新任务状态"""
        self.status = status
        self.updated_at = time.time()
        if status == TaskStatus.COMPLETED:
            self.completed_at = time.time()
            self.progress = 1.0
    
    def update_progress(self, progress: float):
        """更新任务进度"""
        self.progress = min(max(0.0, progress), 1.0)
        self.updated_at = time.time()
