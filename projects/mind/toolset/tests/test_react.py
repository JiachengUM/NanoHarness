from rich import print

import asyncer

from aicore.models.credentials import create_client, AsyncArk, ModelName
from aicore.agents.events import ReActEventPrinter, EventCapturer
from aicore.agents.react import ReActAgentBase, ResponseParams
from aicore.tools.base import BaseTool

from projects.mind.toolset.poi_search import SGMPoiWorker, poi_search_tool_with_planning

QUERIES = [
    "北京望京的咖啡店",
    "人民大道221号附近3公里内的酒店",
    "广州天河区的美食",
    "上海的景点",
    "深圳南山区的美食",
    "成都春熙路的餐厅",
    "请帮我找附近的海底捞餐厅",  # 理应无法提取合理的address 
]

async def test_react_agent_stream(agent: ReActAgentBase):
    # 测试流式输出

    for i, query in enumerate(QUERIES[-1:]):
        print("\n" + "="*80)
        print(f"测试流式输出 #{i+1}: {query}")
        print("="*80)

        capturer = EventCapturer()
        system_prompt =  "如果有function_call，请一定要先进行回复，告知用户要进行的动作，再去执行function_call。"
        res = await agent.astream_run(query, system_prompt, event_listeners=[ReActEventPrinter(print), capturer])

        print("以下为事件统计信息:")
        capturer.dump(print=print)

        #print("\n最终响应: ")
        #print(res)
        print("="*80)

if __name__ == "__main__":
    #model = ModelName.SEED_1_8_251228
    model = ModelName.SEED_1_6_251015
    tools: list[BaseTool] = [poi_search_tool_with_planning(SGMPoiWorker())]
    client, model = create_client(model, AsyncArk)
    params = ResponseParams(thinking = {"type": "disabled"})

    agent = ReActAgentBase(
        tools=tools,
        model=model,
        client=client,
        params=params,
        max_turns=5,
    )

    #print(agent)
    #print(agent.model_dump())

    asyncer.syncify(test_react_agent_stream, False)(agent)

    # test_react_agent(agent)