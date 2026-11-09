"""打印 ReAct 流式事件：SDK 原始 ResponseStreamEvent + 自定义 agent.* 事件。"""

import asyncio
import uuid

from rich import print

from aicore.agents.react import (
    ReActAgentBase,
    ToolCallsEvent,
    ToolResultsEvent,
    FailedEvent,
)

from projects.mind.complex_reasoning.agent.agent import create_agent
from projects.mind.complex_reasoning.tools import get_default_tools
from projects.mind.complex_reasoning.utils.http_client import HttpClient


def make_chat_id() -> str:
    return "chatbox_" + uuid.uuid4().hex


async def run_stream_once(agent: ReActAgentBase, query: str) -> None:
    print("\n" + "=" * 80)
    print(f"流式事件测试: {query}")
    print("=" * 80)

    async for event in agent.astream(query):
        if isinstance(event, ToolCallsEvent):
            print(f"[agent.event] {event.type} turn={event.turn}")
            print(event.tool_calls)
            continue

        if isinstance(event, ToolResultsEvent):
            print(f"[agent.event] {event.type} turn={event.turn}")
            print(event.tool_results)
            continue

        if isinstance(event, FailedEvent):
            print(f"[agent.event] {event.type} reason={event.reason}")
            continue

        # SDK 原始流事件：仅打印对调试有价值的事件，过滤 created/in_progress 等噪声。
        event_type = str(getattr(event, "type", ""))
        if event_type == "response.output_text.delta":
            delta = str(getattr(event, "delta", "") or "")
            if delta:
                print(delta, end="")
            continue
        if event_type == "response.function_call_arguments.done":
            print("\n[sdk.event] function_call_arguments.done")
            print(getattr(event, "arguments", ""))
            continue
        if event_type == "response.completed":
            response = getattr(event, "response", None)
            response_id = getattr(response, "id", None) if response is not None else None
            print(f"\n[sdk.event] response.completed response_id={response_id}")
            continue
        if event_type in {"response.failed", "response.error", "response.incomplete"}:
            print(f"\n[sdk.event] {event_type}: {event!r}")
            continue

    print("=" * 80)


async def main() -> None:
    chat_id = make_chat_id()
    tools = get_default_tools(chat_id)
    agent = create_agent(tools=tools, max_turns=5)
    query = "你好呀，你能给我帮我搜一下今天的新闻吗"

    try:
        await run_stream_once(agent, query)
    finally:
        await HttpClient.close_for_current_loop()


if __name__ == "__main__":
    asyncio.run(main())
