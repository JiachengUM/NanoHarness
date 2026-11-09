import asyncio

import inspect

from rich import print

from langchain.agents import AgentState
from langchain.tools import tool, ToolRuntime
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from nanoai.model.config import ModelName,ARK_API_KEY_FOR_1_8,ARK_BASE_URL
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages.base import BaseMessage
from langgraph.types import StreamMode

model = ChatOpenAI(
    model=ModelName.DOUBAO_SEED_1_8_PREVIEW,
    base_url=ARK_BASE_URL,
    api_key=ARK_API_KEY_FOR_1_8,
)

@tool(description="参数location输入“前滩”或者“外滩”，搜索这两个地点的餐厅")
def search_restaurant(location: str) -> list[str]:
    """根据location地点，搜索该地点附近的餐厅"""
    if location == "前滩":
        return ["烤鸭"]
    else:
        return ["星巴克"]

system_prompt = "你是用户助手"

agent = create_agent(
    model=model,
    system_prompt=system_prompt,
    tools=[search_restaurant],
)

query = "我想在前滩找一个餐厅"

def test_agent_basic():
    
    response = agent.invoke(
         {"messages": [{"role": "user", "content": query}]}
    )
    print("-" * 80)
    print(f"用户：{query}")
    print(f"管家：{response}")
    print("-" * 80)


def test_agent_stream(mode: StreamMode):
    res = agent.stream(  
        {"messages": [{"role": "user", "content": query}]},
        stream_mode=mode,
    )

    if mode=="updates":
        for chunk in res:
            for step, data in chunk.items():
                print(f"step: {step}")
                print(f"content: {data['messages'][-1].content_blocks}")
    elif mode == "messages":
        for token, metadata in res:
            print(f"node: {metadata['langgraph_node']}")
            print(f"content: {token.content_blocks}")
            print("\n")


def main():
    #print(inspect.getfile(create_agent))
    #return

    # test_agent_basic()
    # test_agent_stream("messages")
    test_agent_stream("updates")


if __name__ == "__main__":
    main()