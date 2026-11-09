"""
该模块实现了一个异步运行器，用于协调用户数据输入、Agent处理和客户端输出。
使用anyio库实现异步任务管理和内存对象流通信，实现了生产者-消费者模式的解耦。
"""

from typing import final

from anyio import create_task_group, create_memory_object_stream

from aicore.simulation.user_env.data_source import UserDataSourceBase
from aicore.core.event import EventBase, EventListener, EventGenerator

__all__ = [
    "UserDataSourceBase",
    "EventListener",
    "EventGenerator",
    "AgentRunnerBase",
]

class AgentRunnerBase[AOE: EventBase, ROE: EventBase, InE]:
    def __init__(
        self,
        user_data: UserDataSourceBase,
        agent: EventGenerator[AOE],
        client: EventListener[AOE | ROE],
        ):
        """
        初始化Runner实例

        参数：
            user_data: 实现UserDataSourceProtocol的用户数据提供器
            agent: MasterAgentBase实例，用于处理用户输入
            client: 实现ClientProtocol的客户端处理器

        AOE: Agent Output Event
        ROE: Runner Output Event
        """
        self._user_data = user_data
        self._agent = agent
        self._client = client

        self._agent_in_send, self._agent_in_receive = create_memory_object_stream[InE | str](10)
        self._agent_out_send, self._agent_out_receive = create_memory_object_stream[AOE](10)
        

    async def _run_user_data(self):
        async with self._agent_in_send:    # 必须的。如果没有，所有stream都不会关闭。
            async for data in self._user_data():
                await self._agent_in_send.send(data)

    @final
    async def _run_client(self):
        async with self._agent_out_receive:
            async for event in self._agent_out_receive:
                self._client(event)

    async def _process_agent_out_event(self, event: AOE) -> None:
        await self._agent_out_send.send(event)
    
    @final
    async def _run_agent(self):
        """
        Agent处理任务的核心逻辑：
        1. 从用户数据流中接收输入
        TODO:
        """
        async with self._agent_in_receive, self._agent_out_send:
            # 异步迭代接收用户输入
            async for input in self._agent_in_receive:
                # 调用Agent的异步流式接口处理输入
                async for event in self._agent.astream(input):
                    await self._process_agent_out_event(event)
                

    async def run(self):
        """
        启动所有异步任务的主方法：
        1. 创建任务组（Task Group）来管理三个异步任务
        2. 启动用户数据提供任务
        3. 启动Agent处理任务
        4. 启动客户端处理任务

        任务组会自动管理所有任务的生命周期，任何一个任务失败都会导致所有任务终止
        """
        async with create_task_group() as tg:
            # 启动用户数据提供任务
            tg.start_soon(self._run_user_data)
            # 启动Agent处理任务
            tg.start_soon(self._run_agent)
            # 启动客户端处理任务
            tg.start_soon(self._run_client)
