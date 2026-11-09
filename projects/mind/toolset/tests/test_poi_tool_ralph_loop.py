import asyncio

from rich import print

from projects.mind.toolset.poi_search import SGMPoiWorker

from aicore.agents.react import ReActEventPrinter
from aicore.agents.experiments.base import _create_agent
from projects.mind.toolset.poi_search import poi_search_tool
from aicore.models.credentials import ModelName
from aicore.agents.experiments.ralph import ralph_loop, ReActExecutor, LMEvaluator, ModelParams, RalphReActEventPrinter


async def test_agent():
    poi_tool = poi_search_tool(SGMPoiWorker())
    _guidelines = ["""
"""]
    agent = _create_agent(model=ModelName.SEED_1_8_251228, tools=[poi_tool], guidelines=_guidelines)
    
    # query = "我在上海旅游，带小孩，想找好吃的火锅，市中心即可，人均在100元左右"
    query = "导航去上海市闵行区天安豪园"

    print(f"user: {query}")
    async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
        pass
    assert agent.state.run_result is not None
    print(f"\nassistant(完整): {agent.state.run_result.response.raw_text}")


async def test_ralph_loop():
    goal = "我带老人在北京旅游，想找几个有文化气息的，风景优美的户外景区逛逛"
    # goal = "找一家附近的火锅店，告诉我营业时间和人均消费"
    poi_tool = poi_search_tool(SGMPoiWorker())

    executor = ReActExecutor(params=ModelParams(model=ModelName.SEED_1_8_251228), tools=[poi_tool])
    
    evaluator = LMEvaluator(params=ModelParams(model=ModelName.SEED_1_8_251228))
    
    event_printer = RalphReActEventPrinter()
    
    async for event in ralph_loop(goal, executor, evaluator, max_turns=2):
        event_printer(event)


async def main():
    # await test_agent()
    print("--------------------")
    await test_ralph_loop()


if __name__ == "__main__":
    asyncio.run(main())