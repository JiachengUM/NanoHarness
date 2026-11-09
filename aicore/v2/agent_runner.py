from typing import override

from anyio import create_task_group

from aicore.simulation.agent_runner import AgentRunnerBase, UserDataSourceBase, EventListener

from aicore.events.task import TaskEvent, TaskSuccessEvent
from aicore.v2.agent_model import AgentBase, AgentInputEvent, AgentOutEvent
from aicore.runtime.task import TaskManager

class AgentRunner(AgentRunnerBase[AgentOutEvent, TaskEvent, AgentInputEvent]):
    def __init__(
        self,
        user_data: UserDataSourceBase,
        agent: AgentBase,
        task_manager: TaskManager,
        client: EventListener[AgentOutEvent | TaskEvent],
        ):
        """
        初始化Runner实例

        参数：
            user_data: 实现UserDataSourceProtocol的用户数据提供器
            agent: MasterAgentBase实例，用于处理用户输入
            client: 实现ClientProtocol的客户端处理器
        """
        # TODO: 这里的type error有些问题
        super().__init__(user_data, agent, client)

        self.task_manager = task_manager

    @property
    def agent(self) -> AgentBase:
        return self._agent # type: ignore

    @override
    async def _run_user_data(self):
        """不使用async with，这样不会影响_run_user_data，但副作用是永远不会停止。
        TODO: 这样很丑陋。以及，当_run_user_data结束时，如何优雅的退出，这也是个问题。
        """
        async for data in self._user_data():
            await self._agent_in_send.send(data)

    async def _listen_task(self):
        async for event in self.task_manager.astream():
            self._client(event)

            match event:
                case TaskSuccessEvent():
                    await self._agent_in_send.send(event)

                case _:
                    pass

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
            # 启动任务管理器和任务监听任务
            tg.start_soon(self.task_manager.run)
            tg.start_soon(self._listen_task)
