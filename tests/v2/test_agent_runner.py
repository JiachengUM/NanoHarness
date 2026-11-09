import anyio

from rich import print

from aicore.v2.agent_runner import AgentOutEvent, AgentRunner, TaskEvent

from aicore.simulation.user_env.data_source import UserDataMocked
from aicore.v2.agent_mock import AgentMocked
from aicore.runtime.task import TaskManager
from aicore.core.event import EventPrinter

async def test_run():
    """
    测试函数，创建Agent和Runner并启动运行
    """
    # 创建Agent实例
    agent = AgentMocked()

    # 创建user data
    #user_data = ["你好", "再见"]  # 正常对话
    user_data = ["天气如何"]  # 包含任务的对话
    user_data = ["天气如何", "你好", "再见"]  # 任务先创建，但是在正常对话之后才结束

    # 创建Runner实例
    runner = AgentRunner(
        user_data=UserDataMocked(user_data),
        agent=agent,
        task_manager = TaskManager(),
        client=EventPrinter[AgentOutEvent | TaskEvent](print=print),
    )
    # 启动Runner
    await runner.run()


if __name__ == "__main__":
    anyio.run(test_run)
