import anyio

from aicore.v1.simulation.runner import Runner
from aicore.models.credentials import ModelName
from aicore.v1.experiments.base import create_agent, EventPrinter

from aicore.simulation.user_env.data_source import UserDataMocked


async def test_run():
    """
    测试函数，创建Agent和Runner并启动运行
    """
    # 创建Agent实例
    agent = create_agent(ModelName.SEED_1_8_251228)
    # 创建Runner实例
    runner = Runner(
        user_data=UserDataMocked(["你好", "请介绍自己", "再见"]),
        agent=agent,
        client=EventPrinter(),
    )
    # 启动Runner
    await runner.run()


if __name__ == "__main__":
    """
    程序入口，使用anyio.run运行异步测试函数
    """
    anyio.run(test_run)
