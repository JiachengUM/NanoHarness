import asyncio

from rich import print

from aicore.models.credentials import ModelName
from aicore.v1.experiments.agent import create_agent, Agent
from typing import Any
from projects.mind.toolset.dag import get_prompt
from aicore.tools.dag.plan_execution_tool import PlanTool
from aicore.tools.dag.operator_executors import setup_executors


def read_txt(path: str) -> str:
    """读取文本文件"""
    with open(path, "r", encoding='utf-8') as file:
        return file.read()


async def process_query(agent: Agent, query: str) -> Any:
    """运行 Agent 并从对话历史中提取结构化数据

    Args:
        query: 用户查询文本
        agent: 已创建的 Agent 实例

    Returns:
        (system_msg, assistant_msg, tool_call_input, tool_call_output) 四元组
        - system_msg: 系统提示词
        - assistant_msg: 助手最终回复
        - tool_call_input: 工具调用入参列表 [{tool_name: arguments}, ...]
        - tool_call_output: 工具调用输出列表（尽量还原为 PlanExecutionOutput）
    """
    await agent.run_astream(query, event_listeners=[])
    _, state = await agent.dump()
    return state


QUERIES = [
    "帮我找在附近公园旁边找个评分4以上离我最近的咖啡店，人均不高于20，最好附近有麦当劳和游乐场。",
    #"先搜索杭州西湖附近评分最高的咖啡馆，看看人均消费，再查一下那家店附近500米内有没有停车场",
]


async def run() -> None:
    """批量评测主流程

    1. 初始化执行器（setup_executors）
    2. 读取 multi_step_query.txt 中的查询列表
    3. 创建 Agent（绑定 PlanTool，使用 SEED_2_0_PRO 模型）
    4. 并发执行所有查询（asyncio.gather）
    5. 打印结果摘要
    6. 写入 CSV 文件
    """
    setup_executors()
    plan_tool = PlanTool()
    agent = create_agent(model=ModelName.SEED_2_0_PRO_260215, tools=[plan_tool], system_prompt=get_prompt(), react_max_turns=3)
    tasks = [process_query(agent, query) for query in QUERIES]
    results = await asyncio.gather(*tasks)

    print("\n=== 执行结果 ===")
    for i, result in enumerate(results, 1):
        print(f"\n{'='*60}")
        print(f"样本 {i} | 查询: {result['query']}")
        print(f"{'='*60}")
        print(f"助手回复: {result['assistant_msg']}")
        

if __name__ == "__main__":
    asyncio.run(run())