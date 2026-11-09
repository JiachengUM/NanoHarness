import time
import random
from typing import Dict, List, Optional
from projects.mind.demo.task import Task, TaskRun, TaskStatus
from projects.mind.demo.task.run import TaskResult
from .base import TaskManager

class FakeTaskManager(TaskManager):
    """
    模拟任务管理器实现
    
    用于模拟任务的提交和执行过程
    """
    
    def __init__(self):
        """
        初始化 FakeTaskManager 实例
        """
        # 存储正在处理的任务
        self._tasks: Dict[str, TaskRun] = {}
        # 存储已完成的任务
        self._completed_tasks: List[TaskRun] = []
        # 存储任务定义
        self._task_definitions: Dict[str, Task] = {}
    
    def submit(self, task: Task) -> str:
        """
        提交任务
        
        参数：
        - task: Task - 任务对象
        
        返回：
        - str - 任务 ID
        """
        # 存储任务定义
        self._task_definitions[task.task_id] = task
        
        # 创建任务执行对象
        task_run = TaskRun(task_id=task.task_id)
        task_run.status = TaskStatus.IN_PROGRESS
        # 存储结果时间
        task_run.metadata = {"result_after": time.time() + random.uniform(1.0, 3.0)}
        
        # 存储任务执行对象
        self._tasks[task_run.task_id] = task_run
        return task_run.task_id
    
    def query(self, task_id: str) -> TaskResult:
        """
        查询任务状态
        
        参数：
        - task_id: str - 任务 ID
        
        返回：
        - TaskResult - 任务响应，包含状态和内容
        """
        task_run = self._tasks.get(task_id)
        if not task_run:
            return TaskResult(status="failed", error="Task not found")
        
        now = time.time()
        result_after = task_run.metadata.get("result_after", now + 1000)
        if now >= result_after:
            task_run.update_status(TaskStatus.COMPLETED)
            # 获取任务定义以获取prompt
            task = self._task_definitions.get(task_run.task_id)
            prompt = task.prompt if task else "未知任务"
            task_run.result = f"✅ 已处理指令: {prompt}"
            self._completed_tasks.append(task_run)
            # 从正在处理的任务中移除
            self._tasks.pop(task_id, None)
        
        return TaskResult(
            status=task_run.status,
            content=task_run.result if task_run.status == TaskStatus.COMPLETED else None,
            error=None
        )
    
    def get_task(self, task_id: str) -> Optional[TaskRun]:
        """
        获取任务执行对象
        
        参数：
        - task_id: str - 任务 ID
        
        返回：
        - Optional[TaskRun] - 任务执行对象，如果不存在则返回 None
        """
        # 先检查正在处理的任务
        if task_id in self._tasks:
            return self._tasks[task_id]
        # 再检查已完成的任务
        for task_run in self._completed_tasks:
            if task_run.task_id == task_id:
                return task_run
        return None
    
    def get_completed_tasks(self) -> List[TaskRun]:
        """
        获取已完成的任务列表
        
        返回：
        - List[TaskRun] - 已完成的任务列表
        """
        return self._completed_tasks.copy()
    
    def get_pending_tasks(self) -> List[TaskRun]:
        """
        获取待处理的任务列表
        
        返回：
        - List[TaskRun] - 待处理的任务列表
        """
        return list(self._tasks.values())
    
    def clear(self):
        """
        清空所有任务
        """
        self._tasks.clear()
        self._completed_tasks.clear()
        self._task_definitions.clear()
