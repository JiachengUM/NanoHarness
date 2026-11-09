import asyncio
from typing import Callable

from .data_source import UserDataSource
from .simulated_source import SimulatedDataSource

class UserEnv:
    """
    用户输入环境类
    
    负责管理用户输入队列，监听外部数据源，提供输入注入功能
    
    属性：
    - input_queue: asyncio.Queue - 用户输入队列
    - running: bool - 运行状态标志
    - data_sources: List[UserDataSource] - 数据源列表
    """
    
    def __init__(
        self, 
        data_sources : list[UserDataSource],
        agent_running_callback=None, 
        completion_callback=None,
        ):
        """
        初始化输入环境
        创建输入队列，设置初始状态，添加数据源        
        """
        self.input_queue = asyncio.Queue()
        self.running = True

        self.data_sources= data_sources

    
    def set_callback(
        self, 
        agent_running_callback : Callable[[], bool], 
        completion_callback : Callable[[], None],
        ):
        """
        设置回调函数

        参数：
        - agent_running_callback: Optional[Callable] - 用于检查代理是否仍在运行的回调函数
        - completion_callback: Optional[Callable] - 用于在模拟输入完成后通知的回调函数
        """

        # 为第一个模拟数据源设置回调函数
        for source in self.data_sources:
            if isinstance(source, SimulatedDataSource):
                source.set_completion_callback(completion_callback)
                source.set_agent_running_callback(agent_running_callback)
                break


    async def start_listening(self):
        """
        开始监听所有数据源
        """
        for data_source in self.data_sources:
            await data_source.start(self.input_queue)
    
    async def stop_listening(self):
        """
        停止监听所有数据源
        """
        for data_source in self.data_sources:
            await data_source.stop()
    
    async def inject_input(self, text: str):
        """
        注入用户输入
        
        将用户输入添加到输入队列
        
        参数：
        - text: str - 要注入的用户输入文本
        """
        if text.strip():
            await self.input_queue.put(text.strip())
    
    def stop(self):
        """
        停止输入环境
        
        设置运行状态为 False，停止所有数据源
        """
        self.running = False
        # 这里可以添加停止所有数据源的逻辑
        # 或者由调用者显式调用 stop_listening()
