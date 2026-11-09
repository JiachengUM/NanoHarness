from abc import ABC, abstractmethod

from typing import Sequence, Any

from projects.mind.intent.intent_data.category import IntentCategory

class IntentClassifierBase(ABC):
    """意图分类器基类"""
    
    def __init__(self, categories: Sequence[IntentCategory]):
        """
        初始化意图分类器
        
        参数：
        - categories: List[TaskCategory] - 任务类别列表
        """
        self.categories = categories
    
    @abstractmethod
    def run(self, prompt: str, /,) -> tuple[str, Any]:
        """
        执行意图分类
        
        参数：
        - prompt: str - 用户指令内容
        
        返回：
        - tuple[str, Any] - (意图分类结果，任意定制化的中间过程)
        """
        pass

    @abstractmethod
    async def arun(self, prompt: str, /,) -> tuple[str, Any]:
        raise NotImplementedError("arun method must be implemented")