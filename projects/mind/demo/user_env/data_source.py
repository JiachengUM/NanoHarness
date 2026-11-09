from abc import ABC, abstractmethod

import asyncio

class UserDataSource(ABC):
    """
    用户数据源抽象接口
    
    定义用户数据源的通用接口，支持不同类型的输入源
    """
    
    def __init__(self):
        self.running = False
        self.task: asyncio.Task | None = None
    
    @abstractmethod
    async def _listen(self, input_queue: asyncio.Queue):
        """
        内部监听逻辑，由具体实现类实现
        
        参数：
        - input_queue: asyncio.Queue - 输入队列，用于存放监听到的输入
        """
        pass
    
    async def start(self, input_queue: asyncio.Queue):
        """
        启动数据源，开始监听输入
        
        参数：
        - input_queue: asyncio.Queue - 输入队列，用于存放监听到的输入
        """
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._listen(input_queue))
    
    async def stop(self):
        """
        停止数据源，清理资源
        """
        if self.running:
            self.running = False
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                self.task = None
    
    def is_running(self) -> bool:
        """
        检查数据源是否正在运行
        
        返回：
        - bool - 运行状态
        """
        return self.running