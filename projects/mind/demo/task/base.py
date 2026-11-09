from pydantic import BaseModel, Field
from typing import Dict, Any
import time
import uuid

from .types import TaskType

class Task(BaseModel):
    """任务定义模型"""
    # 核心字段
    task_id: str = Field(default_factory=lambda: f"task-{int(time.time())}-{uuid.uuid4().hex[:8]}")
    prompt: str  # 原始指令
    task_type: TaskType  # 任务类型
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True  # 使用枚举值而不是枚举对象
