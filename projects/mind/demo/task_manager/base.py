from abc import ABC, abstractmethod
from typing import Optional, List
from projects.mind.demo.task import Task, TaskRun
from projects.mind.demo.task.run import TaskResult

class TaskManager(ABC):
    """
    任务管理器抽象接口
    
    定义任务管理的核心功能，包括提交任务、查询任务状态等
    """
    
    @abstractmethod
    def submit(self, task: Task) -> str:
        """
        提交任务
        
        参数：
        - task: Task - 任务对象
        
        返回：
        - str - 任务 ID
        """
        pass
    
    @abstractmethod
    def query(self, task_id: str) -> TaskResult:
        """
        查询任务状态
        
        参数：
        - task_id: str - 任务 ID
        
        返回：
        - TaskResult - 任务响应，包含状态和内容
        """
        pass
    
    @abstractmethod
    def get_task(self, task_id: str) -> Optional[TaskRun]:
        """
        获取任务执行对象
        
        参数：
        - task_id: str - 任务 ID
        
        返回：
        - Optional[TaskRun] - 任务执行对象，如果不存在则返回 None
        """
        pass
    
    @abstractmethod
    def get_completed_tasks(self) -> List[TaskRun]:
        """
        获取已完成的任务列表
        
        返回：
        - List[TaskRun] - 已完成的任务列表
        """
        pass
    
    @abstractmethod
    def get_pending_tasks(self) -> List[TaskRun]:
        """
        获取待处理的任务列表
        
        返回：
        - List[TaskRun] - 待处理的任务列表
        """
        pass
    
    @abstractmethod
    def clear(self):
        """
        清空所有任务
        """
        pass
