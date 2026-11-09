import asyncio
import random

from typing import Iterable, Callable

from .data_source import UserDataSource

class SimulatedDataSource(UserDataSource):
    """
    模拟用户数据源
    
    基于预设的用户输入序列，模拟用户输入
    """
    
    def __init__(self, user_feed: Iterable[str]):
        """
        初始化模拟数据源
        
        参数：
        - user_feed: Iterable[str] - 模拟用户输入序列
        """
        super().__init__()
        self.user_feed = user_feed
        self.completion_callback = None
        self.agent_running_callback = None
    
    def set_completion_callback(self, callback: Callable[[], None]):
        """
        设置完成回调函数
        
        参数：
        - callback: Callable - 完成回调函数
        """
        self.completion_callback = callback
    
    def set_agent_running_callback(self, callback: Callable[[], bool]):
        """
        设置Agent运行状态检查回调函数
        
        参数：
        - callback: Callable - Agent运行状态检查回调函数
        """
        self.agent_running_callback = callback
    
    async def _listen(self, input_queue: asyncio.Queue):
        """
        模拟用户输入逻辑
        
        参数：
        - input_queue: asyncio.Queue - 输入队列，用于存放模拟的输入
        """
        for utt in self.user_feed:
            # 检查是否应该继续运行
            if not self.running:
                break
            if self.agent_running_callback and not self.agent_running_callback():
                break
            
            await input_queue.put(utt)
            # 随机等待时间，增加真实感
            await asyncio.sleep(random.uniform(1.0, 2.0))
        
        # 模拟输入完成后保持运行，等待用户手动退出
        print("模拟输入完成，按 q 或 ESC 退出程序")
        
        # 调用完成回调函数
        if self.completion_callback:
            self.completion_callback()
